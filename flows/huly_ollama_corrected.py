#!/usr/bin/env python3
"""
Huly to FalkorDB pipeline with Ollama LLM integration.
Follows CocoIndex patterns for project management data processing.
"""

import os
import uuid
import redis
import dataclasses
import logging
from datetime import timedelta
from typing import List, Dict, Any, Optional, Tuple
from bs4 import BeautifulSoup
import json

import cocoindex
from cocoindex import DataScope, FlowBuilder

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('HulyOllamaCorrect')

# --- Data structures for LLM extraction ---

@dataclasses.dataclass
class HulyMetadata:
    """Metadata extracted from Huly JSON content."""
    type: str
    id: str
    name: str
    description: str
    project_id: str
    status: str
    priority: str
    component: str
    milestone: str

@dataclasses.dataclass
class Entity:
    """
    An entity extracted from Huly project/issue content.
    Should be core concepts, technologies, components, or important nouns.
    Examples: 'GitHub Actions', 'Container Registry', 'Pipeline', 'FalkorDB'
    """
    name: str
    type: str  # TECHNOLOGY, CONCEPT, PERSON, ORGANIZATION, COMPONENT, MILESTONE
    description: str

@dataclasses.dataclass
class Relationship:
    """
    Describe a relationship between two entities.
    Examples: 'Pipeline uses Docker', 'GitHub Actions builds Container'
    """
    subject: str
    predicate: str
    object: str
    fact: str

@dataclasses.dataclass
class HulyAnalysis:
    """Complete analysis of Huly project/issue data."""
    summary: str
    entities: List[Entity]
    relationships: List[Relationship]

# --- FalkorDB Connection Setup ---
def get_falkor_connection():
    """Get Redis connection to FalkorDB."""
    host = os.environ.get('FALKOR_HOST', 'localhost')
    port = int(os.environ.get('FALKOR_PORT', '6379'))
    return redis.Redis(host=host, port=port, decode_responses=True)

# --- Helper Functions ---

def safe_cypher_string(s: str) -> str:
    """Escape string for Cypher queries."""
    if not s:
        return ""
    return s.replace("'", "\\'").replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r')

@cocoindex.op.function()
def extract_project_id(metadata: HulyMetadata) -> str:
    """Extract project_id from metadata."""
    return metadata.project_id or ""

@cocoindex.op.function()
def create_group_id(project_name: str) -> str:
    """Create group_id from project name."""
    if not project_name:
        return "huly"

    # Convert to lowercase, replace non-alphanumeric with hyphens
    group_id = ''.join(c.lower() if c.isalnum() else '-' for c in project_name)
    # Remove multiple consecutive hyphens and strip edges
    while '--' in group_id:
        group_id = group_id.replace('--', '-')
    return group_id.strip('-') or "huly"

# --- CocoIndex Transform Functions ---

@cocoindex.op.function()
def extract_huly_metadata(content: Dict[str, Any]) -> HulyMetadata:
    """Extract metadata from Huly JSON content."""
    try:
        data = content

        return HulyMetadata(
            type=data.get("type", "unknown"),
            id=data.get("id", ""),
            name=data.get("name", data.get("title", "")),
            description=data.get("description", ""),
            project_id=data.get("project_id", ""),
            status=data.get("status", ""),
            priority=data.get("priority", ""),
            component=data.get("component", ""),
            milestone=data.get("milestone", "")
        )
    except Exception as e:
        logger.error(f"Error extracting Huly metadata: {e}")
        return HulyMetadata(
            type="unknown",
            id="",
            name="",
            description="",
            project_id="",
            status="",
            priority="",
            component="",
            milestone=""
        )

