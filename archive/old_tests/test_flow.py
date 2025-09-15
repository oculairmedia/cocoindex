#!/usr/bin/env python3
"""
Simple test script to see what the flow would do in dry-run mode
"""

import os
import sys
sys.path.append("python")

# Set dry run mode
os.environ["DRY_RUN"] = "true"

# Import the functions from the flow
from flows.bookstack_to_falkor import (
    html_to_text, embed_qwen3, export_to_falkor, 
    extract_output, _embed_tag_cached, Falkor
)

import json
from pathlib import Path

def test_pipeline():
    print("=== Testing BookStack to FalkorDB Pipeline (DRY RUN) ===\n")
    
    # Initialize Falkor client in dry-run mode
    falkor = Falkor(dry_run=True)
    
    # Process each JSON file
    for json_file in Path("bookstack_export").glob("*.json"):
        print(f"\n📄 Processing: {json_file.name}")
        
        # Load the page data
        with open(json_file, 'r', encoding='utf-8') as f:
            page = json.load(f)
        
        print(f"Title: {page.get('title', 'N/A')}")
        print(f"Tags: {page.get('tags', [])}")
        print(f"Book: {page.get('book', 'N/A')}")
        
        # Convert HTML to text
        html_content = page.get('body_html', '')
        text_content = html_to_text(html_content)
        print(f"Content length: {len(text_content)} chars")
        
        # Simulate chunking (normally done by CocoIndex)
        # Using simple chunking for demo
        chunk_size = 1200
        chunks = [text_content[i:i+chunk_size] for i in range(0, len(text_content), chunk_size-300)]
        print(f"Generated {len(chunks)} chunk(s)")
        
        # Process each chunk
        for i, chunk_text in enumerate(chunks):
            print(f"\n--- Chunk {i+1} ---")
            export_to_falkor(page, chunk_text.strip())
        
        print("\n" + "="*60)

if __name__ == "__main__":
    test_pipeline()