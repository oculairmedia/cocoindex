#!/usr/bin/env python3
"""
Direct BookStack to FalkorDB ingestion test
Bypasses CocoIndex to test basic flow
"""

import os
import json
import redis
from bs4 import BeautifulSoup

def html_to_text(html_content):
    """Convert HTML to clean text."""
    soup = BeautifulSoup(html_content, "html.parser")
    
    # Remove script and style elements
    for script in soup(["script", "style"]):
        script.decompose()
    
    text = soup.get_text(separator="\n", strip=True)
    
    # Clean up whitespace
    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    text = "\n".join(chunk for chunk in chunks if chunk)
    
    return text[:500]  # Limit for testing

def main():
    print("Direct BookStack to FalkorDB Ingestion Test")
    print("=" * 50)
    
    # Connect to FalkorDB
    r = redis.Redis(host='localhost', port=6379, decode_responses=True)
    graph_name = 'graphiti_migration'
    
    # Test connection
    print(f"Testing connection...")
    try:
        r.ping()
        print("Connected to FalkorDB")
    except Exception as e:
        print(f"Connection failed: {e}")
        return
    
    # Get first few JSON files
    export_dir = "bookstack_export_full"
    json_files = [f for f in os.listdir(export_dir) if f.endswith('.json')][:5]
    
    print(f"Processing {len(json_files)} files...")
    
    processed = 0
    for filename in json_files:
        filepath = os.path.join(export_dir, filename)
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Extract basic info
            title = data.get('title', 'Untitled')
            book = data.get('book', 'Unknown')
            url = data.get('url', '')
            html_content = data.get('body_html', '')
            
            # Convert HTML to text
            text_content = html_to_text(html_content)
            
            # Create Cypher query to insert document node
            # Using string formatting for FalkorDB parameters
            cypher = f"""
            CREATE (d:Document {{
                filename: '{filename.replace("'", "\\'")}',
                title: '{title.replace("'", "\\'")}',
                book: '{book.replace("'", "\\'")}',
                url: '{url.replace("'", "\\'")}',
                content: '{text_content.replace("'", "\\'")}'
            }})
            RETURN d.title
            """
            
            # Execute query
            result = r.execute_command('GRAPH.QUERY', graph_name, cypher)
            print(f"Processed: {title[:50]}...")
            processed += 1
            
        except Exception as e:
            print(f"Error processing {filename}: {e}")
    
    print(f"\nProcessed {processed} documents")
    
    # Verify data in graph
    print("\nVerifying data in FalkorDB...")
    try:
        result = r.execute_command('GRAPH.QUERY', graph_name, 'MATCH (d:Document) RETURN count(d)')
        count = result[1][0][0] if result[1] else 0
        print(f"Found {count} Document nodes in graph")
        
        # Show sample documents
        result = r.execute_command('GRAPH.QUERY', graph_name, 'MATCH (d:Document) RETURN d.title, d.book LIMIT 3')
        if result[1]:
            print("\nSample documents:")
            for row in result[1]:
                print(f"  - {row[0]} (Book: {row[1]})")
                
    except Exception as e:
        print(f"Error verifying data: {e}")

if __name__ == "__main__":
    main()