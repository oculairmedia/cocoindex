#!/usr/bin/env python3
"""
Test simple Ollama Gemma3 extraction with CocoIndex.
"""

import os
import json
from pathlib import Path

# Test reading a sample BookStack file
sample_file = Path("bookstack_export_full") / "page_10.json"
if sample_file.exists():
    with open(sample_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print(f"Testing with: {data.get('title', 'Unknown')}")
    print(f"Book: {data.get('book', 'Unknown')}")
    print(f"Tags: {data.get('tags', [])}")
    print()
    
    # Run the processing function directly
    from flows.bookstack_ollama_simple import process_page_with_ollama
    
    result = process_page_with_ollama(json.dumps(data))
    print(f"Processing result: {result}")
else:
    print("No sample file found")