#!/usr/bin/env python3
"""
Custom FalkorDB export functions for CocoIndex pipeline.
Handles the Redis protocol properly for FalkorDB integration.
"""

import os
import uuid
import redis
import json
from typing import Dict, List, Any
from datetime import datetime

def get_falkor_connection():
    """Get FalkorDB connection using Redis protocol."""
    try:
        r = redis.Redis(
            host=os.environ.get('FALKOR_HOST', 'localhost'),
            port=int(os.environ.get('FALKOR_PORT', '6379')),
            decode_responses=True
        )
        r.ping()
        print(f"✅ Connected to FalkorDB at {r.connection_pool.connection_kwargs['host']}:{r.connection_pool.connection_kwargs['port']}")
        return r
    except Exception as e:
        print(f"❌ FalkorDB connection failed: {e}")
        return None

def safe_cypher_string(text: str) -> str:
    """Make string safe for Cypher queries."""
    if not text:
        return ""
    # Escape quotes and limit length
    return text.replace("'", "\\'").replace('"', '\\"')[:500]

def export_documents_to_falkor(documents: List[Dict[str, Any]], graph_name: str = "graphiti_migration"):
    """Export documents as Episodic nodes to FalkorDB."""
    falkor = get_falkor_connection()
    if not falkor:
        return False
    
    success_count = 0
    error_count = 0
    
    for doc in documents:
        try:
            # Generate deterministic UUID
            doc_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"doc:{doc['page_id']}"))
            
            # Prepare safe strings
            title = safe_cypher_string(doc.get('title', 'Untitled'))
            summary = safe_cypher_string(doc.get('summary', ''))
            group_id = safe_cypher_string(doc.get('group_id', 'unknown'))
            url = safe_cypher_string(doc.get('url', ''))
            
            # Create Episodic node with Graphiti schema
            cypher = f"""
            MERGE (d:Episodic {{uuid: '{doc_uuid}'}})
            ON CREATE SET d.created_at = timestamp()
            SET d.name = '{title}',
                d.content = '{summary}',
                d.group_id = '{group_id}',
                d.source = 'BookStack',
                d.source_description = '{url}',
                d.valid_at = timestamp()
            RETURN d.uuid
            """
            
            result = falkor.execute_command('GRAPH.QUERY', graph_name, cypher)
            success_count += 1
            
        except Exception as e:
            print(f"❌ Error exporting document {doc.get('filename', 'unknown')}: {e}")
            error_count += 1
    
    print(f"📄 Exported {success_count} documents, {error_count} errors")
    return success_count > 0

def export_entities_to_falkor(entities: List[Dict[str, Any]], graph_name: str = "graphiti_migration"):
    """Export entities as Entity nodes to FalkorDB."""
    falkor = get_falkor_connection()
    if not falkor:
        return False
    
    success_count = 0
    error_count = 0
    
    for entity in entities:
        try:
            # Generate deterministic UUID
            entity_name = entity.get('name', '').lower().strip()
            group_id = entity.get('group_id', 'unknown')
            entity_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"entity:{entity_name}:{group_id}"))
            
            # Prepare safe strings
            name = safe_cypher_string(entity_name)
            description = safe_cypher_string(entity.get('description', ''))
            entity_type = safe_cypher_string(entity.get('type', 'UNKNOWN'))
            group_id_safe = safe_cypher_string(group_id)
            
            # Create Entity node with Graphiti schema
            cypher = f"""
            MERGE (e:Entity {{name: '{name}', group_id: '{group_id_safe}'}})
            ON CREATE SET e.uuid = '{entity_uuid}',
                         e.created_at = timestamp(),
                         e.labels = ['Entity']
            SET e.entity_type = '{entity_type}',
                e.summary = '{description}'
            RETURN e.uuid
            """
            
            result = falkor.execute_command('GRAPH.QUERY', graph_name, cypher)
            success_count += 1
            
        except Exception as e:
            print(f"❌ Error exporting entity {entity.get('name', 'unknown')}: {e}")
            error_count += 1
    
    print(f"🏷️  Exported {success_count} entities, {error_count} errors")
    return success_count > 0

