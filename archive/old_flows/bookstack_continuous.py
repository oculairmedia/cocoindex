"""
Continuous BookStack to FalkorDB sync pipeline
This flow continuously monitors BookStack and syncs changes to FalkorDB
"""
from __future__ import annotations

import os
import json
import hashlib
import uuid
from datetime import timedelta, datetime
from typing import List, Dict, Any
import dataclasses

import cocoindex
from cocoindex import DataScope, FlowBuilder
import requests
from bs4 import BeautifulSoup

# Configuration
BOOKSTACK_URL = os.environ.get("BS_URL", "https://bstest.integrative-systems.org")
BOOKSTACK_TOKEN_ID = os.environ.get("BS_TOKEN_ID")
BOOKSTACK_TOKEN_SECRET = os.environ.get("BS_TOKEN_SECRET")
FALKOR_HOST = os.environ.get("FALKOR_HOST", "localhost")
FALKOR_PORT = int(os.environ.get("FALKOR_PORT", "6379"))
FALKOR_GRAPH = os.environ.get("FALKOR_GRAPH", "graphiti_migration")

# Data classes for structured extraction
@dataclasses.dataclass
class Entity:
    name: str
    type: str  # PERSON, ORGANIZATION, CONCEPT, TECHNOLOGY, LOCATION
    description: str

@dataclasses.dataclass
class Relationship:
    subject: str
    predicate: str
    object: str
    fact: str

@dataclasses.dataclass
class ExtractedEntities:
    entities: List[Entity]
    relationships: List[Relationship]

# Helper functions
@cocoindex.op.function()
def fetch_bookstack_pages() -> List[Dict[str, Any]]:
    """Fetch all pages from BookStack API."""
    headers = {
        "Authorization": f"Token {BOOKSTACK_TOKEN_ID}:{BOOKSTACK_TOKEN_SECRET}"
    }
    
    all_pages = []
    url = f"{BOOKSTACK_URL}/api/pages"
    
    while url:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        # Get detailed page content for each page
        for page in data.get('data', []):
            page_url = f"{BOOKSTACK_URL}/api/pages/{page['id']}"
            page_response = requests.get(page_url, headers=headers)
            if page_response.status_code == 200:
                page_detail = page_response.json()
                all_pages.append(page_detail)
        
        # Check for next page
        url = data.get('links', {}).get('next')
    
    return all_pages

@cocoindex.op.function()
def process_bookstack_page(page: Dict[str, Any]) -> Dict[str, Any]:
    """Process a BookStack page and extract relevant fields."""
    # Convert HTML to text
    html_content = page.get('html', '')
    soup = BeautifulSoup(html_content, 'html.parser')
    text_content = soup.get_text(separator='\n', strip=True)
    
    # Extract book and chapter info
    book_name = "Unknown"
    chapter_name = ""
    
    # Try to get book from page details
    if 'book' in page:
        book_name = page['book'].get('name', book_name)
    elif 'book_id' in page:
        book_name = f"Book_{page['book_id']}"
    
    if 'chapter' in page:
        chapter_name = page['chapter'].get('name', '')
    
    # Get tags
    tags = []
    if 'tags' in page:
        tags = [tag['name'] for tag in page['tags']]
    
    return {
        'id': page['id'],
        'title': page.get('name', 'Untitled'),
        'slug': page.get('slug', ''),
        'text_content': text_content,
        'html_content': html_content,
        'book': book_name,
        'chapter': chapter_name,
        'tags': tags,
        'updated_at': page.get('updated_at', datetime.now().isoformat()),
        'created_at': page.get('created_at', datetime.now().isoformat()),
        'url': f"{BOOKSTACK_URL}/books/{page.get('book_slug', 'unknown')}/page/{page.get('slug', page['id'])}"
    }