@cocoindex.op.function()
def extract_text_content(metadata: HulyMetadata) -> str:
    """Extract clean text content from Huly data."""
    content_parts = []

    # Add title/name
    if metadata.name:
        content_parts.append(f"Title: {metadata.name}")

    # Add description
    if metadata.description:
        content_parts.append(f"Description: {metadata.description}")

    # Add project context
    if metadata.project_id:
        content_parts.append(f"Project: {metadata.project_id}")

    # Add status and priority for issues
    if metadata.type == "issue":
        if metadata.status:
            content_parts.append(f"Status: {metadata.status}")
        if metadata.priority:
            content_parts.append(f"Priority: {metadata.priority}")
        if metadata.component:
            content_parts.append(f"Component: {metadata.component}")
        if metadata.milestone:
            content_parts.append(f"Milestone: {metadata.milestone}")

    return "\n".join(content_parts)

@cocoindex.op.function()
def log_llm_start(text_content: str) -> str:
    """Log the start of LLM processing."""
    logger.info(f"🤖 Starting LLM analysis for content: {text_content[:100]}...")
    return text_content

@cocoindex.op.function()
def export_to_falkordb_simple(analysis: HulyAnalysis) -> HulyAnalysis:
    """Export analysis results to FalkorDB with Graphiti schema - for issues."""
    try:
        logger.info(f"🚀 Starting FalkorDB export with {len(analysis.entities)} entities")
        falkor = get_falkor_connection()
        graph_name = os.environ.get('FALKOR_GRAPH', 'graphiti_migration')

        # Use default values since we don't have metadata in this simple version
        group_id = "huly"
        title = safe_cypher_string(analysis.summary[:100] if analysis.summary else "Untitled")
        item_id = str(uuid.uuid4())
        summary_text = safe_cypher_string(analysis.summary)

        # Always create as Episodic for now (assuming issues)
        if True:
            # Issues become Episodic nodes (temporal events)
            doc_uuid = str(uuid.uuid4())
            doc_cypher = f"""
            MERGE (d:Episodic {{uuid: '{doc_uuid}'}})
            ON CREATE SET d.created_at = timestamp(),
                         d.name = '{title[:50]}',
                         d.group_id = '{group_id}',
                         d.source = 'issue',
                         d.source_description = 'Huly project management issue'
            SET d.content = '{summary_text}',
                d.valid_at = timestamp(),
                d.huly_id = '{safe_cypher_string(item_id)}'
            RETURN d.uuid
            """
            falkor.execute_command('GRAPH.QUERY', graph_name, doc_cypher)
            logger.info(f"📄 Created Episodic node for issue: {title[:50]}...")


        # Create entities with deduplication
        for entity in analysis.entities:
            entity_name = safe_cypher_string(entity.name.lower().strip())
            entity_desc = safe_cypher_string(entity.description)
            entity_uuid = str(uuid.uuid4())

            entity_cypher = f"""
            MERGE (e:Entity {{name: '{entity_name}', group_id: '{group_id}'}})
            ON CREATE SET e.uuid = '{entity_uuid}',
                         e.created_at = timestamp()
            SET e.summary = '{entity_desc}',
                e.entity_type = '{entity.type}'
            RETURN e.uuid
            """

            falkor.execute_command('GRAPH.QUERY', graph_name, entity_cypher)

            # Create mention relationship (always from Episodic for now)
            mention_cypher = f"""
            MATCH (d:Episodic {{uuid: '{doc_uuid}'}}),
                  (e:Entity {{name: '{entity_name}', group_id: '{group_id}'}})
            MERGE (d)-[r:MENTIONS]->(e)
            ON CREATE SET r.uuid = '{str(uuid.uuid4())}',
                         r.created_at = timestamp()
            """

            falkor.execute_command('GRAPH.QUERY', graph_name, mention_cypher)

        # Create relationships between entities
        for rel in analysis.relationships:
            subject = safe_cypher_string(rel.subject.lower().strip())
            object_name = safe_cypher_string(rel.object.lower().strip())
            predicate = safe_cypher_string(rel.predicate)
            fact = safe_cypher_string(rel.fact)

            rel_cypher = f"""
            MATCH (e1:Entity {{name: '{subject}', group_id: '{group_id}'}}),
                  (e2:Entity {{name: '{object_name}', group_id: '{group_id}'}})
            MERGE (e1)-[r:RELATES_TO {{predicate: '{predicate}'}}]->(e2)
            ON CREATE SET r.uuid = '{str(uuid.uuid4())}',
                         r.created_at = timestamp(),
                         r.group_id = '{group_id}'
            SET r.fact = '{fact}'
            """

            falkor.execute_command('GRAPH.QUERY', graph_name, rel_cypher)

        logger.info(f"✅ Exported to FalkorDB: {len(analysis.entities)} entities, {len(analysis.relationships)} relationships")

    except Exception as e:
        logger.error(f"❌ Error exporting to FalkorDB: {e}", exc_info=True)

    logger.info(f"✅ FalkorDB export completed")
    return analysis

