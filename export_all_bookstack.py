#!/usr/bin/env python3
"""
Export ALL BookStack pages to JSON files for ingestion
"""

import os
import json
import requests
from pathlib import Path

BOOKSTACK_URL = "https://knowledge.oculair.ca"
BOOKSTACK_TOKEN_ID = "POnHR9Lbvm73T2IOcyRSeAqpA8bSGdMT"
BOOKSTACK_TOKEN_SECRET = "735wM5dScfUkcOy7qcrgqQ1eC5fBF7IE"
EXPORT_DIR = "bookstack_export_full"

def export_all_pages():
    """Export all BookStack pages."""
    Path(EXPORT_DIR).mkdir(exist_ok=True)
    
    headers = {
        "Authorization": f"Token {BOOKSTACK_TOKEN_ID}:{BOOKSTACK_TOKEN_SECRET}",
        "Accept": "application/json"
    }
    
    print("Exporting ALL BookStack pages...")
    print(f"Export directory: {EXPORT_DIR}")
    
    try:
        # Get all pages with pagination
        offset = 0
        count = 50
        total_exported = 0
        
        while True:
            print(f"\nFetching pages {offset + 1} to {offset + count}...")
            url = f"{BOOKSTACK_URL}/api/pages?count={count}&offset={offset}"
            response = requests.get(url, headers=headers, timeout=15)
            
            if response.status_code != 200:
                print(f"Error fetching pages: {response.status_code}")
                break
            
            data = response.json()
            pages = data.get('data', [])
            
            if not pages:
                print("No more pages found.")
                break
            
            print(f"Processing {len(pages)} pages...")
            
            for page_summary in pages:
                page_id = page_summary['id']
                
                # Get detailed page data
                detail_url = f"{BOOKSTACK_URL}/api/pages/{page_id}?include=book,chapter,tags"
                detail_response = requests.get(detail_url, headers=headers, timeout=10)
                
                if detail_response.status_code == 200:
                    page_detail = detail_response.json()
                    
                    # Extract data in our schema format
                    export_data = {
                        "id": page_detail['id'],
                        "title": page_detail.get('name', 'Untitled'),
                        "slug": page_detail.get('slug', ''),
                        "url": f"{BOOKSTACK_URL}/books/{page_detail.get('book_slug', 'unknown')}/page/{page_detail.get('slug', page_detail['id'])}",
                        "updated_at": page_detail.get('updated_at', ''),
                        "body_html": page_detail.get('html', ''),
                        "tags": [tag['name'] for tag in page_detail.get('tags', [])],
                        "book": page_detail.get('book', {}).get('name', 'Unknown'),
                        "chapter": page_detail.get('chapter', {}).get('name', '') if page_detail.get('chapter') else ""
                    }
                    
                    # Save to file
                    filename = f"{EXPORT_DIR}/page_{page_id}.json"
                    with open(filename, 'w', encoding='utf-8') as f:
                        json.dump(export_data, f, indent=2, ensure_ascii=False)
                    
                    total_exported += 1
                    # Handle Unicode in title for display
                    safe_title = export_data['title'].encode('ascii', 'replace').decode('ascii')
                    print(f"  Exported: {safe_title} -> {filename}")
                else:
                    print(f"  Failed to get details for page {page_id}: {detail_response.status_code}")
            
            offset += len(pages)
            
            # Check if we got less than requested (last page)
            if len(pages) < count:
                break
        
        print(f"\n=== Export Complete ===")
        print(f"Total pages exported: {total_exported}")
        print(f"Files saved to: {EXPORT_DIR}/")
        
        return total_exported
        
    except Exception as e:
        print(f"Error during export: {e}")
        return 0

if __name__ == "__main__":
    export_all_pages()