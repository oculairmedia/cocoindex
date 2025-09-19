#!/usr/bin/env python3
"""
Graphiti-compliant BookStack to FalkorDB pipeline.
Fully conforms to Graphiti schema specification.
"""

import os
import uuid
import redis
import dataclasses
import logging
from datetime import datetime, timezone, timedelta
from typing import List

import cocoindex
from cocoindex import DataScope, FlowBuilder

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('BookStackGraphiti')

# --- Data structures following Graphiti schema ---
@dataclasses.dataclass
class BookStackPage:
    """BookStack page structure."""
    id: int
    title: str
    body_html: str
    book: str
    url: str
    tags: List[str]

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
class DocumentSummary:
    """Document summary extracted by LLM."""
    title: str
    summary: str

@dataclasses.dataclass
class DocumentAnalysis:
    """Complete analysis of a BookStack document."""
    entities: List[Entity]
    relationships: List[Relationship]
    summary: DocumentSummary

@dataclasses.dataclass
class PageMetadata:
    """Page metadata structure."""
    page_id: str
    title: str
    book: str
    url: str
    tags: List[str]

# --- Graphiti-compliant helper functions ---
def generate_deterministic_uuid(namespace: str, identifier: str) -> str:
    """Generate deterministic UUID for idempotency."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{namespace}-{identifier}"))

def create_iso_timestamp() -> str:
    """Create ISO 8601 timestamp."""
    return datetime.now(timezone.utc).isoformat()

def normalize_entity_name(name: str) -> str:
    """Normalize entity names for consistency."""
    return name.lower().strip()

def create_group_id(book_name: str) -> str:
    """Create group_id from book name."""
    if not book_name:
        return "bookstack-default"
    return book_name.lower().replace(" ", "-").replace("_", "-")

def safe_cypher_string(text: str) -> str:
    """Make string safe for Cypher queries."""
    if not text:
        return ""
    return text.replace("'", "\\'").replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r')

# --- CocoIndex transform functions ---
@cocoindex.op.function()
def extract_text_from_html(page: BookStackPage) -> str:
    """Extract clean text from HTML content."""
    from bs4 import BeautifulSoup

    html_content = page.body_html
    if not html_content:
        return ""

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

@cocoindex.op.function()
def extract_page_metadata(page: BookStackPage) -> PageMetadata:
    """Extract page metadata from parsed JSON."""
    return PageMetadata(
        page_id=str(page.id),
        title=page.title,
        book=page.book,
        url=page.url,
        tags=page.tags
    )

@cocoindex.op.function()
def parse_bookstack_json(json_content: str) -> BookStackPage:
    """Parse BookStack JSON into structured data."""
    import json
    data = json.loads(json_content)
    return BookStackPage(
        id=data.get("id", 0),
        title=data.get("title", "Untitled"),
        body_html=data.get("body_html", ""),
        book=data.get("book", "Unknown"),
        url=data.get("url", ""),
        tags=data.get("tags", [])
    )

@cocoindex.op.function()
def log_processing_start(page: BookStackPage) -> BookStackPage:
    """Log when starting to process a document."""
    logger.info(f"📄 Processing BookStack page: {page.title} (ID: {page.id})")
    return page

# --- FalkorDB Export Functions ---
def get_falkor_connection():
    """Get FalkorDB connection."""
    try:
        r = redis.Redis(
            host=os.environ.get('FALKOR_HOST', 'localhost'),
            port=int(os.environ.get('FALKOR_PORT', '6379')),
            decode_responses=True
        )
        r.ping()
        return r
    except Exception as e:
        logger.error(f"FalkorDB connection failed: {e}")
        return None

@cocoindex.op.function()
def export_to_falkor_graphiti(analysis: DocumentAnalysis, metadata: PageMetadata, full_content: str) -> DocumentAnalysis:
    """Export analysis results to FalkorDB with full Graphiti schema compliance."""
    falkor = get_falkor_connection()
    if not falkor:
        logger.error("❌ No FalkorDB connection available")
        return analysis

    graph_name = os.environ.get('FALKOR_GRAPH', 'graphiti_migration')
    
    try:
        # Create group_id based on book
        group_id = create_group_id(metadata.book)
        
        # Generate deterministic UUID for episodic node
        episodic_uuid = generate_deterministic_uuid("bookstack-episodic", metadata.page_id)
        
        # Create Episodic node (Graphiti compliant)
        title = safe_cypher_string(metadata.title)
        content = safe_cypher_string(full_content)
        summary = safe_cypher_string(analysis.summary.summary)
        
        episodic_cypher = f"""
        MERGE (e:Episodic {{uuid: '{episodic_uuid}'}})
        ON CREATE SET e.name = '{title}',
                     e.group_id = '{group_id}',
                     e.source = 'bookstack',
                     e.source_description = 'BookStack knowledge base content',
                     e.created_at = timestamp()
        SET e.content = '{content}',
            e.valid_at = timestamp(),
            e.bookstack_id = '{metadata.page_id}',
            e.bookstack_url = '{safe_cypher_string(metadata.url)}',
            e.book_name = '{safe_cypher_string(metadata.book)}'
        RETURN e.uuid
        """
        
        falkor.execute_command('GRAPH.QUERY', graph_name, episodic_cypher)
        logger.info(f"📄 Created Episodic node: {title[:50]}...")
        
        # Create Entity nodes with Graphiti compliance
        for entity in analysis.entities:
            entity_name = normalize_entity_name(entity.name)
            entity_summary = safe_cypher_string(entity.description)
            entity_uuid = generate_deterministic_uuid("entity", f"{entity_name}-{group_id}")
            
            entity_cypher = f"""
            MERGE (ent:Entity {{name: '{safe_cypher_string(entity_name)}', group_id: '{group_id}'}})
            ON CREATE SET ent.uuid = '{entity_uuid}',
                         ent.created_at = timestamp()
            SET ent.summary = '{entity_summary}',
                ent.entity_type = '{entity.type}',
                ent.labels = ['{entity.type}']
            RETURN ent.uuid
            """
            
            falkor.execute_command('GRAPH.QUERY', graph_name, entity_cypher)
            
            # Create MENTIONS relationship (Graphiti compliant)
            mention_uuid = generate_deterministic_uuid("mentions", f"{episodic_uuid}-{entity_uuid}")
            mention_cypher = f"""
            MATCH (ep:Episodic {{uuid: '{episodic_uuid}'}}),
                  (ent:Entity {{name: '{safe_cypher_string(entity_name)}', group_id: '{group_id}'}})
            MERGE (ep)-[r:MENTIONS]->(ent)
            ON CREATE SET r.uuid = '{mention_uuid}',
                         r.created_at = timestamp(),
                         r.group_id = '{group_id}'
            """
            
            falkor.execute_command('GRAPH.QUERY', graph_name, mention_cypher)
        
        # Create RELATES_TO relationships between entities (Graphiti compliant)
        for rel in analysis.relationships:
            subject_name = normalize_entity_name(rel.subject)
            object_name = normalize_entity_name(rel.object)
            predicate = safe_cypher_string(rel.predicate)
            fact = safe_cypher_string(rel.fact)
            
            relates_uuid = generate_deterministic_uuid("relates", f"{subject_name}-{object_name}-{group_id}")
            
            relates_cypher = f"""
            MATCH (e1:Entity {{name: '{safe_cypher_string(subject_name)}', group_id: '{group_id}'}}),
                  (e2:Entity {{name: '{safe_cypher_string(object_name)}', group_id: '{group_id}'}})
            MERGE (e1)-[r:RELATES_TO]->(e2)
            ON CREATE SET r.uuid = '{relates_uuid}',
                         r.created_at = timestamp(),
                         r.group_id = '{group_id}'
            SET r.predicate = '{predicate}',
                r.fact = '{fact}'
            """
            
            falkor.execute_command('GRAPH.QUERY', graph_name, relates_cypher)
        
        logger.info(f"✅ Graphiti export complete: {len(analysis.entities)} entities, {len(analysis.relationships)} relationships")
        
    except Exception as e:
        logger.error(f"❌ Error exporting to FalkorDB: {e}")
    
    return analysis

# --- Main CocoIndex Flow ---
@cocoindex.flow_def(name="BookStackGraphitiCompliant")
def bookstack_graphiti_flow(flow_builder: FlowBuilder, data_scope: DataScope) -> None:
    """Graphiti-compliant BookStack to FalkorDB flow."""
    
    # Add source for BookStack JSON files
    data_scope["documents"] = flow_builder.add_source(
        cocoindex.sources.LocalFile(
            path="bookstack_export_full",
            included_patterns=["*.json"]
        ),
        refresh_interval=timedelta(minutes=2)
    )
    
    # Process each document
    with data_scope["documents"].row() as doc:
        # Parse JSON content into structured data
        doc["parsed"] = doc["content"].transform(parse_bookstack_json)

        # Log processing start
        doc["logged"] = doc["parsed"].transform(log_processing_start)

        # Extract metadata
        doc["metadata"] = doc["parsed"].transform(extract_page_metadata)

        # Extract full text content
        doc["full_content"] = doc["parsed"].transform(extract_text_from_html)
        
        # Extract comprehensive analysis using Ollama
        doc["analysis"] = doc["full_content"].transform(
            cocoindex.functions.ExtractByLlm(
                llm_spec=cocoindex.LlmSpec(
                    api_type=cocoindex.LlmApiType.OLLAMA,
                    model="gemma3:12b",
                    address=os.environ.get("OLLAMA_URL", "http://100.81.139.20:11434")
                ),
                output_type=DocumentAnalysis,
                instruction="""
                You are an expert knowledge graph entity extractor. Analyze this BookStack documentation and extract:

                1. ENTITIES: Extract important entities and classify them:
                   - TECHNOLOGY: Software, frameworks, tools, programming languages, databases
                   - CONCEPT: Abstract ideas, methodologies, processes, principles
                   - PERSON: Individual people, authors, developers
                   - ORGANIZATION: Companies, institutions, teams
                   - LOCATION: Places, regions, countries
                   - TAG: Labels or categories

                2. RELATIONSHIPS: Identify meaningful relationships between entities:
                   - Use predicates like: uses, implements, part_of, depends_on, created_by, relates_to
                   - Provide supporting facts from the text

                3. SUMMARY: Create a clear title and brief 2-3 sentence summary.

                Focus on technical and domain-specific entities. Normalize entity names to lowercase.
                Return a complete DocumentAnalysis with entities, relationships, and summary.
                """
            )
        )
        
        # Export to FalkorDB with Graphiti compliance
        doc["exported"] = doc["analysis"].transform(
            export_to_falkor_graphiti,
            metadata=doc["metadata"],
            full_content=doc["full_content"]
        )

if __name__ == "__main__":
    print("Graphiti-Compliant BookStack to FalkorDB Flow")
    print("=" * 50)
    print("✅ Full Graphiti schema compliance")
    print("✅ Deterministic UUID generation")
    print("✅ Episodic nodes with all required fields")
    print("✅ Entity nodes with summary field")
    print("✅ Proper relationship UUIDs")
    print("\nRun with: cocoindex update --setup flows/bookstack_graphiti_compliant.py")
