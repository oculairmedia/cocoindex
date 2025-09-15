#!/usr/bin/env python3
"""
Enhanced BookStack to FalkorDB pipeline - simplified version for testing.
Uses basic extraction with CocoIndex patterns.
"""

import os
import json
import uuid
import redis
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup

import cocoindex
from cocoindex import DataScope, FlowBuilder

# --- Data structures ---
@dataclass
class Entity:
    """An entity extracted from content."""
    name: str
    type: str  # PERSON, ORGANIZATION, CONCEPT, TECHNOLOGY, LOCATION, TAG
    description: str

@dataclass
class Relationship:
    """A relationship between two entities."""
    subject: str
    predicate: str
    object: str
    fact: str  # Supporting evidence/context

# --- FalkorDB Connection Setup ---
def get_falkor_connection():
    """Get FalkorDB connection for localhost."""
    try:
        r = redis.Redis(
            host=os.environ.get('FALKOR_HOST', 'localhost'),
            port=int(os.environ.get('FALKOR_PORT', '6379')),
            decode_responses=True
        )
        r.ping()
        print(f"Connected to FalkorDB at {r.connection_pool.connection_kwargs['host']}:{r.connection_pool.connection_kwargs['port']}")
        return r
    except Exception as e:
        print(f"FalkorDB connection failed: {e}")
        return None

# Global connection
_FALKOR = get_falkor_connection()
_GRAPH_NAME = os.environ.get('FALKOR_GRAPH', 'graphiti_migration')

# --- CocoIndex helper functions ---
@cocoindex.op.function()
def extract_text_from_json(parsed_json: dict) -> str:
    """Extract and convert HTML content to text from parsed JSON."""
    html_content = parsed_json.get("body_html", "")
    soup = BeautifulSoup(html_content, "html.parser")
    
    # Remove script and style elements
    for script in soup(["script", "style"]):
        script.decompose()
    
    text = soup.get_text(separator="\n", strip=True)
    
    # Clean up whitespace
    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    text = "\n".join(chunk for chunk in chunks if chunk)
    
    return text[:1000]  # Limit for processing

@cocoindex.op.function()
def extract_title_from_json(parsed_json: dict) -> str:
    """Extract title from parsed JSON."""
    return parsed_json.get("title", "Untitled")

@cocoindex.op.function()
def extract_book_from_json(parsed_json: dict) -> str:
    """Extract book name from parsed JSON."""
    return parsed_json.get("book", "Unknown")

@cocoindex.op.function()
def extract_tags_from_json(parsed_json: dict) -> List[str]:
    """Extract tags from parsed JSON."""
    return parsed_json.get("tags", [])

@cocoindex.op.function()
def generate_episodic_uuid(filename: str) -> str:
    """Generate deterministic UUID for episodic node."""
    page_id = filename.replace("page_", "").replace(".json", "")
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"doc:{page_id}"))

@cocoindex.op.function()
def generate_group_id(book_name: str) -> str:
    """Generate group ID from book name."""
    # Simple slugify
    return book_name.lower().replace(" ", "-").replace("_", "-")

@cocoindex.op.function()
def extract_basic_entities(text: str) -> List[dict]:
    """Extract entities using simple keyword matching."""
    entities = []
    
    keywords = {
        'docker': ('TECHNOLOGY', 'Containerization platform'),
        'kubernetes': ('TECHNOLOGY', 'Container orchestration'),
        'python': ('TECHNOLOGY', 'Programming language'),
        'api': ('CONCEPT', 'Application Programming Interface'),
        'database': ('CONCEPT', 'Data storage system'),
        'redis': ('TECHNOLOGY', 'In-memory data store'),
        'postgresql': ('TECHNOLOGY', 'Relational database'),
        'falkor': ('TECHNOLOGY', 'Graph database'),
        'graphiti': ('TECHNOLOGY', 'Knowledge graph framework'),
        'bookstack': ('TECHNOLOGY', 'Documentation platform'),
    }
    
    text_lower = text.lower()
    for keyword, (entity_type, description) in keywords.items():
        if keyword in text_lower:
            entities.append({
                'name': keyword.title(),
                'type': entity_type,
                'description': description,
                'uuid': str(uuid.uuid5(uuid.NAMESPACE_DNS, f"ent:{keyword}"))
            })
    
    return entities

@cocoindex.op.function()
def extract_tag_entities(tags: List[str]) -> List[dict]:
    """Extract entities from BookStack tags."""
    entities = []
    for tag in tags:
        entities.append({
            'name': tag,
            'type': "TAG",
            'description': f"BookStack tag: {tag}",
            'uuid': str(uuid.uuid5(uuid.NAMESPACE_DNS, f"tag:{tag}"))
        })
    return entities

