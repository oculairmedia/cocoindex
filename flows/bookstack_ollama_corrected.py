#!/usr/bin/env python3
"""
Corrected BookStack to FalkorDB pipeline with proper CocoIndex conventions.
Follows official CocoIndex patterns for Ollama LLM integration.
"""

import os
import uuid
import redis
import dataclasses
import logging
from datetime import timedelta
from typing import List

import cocoindex
from cocoindex import DataScope, FlowBuilder

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('BookStackOllamaCorrect')

# --- Data structures following CocoIndex patterns ---
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

# --- Helper functions following CocoIndex patterns ---
@cocoindex.op.function()
def extract_text_from_html(parsed_json: dict) -> str:
    """Extract clean text from HTML content."""
    from bs4 import BeautifulSoup
    
    html_content = parsed_json.get("body_html", "")
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
def extract_page_metadata(parsed_json: dict) -> PageMetadata:
    """Extract page metadata from parsed JSON."""
    return PageMetadata(
        page_id=str(parsed_json.get("id", 0)),
        title=parsed_json.get("title", "Untitled"),
        book=parsed_json.get("book", "Unknown"),
        url=parsed_json.get("url", ""),
        tags=parsed_json.get("tags", [])
    )

@cocoindex.op.function()
def create_group_id(book_name: str) -> str:
    """Create group_id from book name."""
    return book_name.lower().replace(" ", "-").replace("_", "-")

@cocoindex.op.function()
def log_llm_start(text_content: str) -> str:
    """Log before LLM processing starts."""
    logger.info(f"🤖 Starting LLM extraction for document (length: {len(text_content)} chars)")
    logger.info(f"📄 Content preview: {text_content[:200]}...")
    return text_content

@cocoindex.op.function()
def log_llm_result(analysis: DocumentAnalysis) -> DocumentAnalysis:
    """Log LLM extraction results."""
    logger.info(f"✅ LLM extraction completed successfully!")
    logger.info(f"📊 Extracted {len(analysis.entities)} entities, {len(analysis.relationships)} relationships")
    logger.info(f"📝 Summary: {analysis.summary.title}")
    for i, entity in enumerate(analysis.entities[:3]):  # Log first 3 entities
        logger.info(f"   Entity {i+1}: {entity.name} ({entity.type})")
    return analysis

@cocoindex.op.function()
def log_document_start(parsed_json: dict) -> dict:
    """Log when starting to process a document."""
    title = parsed_json.get("title", "Untitled")
    page_id = parsed_json.get("id", "unknown")
    logger.info(f"📄 Processing document: {title} (ID: {page_id})")
    return parsed_json

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

def safe_cypher_string(text: str) -> str:
    """Make string safe for Cypher queries."""
    if not text:
        return ""
    return text.replace("'", "\\'").replace('"', '\\"')[:500]

@cocoindex.op.function()
def export_to_falkor(analysis: DocumentAnalysis) -> DocumentAnalysis:
    """Export analysis results to FalkorDB."""
    falkor = get_falkor_connection()
    if not falkor:
        logger.error("❌ No FalkorDB connection available")
        return analysis

    graph_name = os.environ.get('FALKOR_GRAPH', 'graphiti_migration')

    try:
        # Create document node
        title = safe_cypher_string(analysis.summary.title)
        summary_text = safe_cypher_string(analysis.summary.summary)
        doc_uuid = str(uuid.uuid4())
        group_id = "bookstack"

        doc_cypher = f"""
        MERGE (d:Document {{name: '{title}'}})
        ON CREATE SET d.uuid = '{doc_uuid}',
                     d.created_at = timestamp(),
                     d.group_id = '{group_id}'
        SET d.content = '{summary_text}',
            d.source = 'bookstack'
        RETURN d.uuid
        """

        falkor.execute_command('GRAPH.QUERY', graph_name, doc_cypher)
        logger.info(f"📄 Created FalkorDB document: {title[:50]}...")

        # Create entities with deduplication
        for entity in analysis.entities:
            entity_name = safe_cypher_string(entity.name.lower().strip())
            entity_desc = safe_cypher_string(entity.description)
            entity_uuid = str(uuid.uuid4())

            entity_cypher = f"""
            MERGE (e:Entity {{name: '{entity_name}'}})
            ON CREATE SET e.uuid = '{entity_uuid}',
                         e.created_at = timestamp(),
                         e.group_id = '{group_id}'
            SET e.entity_type = '{entity.type}',
                e.description = '{entity_desc}'
            RETURN e.uuid
            """

            falkor.execute_command('GRAPH.QUERY', graph_name, entity_cypher)

            # Create mention relationship
            mention_cypher = f"""
            MATCH (d:Document {{name: '{title}'}}),
                  (e:Entity {{name: '{entity_name}'}})
            MERGE (d)-[r:MENTIONS]->(e)
            ON CREATE SET r.created_at = timestamp()
            """

            falkor.execute_command('GRAPH.QUERY', graph_name, mention_cypher)

        # Create relationships between entities
        for rel in analysis.relationships:
            subject = safe_cypher_string(rel.subject.lower().strip())
            object_name = safe_cypher_string(rel.object.lower().strip())
            predicate = safe_cypher_string(rel.predicate)

            rel_cypher = f"""
            MATCH (e1:Entity {{name: '{subject}'}}),
                  (e2:Entity {{name: '{object_name}'}})
            MERGE (e1)-[r:RELATES_TO {{predicate: '{predicate}'}}]->(e2)
            ON CREATE SET r.created_at = timestamp()
            SET r.fact = '{safe_cypher_string(rel.fact)}'
            """

            falkor.execute_command('GRAPH.QUERY', graph_name, rel_cypher)

        logger.info(f"✅ Exported to FalkorDB: {len(analysis.entities)} entities, {len(analysis.relationships)} relationships")

    except Exception as e:
        logger.error(f"❌ Error exporting to FalkorDB: {e}")

    return analysis