@cocoindex.op.function()
def extract_entities_from_page(text: str, tags: List[str]) -> ExtractedEntities:
    """Extract entities and relationships from page content."""
    entities = []
    
    # Add tag entities
    for tag in tags:
        entities.append(Entity(
            name=tag.replace('-', ' ').title(),
            type='CONCEPT',
            description=f'Tag from BookStack page'
        ))
    
    # Simple keyword extraction for demo (in production, use LLM)
    tech_keywords = ['python', 'javascript', 'api', 'database', 'machine learning', 
                     'artificial intelligence', 'docker', 'kubernetes', 'react', 'vue']
    
    text_lower = text.lower()
    for keyword in tech_keywords:
        if keyword in text_lower:
            entities.append(Entity(
                name=keyword.title(),
                type='TECHNOLOGY',
                description=f'Technology mentioned in content'
            ))
    
    # Create relationships between entities in same document
    relationships = []
    if len(entities) >= 2:
        for i in range(len(entities)):
            for j in range(i + 1, len(entities)):
                relationships.append(Relationship(
                    subject=entities[i].name,
                    predicate='co_occurs_with',
                    object=entities[j].name,
                    fact=f'Both appear in the same document'
                ))
    
    return ExtractedEntities(entities=entities, relationships=relationships)

@cocoindex.op.function() 
def create_page_hash(page: Dict[str, Any]) -> str:
    """Create a hash of page content for change detection."""
    content = f"{page['title']}:{page['text_content']}:{page['updated_at']}"
    return hashlib.sha256(content.encode()).hexdigest()

# Custom target for FalkorDB
@cocoindex.op.target_connector(spec_cls=cocoindex.targets.BaseTargetSpec)
class FalkorDBConnector:
    """FalkorDB target connector for CocoIndex."""
    
    @staticmethod
    def get_persistent_key(spec: cocoindex.targets.BaseTargetSpec, target_name: str) -> str:
        return f"falkordb_{FALKOR_HOST}_{FALKOR_PORT}_{FALKOR_GRAPH}_{target_name}"
    
    @staticmethod
    def prepare(spec: cocoindex.targets.BaseTargetSpec) -> Any:
        """Prepare FalkorDB connection."""
        import redis
        client = redis.Redis(host=FALKOR_HOST, port=FALKOR_PORT, decode_responses=True)
        # Test connection
        client.ping()
        return client
    
    @staticmethod
    def mutate(
        *all_mutations: tuple[Any, dict[str, dict | None]],
    ) -> None:
        """Write mutations to FalkorDB."""
        for client, mutations in all_mutations:
            for key, mutation in mutations.items():
                if mutation is None:
                    continue  # Skip deletions for now
                
                # Handle different mutation types
                if mutation.get('_type') == 'document':
                    # Create document node
                    doc_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"doc_{mutation['id']}"))
                    query = f"""
                    MERGE (d:Episodic {{uuid: '{doc_uuid}'}})
                    SET d.name = '{mutation['title'].replace("'", "\\'")}',
                        d.content = '{mutation['text_content'][:500].replace("'", "\\'")}...',
                        d.group_id = '{mutation['book'].replace("'", "\\'")}',
                        d.chapter = '{mutation['chapter'].replace("'", "\\'")}',
                        d.updated_at = '{mutation['updated_at']}',
                        d.source = 'BookStack',
                        d.source_description = '{mutation['url'].replace("'", "\\'")}'
                    """
                    client.execute_command("GRAPH.QUERY", FALKOR_GRAPH, query)
                
                elif mutation.get('_type') == 'entity':
                    # Create entity node
                    entity_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"entity_{mutation['name']}"))
                    query = f"""
                    MERGE (e:Entity {{name: '{mutation['name'].replace("'", "\\'")}'}})
                    SET e.uuid = '{entity_uuid}',
                        e.type = '{mutation['type']}',
                        e.description = '{mutation['description'].replace("'", "\\'")}'
                    """
                    client.execute_command("GRAPH.QUERY", FALKOR_GRAPH, query)
                
                elif mutation.get('_type') == 'relationship':
                    # Create relationship
                    query = f"""
                    MATCH (s:Entity {{name: '{mutation['subject'].replace("'", "\\'")}'}}),
                          (o:Entity {{name: '{mutation['object'].replace("'", "\\'")}'}}),
                          (d:Episodic {{uuid: '{mutation['doc_uuid']}'}})
                    MERGE (s)-[r:{mutation['predicate'].upper()}]->(o)
                    SET r.fact = '{mutation['fact'].replace("'", "\\'")}'
                    MERGE (d)-[:MENTIONS]->(s)
                    MERGE (d)-[:MENTIONS]->(o)
                    """
                    client.execute_command("GRAPH.QUERY", FALKOR_GRAPH, query)

