#!/usr/bin/env python3
"""
Enhanced BookStack to FalkorDB pipeline for localhost setup.
Combines our advanced features with working localhost FalkorDB connection.
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

# --- Data structures for enhanced extraction ---
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
        print(f"✅ Connected to FalkorDB at {r.connection_pool.connection_kwargs['host']}:{r.connection_pool.connection_kwargs['port']}")
        return r
    except Exception as e:
        print(f"❌ FalkorDB connection failed: {e}")
        return None

# Global connection
_FALKOR = get_falkor_connection()
_GRAPH_NAME = os.environ.get('FALKOR_GRAPH', 'graphiti_migration')

# --- Enhanced helper functions ---
def html_to_text(html_content: str) -> str:
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
    
    return text

def normalize_entity_name(name: str) -> str:
    """Normalize entity names for consistent deduplication."""
    return name.lower().strip()

def extract_entities_from_tags(tags: List[str]) -> List[Entity]:
    """Extract entities from BookStack tags."""
    entities = []
    for tag in tags:
        entities.append(Entity(
            name=normalize_entity_name(tag),
            type="TAG",
            description=f"BookStack tag: {tag}"
        ))
    return entities

def extract_entities_with_llm(text: str) -> List[Entity]:
    """Extract entities from text using LLM (mock for now)."""
    # Mock implementation - replace with real LLM call
    entities = []
    
    # Simple keyword-based extraction for demo
    keywords = {
        'bookstack': ('TECHNOLOGY', 'Knowledge management platform'),
        'falkordb': ('TECHNOLOGY', 'Graph database system'),
        'documentation': ('CONCEPT', 'Written material providing information'),
        'api': ('TECHNOLOGY', 'Application Programming Interface'),
        'database': ('TECHNOLOGY', 'Data storage system'),
        'graph': ('CONCEPT', 'Network of connected data'),
    }
    
    text_lower = text.lower()
    for keyword, (entity_type, description) in keywords.items():
        if keyword in text_lower:
            entities.append(Entity(
                name=normalize_entity_name(keyword),
                type=entity_type,
                description=description
            ))
    
    return entities

def extract_relationships_with_llm(text: str, entities: List[Entity]) -> List[Relationship]:
    """Extract relationships between entities (mock for now)."""
    relationships = []
    entity_names = [e.name for e in entities]
    
    # Simple relationship extraction
    if len(entity_names) >= 2:
        relationships.append(Relationship(
            subject=entity_names[0],
            predicate="relates_to",
            object=entity_names[1],
            fact=f"Both {entity_names[0]} and {entity_names[1]} are mentioned in the same context"
        ))
    
    return relationships

def deduplicate_entities(entities: List[Entity]) -> List[Entity]:
    """Remove duplicate entities, keeping the best description."""
    seen = {}
    for entity in entities:
        key = normalize_entity_name(entity.name)
        if key not in seen:
            seen[key] = entity
        else:
            # Keep entity with longer description
            if len(entity.description) > len(seen[key].description):
                seen[key] = entity
    return list(seen.values())

def deduplicate_relationships(relationships: List[Relationship]) -> List[Relationship]:
    """Remove duplicate relationships."""
    seen = set()
    unique_rels = []
    for rel in relationships:
        key = (normalize_entity_name(rel.subject), rel.predicate, normalize_entity_name(rel.object))
        if key not in seen:
            seen.add(key)
            unique_rels.append(rel)
    return unique_rels

def safe_cypher_string(text: str) -> str:
    """Make string safe for Cypher queries."""
    if not text:
        return ""
    # Escape single quotes and limit length
    return text.replace("'", "\\'").replace('"', '\\"')[:500]

def export_to_falkor(page_info: Dict, text_content: str, entities: List[Entity], relationships: List[Relationship]):
    """Export enhanced data to FalkorDB with proper deduplication."""
    if not _FALKOR:
        print("❌ No FalkorDB connection available")
        return
    
    try:
        # 1. Create document node (Episodic in Graphiti schema)
        doc_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"doc_{page_info['id']}"))
        title = safe_cypher_string(page_info.get('title', 'Untitled'))
        content = safe_cypher_string(text_content)
        book = safe_cypher_string(page_info.get('book', 'Unknown'))
        url = safe_cypher_string(page_info.get('url', ''))
        
        doc_cypher = f"""
        MERGE (d:Episodic {{uuid: '{doc_uuid}'}})
        ON CREATE SET d.created_at = timestamp()
        SET d.name = '{title}',
            d.content = '{content}',
            d.group_id = '{book}',
            d.source = 'text',
            d.source_description = '{url}',
            d.valid_at = timestamp()
        RETURN d.uuid
        """
        
        result = _FALKOR.execute_command('GRAPH.QUERY', _GRAPH_NAME, doc_cypher)
        print(f"📄 Created document: {title[:50]}...")
        
        # 2. Create entities with deduplication
        for entity in entities:
            entity_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"entity_{entity.name}_{book}"))
            entity_name = safe_cypher_string(entity.name)
            entity_desc = safe_cypher_string(entity.description)
            
            entity_cypher = f"""
            MERGE (e:Entity {{name: '{entity_name}', group_id: '{book}'}})
            ON CREATE SET e.uuid = '{entity_uuid}',
                         e.created_at = timestamp(),
                         e.labels = ['Entity']
            SET e.entity_type = '{entity.type}',
                e.description = '{entity_desc}'
            RETURN e.uuid
            """
            
            _FALKOR.execute_command('GRAPH.QUERY', _GRAPH_NAME, entity_cypher)
            
            # 3. Create mention relationship
            mention_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"mention_{doc_uuid}_{entity_name}"))
            mention_cypher = f"""
            MATCH (d:Episodic {{uuid: '{doc_uuid}'}}),
                  (e:Entity {{name: '{entity_name}', group_id: '{book}'}})
            MERGE (d)-[r:MENTIONS {{group_id: '{book}'}}]->(e)
            ON CREATE SET r.uuid = '{mention_uuid}',
                         r.created_at = timestamp()
            """
            
            _FALKOR.execute_command('GRAPH.QUERY', _GRAPH_NAME, mention_cypher)
        
        # 4. Create relationships between entities
        for rel in relationships:
            rel_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"rel_{rel.subject}_{rel.predicate}_{rel.object}_{book}"))
            subject = safe_cypher_string(rel.subject)
            object_name = safe_cypher_string(rel.object)
            fact = safe_cypher_string(rel.fact)
            
            rel_cypher = f"""
            MATCH (e1:Entity {{name: '{subject}', group_id: '{book}'}}),
                  (e2:Entity {{name: '{object_name}', group_id: '{book}'}})
            MERGE (e1)-[r:RELATES_TO {{predicate: '{rel.predicate}', group_id: '{book}'}}]->(e2)
            ON CREATE SET r.uuid = '{rel_uuid}',
                         r.created_at = timestamp()
            SET r.fact = '{fact}'
            """
            
            _FALKOR.execute_command('GRAPH.QUERY', _GRAPH_NAME, rel_cypher)
        
        print(f"✅ Exported {len(entities)} entities, {len(relationships)} relationships")
        
    except Exception as e:
        print(f"❌ Error exporting to FalkorDB: {e}")

# --- CocoIndex helper functions ---
@cocoindex.op.function()
def extract_html_content(parsed_json: dict) -> str:
    """Extract and convert HTML content to text from parsed JSON."""
    return html_to_text(parsed_json.get("body_html", ""))

@cocoindex.op.function()
def process_page_enhanced(json_content: str) -> str:
    """Process a single page with enhanced extraction."""
    try:
        # Parse JSON
        if isinstance(json_content, str):
            page_data = json.loads(json_content)
        else:
            page_data = json_content
        
        # Extract page info
        page_info = {
            "id": page_data.get("id", 0),
            "title": page_data.get("title", "Untitled"),
            "url": page_data.get("url", ""),
            "book": page_data.get("book", "Unknown"),
            "tags": page_data.get("tags", [])
        }
        
        # Convert HTML to text
        text_content = html_to_text(page_data.get("body_html", ""))
        
        # Extract entities from tags and content
        tag_entities = extract_entities_from_tags(page_info["tags"])
        content_entities = extract_entities_with_llm(text_content)
        all_entities = deduplicate_entities(tag_entities + content_entities)
        
        # Extract relationships
        relationships = extract_relationships_with_llm(text_content, all_entities)
        relationships = deduplicate_relationships(relationships)
        
        # Export to FalkorDB
        export_to_falkor(page_info, text_content, all_entities, relationships)
        
        return f"Processed {page_info['title']}: {len(all_entities)} entities, {len(relationships)} relationships"
        
    except Exception as e:
        return f"Error processing page: {e}"

# --- Main CocoIndex Flow ---
@cocoindex.flow_def(name="BookStackEnhancedLocalhost")
def bookstack_enhanced_flow(flow_builder: FlowBuilder, data_scope: DataScope) -> None:
    """Enhanced BookStack to FalkorDB flow for localhost setup."""
    
    # Add source for BookStack JSON files
    data_scope["pages"] = flow_builder.add_source(
        cocoindex.sources.LocalFile(
            path="bookstack_export_full",
            included_patterns=["*.json"]
        ),
        refresh_interval=timedelta(minutes=2)
    )
    
    # Add collector for processing results
    processed_pages = data_scope.add_collector()
    
    # Process each page
    with data_scope["pages"].row() as page:
        # Process the page with enhanced extraction
        result = page["content"].transform(process_page_enhanced)
        
        # Collect processing results
        processed_pages.collect(
            filename=page["filename"],
            result=result
        )
    
    # Export processing statistics to PostgreSQL for observability
    processed_pages.export(
        "bookstack_enhanced_processing",
        cocoindex.targets.Postgres(),
        primary_key_fields=["filename"]
    )

if __name__ == "__main__":
    print("Enhanced BookStack to FalkorDB Flow (Localhost)")
    print("=" * 50)
    print("Features:")
    print("✅ Enhanced entity extraction (tags + content)")
    print("✅ Relationship discovery")
    print("✅ Multi-level deduplication")
    print("✅ Graphiti schema compliance")
    print("✅ Direct FalkorDB connection")
    print("\nRun with: python run_cocoindex.py update --setup flows/bookstack_enhanced_localhost.py")
