"""
Continuous BookStack to FalkorDB sync using CocoIndex
Based on the documented enhanced pipeline with proper CocoIndex patterns
"""

import os
import json
import requests
from datetime import timedelta
from pathlib import Path

import cocoindex
from cocoindex import DataScope, FlowBuilder

# Configuration
BOOKSTACK_URL = os.environ.get("BS_URL", "https://knowledge.oculair.ca")
BOOKSTACK_TOKEN_ID = os.environ.get("BS_TOKEN_ID", "POnHR9Lbvm73T2IOcyRSeAqpA8bSGdMT")
BOOKSTACK_TOKEN_SECRET = os.environ.get("BS_TOKEN_SECRET", "735wM5dScfUkcOy7qcrgqQ1eC5fBF7IE")
EXPORT_DIR = "bookstack_export_continuous"

# Ensure export directory exists
Path(EXPORT_DIR).mkdir(exist_ok=True)

@cocoindex.op.function()
def export_bookstack_pages() -> bool:
    """Export all BookStack pages to JSON files."""
    headers = {
        "Authorization": f"Token {BOOKSTACK_TOKEN_ID}:{BOOKSTACK_TOKEN_SECRET}",
        "Accept": "application/json",
        "User-Agent": "cocoindex-bookstack-export/1.0"
    }
    
    try:
        # Fetch all pages with pagination and timeouts
        all_pages = []
        url = f"{BOOKSTACK_URL}/api/pages"
        page_count = 0
        max_pages = 20  # Limit for testing
        
        print(f"Connecting to {BOOKSTACK_URL}...")
        
        while url and page_count < max_pages:
            print(f"Fetching page {page_count + 1}...")
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            page_count += 1
            
            for page in data.get('data', []):
                print(f"  Fetching details for page {page['id']}...")
                page_url = f"{BOOKSTACK_URL}/api/pages/{page['id']}?include=book,chapter,tags"
                page_response = requests.get(page_url, headers=headers, timeout=10)
                if page_response.status_code == 200:
                    page_detail = page_response.json()
                    
                    # Get book and chapter info
                    book_name = "Unknown"
                    chapter_name = ""
                    
                    # Try to get book info
                    if page_detail.get('book_id'):
                        book_url = f"{BOOKSTACK_URL}/api/books/{page_detail['book_id']}"
                        book_response = requests.get(book_url, headers=headers)
                        if book_response.status_code == 200:
                            book_data = book_response.json()
                            book_name = book_data.get('name', f"Book_{page_detail['book_id']}")
                    
                    # Get tags
                    tags = []
                    if 'tags' in page_detail:
                        tags = [tag['name'] for tag in page_detail['tags']]
                    
                    # Create export data matching our schema
                    export_data = {
                        "id": page_detail['id'],
                        "title": page_detail.get('name', 'Untitled'),
                        "slug": page_detail.get('slug', ''),
                        "url": f"{BOOKSTACK_URL}/books/{page_detail.get('book_slug', 'unknown')}/page/{page_detail.get('slug', page_detail['id'])}",
                        "updated_at": page_detail.get('updated_at', ''),
                        "body_html": page_detail.get('html', ''),
                        "tags": tags,
                        "book": book_name,
                        "chapter": chapter_name
                    }
                    
                    # Save to file
                    filename = f"{EXPORT_DIR}/page_{page_detail['id']}.json"
                    with open(filename, 'w', encoding='utf-8') as f:
                        json.dump(export_data, f, indent=2)
                    
                    all_pages.append(export_data)
            
            # Check for next page
            url = data.get('links', {}).get('next')
        
        print(f"Exported {len(all_pages)} pages to {EXPORT_DIR}")
        return True
        
    except Exception as e:
        print(f"Error exporting BookStack pages: {e}")
        return False

# Use the existing enhanced flow but with continuous monitoring
@cocoindex.op.function()
def trigger_export() -> dict:
    """Trigger BookStack export and return status."""
    success = export_bookstack_pages()
    return {"success": success, "timestamp": cocoindex.GeneratedField.NOW}

