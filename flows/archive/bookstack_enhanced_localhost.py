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
    return html_to_text(parsed_json.get("body_html", ""))

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
def generate_entity_uuid_from_obj(entity: Entity) -> str:
    """Generate deterministic UUID for entity from Entity object."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"ent:{entity.name.lower()}"))

@cocoindex.op.function()
def generate_group_id(book_name: str) -> str:
    """Generate group ID from book name."""
    return slugify_name(book_name)

@cocoindex.op.function()
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

@cocoindex.op.function()
def extract_relationships_from_text(text: str) -> List[Relationship]:
    """Extract relationships from text using LLM (simplified for CocoIndex)."""
    try:
        # For now, use fallback extraction since we can't access other page data in transform
        entities = extract_entities_with_llm(text)
        return extract_relationships_fallback(entities)
    except Exception as e:
        print(f"Relationship extraction failed: {e}")
        return []

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

@cocoindex.op.function()
def extract_entities_with_llm(text: str) -> List[Entity]:
    """Extract entities from text using LLM."""
    # Use CocoIndex LLM extraction
    try:
        extractor = cocoindex.functions.ExtractByLlm(
            llm_spec=cocoindex.LlmSpec(
                api_type=cocoindex.LlmApiType.OPENAI,
                model="gpt-4o"
            ),
            output_type=List[Entity],
            instruction="""
            Extract important entities from this BookStack documentation text.
            Focus on:
            - Technologies, tools, and frameworks mentioned
            - Important concepts and methodologies
            - Product names and systems
            - Organizations and people (if relevant)
            
            For each entity, provide:
            - name: The exact name as it appears
            - type: TECHNOLOGY, CONCEPT, ORGANIZATION, PERSON, LOCATION, or TAG
            - description: Brief description of what this entity represents
            
            Exclude common words and focus on domain-specific entities.
            """
        )
        entities = extractor(text)
        return entities if entities else []
    except Exception as e:
        print(f"LLM extraction failed: {e}")
        # Fallback to keyword extraction
        return extract_entities_fallback(text)

def extract_entities_fallback(text: str) -> List[Entity]:
    """Fallback entity extraction using keywords."""
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

@cocoindex.op.function()
def extract_relationships_with_llm(text: str, entities: List[Entity]) -> List[Relationship]:
    """Extract relationships between entities using LLM."""
    if not entities or len(entities) < 2:
        return []
    
    try:
        entity_list = ", ".join([e.name for e in entities])
        extractor = cocoindex.functions.ExtractByLlm(
            llm_spec=cocoindex.LlmSpec(
                api_type=cocoindex.LlmApiType.OPENAI,
                model="gpt-4o"
            ),
            output_type=List[Relationship],
            instruction=f"""
            Extract relationships between these entities from the given text: {entity_list}
            
            For each relationship, provide:
            - subject: The entity that is doing something or has a property
            - predicate: The relationship type (e.g., "uses", "implements", "is_part_of", "requires", "connects_to")
            - object: The entity being acted upon or related to
            - fact: A brief description of evidence from the text supporting this relationship
            
            Focus on meaningful technical relationships. Only extract relationships that are clearly stated or strongly implied in the text.
            """
        )
        relationships = extractor(text)
        return relationships if relationships else []
    except Exception as e:
        print(f"LLM relationship extraction failed: {e}")
        # Fallback to simple relationship extraction
        return extract_relationships_fallback(entities)

def extract_relationships_fallback(entities: List[Entity]) -> List[Relationship]:
    """Fallback relationship extraction."""
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
    """Enhanced BookStack to FalkorDB flow with LLM entity extraction."""
    
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
    relates_edges = data_scope.add_collector()
    
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
        
        # LLM-powered entity extraction from content
        page["llm_entities"] = page["text_content"].transform(extract_entities_with_llm)
        
        # Extract tag-based entities
        page["tag_entities"] = page["tags"].transform(extract_entities_from_tags)
        
        # LLM-powered relationship extraction
        page["relationships"] = page["text_content"].transform(extract_relationships_from_text)
        
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
        
        # Create entity nodes from LLM extraction
        with page["llm_entities"].row() as entity:
            entity_nodes.collect(
                uuid=entity.transform(generate_entity_uuid_from_obj),
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
                target_uuid=entity.transform(generate_entity_uuid_from_obj)
            )
        
        # Create entity nodes from tags
        with page["tag_entities"].row() as entity:
            entity_nodes.collect(
                uuid=entity.transform(generate_entity_uuid_from_obj),
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
                target_uuid=entity.transform(generate_entity_uuid_from_obj)
            )
        
        # Create relationship edges
        with page["relationships"].row() as relationship:
            relates_edges.collect(
                uuid=cocoindex.GeneratedField.UUID,
                name=relationship["predicate"],
                fact=relationship["fact"],
                group_id=page["book"].transform(generate_group_id),
                created_at=cocoindex.GeneratedField.NOW,
                source_entity=relationship["subject"],
                target_entity=relationship["object"]
            )
    
    # Export to FalkorDB using Neo4j targets if available
    if _FALKOR:
        # Create Neo4j connection spec for CocoIndex
        falkor_conn_spec = cocoindex.add_auth_entry(
            "FalkorDBConnection",
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
        
        # Export Entity nodes (with deduplication on name+group_id)
        entity_nodes.export(
            "entity_nodes",
            cocoindex.targets.Neo4j(
                connection=falkor_conn_spec,
                mapping=cocoindex.targets.Nodes(label="Entity")
            ),
            primary_key_fields=["name", "group_id"],
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
        
        # Export RELATES_TO relationships
        relates_edges.export(
            "relates_edges",
            cocoindex.targets.Neo4j(
                connection=falkor_conn_spec,
                mapping=cocoindex.targets.Relationships(
                    rel_type="RELATES_TO",
                    source=cocoindex.targets.NodeFromFields(
                        label="Entity",
                        fields=[cocoindex.targets.TargetFieldMapping("source_entity", "name")]
                    ),
                    target=cocoindex.targets.NodeFromFields(
                        label="Entity", 
                        fields=[cocoindex.targets.TargetFieldMapping("target_entity", "name")]
                    ),
                ),
            ),
            primary_key_fields=["uuid"],
        )
    else:
        # Fallback to PostgreSQL for observability
        episodic_nodes.export(
            "bookstack_episodic_nodes",
            cocoindex.targets.Postgres(),
            primary_key_fields=["uuid"]
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
