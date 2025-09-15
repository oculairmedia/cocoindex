#!/usr/bin/env python3
"""
Ingest all BookStack documents into FalkorDB
"""

import os
import redis
import json
import glob
from pathlib import Path

# Set up environment
os.environ["FALKOR_HOST"] = "localhost"
os.environ["FALKOR_PORT"] = "6379"
os.environ["FALKOR_GRAPH"] = "graphiti_migration"

def escape_quotes(text):
    """Escape single quotes for Cypher queries."""
    return text.replace("'", "\\'") if text else ""

def ingest_all_bookstack_data():
    """Ingest all BookStack data into FalkorDB."""
    print("Ingesting All BookStack Data into FalkorDB")
    print("=" * 50)
    
    # Connect to FalkorDB
    r = redis.Redis(host='localhost', port=6379, decode_responses=True)
    
    # Test connection
    print("Testing connection...")
    r.ping()
    print("Connected successfully!")
    
    # Find all JSON files
    json_files = glob.glob('bookstack_export_full/*.json')
    print(f"\nFound {len(json_files)} BookStack pages to ingest")
    
    total_entities = 0
    total_relationships = 0
    total_documents = 0
    
    for json_file in json_files:
        with open(json_file, 'r', encoding='utf-8') as f:
            page_data = json.load(f)
        
        # Handle Unicode characters in title for display
        safe_title = page_data['title'].encode('ascii', 'replace').decode('ascii')
        print(f"\nProcessing: {safe_title}")
        
        # Create document node
        query = f"""
        MERGE (d:Document {{id: '{page_data['id']}'}})
        SET d.title = '{escape_quotes(page_data['title'])}', 
            d.url = '{escape_quotes(page_data.get('url', ''))}', 
            d.book = '{escape_quotes(page_data.get('book', 'Unknown'))}',
            d.chapter = '{escape_quotes(page_data.get('chapter', ''))}',
            d.updated_at = '{page_data.get('updated_at', '')}'
        RETURN d
        """
        r.execute_command("GRAPH.QUERY", "graphiti_migration", query)
        total_documents += 1
        
        # Create entities from tags
        for tag in page_data.get('tags', []):
            entity_name = tag.replace('-', ' ').title()
            query = f"""
            MERGE (e:Entity {{name: '{escape_quotes(entity_name)}'}})
            SET e.type = 'TAG', e.source = 'BookStack'
            RETURN e
            """
            r.execute_command("GRAPH.QUERY", "graphiti_migration", query)
            total_entities += 1
            
            # Link document to entity
            query = f"""
            MATCH (d:Document {{id: '{page_data['id']}'}})
            MATCH (e:Entity {{name: '{escape_quotes(entity_name)}'}})
            MERGE (d)-[r:HAS_ENTITY]->(e)
            RETURN r
            """
            r.execute_command("GRAPH.QUERY", "graphiti_migration", query)
            total_relationships += 1
        
        # Extract concepts from content (simple approach)
        content_text = page_data.get('body_html', '')
        
        # Look for common technology terms
        tech_terms = ['machine learning', 'artificial intelligence', 'ai', 'ml', 
                      'deep learning', 'neural network', 'data science', 'python',
                      'tensorflow', 'pytorch', 'scikit-learn', 'pandas', 'numpy']
        
        for term in tech_terms:
            if term.lower() in content_text.lower():
                entity_name = term.title()
                query = f"""
                MERGE (e:Entity {{name: '{escape_quotes(entity_name)}'}})
                SET e.type = 'TECHNOLOGY', e.source = 'ContentExtraction'
                RETURN e
                """
                r.execute_command("GRAPH.QUERY", "graphiti_migration", query)
                
                # Link document to technology entity
                query = f"""
                MATCH (d:Document {{id: '{page_data['id']}'}})
                MATCH (e:Entity {{name: '{escape_quotes(entity_name)}'}})
                MERGE (d)-[r:MENTIONS]->(e)
                RETURN r
                """
                try:
                    r.execute_command("GRAPH.QUERY", "graphiti_migration", query)
                    total_relationships += 1
                except:
                    pass  # Skip if relationship already exists
    
    # Create relationships between related entities
    print("\nCreating entity relationships...")
    
    # Link entities that appear in the same documents
    query = """
    MATCH (d:Document)-[:HAS_ENTITY|MENTIONS]->(e1:Entity)
    MATCH (d)-[:HAS_ENTITY|MENTIONS]->(e2:Entity)
    WHERE e1.name < e2.name
    MERGE (e1)-[r:RELATED_TO]->(e2)
    SET r.source = 'co-occurrence'
    RETURN COUNT(r) as relationships_created
    """
    result = r.execute_command("GRAPH.QUERY", "graphiti_migration", query)
    
    print("\n" + "=" * 50)
    print("Ingestion Summary:")
    print(f"  Documents ingested: {total_documents}")
    print(f"  Entities created: {total_entities}")
    print(f"  Relationships created: {total_relationships}")
    
    # Show some statistics
    query = "MATCH (n) RETURN labels(n)[0] as label, COUNT(n) as count"
    result = r.execute_command("GRAPH.QUERY", "graphiti_migration", query)
    
    print("\nGraph Statistics:")
    if len(result) > 1:
        for row in result[1]:
            print(f"  {row[0]}: {row[1]} nodes")
    
    query = "MATCH ()-[r]->() RETURN type(r) as type, COUNT(r) as count"
    result = r.execute_command("GRAPH.QUERY", "graphiti_migration", query)
    
    print("\nRelationship Statistics:")
    if len(result) > 1:
        for row in result[1]:
            print(f"  {row[0]}: {row[1]} relationships")
    
    print("\n" + "=" * 50)
    print("Ingestion completed successfully!")
    print("\nView the graph at: http://localhost:3000")
    print("Connect to: localhost:6379 / graphiti_migration")
    print("\nSample queries to try:")
    print("  MATCH (d:Document) RETURN d LIMIT 10")
    print("  MATCH (e:Entity {type: 'TAG'}) RETURN e")
    print("  MATCH (d:Document)-[r]->(e:Entity) RETURN d, r, e LIMIT 50")
    print("  MATCH (e1:Entity)-[:RELATED_TO]-(e2:Entity) RETURN e1, e2")

if __name__ == "__main__":
    ingest_all_bookstack_data()