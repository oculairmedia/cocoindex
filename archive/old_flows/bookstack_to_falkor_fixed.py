"""
CocoIndex flow: BookStack JSON -> FalkorDB (Graphiti-compatible)
Fixed version following proper CocoIndex patterns from examples
"""
from __future__ import annotations

import os
import re
import json
import uuid
import dataclasses
from datetime import timedelta
from typing import List, Optional

import cocoindex
from cocoindex import DataScope, FlowBuilder

# Set up environment
os.environ.setdefault("FALKOR_HOST", "localhost")
os.environ.setdefault("FALKOR_PORT", "6379")
os.environ.setdefault("FALKOR_GRAPH", "graphiti_migration")

# --- Data structures for entity extraction ---
@dataclasses.dataclass
class Entity:
    """An entity extracted from content."""
    name: str
    type: str  # PERSON, ORGANIZATION, CONCEPT, TECHNOLOGY, LOCATION
    description: str

@dataclasses.dataclass
class Relationship:
    """A relationship between two entities."""
    subject: str
    predicate: str
    object: str
    fact: str

@dataclasses.dataclass
class ExtractedData:
    """Container for extracted entities and relationships."""
    entities: List[Entity]
    relationships: List[Relationship]

# --- Helper functions ---
@cocoindex.op.function()
def html_to_text(html: str) -> str:
    """Convert HTML to plain text."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    
    # Remove script and style elements
    for script in soup(["script", "style"]):
        script.decompose()
    
    # Get text
    text = soup.get_text(separator="\n", strip=True)
    
    # Clean up whitespace
    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    text = "\n".join(chunk for chunk in chunks if chunk)
    
    return text

@cocoindex.op.function()
def process_page(page_json: cocoindex.Json) -> dict:
    """Process a BookStack page JSON and extract key fields."""
    return {
        "id": page_json.get("id", 0),
        "title": page_json.get("title", "Untitled"),
        "slug": page_json.get("slug", ""),
        "url": page_json.get("url", ""),
        "book": page_json.get("book", "Unknown"),
        "chapter": page_json.get("chapter", ""),
        "tags": page_json.get("tags", []),
        "body_html": page_json.get("body_html", ""),
        "updated_at": page_json.get("updated_at", ""),
    }

@cocoindex.op.function()
def create_chunks(text: str, title: str) -> List[dict]:
    """Split text into chunks for processing."""
    chunk_size = 1200
    overlap = 300
    chunks = []
    
    if not text:
        return [{"text": "", "title": title, "chunk_idx": 0}]
    
    for i in range(0, len(text), chunk_size - overlap):
        chunk_text = text[i:i + chunk_size].strip()
        if chunk_text:
            chunks.append({
                "text": chunk_text,
                "title": title,
                "chunk_idx": len(chunks)
            })
    
    return chunks if chunks else [{"text": "", "title": title, "chunk_idx": 0}]

@cocoindex.op.function()
def normalize_entity_name(name: str) -> str:
    """Normalize entity names for deduplication."""
    # Remove extra whitespace
    name = re.sub(r'\s+', ' ', name.strip())
    # Title case for proper names
    name = name.title()
    return name

# --- Mock entity extraction (replace with LLM in production) ---
@cocoindex.op.function()
def extract_entities_and_relationships(text: str, tags: List[str]) -> ExtractedData:
    """Extract entities and relationships from text."""
    entities = []
    
    # Extract entities from tags
    for tag in tags:
        entities.append(Entity(
            name=normalize_entity_name(tag.replace("-", " ")),
            type="CONCEPT",
            description=f"Tag from BookStack"
        ))
    
    # Mock extraction from content (in production, use LLM)
    if "machine learning" in text.lower():
        entities.append(Entity(
            name="Machine Learning",
            type="TECHNOLOGY",
            description="A type of artificial intelligence"
        ))
    
    if "data" in text.lower():
        entities.append(Entity(
            name="Data",
            type="CONCEPT",
            description="Information used for analysis"
        ))
    
    # Mock relationships
    relationships = []
    if len(entities) >= 2:
        relationships.append(Relationship(
            subject=entities[0].name,
            predicate="relates_to",
            object=entities[1].name,
            fact="Entities found in the same document"
        ))
    
    return ExtractedData(entities=entities, relationships=relationships)

# --- Create custom FalkorDB target ---
@cocoindex.op.target_connector(metadata_file_suffix=".falkor_metadata.json")
class FalkorDBTarget:
    """Custom target for FalkorDB graph database."""
    
    def __init__(self, host: str = None, port: int = None, graph: str = None):
        self.host = host or os.environ.get("FALKOR_HOST", "localhost")
        self.port = port or int(os.environ.get("FALKOR_PORT", "6379"))
        self.graph = graph or os.environ.get("FALKOR_GRAPH", "graphiti_migration")
        self._client = None
    
    def _get_client(self):
        if self._client is None:
            import redis
            self._client = redis.Redis(host=self.host, port=self.port, decode_responses=True)
            # Test connection
            self._client.ping()
        return self._client
    
    def mutate(self, items: List[dict], metadata: Optional[dict] = None) -> dict:
        """Write items to FalkorDB."""
        client = self._get_client()
        
        for item in items:
            if item.get("_type") == "entity":
                # Create entity node
                query = f"""
                MERGE (e:Entity {{name: $name}})
                SET e.type = $type, e.description = $description
                """
                params = {
                    "name": item["name"],
                    "type": item["type"],
                    "description": item["description"]
                }
                client.execute_command("GRAPH.QUERY", self.graph, query, "--compact", json.dumps(params))
            
            elif item.get("_type") == "relationship":
                # Create relationship
                query = f"""
                MATCH (s:Entity {{name: $subject}})
                MATCH (o:Entity {{name: $object}})
                MERGE (s)-[r:{item["predicate"].upper()}]->(o)
                SET r.fact = $fact
                """
                params = {
                    "subject": item["subject"],
                    "object": item["object"],
                    "fact": item["fact"]
                }
                client.execute_command("GRAPH.QUERY", self.graph, query, "--compact", json.dumps(params))
        
        return {"items_written": len(items)}

# --- Main Flow Definition ---
@cocoindex.flow_def(name="BookStackToFalkorFixed")
def bookstack_to_falkor_flow(flow_builder: FlowBuilder, data_scope: DataScope) -> None:
    """Fixed BookStack to FalkorDB flow following proper CocoIndex patterns."""
    
    # Add source for BookStack JSON files
    data_scope["pages"] = flow_builder.add_source(
        cocoindex.sources.LocalFile(
            path="bookstack_export",
            included_patterns=["*.json"]
        ),
        refresh_interval=timedelta(seconds=30)
    )
    
    # Create collectors for entities and relationships
    entities_collector = data_scope.add_collector()
    relationships_collector = data_scope.add_collector()
    
    # Process each page
    with data_scope["pages"].row() as page:
        # Parse JSON and extract page data
        page_data = page["content"].transform(
            cocoindex.functions.ParseJson()
        ).transform(process_page)
        
        # Convert HTML to text
        text_content = page_data["body_html"].transform(html_to_text)
        
        # Extract entities and relationships
        extracted = text_content.transform(
            extract_entities_and_relationships,
            tags=page_data["tags"]
        )
        
        # Collect entities
        with extracted["entities"].row() as entity:
            entities_collector.collect(
                _type="entity",
                name=entity["name"],
                type=entity["type"], 
                description=entity["description"],
                page_id=page_data["id"],
                page_title=page_data["title"]
            )
        
        # Collect relationships
        with extracted["relationships"].row() as rel:
            relationships_collector.collect(
                _type="relationship",
                subject=rel["subject"],
                predicate=rel["predicate"],
                object=rel["object"],
                fact=rel["fact"],
                page_id=page_data["id"],
                page_title=page_data["title"]
            )
    
    # Export to FalkorDB
    # First export entities
    entities_collector.export(
        "falkor_entities",
        FalkorDBTarget(),
        primary_key_fields=["name"]
    )
    
    # Then export relationships
    relationships_collector.export(
        "falkor_relationships", 
        FalkorDBTarget(),
        primary_key_fields=["subject", "predicate", "object"]
    )

if __name__ == "__main__":
    # Test the flow
    print("Flow defined successfully!")