#!/usr/bin/env python3
"""
Test direct export to FalkorDB without CocoIndex.
"""

import os
import json
import glob
from flows.bookstack_ollama_simple import process_page_with_ollama, _FALKOR

# Get all JSON files
json_files = glob.glob("bookstack_export_full/*.json")
print(f"Found {len(json_files)} JSON files to process")

# Process first 5 files directly
for i, json_file in enumerate(json_files[:5]):
    with open(json_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    print(f"\nProcessing file {i+1}: {json_file}")
    result = process_page_with_ollama(content)
    print(f"Result: {result}")
    
print("\nDirect processing complete!")