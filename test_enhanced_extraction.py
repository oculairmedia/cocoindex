#!/usr/bin/env python3
"""
Test enhanced Ollama extraction on a few sample documents.
"""

import json
import glob
from flows.bookstack_ollama_enhanced import process_page_with_enhanced_ollama

# Test with 3 sample documents
json_files = sorted(glob.glob("bookstack_export_full/*.json"))[:3]

print("Testing Enhanced Ollama Entity Extraction")
print("=" * 50)

for i, json_file in enumerate(json_files):
    print(f"\nTesting file {i+1}: {json_file}")
    
    with open(json_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    result = process_page_with_enhanced_ollama(content)
    
    print(f"Result: {result}")
    print("-" * 30)

print("\nSample test complete!")