# --- Main CocoIndex Flow ---
@cocoindex.flow_def(name="BookStackEnhancedSimple")
def bookstack_enhanced_simple_flow(flow_builder: FlowBuilder, data_scope: DataScope) -> None:
    """Enhanced BookStack to FalkorDB flow - simplified version."""
    
    # Add source for BookStack JSON files
    data_scope["pages"] = flow_builder.add_source(
        cocoindex.sources.LocalFile(
            path="bookstack_export_full",
            included_patterns=["*.json"]
        ),
        refresh_interval=timedelta(minutes=2)
    )
    
    # Add collectors for entities and relationships
    episodic_nodes = data_scope.add_collector()
    entity_nodes = data_scope.add_collector()
    mentions_edges = data_scope.add_collector()
    
    # Process each page
    with data_scope["pages"].row() as page:
        # Parse JSON content
        page["parsed"] = page["content"].transform(cocoindex.functions.ParseJson())
        
        # Extract text content from HTML
        page["text_content"] = page["parsed"].transform(extract_text_from_json)
        
        # Extract page metadata
        page["title"] = page["parsed"].transform(extract_title_from_json)
        page["book"] = page["parsed"].transform(extract_book_from_json)
        page["tags"] = page["parsed"].transform(extract_tags_from_json)
        
        # Extract entities from content
        page["content_entities"] = page["text_content"].transform(extract_basic_entities)
        
        # Extract tag-based entities
        page["tag_entities"] = page["tags"].transform(extract_tag_entities)
        
        # Create episodic node for the document
        episodic_nodes.collect(
            uuid=page["filename"].transform(generate_episodic_uuid),
            name=page["title"],
            content=page["text_content"],
            source="BookStack",
            source_description=page["book"],
            valid_at=cocoindex.GeneratedField.NOW,
            group_id=page["book"].transform(generate_group_id),
            created_at=cocoindex.GeneratedField.NOW
        )
        
        # Create entity nodes from content entities
        with page["content_entities"].row() as entity:
            entity_nodes.collect(
                uuid=entity["uuid"],
                name=entity["name"],
                labels=[entity["type"]],
                summary=entity["description"],
                group_id=page["book"].transform(generate_group_id),
                created_at=cocoindex.GeneratedField.NOW
            )
            
            # Create mention relationships
            mentions_edges.collect(
                uuid=cocoindex.GeneratedField.UUID,
                group_id=page["book"].transform(generate_group_id),
                created_at=cocoindex.GeneratedField.NOW,
                source_uuid=page["filename"].transform(generate_episodic_uuid),
                target_uuid=entity["uuid"]
            )
        
        # Create entity nodes from tags
        with page["tag_entities"].row() as entity:
            entity_nodes.collect(
                uuid=entity["uuid"],
                name=entity["name"],
                labels=[entity["type"]],
                summary=entity["description"],
                group_id=page["book"].transform(generate_group_id),
                created_at=cocoindex.GeneratedField.NOW
            )
            
            # Create mention relationships
            mentions_edges.collect(
                uuid=cocoindex.GeneratedField.UUID,
                group_id=page["book"].transform(generate_group_id),
                created_at=cocoindex.GeneratedField.NOW,
                source_uuid=page["filename"].transform(generate_episodic_uuid),
                target_uuid=entity["uuid"]
            )
    
    # Export to FalkorDB using Neo4j targets if available
    if _FALKOR:
        # Create Neo4j connection spec for CocoIndex
        falkor_conn_spec = cocoindex.add_auth_entry(
            "FalkorDBConnectionSimple",
            cocoindex.targets.Neo4jConnection(
                uri=f"bolt://localhost:6379",
                user="",
                password="",
            ),
        )
        
        # Export Episodic nodes
        episodic_nodes.export(
            "episodic_nodes",
            cocoindex.targets.Neo4j(
                connection=falkor_conn_spec,
                mapping=cocoindex.targets.Nodes(label="Episodic")
            ),
            primary_key_fields=["uuid"],
        )
        
        # Export Entity nodes (with deduplication on uuid)
        entity_nodes.export(
            "entity_nodes",
            cocoindex.targets.Neo4j(
                connection=falkor_conn_spec,
                mapping=cocoindex.targets.Nodes(label="Entity")
            ),
            primary_key_fields=["uuid"],
        )
        
        # Export MENTIONS relationships
        mentions_edges.export(
            "mentions_edges",
            cocoindex.targets.Neo4j(
                connection=falkor_conn_spec,
                mapping=cocoindex.targets.Relationships(
                    rel_type="MENTIONS",
                    source=cocoindex.targets.NodeFromFields(
                        label="Episodic",
                        fields=[cocoindex.targets.TargetFieldMapping("source_uuid", "uuid")]
                    ),
                    target=cocoindex.targets.NodeFromFields(
                        label="Entity",
                        fields=[cocoindex.targets.TargetFieldMapping("target_uuid", "uuid")]
                    ),
                ),
            ),
            primary_key_fields=["uuid"],
        )
    else:
        # Fallback to PostgreSQL for observability
        episodic_nodes.export(
            "bookstack_episodic_nodes_simple",
            cocoindex.targets.Postgres(),
            primary_key_fields=["uuid"]
        )

if __name__ == "__main__":
    print("Enhanced BookStack to FalkorDB Flow (Simple)")
    print("=" * 50)
    print("Features:")
    print("- Basic entity extraction (keyword matching)")
    print("- Tag extraction from BookStack")
    print("- Graphiti schema compliance")
    print("- Direct FalkorDB connection")
    print("\nRun with: python run_cocoindex.py update --setup flows/bookstack_enhanced_simple.py")