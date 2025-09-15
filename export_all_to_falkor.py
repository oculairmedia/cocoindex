#!/usr/bin/env python3
"""
Export all BookStack documents to FalkorDB directly.
"""

import os
import json
import glob
from flows.bookstack_ollama_simple import process_page_with_ollama, _FALKOR

# Get all JSON files
json_files = sorted(glob.glob("bookstack_export_full/*.json"))
print(f"Found {len(json_files)} JSON files to process")

success_count = 0
error_count = 0

# Process all files
for i, json_file in enumerate(json_files):
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        result = process_page_with_ollama(content)
        
        if result['status'] == 'success':
            success_count += 1
            if (i + 1) % 10 == 0:
                print(f"Progress: {i+1}/{len(json_files)} processed ({success_count} successful)")
        else:
            error_count += 1
            print(f"Error processing {json_file}: {result.get('error', 'Unknown error')}")
            
    except Exception as e:
        error_count += 1
        print(f"Exception processing {json_file}: {e}")

print(f"\nExport complete!")
print(f"Total files: {len(json_files)}")
print(f"Successful: {success_count}")
print(f"Errors: {error_count}")