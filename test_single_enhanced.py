#!/usr/bin/env python3
"""
Test enhanced extraction on a single document.
"""

import json
from flows.bookstack_ollama_enhanced import process_page_with_enhanced_ollama

# Test with one document
with open("bookstack_export_full/page_102.json", 'r', encoding='utf-8') as f:
    content = f.read()

print("Testing single document with enhanced extraction...")
result = process_page_with_enhanced_ollama(content)
print(f"Result: {result}")