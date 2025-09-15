#!/usr/bin/env python3
"""
Test enhanced extraction on a batch of documents.
"""

import glob
import time
from flows.bookstack_ollama_enhanced import process_page_with_enhanced_ollama

# Test with first 20 files
json_files = sorted(glob.glob("bookstack_export_full/*.json"))[:20]
print(f"Testing enhanced extraction on {len(json_files)} documents...")

success_count = 0
error_count = 0
total_entities = 0
ollama_entities = 0
fallback_entities = 0

start_time = time.time()

for i, json_file in enumerate(json_files):
    print(f"\n[{i+1}/{len(json_files)}] Processing: {json_file.split('/')[-1]}")
    
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        result = process_page_with_enhanced_ollama(content)
        
        if result['status'] == 'success':
            success_count += 1
            total_entities += result['entities_found']
            ollama_entities += result.get('ollama_entities', 0)
            fallback_entities += (result['entities_found'] - result.get('ollama_entities', 0))
            
            print(f"  SUCCESS: {result['title'][:40]} - {result['entities_found']} entities")
        else:
            error_count += 1
            print(f"  ERROR: {result.get('error', 'Unknown')}")
            
    except Exception as e:
        error_count += 1
        print(f"  EXCEPTION: {e}")

elapsed = time.time() - start_time
print(f"\nEnhanced extraction test complete!")
print(f"Time: {elapsed:.1f} seconds")
print(f"Success: {success_count}/{len(json_files)}")
print(f"Errors: {error_count}")
print(f"Total entities: {total_entities}")
print(f"Ollama entities: {ollama_entities}")
print(f"Fallback entities: {fallback_entities}")
print(f"Avg entities per doc: {total_entities/success_count:.1f}" if success_count > 0 else "")