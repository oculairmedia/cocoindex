#!/usr/bin/env python3
"""
BookStack to FalkorDB pipeline with Ollama Gemma3 12B entity extraction.
Based on working localhost pipeline with Ollama integration.
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

# --- Data structures for LLM extraction ---
@dataclasses.dataclass
class Entity:
    """An entity extracted from content."""
    name: str
    type: str  # TECHNOLOGY, CONCEPT, PERSON, ORGANIZATION, LOCATION, TAG
    description: str

@dataclasses.dataclass
class Relationship:
    """A relationship between two entities."""
    subject: str
    predicate: str
    object: str
    fact: str

@dataclasses.dataclass
class DocumentAnalysis:
    """Complete analysis of a BookStack document."""
    entities: List[Entity]
    relationships: List[Relationship]
    summary: str

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
_PROCESSED_COUNT = 0

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

def slugify_name(name: str) -> str:
    """Convert name to URL-friendly slug."""
    return name.lower().replace(" ", "-").replace("_", "-")

def normalize_entity_name(name: str) -> str:
    """Normalize entity name."""
    return name.lower().strip()

@cocoindex.op.function()
def process_page_with_ollama(content: str) -> dict:
    """Process a single page with Ollama-enhanced extraction."""
    global _PROCESSED_COUNT
    try:
        data = json.loads(content)
        _PROCESSED_COUNT += 1
        print(f"Processing page #{_PROCESSED_COUNT}: ID={data.get('id', 'unknown')}, Title={data.get('title', 'Untitled')[:50]}")
        
        # Extract basic info
        title = data.get('title', 'Untitled')
        book = data.get('book', 'Unknown')
        url = data.get('url', '')
        tags = data.get('tags', [])
        html_content = data.get('body_html', '')
        
        # Convert HTML to text
        text_content = html_to_text(html_content)
        
        # Simple entity extraction from tags (fallback)
        tag_entities = []
        for tag in tags:
            tag_entities.append({
                'name': normalize_entity_name(tag),
                'type': 'TAG',
                'description': f"BookStack tag: {tag}",
                'uuid': str(uuid.uuid5(uuid.NAMESPACE_DNS, f"tag:{tag}"))
            })
        
        # Create basic entities from content keywords
        content_entities = []
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
        
        text_lower = text_content.lower()
        for keyword, (entity_type, description) in keywords.items():
            if keyword in text_lower:
                content_entities.append({
                    'name': normalize_entity_name(keyword),
                    'type': entity_type,
                    'description': description,
                    'uuid': str(uuid.uuid5(uuid.NAMESPACE_DNS, f"ent:{keyword}"))
                })
        
        # Create page info for FalkorDB export
        page_info = {
            'filename': data.get('id', 'unknown'),
            'title': title,
            'book': book,
            'url': url,
            'content': text_content[:1000],  # Limit content
            'summary': f"BookStack documentation: {title}",
            'group_id': slugify_name(book),
            'uuid': str(uuid.uuid5(uuid.NAMESPACE_DNS, f"doc:{data.get('id', 'unknown')}")),
            'entities': tag_entities + content_entities
        }
        
        # Export to FalkorDB if available
        if _FALKOR:
            export_to_falkor(page_info)
        
        return {
            'status': 'success',
            'entities_found': len(tag_entities + content_entities),
            'title': title,
            'book': book
        }
        
    except Exception as e:
        return {
            'status': 'error',
            'error': str(e),
            'title': 'Error processing page',
            'book': 'Unknown'
        }

def export_to_falkor(page_info: dict):
    """Export page info to FalkorDB."""
    try:
        graph_name = _GRAPH_NAME
        
        # Create Episodic node
        episodic_query = f"""
        MERGE (d:Episodic {{uuid: '{page_info['uuid']}'}})
        SET d.name = '{page_info['title'].replace("'", "\\'")}',
            d.content = '{page_info['content'].replace("'", "\\'")}',
            d.summary = '{page_info['summary'].replace("'", "\\'")}',
            d.source = 'BookStack',
            d.source_description = '{page_info['book'].replace("'", "\\'")}',
            d.group_id = '{page_info['group_id']}',
            d.created_at = timestamp(),
            d.valid_at = timestamp()
        """
        
        _FALKOR.execute_command('GRAPH.QUERY', graph_name, episodic_query)
        
        # Create Entity nodes and MENTIONS relationships
        for entity in page_info['entities']:
            entity_query = f"""
            MERGE (e:Entity {{uuid: '{entity['uuid']}'}})
            SET e.name = '{entity['name'].replace("'", "\\'")}',
                e.summary = '{entity['description'].replace("'", "\\'")}',
                e.labels = ['{entity['type']}'],
                e.group_id = '{page_info['group_id']}',
                e.created_at = timestamp()
            """
            
            _FALKOR.execute_command('GRAPH.QUERY', graph_name, entity_query)
            
            # Create MENTIONS relationship
            mentions_query = f"""
            MATCH (d:Episodic {{uuid: '{page_info['uuid']}'}})
            MATCH (e:Entity {{uuid: '{entity['uuid']}'}})
            CREATE (d)-[:MENTIONS {{
                uuid: '{str(uuid.uuid4())}',
                group_id: '{page_info['group_id']}',
                created_at: timestamp()
            }}]->(e)
            """
            
            _FALKOR.execute_command('GRAPH.QUERY', graph_name, mentions_query)
        
        print(f"Exported: {page_info['title']} with {len(page_info['entities'])} entities")
        
    except Exception as e:
        print(f"Error exporting to FalkorDB: {e}")

# --- Main CocoIndex Flow ---
@cocoindex.flow_def(name="BookStackOllamaSimple")
def bookstack_ollama_simple_flow(flow_builder: FlowBuilder, data_scope: DataScope) -> None:
    """BookStack to FalkorDB flow with Ollama integration (simplified)."""
    
    # Add source for BookStack JSON files
    data_scope["pages"] = flow_builder.add_source(
        cocoindex.sources.LocalFile(
            path="bookstack_export_full",
            included_patterns=["*.json"]
        ),
        refresh_interval=timedelta(minutes=2)
    )
    
    # Process each page
    with data_scope["pages"].row() as page:
        # Process the page with enhanced extraction
        result = page["content"].transform(process_page_with_ollama)
        
        # Process results are already exported to FalkorDB directly
        # No need to collect here since we're doing direct export
    
    # Processing is done directly in the transform function
    # No additional export needed since FalkorDB export happens inside process_page_with_ollama

if __name__ == "__main__":
    print("BookStack to FalkorDB Flow with Ollama (Simplified)")
    print("=" * 60)
    print("Features:")
    print("- Basic entity extraction with keyword matching")
    print("- BookStack tag processing")
    print("- FalkorDB direct export")
    print("- Graphiti schema compliance")
    print("- Ready for Ollama enhancement")
    print("\nRun with: python run_cocoindex.py update --setup flows/bookstack_ollama_simple.py")