# --- Main CocoIndex Flow ---
@cocoindex.flow_def(name="HulyOllamaCorrect")
def huly_ollama_corrected_flow(flow_builder: FlowBuilder, data_scope: DataScope) -> None:
    """Huly to FalkorDB flow with Ollama LLM integration."""

    # Add source for Huly JSON files
    data_scope["documents"] = flow_builder.add_source(
        cocoindex.sources.LocalFile(
            path="huly_export_mock",  # Will be changed to huly_export_full when API works
            included_patterns=["*.json"]
        ),
        refresh_interval=timedelta(minutes=2)
    )

    # Add collectors for different data types
    documents_collector = data_scope.add_collector()
    entities_collector = data_scope.add_collector()
    relationships_collector = data_scope.add_collector()

    # Process each document
    with data_scope["documents"].row() as doc:
        # Parse JSON content
        doc["parsed"] = doc["content"].transform(cocoindex.functions.ParseJson())

        # Extract metadata
        doc["metadata"] = doc["parsed"].transform(extract_huly_metadata)

        # Extract clean text content
        doc["text_content"] = doc["metadata"].transform(extract_text_content)

        # Extract project_id and create group_id
        doc["project_id"] = doc["metadata"].transform(extract_project_id)
        doc["group_id"] = doc["project_id"].transform(create_group_id)

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
                output_type=HulyAnalysis,
                instruction="""
                Extract entities and relationships from this data.

                Entities (3-5): Key technologies, components, or concepts. Include name, type, description.
                Relationships (2-4): How entities connect (uses, implements, contains).
                Summary: 1 sentence about the main topic.

                Be concise.
                """
            )
        )

        # Export to FalkorDB (simplified - passing analysis only)
        doc["exported"] = doc["analysis"].transform(export_to_falkordb_simple)

        # Collect data for reporting
        documents_collector.collect(
            filename=doc["filename"],
            item_id=doc["metadata"]["id"],
            title=doc["metadata"]["name"],
            type=doc["metadata"]["type"],
            project_id=doc["metadata"]["project_id"],
            status=doc["metadata"]["status"],
            priority=doc["metadata"]["priority"],
            group_id=doc["group_id"]
        )

        # Process extracted entities
        with doc["analysis"]["entities"].row() as entity:
            entities_collector.collect(
                id=cocoindex.GeneratedField.UUID,
                name=entity["name"],
                type=entity["type"],
                description=entity["description"],
                group_id=doc["group_id"]
            )

        # Process relationships
        with doc["analysis"]["relationships"].row() as relationship:
            relationships_collector.collect(
                id=cocoindex.GeneratedField.UUID,
                subject=relationship["subject"],
                predicate=relationship["predicate"],
                object=relationship["object"],
                fact=relationship["fact"],
                group_id=doc["group_id"]
            )

if __name__ == "__main__":
    # This allows the flow to be run directly for testing
    print("Huly to FalkorDB pipeline flow ready!")
    print("Use: cocoindex update --setup flows/huly_ollama_corrected.py")