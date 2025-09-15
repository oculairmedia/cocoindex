#!/usr/bin/env python3
"""
Test script to validate Ollama-enhanced extraction results in FalkorDB.
"""

import os
import redis

# Connect to FalkorDB
r = redis.Redis(
    host=os.environ.get('FALKOR_HOST', 'localhost'),
    port=int(os.environ.get('FALKOR_PORT', '6379')),
    decode_responses=True
)

graph_name = os.environ.get('FALKOR_GRAPH', 'graphiti_migration')

print("Validating Ollama-enhanced extraction results")
print("=" * 50)

# Count Episodic nodes
episodic_query = "MATCH (d:Episodic) RETURN count(d) as count"
result = r.execute_command('GRAPH.QUERY', graph_name, episodic_query, '--read-only')
episodic_count = result[1][0][0] if result[1] else 0
print(f"Episodic nodes: {episodic_count}")

# Count Entity nodes
entity_query = "MATCH (e:Entity) RETURN count(e) as count"
result = r.execute_command('GRAPH.QUERY', graph_name, entity_query, '--read-only')
entity_count = result[1][0][0] if result[1] else 0
print(f"Entity nodes: {entity_count}")

# Count MENTIONS relationships
mentions_query = "MATCH ()-[m:MENTIONS]->() RETURN count(m) as count"
result = r.execute_command('GRAPH.QUERY', graph_name, mentions_query, '--read-only')
mentions_count = result[1][0][0] if result[1] else 0
print(f"MENTIONS relationships: {mentions_count}")

# Sample some entities by type
print("\nEntity types:")
type_query = """
MATCH (e:Entity)
WITH e.labels[0] as type, count(e) as count
RETURN type, count
ORDER BY count DESC
LIMIT 10
"""
result = r.execute_command('GRAPH.QUERY', graph_name, type_query, '--read-only')
if result[1]:
    for row in result[1]:
        print(f"  {row[0]}: {row[1]}")

# Sample some recent documents
print("\nRecent documents:")
recent_query = """
MATCH (d:Episodic)
RETURN d.name, d.group_id, d.source_description
ORDER BY d.created_at DESC
LIMIT 5
"""
result = r.execute_command('GRAPH.QUERY', graph_name, recent_query, '--read-only')
if result[1]:
    for row in result[1]:
        print(f"  {row[0]} (Book: {row[2]}, Group: {row[1]})")

# Check entities per document
print("\nEntities per document (sample):")
entity_doc_query = """
MATCH (d:Episodic)-[m:MENTIONS]->(e:Entity)
WITH d.name as doc, count(e) as entity_count
RETURN doc, entity_count
ORDER BY entity_count DESC
LIMIT 5
"""
result = r.execute_command('GRAPH.QUERY', graph_name, entity_doc_query, '--read-only')
if result[1]:
    for row in result[1]:
        print(f"  {row[0]}: {row[1]} entities")

print("\nValidation complete!")