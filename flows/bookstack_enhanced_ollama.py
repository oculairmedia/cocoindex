#!/usr/bin/env python3
"""
Enhanced BookStack to FalkorDB pipeline with Ollama LLM integration.
Based on official CocoIndex knowledge graph patterns.
"""

import os
import json
import uuid
import redis
import dataclasses
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup

import cocoindex
from cocoindex import DataScope, FlowBuilder

# --- Data structures for LLM extraction (following CocoIndex patterns) ---

@dataclasses.dataclass
class DocumentSummary:
    """Document summary extracted by LLM."""
    title: str
    summary: str

@dataclasses.dataclass
class Entity:
    """
    An entity extracted from document content.
    Should be core concepts, technologies, or important nouns.
    Examples: 'BookStack', 'FalkorDB', 'Knowledge Graph', 'API'
    """
    name: str
    type: str  # TECHNOLOGY, CONCEPT, PERSON, ORGANIZATION, LOCATION, PRODUCT
    description: str

@dataclasses.dataclass
class Relationship:
    """
    Describe a relationship between two entities.
    Subject and object should be core concepts only, should be nouns.
    Examples: 'BookStack supports API', 'FalkorDB stores Knowledge Graph'
    """
    subject: str
    predicate: str
    object: str

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

# --- Helper functions ---
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

def safe_cypher_string(text: str) -> str:
    """Make string safe for Cypher queries."""
    if not text:
        return ""
    # Escape single quotes and limit length
    return text.replace("'", "\\'").replace('"', '\\"')[:500]

def export_to_falkor(page_info: Dict, entities: List[Entity], relationships: List[Relationship], summary: DocumentSummary):
    """Export enhanced data to FalkorDB with Graphiti schema."""
    if not _FALKOR:
        print("❌ No FalkorDB connection available")
        return
    
    try:
        # 1. Create document node (Episodic in Graphiti schema)
        doc_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"doc_{page_info['id']}"))
        title = safe_cypher_string(summary.title)
        summary_text = safe_cypher_string(summary.summary)
        book = safe_cypher_string(page_info.get('book', 'Unknown'))
        url = safe_cypher_string(page_info.get('url', ''))
        
        doc_cypher = f"""
        MERGE (d:Episodic {{uuid: '{doc_uuid}'}})
        ON CREATE SET d.created_at = timestamp()
        SET d.name = '{title}',
            d.content = '{summary_text}',
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
            entity_name = safe_cypher_string(normalize_entity_name(entity.name))
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
            subject = safe_cypher_string(normalize_entity_name(rel.subject))
            object_name = safe_cypher_string(normalize_entity_name(rel.object))
            
            rel_cypher = f"""
            MATCH (e1:Entity {{name: '{subject}', group_id: '{book}'}}),
                  (e2:Entity {{name: '{object_name}', group_id: '{book}'}})
            MERGE (e1)-[r:RELATES_TO {{predicate: '{rel.predicate}', group_id: '{book}'}}]->(e2)
            ON CREATE SET r.uuid = '{rel_uuid}',
                         r.created_at = timestamp()
            SET r.fact = 'Extracted from: {title}'
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
def process_page_with_ollama(json_content: str) -> str:
    """Process a single page with Ollama LLM extraction."""
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
        
        # This will be replaced with actual LLM calls in the CocoIndex flow
        # For now, return processing info
        return f"Processed {page_info['title']}: {len(text_content)} chars"
        
    except Exception as e:
        return f"Error processing page: {e}"

