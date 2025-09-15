"""
Simplified BookStack to FalkorDB flow for testing
"""
from __future__ import annotations

import os
import re
import json
from datetime import timedelta

import cocoindex
from cocoindex import DataScope, FlowBuilder


@cocoindex.op.function()
def process_page_and_chunk(json_str: str) -> list[dict]:
    """Process a page JSON and return chunks with metadata"""
    from bs4 import BeautifulSoup
    
    # Parse JSON
    page = json.loads(json_str)
    
    # Extract HTML to text
    html = page.get("body_html", "")
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n")
    
    # Simple chunking
    chunk_size = 1200
    overlap = 300
    chunks = []
    
    for i in range(0, len(text), chunk_size - overlap):
        chunk_text = text[i:i + chunk_size].strip()
        if chunk_text:
            chunks.append({
                "text": chunk_text,
                "page_id": page.get("id"),
                "title": page.get("title", "Untitled"),
                "url": page.get("url", ""),
                "book": page.get("book", ""),
                "tags": page.get("tags", [])
            })
    
    # If no chunks, create one with empty text
    if not chunks:
        chunks.append({
            "text": "",
            "page_id": page.get("id"),
            "title": page.get("title", "Untitled"),
            "url": page.get("url", ""),
            "book": page.get("book", ""),
            "tags": page.get("tags", [])
        })
    
    return chunks


@cocoindex.op.function()
def print_chunk_info(chunk: dict) -> None:
    """Print chunk information for debugging"""
    print(f"\n[CHUNK] Page: {chunk['title']} (ID: {chunk['page_id']})")
    print(f"Book: {chunk['book']}")
    print(f"Tags: {chunk['tags']}")
    print(f"Text length: {len(chunk['text'])} chars")
    print(f"Text preview: {chunk['text'][:100]}...")
    print("-" * 60)


@cocoindex.flow_def(name="BookStackToFalkorSimple")
def bookstack_to_falkor_simple(flow_builder: FlowBuilder, data_scope: DataScope):
    # Add source for JSON files
    data_scope["pages"] = flow_builder.add_source(
        cocoindex.sources.LocalFile(path="bookstack_export", included_patterns=["*.json"]),
        refresh_interval=timedelta(minutes=2),
    )
    
    # Process each page
    with data_scope["pages"].row() as page:
        # Process and chunk the page
        chunks = page["content"].transform(process_page_and_chunk)
        
        # Process each chunk
        with chunks.row() as chunk:
            # For now, just print the chunk info
            chunk.call(print_chunk_info)