# --- Main CocoIndex Flow ---
@cocoindex.flow_def(name="BookStackOllamaCorrect")
def bookstack_ollama_corrected_flow(flow_builder: FlowBuilder, data_scope: DataScope) -> None:
    """Corrected BookStack to FalkorDB flow with proper Ollama integration."""
    
    # Add source for BookStack JSON files
    data_scope["documents"] = flow_builder.add_source(
        cocoindex.sources.LocalFile(
            path="bookstack_export_full",
            included_patterns=["*.json"]
        ),
        refresh_interval=timedelta(minutes=2)
    )
    
    # Add collectors for different data types
    documents_collector = data_scope.add_collector()
    entities_collector = data_scope.add_collector()
    relationships_collector = data_scope.add_collector()
    mentions_collector = data_scope.add_collector()
    
    # Process each document
    with data_scope["documents"].row() as doc:
        # Parse JSON content
        doc["parsed"] = doc["content"].transform(cocoindex.functions.ParseJson())
        
        # Extract metadata
        doc["metadata"] = doc["parsed"].transform(extract_page_metadata)
        
        # Extract clean text content
        doc["text_content"] = doc["parsed"].transform(extract_text_from_html)
        
        # Create group_id
        doc["group_id"] = doc["metadata"]["book"].transform(create_group_id)

        # Log before LLM processing
        doc["text_logged"] = doc["text_content"].transform(log_llm_start)

        # Extract comprehensive analysis using Ollama
        doc["analysis"] = doc["text_logged"].transform(
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

        # Log LLM extraction results
        doc["analysis_logged"] = doc["analysis"].transform(log_llm_result)

        # Export to FalkorDB
        doc["falkor_exported"] = doc["analysis_logged"].transform(export_to_falkor)

        # Collect document information
        documents_collector.collect(
            filename=doc["filename"],
            page_id=doc["metadata"]["page_id"],
            title=doc["analysis"]["summary"]["title"],
            summary=doc["analysis"]["summary"]["summary"],
            book=doc["metadata"]["book"],
            group_id=doc["group_id"],
            url=doc["metadata"]["url"]
        )
        
        # Process extracted entities
        with doc["analysis"]["entities"].row() as entity:
            entities_collector.collect(
                id=cocoindex.GeneratedField.UUID,
                name=entity["name"],
                type=entity["type"],
                description=entity["description"],
                group_id=doc["group_id"],
                source_filename=doc["filename"]
            )
            
            # Create mention relationship
            mentions_collector.collect(
                id=cocoindex.GeneratedField.UUID,
                document_filename=doc["filename"],
                entity_name=entity["name"],
                group_id=doc["group_id"]
            )
        
        # Process extracted relationships
        with doc["analysis"]["relationships"].row() as rel:
            relationships_collector.collect(
                id=cocoindex.GeneratedField.UUID,
                subject=rel["subject"],
                predicate=rel["predicate"],
                object=rel["object"],
                fact=rel["fact"],
                group_id=doc["group_id"],
                source_filename=doc["filename"]
            )
    
    # Export to PostgreSQL (CocoIndex standard approach)
    documents_collector.export(
        "bookstack_documents",
        cocoindex.targets.Postgres(),
        primary_key_fields=["filename"]
    )
    
    entities_collector.export(
        "bookstack_entities",
        cocoindex.targets.Postgres(),
        primary_key_fields=["id"]
    )
    
    relationships_collector.export(
        "bookstack_relationships",
        cocoindex.targets.Postgres(),
        primary_key_fields=["id"]
    )
    
    mentions_collector.export(
        "bookstack_mentions",
        cocoindex.targets.Postgres(),
        primary_key_fields=["id"]
    )

if __name__ == "__main__":
    print("Corrected BookStack to FalkorDB Flow with Proper Ollama Integration")
    print("=" * 70)
    print("✅ Follows CocoIndex conventions")
    print("✅ Proper Ollama LlmSpec with address parameter")
    print("✅ Uses ExtractByLlm instead of custom clients")
    print("✅ Exports to PostgreSQL (standard CocoIndex approach)")
    print("✅ Proper error handling and fallbacks")
    print("\nRun with: python run_cocoindex.py update --setup flows/bookstack_ollama_corrected.py")
