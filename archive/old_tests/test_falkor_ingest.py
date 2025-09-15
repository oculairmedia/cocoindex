#!/usr/bin/env python3
"""
Test actual data ingestion into FalkorDB
"""

import os
import redis
import json

# Set up environment
os.environ["FALKOR_HOST"] = "localhost"
os.environ["FALKOR_PORT"] = "6379"
os.environ["FALKOR_GRAPH"] = "graphiti_migration"

def ingest_bookstack_data():
    """Ingest BookStack data into FalkorDB."""
    print("Testing BookStack Data Ingestion into FalkorDB")
    print("=" * 50)
    
    # Connect to FalkorDB
    r = redis.Redis(host='localhost', port=6379, decode_responses=True)
    
    # Test connection
    print("Testing connection...")
    r.ping()
    print("Connected successfully!")
    
    # Read sample BookStack data
    with open('bookstack_export/page_1.json', 'r') as f:
        page_data = json.load(f)
    
    print(f"\nIngesting page: {page_data['title']}")
    
    # Create entities from tags
    entities_created = 0
    for tag in page_data.get('tags', []):
        entity_name = tag.replace('-', ' ').title()
        query = f"""
        MERGE (e:Entity {{name: '{entity_name}'}})
        SET e.type = 'TAG', e.source = 'BookStack'
        RETURN e
        """
        result = r.execute_command("GRAPH.QUERY", "graphiti_migration", query)
        entities_created += 1
        print(f"  Created entity: {entity_name}")
    
    # Create document node
    query = f"""
    MERGE (d:Document {{id: '{page_data['id']}'}})
    SET d.title = '{page_data['title']}', d.url = '{page_data.get('url', '')}', d.book = '{page_data.get('book', 'Unknown')}'
    RETURN d
    """
    result = r.execute_command("GRAPH.QUERY", "graphiti_migration", query)
    print(f"  Created document: {page_data['title']}")
    
    # Link document to entities
    relationships_created = 0
    for tag in page_data.get('tags', []):
        entity_name = tag.replace('-', ' ').title()
        query = f"""
        MATCH (d:Document {{id: '{page_data['id']}'}})
        MATCH (e:Entity {{name: '{entity_name}'}})
        MERGE (d)-[r:HAS_ENTITY]->(e)
        RETURN r
        """
        result = r.execute_command("GRAPH.QUERY", "graphiti_migration", query)
        relationships_created += 1
    
    print(f"\nIngestion Summary:")
    print(f"  Entities created: {entities_created}")
    print(f"  Relationships created: {relationships_created}")
    
    # Query to verify
    print("\nVerifying data in graph...")
    query = "MATCH (d:Document)-[r:HAS_ENTITY]->(e:Entity) RETURN d.title, e.name"
    result = r.execute_command("GRAPH.QUERY", "graphiti_migration", query)
    
    if len(result) > 1 and len(result[1]) > 0:
        print("  Found relationships:")
        for row in result[1]:
            print(f"    {row[0]} -> {row[1]}")
    
    print("\nIngestion completed successfully!")
    print("\nView the graph at: http://localhost:3000")
    print("Connect to: localhost:6379 / graphiti_migration")

if __name__ == "__main__":
    ingest_bookstack_data()