"""
BookStack to FalkorDB continuous sync using CocoIndex
Uses a function to fetch BookStack data and local file monitoring for changes
"""

import os
import json
import dataclasses
import requests
from datetime import timedelta
from typing import List
from pathlib import Path

import cocoindex
from cocoindex import DataScope, FlowBuilder

# Configuration
BOOKSTACK_URL = os.environ.get("BS_URL", "https://knowledge.oculair.ca")
BOOKSTACK_TOKEN_ID = os.environ.get("BS_TOKEN_ID", "POnHR9Lbvm73T2IOcyRSeAqpA8bSGdMT")
BOOKSTACK_TOKEN_SECRET = os.environ.get("BS_TOKEN_SECRET", "735wM5dScfUkcOy7qcrgqQ1eC5fBF7IE")
SYNC_DIR = "bookstack_sync"

# Ensure sync directory exists
Path(SYNC_DIR).mkdir(exist_ok=True)

# Data structures for LLM extraction
@dataclasses.dataclass
class Entity:
    """An entity extracted from content."""
    name: str
    type: str  # PERSON, ORGANIZATION, CONCEPT, TECHNOLOGY, LOCATION
    description: str

@dataclasses.dataclass
class Relationship:
    """A relationship between two entities."""
    subject: str
    predicate: str
    object: str
    fact: str

@dataclasses.dataclass
class DocumentSummary:
    """Summary of a BookStack page."""
    title: str
    summary: str

# Function to sync BookStack data
@cocoindex.op.function()
def sync_bookstack_data() -> bool:
    """Fetch latest BookStack data and save to sync directory."""
    headers = {
        "Authorization": f"Token {BOOKSTACK_TOKEN_ID}:{BOOKSTACK_TOKEN_SECRET}",
        "Accept": "application/json"
    }
    
    try:
        print(f"Syncing from {BOOKSTACK_URL}...")
        
        # Fetch pages with pagination
        all_pages = []
        offset = 0
        count = 50
        
        while True:
            url = f"{BOOKSTACK_URL}/api/pages?count={count}&offset={offset}"
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            data = response.json()
            pages = data.get('data', [])
            
            if not pages:
                break
            
            # Get detailed data for each page
            for page_summary in pages:
                page_id = page_summary['id']
                detail_url = f"{BOOKSTACK_URL}/api/pages/{page_id}?include=book,chapter,tags"
                detail_response = requests.get(detail_url, headers=headers, timeout=10)
                
                if detail_response.status_code == 200:
                    page_detail = detail_response.json()
                    
                    # Create our format
                    page_data = {
                        "id": page_detail['id'],
                        "title": page_detail.get('name', 'Untitled'),
                        "content": page_detail.get('html', ''),
                        "book": page_detail.get('book', {}).get('name', 'Unknown'),
                        "chapter": page_detail.get('chapter', {}).get('name', '') if page_detail.get('chapter') else "",
                        "tags": [tag['name'] for tag in page_detail.get('tags', [])],
                        "url": f"{BOOKSTACK_URL}/books/{page_detail.get('book_slug', 'unknown')}/page/{page_detail.get('slug', page_detail['id'])}",
                        "updated_at": page_detail.get('updated_at', '')
                    }
                    
                    # Save to file
                    filename = f"{SYNC_DIR}/page_{page_id}.json"
                    with open(filename, 'w', encoding='utf-8') as f:
                        json.dump(page_data, f, indent=2, ensure_ascii=False)
                    
                    all_pages.append(page_data)
            
            offset += len(pages)
            if len(pages) < count:
                break
        
        print(f"Synced {len(all_pages)} pages")
        return True
        
    except Exception as e:
        print(f"Sync error: {e}")
        return False