# Main flow definition
@cocoindex.flow_def(name="BookStackContinuousSync")
def bookstack_continuous_sync(flow_builder: FlowBuilder, data_scope: DataScope) -> None:
    """Continuously sync BookStack content to FalkorDB."""
    
    # Set up periodic fetch of BookStack pages
    data_scope["bookstack_pages"] = flow_builder.add_source(
        cocoindex.sources.CustomSource(
            fetch_function=fetch_bookstack_pages,
            name="BookStackAPI"
        ),
        refresh_interval=timedelta(minutes=5)  # Check every 5 minutes
    )
    
    # Create collectors
    documents_collector = data_scope.add_collector()
    entities_collector = data_scope.add_collector()
    relationships_collector = data_scope.add_collector()
    
    # Process each page
    with data_scope["bookstack_pages"].row() as page:
        # Process page data
        processed = page.transform(process_bookstack_page)
        
        # Create hash for change detection
        page_hash = processed.transform(create_page_hash)
        
        # Extract entities and relationships
        extracted = processed.transform(
            lambda p: extract_entities_from_page(p['text_content'], p['tags'])
        )
        
        # Collect document
        documents_collector.collect(
            _type='document',
            id=processed['id'],
            title=processed['title'],
            text_content=processed['text_content'],
            book=processed['book'],
            chapter=processed['chapter'],
            url=processed['url'],
            updated_at=processed['updated_at'],
            hash=page_hash
        )
        
        # Collect entities
        with extracted['entities'].row() as entity:
            entities_collector.collect(
                _type='entity',
                name=entity['name'],
                type=entity['type'],
                description=entity['description']
            )
        
        # Collect relationships
        doc_uuid = processed.transform(
            lambda p: str(uuid.uuid5(uuid.NAMESPACE_DNS, f"doc_{p['id']}"))
        )
        
        with extracted['relationships'].row() as rel:
            relationships_collector.collect(
                _type='relationship',
                subject=rel['subject'],
                predicate=rel['predicate'],
                object=rel['object'],
                fact=rel['fact'],
                doc_uuid=doc_uuid
            )
    
    # Export to FalkorDB
    target_spec = cocoindex.targets.BaseTargetSpec()
    
    # Export documents (with deduplication based on hash)
    documents_collector.export(
        "bookstack_documents",
        FalkorDBConnector(spec=target_spec),
        primary_key_fields=["id"],
        incremental_key_fields=["hash"]  # Only update if content changed
    )
    
    # Export entities
    entities_collector.export(
        "bookstack_entities",
        FalkorDBConnector(spec=target_spec),
        primary_key_fields=["name"]
    )
    
    # Export relationships
    relationships_collector.export(
        "bookstack_relationships",
        FalkorDBConnector(spec=target_spec),
        primary_key_fields=["subject", "predicate", "object"]
    )

if __name__ == "__main__":
    print("BookStack Continuous Sync Flow defined successfully!")
    print(f"Will sync from: {BOOKSTACK_URL}")
    print(f"To FalkorDB at: {FALKOR_HOST}:{FALKOR_PORT}/{FALKOR_GRAPH}")
    print("Run with: cocoindex update flows/bookstack_continuous.py")