def export_mentions_to_falkor(mentions: List[Dict[str, Any]], graph_name: str = "graphiti_migration"):
    """Export mentions as MENTIONS relationships to FalkorDB."""
    falkor = get_falkor_connection()
    if not falkor:
        return False
    
    success_count = 0
    error_count = 0
    
    for mention in mentions:
        try:
            # Generate UUIDs
            doc_filename = mention.get('document_filename', '')
            page_id = doc_filename.replace('.json', '').split('_')[-1] if '_' in doc_filename else '0'
            doc_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"doc:{page_id}"))
            
            entity_name = mention.get('entity_name', '').lower().strip()
            group_id = mention.get('group_id', 'unknown')
            mention_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"mention:{doc_uuid}:{entity_name}"))
            
            # Prepare safe strings
            name_safe = safe_cypher_string(entity_name)
            group_id_safe = safe_cypher_string(group_id)
            
            # Create MENTIONS relationship
            cypher = f"""
            MATCH (d:Episodic {{uuid: '{doc_uuid}'}}),
                  (e:Entity {{name: '{name_safe}', group_id: '{group_id_safe}'}})
            MERGE (d)-[r:MENTIONS {{group_id: '{group_id_safe}'}}]->(e)
            ON CREATE SET r.uuid = '{mention_uuid}',
                         r.created_at = timestamp()
            RETURN r.uuid
            """
            
            result = falkor.execute_command('GRAPH.QUERY', graph_name, cypher)
            success_count += 1
            
        except Exception as e:
            print(f"❌ Error exporting mention: {e}")
            error_count += 1
    
    print(f"🔗 Exported {success_count} mentions, {error_count} errors")
    return success_count > 0

def export_relationships_to_falkor(relationships: List[Dict[str, Any]], graph_name: str = "graphiti_migration"):
    """Export relationships as RELATES_TO edges to FalkorDB."""
    falkor = get_falkor_connection()
    if not falkor:
        return False
    
    success_count = 0
    error_count = 0
    
    for rel in relationships:
        try:
            # Prepare entity names
            subject = rel.get('subject', '').lower().strip()
            object_name = rel.get('object', '').lower().strip()
            predicate = rel.get('predicate', 'relates_to')
            fact = rel.get('fact', '')
            group_id = rel.get('group_id', 'unknown')
            
            # Generate relationship UUID
            rel_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"rel:{subject}:{predicate}:{object_name}:{group_id}"))
            
            # Prepare safe strings
            subject_safe = safe_cypher_string(subject)
            object_safe = safe_cypher_string(object_name)
            predicate_safe = safe_cypher_string(predicate)
            fact_safe = safe_cypher_string(fact)
            group_id_safe = safe_cypher_string(group_id)
            
            # Create RELATES_TO relationship
            cypher = f"""
            MATCH (e1:Entity {{name: '{subject_safe}', group_id: '{group_id_safe}'}}),
                  (e2:Entity {{name: '{object_safe}', group_id: '{group_id_safe}'}})
            MERGE (e1)-[r:RELATES_TO {{predicate: '{predicate_safe}', group_id: '{group_id_safe}'}}]->(e2)
            ON CREATE SET r.uuid = '{rel_uuid}',
                         r.created_at = timestamp()
            SET r.fact = '{fact_safe}',
                r.name = '{predicate_safe}'
            RETURN r.uuid
            """
            
            result = falkor.execute_command('GRAPH.QUERY', graph_name, cypher)
            success_count += 1
            
        except Exception as e:
            print(f"❌ Error exporting relationship: {e}")
            error_count += 1
    
    print(f"🔄 Exported {success_count} relationships, {error_count} errors")
    return success_count > 0

def test_falkor_connection():
    """Test FalkorDB connection and basic operations."""
    falkor = get_falkor_connection()
    if not falkor:
        return False
    
    try:
        # Test basic query
        graph_name = os.environ.get('FALKOR_GRAPH', 'graphiti_migration')
        result = falkor.execute_command('GRAPH.QUERY', graph_name, 'MATCH (n) RETURN count(n) as node_count')
        print(f"✅ FalkorDB test successful. Current node count: {result}")
        return True
    except Exception as e:
        print(f"❌ FalkorDB test failed: {e}")
        return False

if __name__ == "__main__":
    print("FalkorDB Export Functions Test")
    print("=" * 40)
    test_falkor_connection()
