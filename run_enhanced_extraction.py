#!/usr/bin/env python3
"""
Run enhanced extraction on all documents.
"""

import glob
import time
from flows.bookstack_ollama_enhanced import process_page_with_enhanced_ollama

# Clear existing data first
import redis
r = redis.Redis(host='localhost', port=6379, decode_responses=True)
print("Clearing existing data...")
try:
    r.execute_command('GRAPH.DELETE', 'graphiti_migration')
except:
    print("Graph didn't exist, starting fresh")

# Get all JSON files 
json_files = sorted(glob.glob("bookstack_export_full/*.json"))
print(f"Processing {len(json_files)} documents with enhanced Ollama extraction...")

success_count = 0
error_count = 0
total_entities = 0

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
            
            if (i + 1) % 5 == 0:
                elapsed = time.time() - start_time
                rate = (i + 1) / elapsed * 60  # docs per minute
                print(f"Progress: {i+1}/{len(json_files)} ({success_count} success, {total_entities} entities, {rate:.1f} docs/min)")
                
        # Show progress for every document
        if (i + 1) % 1 == 0:
            print(f"  Processed: {result.get('title', 'Unknown')[:40]} - {result['entities_found']} entities")
        else:
            error_count += 1
            print(f"Error: {json_file} - {result.get('error', 'Unknown')}")
            
    except Exception as e:
        error_count += 1
        print(f"Exception: {json_file} - {e}")

elapsed = time.time() - start_time
print(f"\nEnhanced extraction complete!")
print(f"Time: {elapsed:.1f} seconds")
print(f"Success: {success_count}/{len(json_files)}")
print(f"Errors: {error_count}")
print(f"Total entities: {total_entities}")
print(f"Avg entities per doc: {total_entities/success_count:.1f}" if success_count > 0 else "")