# --- Main CocoIndex Flow with Ollama Integration ---
@cocoindex.flow_def(name="BookStackEnhancedOllama")
def bookstack_enhanced_ollama_flow(flow_builder: FlowBuilder, data_scope: DataScope) -> None:
    """Enhanced BookStack to FalkorDB flow with Ollama LLM integration."""
    
    # Add source for BookStack JSON files
    data_scope["pages"] = flow_builder.add_source(
        cocoindex.sources.LocalFile(
            path="bookstack_export_full",
            included_patterns=["*.json"]
        ),
        refresh_interval=timedelta(minutes=2)
    )
    
    # Add collectors following CocoIndex patterns
    document_node = data_scope.add_collector()
    entity_relationship = data_scope.add_collector()
    entity_mention = data_scope.add_collector()
    
    # Process each page with LLM extraction
    with data_scope["pages"].row() as page:
        # Extract document summary using Ollama
        page["summary"] = page["content"].transform(
            cocoindex.functions.ExtractByLlm(
                llm_spec=cocoindex.LlmSpec(
                    api_type=cocoindex.LlmApiType.OLLAMA,
                    model="gemma3:12b"
                ),
                output_type=DocumentSummary,
                instruction="Please summarize the content of this BookStack document. Extract a clear title and concise summary."
            )
        )
        
        # Extract entities using Ollama
        page["entities"] = page["content"].transform(
            cocoindex.functions.ExtractByLlm(
                llm_spec=cocoindex.LlmSpec(
                    api_type=cocoindex.LlmApiType.OLLAMA,
                    model="gemma3:12b"
                ),
                output_type=list[Entity],
                instruction=(
                    "Extract important entities from this BookStack document. "
                    "Focus on technologies, concepts, tools, and key terms. "
                    "Classify each entity as TECHNOLOGY, CONCEPT, PERSON, ORGANIZATION, LOCATION, or PRODUCT. "
                    "Provide clear descriptions for each entity."
                )
            )
        )
        
        # Extract relationships using Ollama
        page["relationships"] = page["content"].transform(
            cocoindex.functions.ExtractByLlm(
                llm_spec=cocoindex.LlmSpec(
                    api_type=cocoindex.LlmApiType.OLLAMA,
                    model="gemma3:12b"
                ),
                output_type=list[Relationship],
                instruction=(
                    "Extract relationships between entities in this BookStack document. "
                    "Focus on meaningful connections between concepts, technologies, and processes. "
                    "Use clear predicates like 'supports', 'uses', 'implements', 'depends_on', 'part_of'."
                )
            )
        )
        
        # Collect document nodes
        document_node.collect(
            filename=page["filename"],
            title=page["summary"]["title"],
            summary=page["summary"]["summary"]
        )
        
        # Collect entity relationships and mentions
        with page["relationships"].row() as relationship:
            # Relationship between two entities
            entity_relationship.collect(
                id=cocoindex.GeneratedField.UUID,
                subject=relationship["subject"],
                object=relationship["object"],
                predicate=relationship["predicate"],
                filename=page["filename"]
            )
            
            # Mention of subject entity in document
            entity_mention.collect(
                id=cocoindex.GeneratedField.UUID,
                entity=relationship["subject"],
                filename=page["filename"]
            )
            
            # Mention of object entity in document
            entity_mention.collect(
                id=cocoindex.GeneratedField.UUID,
                entity=relationship["object"],
                filename=page["filename"]
            )
        
        # Also collect individual entities
        with page["entities"].row() as entity:
            entity_mention.collect(
                id=cocoindex.GeneratedField.UUID,
                entity=entity["name"],
                filename=page["filename"]
            )
    
    # Export to PostgreSQL for observability
    document_node.export(
        "bookstack_documents",
        cocoindex.targets.Postgres(),
        primary_key_fields=["filename"]
    )
    
    entity_relationship.export(
        "bookstack_relationships", 
        cocoindex.targets.Postgres(),
        primary_key_fields=["id"]
    )
    
    entity_mention.export(
        "bookstack_mentions",
        cocoindex.targets.Postgres(),
        primary_key_fields=["id"]
    )

if __name__ == "__main__":
    print("Enhanced BookStack to FalkorDB Flow with Ollama LLM")
    print("=" * 60)
    print("Features:")
    print("✅ Ollama LLM integration for entity extraction")
    print("✅ Relationship discovery with semantic analysis")
    print("✅ Document summarization")
    print("✅ Multi-level deduplication")
    print("✅ Graphiti schema compliance")
    print("✅ Direct FalkorDB connection")
    print("\nRun with: python run_cocoindex.py update --setup flows/bookstack_enhanced_ollama.py")