# Helper functions
@cocoindex.op.function()
def html_to_text(html_content: str) -> str:
    """Convert HTML to clean text."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html_content, "html.parser")
    
    # Remove script and style elements
    for script in soup(["script", "style"]):
        script.decompose()
    
    text = soup.get_text(separator="\n", strip=True)
    
    # Clean up whitespace
    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    text = "\n".join(chunk for chunk in chunks if chunk)
    
    return text

# FalkorDB connection (Neo4j compatible)
try:
    falkor_conn_spec = cocoindex.add_auth_entry(
        "FalkorDBConnection",
        cocoindex.targets.Neo4jConnection(
            uri=f"bolt://{os.environ.get('FALKOR_HOST', 'localhost')}:{os.environ.get('FALKOR_PORT', '6379')}",
            user="",
            password="",
        ),
    )
except Exception:
    # Fallback to PostgreSQL if FalkorDB connection fails
    print("FalkorDB connection failed, using PostgreSQL")
    falkor_conn_spec = None

# Main flow definition
@cocoindex.flow_def(name="BookStackContinuousSimple")
def bookstack_continuous_simple(flow_builder: FlowBuilder, data_scope: DataScope) -> None:
    """Continuous BookStack sync to FalkorDB."""
    
    # Periodic sync trigger
    data_scope["sync_trigger"] = flow_builder.add_source(
        cocoindex.sources.Timer(interval=timedelta(minutes=5)),
        refresh_interval=timedelta(seconds=1)
    )
    
    sync_status = data_scope.add_collector()
    
    # Trigger sync on timer
    with data_scope["sync_trigger"].row() as trigger:
        status = trigger.transform(lambda _: sync_bookstack_data())
        sync_status.collect(
            timestamp=cocoindex.GeneratedField.NOW,
            success=status
        )
    
    # Monitor synced files
    data_scope["pages"] = flow_builder.add_source(
        cocoindex.sources.LocalFile(
            path=SYNC_DIR,
            included_patterns=["*.json"]
        ),
        refresh_interval=timedelta(seconds=30)
    )
    
    # Collectors for knowledge graph
    document_node = data_scope.add_collector()
    entity_relationship = data_scope.add_collector()
    entity_mention = data_scope.add_collector()
    
    # Process each page
    with data_scope["pages"].row() as page:
        # Parse JSON
        page["parsed"] = page["content"].transform(cocoindex.functions.ParseJson())
        
        # Convert HTML to text
        page["text_content"] = page["parsed"].transform(
            lambda p: html_to_text(p.get("content", ""))
        )
        
        # Extract document summary using LLM
        page["summary"] = page["text_content"].transform(
            cocoindex.functions.ExtractByLlm(
                llm_spec=cocoindex.LlmSpec(
                    api_type=cocoindex.LlmApiType.OPENAI,
                    model="gpt-4o"
                ),
                output_type=DocumentSummary,
                instruction="Summarize this BookStack page content, identifying the main title and key summary."
            )
        )
        
        # Extract relationships using LLM
        page["relationships"] = page["text_content"].transform(
            cocoindex.functions.ExtractByLlm(
                llm_spec=cocoindex.LlmSpec(
                    api_type=cocoindex.LlmApiType.OPENAI,
                    model="gpt-4o"
                ),
                output_type=List[Relationship],
                instruction=(
                    "Extract relationships from this BookStack content. "
                    "Focus on meaningful connections between concepts, technologies, and entities. "
                    "Subject and object should be specific concepts from the content."
                )
            )
        )
        
        # Collect document nodes (Episodic in Graphiti schema)
        document_node.collect(
            uuid=page["parsed"].transform(lambda p: str(p.get("id"))),
            name=page["summary"]["title"],
            content=page["text_content"],
            group_id=page["parsed"].transform(lambda p: p.get("book", "Unknown")),
            valid_at=page["parsed"].transform(lambda p: p.get("updated_at", "")),
            source="BookStack",
            source_description=page["parsed"].transform(lambda p: p.get("url", "")),
            filename=page["filename"]
        )
        
        # Collect relationships and mentions
        with page["relationships"].row() as relationship:
            entity_relationship.collect(
                id=cocoindex.GeneratedField.UUID,
                subject=relationship["subject"],
                object=relationship["object"],
                predicate=relationship["predicate"],
                fact=relationship["fact"],
                group_id=page["parsed"].transform(lambda p: p.get("book", "Unknown"))
            )
            
            # Entity mentions
            entity_mention.collect(
                id=cocoindex.GeneratedField.UUID,
                entity=relationship["subject"],
                document_id=page["parsed"].transform(lambda p: str(p.get("id"))),
                group_id=page["parsed"].transform(lambda p: p.get("book", "Unknown"))
            )
            entity_mention.collect(
                id=cocoindex.GeneratedField.UUID,
                entity=relationship["object"],
                document_id=page["parsed"].transform(lambda p: str(p.get("id"))),
                group_id=page["parsed"].transform(lambda p: p.get("book", "Unknown"))
            )
    
    # Export sync status to PostgreSQL for monitoring
    sync_status.export(
        "bookstack_sync_status",
        cocoindex.targets.Postgres(
            connection=cocoindex.targets.PostgresConnection.from_sqlalchemy_url(
                os.environ.get("COCOINDEX_DB", "postgresql://cocoindex:cocoindex@localhost:5433/cocoindex")
            ),
            primary_key_fields=["timestamp"]
        )
    )
    
    # Export to FalkorDB if available, otherwise PostgreSQL
    if falkor_conn_spec:
        # Export to FalkorDB using Graphiti schema
        document_node.export(
            "episodic_nodes",
            cocoindex.targets.Neo4j(
                connection=falkor_conn_spec,
                mapping=cocoindex.targets.Nodes(label="Episodic")
            ),
            primary_key_fields=["uuid"]
        )
        
        # Declare Entity nodes
        flow_builder.declare(
            cocoindex.targets.Neo4jDeclaration(
                connection=falkor_conn_spec,
                nodes_label="Entity",
                primary_key_fields=["name", "group_id"],
            )
        )
        
        # Export relationships
        entity_relationship.export(
            "entity_relationships",
            cocoindex.targets.Neo4j(
                connection=falkor_conn_spec,
                mapping=cocoindex.targets.Relationships(
                    rel_type="RELATES_TO",
                    source=cocoindex.targets.NodeFromFields(
                        label="Entity",
                        fields=[
                            cocoindex.targets.TargetFieldMapping(source="subject", target="name"),
                            cocoindex.targets.TargetFieldMapping(source="group_id", target="group_id"),
                        ]
                    ),
                    target=cocoindex.targets.NodeFromFields(
                        label="Entity",
                        fields=[
                            cocoindex.targets.TargetFieldMapping(source="object", target="name"),
                            cocoindex.targets.TargetFieldMapping(source="group_id", target="group_id"),
                        ]
                    ),
                ),
            ),
            primary_key_fields=["id"],
        )
        
        # Export mentions
        entity_mention.export(
            "entity_mentions",
            cocoindex.targets.Neo4j(
                connection=falkor_conn_spec,
                mapping=cocoindex.targets.Relationships(
                    rel_type="MENTIONS",
                    source=cocoindex.targets.NodeFromFields(
                        label="Episodic",
                        fields=[
                            cocoindex.targets.TargetFieldMapping(source="document_id", target="uuid"),
                        ]
                    ),
                    target=cocoindex.targets.NodeFromFields(
                        label="Entity",
                        fields=[
                            cocoindex.targets.TargetFieldMapping(source="entity", target="name"),
                            cocoindex.targets.TargetFieldMapping(source="group_id", target="group_id"),
                        ]
                    ),
                ),
            ),
            primary_key_fields=["id"],
        )
    else:
        # Fallback to PostgreSQL
        document_node.export(
            "bookstack_documents",
            cocoindex.targets.Postgres(
                connection=cocoindex.targets.PostgresConnection.from_sqlalchemy_url(
                    os.environ.get("COCOINDEX_DB", "postgresql://cocoindex:cocoindex@localhost:5433/cocoindex")
                ),
                primary_key_fields=["uuid"]
            )
        )
        
        entity_relationship.export(
            "bookstack_relationships",
            cocoindex.targets.Postgres(
                connection=cocoindex.targets.PostgresConnection.from_sqlalchemy_url(
                    os.environ.get("COCOINDEX_DB", "postgresql://cocoindex:cocoindex@localhost:5433/cocoindex")
                ),
                primary_key_fields=["id"]
            )
        )

if __name__ == "__main__":
    print("BookStack Continuous Simple Flow defined!")
    print(f"Will sync from: {BOOKSTACK_URL}")
    print(f"Sync directory: {SYNC_DIR}")
    print("Run with: cocoindex update --setup flows/bookstack_continuous_simple.py")