@cocoindex.flow_def(name="BookStackToFalkorContinuous")
def bookstack_to_falkor_continuous(flow_builder: FlowBuilder, data_scope: DataScope) -> None:
    """Continuous BookStack to FalkorDB sync."""
    
    # Trigger periodic exports
    data_scope["export_trigger"] = flow_builder.add_source(
        cocoindex.sources.Timer(interval=timedelta(minutes=5)),  # Check every 5 minutes
        refresh_interval=timedelta(seconds=1)
    )
    
    export_status = data_scope.add_collector()
    
    with data_scope["export_trigger"].row() as trigger:
        status = trigger.transform(lambda _: trigger_export())
        export_status.collect(
            timestamp=status["timestamp"],
            success=status["success"]
        )
    
    # Monitor the export directory for JSON files
    data_scope["pages"] = flow_builder.add_source(
        cocoindex.sources.LocalFile(
            path=EXPORT_DIR,
            included_patterns=["*.json"]
        ),
        refresh_interval=timedelta(seconds=30)  # Check for new files every 30 seconds
    )
    
    # Now use the same flow logic from bookstack_to_falkor.py
    # Import the functions we need
    import sys
    sys.path.append(os.path.dirname(__file__))
    from bookstack_to_falkor import (
        html_to_text_op,
        extract_entities_op,
        extract_relationships_op
    )
    
    # Create collectors
    processed_pages = data_scope.add_collector()
    extracted_entities = data_scope.add_collector()
    extracted_relationships = data_scope.add_collector()
    
    # Process each page
    with data_scope["pages"].row() as page:
        # Parse JSON content
        page["parsed"] = page["content"].transform(cocoindex.functions.ParseJson())
        
        # Extract HTML content and convert to text
        page["text_content"] = page["parsed"].transform(
            lambda p: html_to_text_op(p.get("body_html", ""))
        )
        
        # Extract entities from content
        page["entities"] = page["text_content"].transform(extract_entities_op)
        
        # Extract relationships between entities
        page["relationships"] = page["text_content"].transform(extract_relationships_op)
        
        # Collect page information
        processed_pages.collect(
            page_id=page["parsed"].transform(lambda p: p.get("id")),
            title=page["parsed"].transform(lambda p: p.get("title")),
            book=page["parsed"].transform(lambda p: p.get("book")),
            url=page["parsed"].transform(lambda p: p.get("url")),
            updated_at=page["parsed"].transform(lambda p: p.get("updated_at")),
            filename=page["filename"]
        )
        
        # Collect entities
        with page["entities"].row() as entity:
            extracted_entities.collect(
                name=entity["name"],
                type=entity["type"],
                description=entity["description"],
                page_id=page["parsed"].transform(lambda p: p.get("id"))
            )
        
        # Collect relationships
        with page["relationships"].row() as rel:
            extracted_relationships.collect(
                subject=rel["subject"],
                predicate=rel["predicate"],
                object=rel["object"],
                fact=rel["fact"],
                page_id=page["parsed"].transform(lambda p: p.get("id"))
            )
    
    # Export to PostgreSQL for tracking
    # In production, you would add FalkorDB export here
    processed_pages.export(
        "bookstack_pages_continuous",
        cocoindex.targets.Postgres(
            connection=cocoindex.targets.PostgresConnection.from_sqlalchemy_url(
                os.environ.get("COCOINDEX_DB", "postgresql://cocoindex:cocoindex@localhost:5433/cocoindex")
            ),
            schema="bookstack_processed",
            primary_key_fields=["page_id"],
            column_types={
                "page_id": "INTEGER",
                "title": "TEXT", 
                "book": "TEXT",
                "url": "TEXT",
                "updated_at": "TIMESTAMP",
                "filename": "TEXT"
            }
        )
    )
    
    print("Continuous BookStack sync flow configured!")
    print("Will check for updates every 5 minutes")
    print(f"Exporting to: {EXPORT_DIR}")

if __name__ == "__main__":
    # Test the export function
    print("Testing BookStack export...")
    export_bookstack_pages()