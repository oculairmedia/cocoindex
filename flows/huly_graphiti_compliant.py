#!/usr/bin/env python3
"""
Graphiti-compliant Huly to FalkorDB pipeline.
Fully conforms to Graphiti schema specification.
"""

import os
import uuid
import redis
import json
import dataclasses
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any

from flows.utils import current_timestamp_iso

import cocoindex
from cocoindex import DataScope, FlowBuilder

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('HulyGraphiti')

# --- Data structures following Graphiti schema ---
@dataclasses.dataclass
class Entity:
    """An entity extracted from Huly project/issue content."""
    name: str
    type: str  # TECHNOLOGY, CONCEPT, PERSON, ORGANIZATION, COMPONENT, MILESTONE, PROJECT
    description: str

@dataclasses.dataclass
class Relationship:
    """A relationship between two entities."""
    subject: str
    predicate: str
    object: str
    fact: str

@dataclasses.dataclass
class HulyMetadata:
    """Huly issue/project metadata structure."""
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
class HulyAnalysis:
    """Complete analysis of Huly project/issue data."""
    summary: str
    entities: List[Entity]
    relationships: List[Relationship]

# --- Graphiti-compliant helper functions ---
def generate_deterministic_uuid(namespace: str, identifier: str) -> str:
    """Generate deterministic UUID for idempotency."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{namespace}-{identifier}"))

def create_iso_timestamp() -> str:
    """Create ISO 8601 timestamp."""
    return current_timestamp_iso()

def normalize_entity_name(name: str) -> str:
    """Normalize entity names for consistency."""
    return name.lower().strip()

def create_group_id(project_name: str) -> str:
    """Create group_id from project name."""
    if not project_name or project_name.strip() == "":
        return "huly-default"

    # Clean and normalize the project name
    cleaned = project_name.strip().lower()
    # Replace spaces and underscores with hyphens
    cleaned = cleaned.replace(' ', '-').replace('_', '-')
    # Remove any non-alphanumeric characters except hyphens
    cleaned = ''.join(c if c.isalnum() or c == '-' else '' for c in cleaned)
    # Remove multiple consecutive hyphens
    while '--' in cleaned:
        cleaned = cleaned.replace('--', '-')
    # Remove leading/trailing hyphens
    cleaned = cleaned.strip('-')

    # If cleaning resulted in empty string, use default
    if not cleaned:
        return "huly-default"

    return f"huly-{cleaned}"

def safe_cypher_string(text: str) -> str:
    """Make string safe for Cypher queries."""
    if not text:
        return ""
    return text.replace("'", "\\'").replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r')

# --- CocoIndex transform functions ---
@cocoindex.op.function()
def extract_huly_metadata(content: str) -> HulyMetadata:
    """Extract metadata from Huly JSON content."""
    try:
        data = json.loads(content) if isinstance(content, str) else content

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

    # Add status and priority
    if metadata.status:
        content_parts.append(f"Status: {metadata.status}")
    if metadata.priority:
        content_parts.append(f"Priority: {metadata.priority}")

    # Add component and milestone
    if metadata.component:
        content_parts.append(f"Component: {metadata.component}")
    if metadata.milestone:
        content_parts.append(f"Milestone: {metadata.milestone}")
    
    return "\n".join(content_parts)

@cocoindex.op.function()
def log_processing_start(metadata: HulyMetadata) -> HulyMetadata:
    """Log when starting to process a Huly item."""
    name = metadata.name or "Untitled"
    item_type = metadata.type or "unknown"
    item_id = metadata.id or "unknown"
    logger.info(f"📄 Processing Huly {item_type}: {name} (ID: {item_id})")
    return metadata

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
def export_to_falkor_graphiti(analysis: HulyAnalysis, metadata: HulyMetadata, full_content: str) -> HulyAnalysis:
    """Export analysis results to FalkorDB with full Graphiti schema compliance."""
    falkor = get_falkor_connection()
    if not falkor:
        logger.error("❌ No FalkorDB connection available")
        return analysis

    graph_name = os.environ.get('FALKOR_GRAPH', 'graphiti_migration')

    try:
        # Create group_id based on project with extensive debugging
        project_name = metadata.project_id or metadata.name or ""
        logger.info(f"🔍 Debug: project_name='{project_name}', metadata.project_id='{metadata.project_id}', metadata.name='{metadata.name}'")

        group_id = create_group_id(project_name)
        logger.info(f"🔍 Debug: Initial group_id='{group_id}'")

        # Ensure group_id is never empty with multiple fallbacks
        if not group_id or group_id.strip() == "" or group_id == "huly-":
            group_id = "huly-default"
            logger.warning(f"⚠️  Using default group_id for item: {metadata.name} (project: {metadata.project_id})")

        # Final validation - absolutely ensure group_id is not empty
        if not group_id:
            group_id = "huly-fallback"
            logger.error(f"🚨 Emergency fallback group_id used for item: {metadata.name}")

        logger.info(f"🔍 Debug: Final group_id='{group_id}'")

        # Generate deterministic UUID for episodic node
        item_id = metadata.id or str(uuid.uuid4())
        episodic_uuid = generate_deterministic_uuid("huly-episodic", item_id)

        # Create Episodic node (Graphiti compliant)
        title = safe_cypher_string(metadata.name or "Untitled")
        content = safe_cypher_string(full_content)
        content_type = metadata.type or "unknown"

        # Final safety check before Cypher execution
        if not group_id or group_id.strip() == "":
            group_id = "huly-emergency"
            logger.error(f"🚨 CRITICAL: Empty group_id detected before Cypher execution! Using emergency fallback.")

        created_at = create_iso_timestamp()
        valid_at = create_iso_timestamp()

        episodic_cypher = f"""
        MERGE (e:Episodic {{uuid: '{episodic_uuid}', group_id: '{group_id}'}})
        ON CREATE SET e.name = '{title}',
                     e.source = 'huly',
                     e.source_description = 'Huly project management data',
                     e.created_at = '{created_at}'
        SET e.content = '{content}',
            e.valid_at = '{valid_at}',
            e.huly_type = '{content_type}',
            e.huly_id = '{safe_cypher_string(item_id)}',
            e.project_id = '{safe_cypher_string(metadata.project_id or "")}',
            e.status = '{safe_cypher_string(metadata.status or "")}',
            e.priority = '{safe_cypher_string(metadata.priority or "")}'
        RETURN e.uuid
        """
        
        falkor.execute_command('GRAPH.QUERY', graph_name, episodic_cypher)
        logger.info(f"📄 Created Episodic node: {title[:50]}...")
        
        # Create Entity nodes with Graphiti compliance
        for entity in analysis.entities:
            entity_name = normalize_entity_name(entity.name)
            entity_summary = safe_cypher_string(entity.description)  # Use description as summary
            entity_uuid = generate_deterministic_uuid("entity", f"{entity_name}-{group_id}")

            # Safety check for group_id in entity creation
            safe_group_id = group_id if group_id and group_id.strip() else "huly-emergency"

            entity_created_at = create_iso_timestamp()

            entity_cypher = f"""
            MERGE (ent:Entity {{uuid: '{entity_uuid}', name: '{safe_cypher_string(entity_name)}', group_id: '{safe_group_id}'}})
            ON CREATE SET ent.created_at = '{entity_created_at}'
            SET ent.summary = '{entity_summary}',
                ent.entity_type = '{entity.type}',
                ent.labels = ['{entity.type}']
            RETURN ent.uuid
            """
            
            falkor.execute_command('GRAPH.QUERY', graph_name, entity_cypher)
            
            # Create MENTIONS relationship (Graphiti compliant)
            mention_uuid = generate_deterministic_uuid("mentions", f"{episodic_uuid}-{entity_uuid}")
            mention_created_at = create_iso_timestamp()

            mention_cypher = f"""
            MATCH (ep:Episodic {{uuid: '{episodic_uuid}'}}),
                  (ent:Entity {{uuid: '{entity_uuid}', name: '{safe_cypher_string(entity_name)}', group_id: '{safe_group_id}'}})
            MERGE (ep)-[r:MENTIONS {{uuid: '{mention_uuid}', group_id: '{safe_group_id}'}}]->(ent)
            ON CREATE SET r.created_at = '{mention_created_at}'
            """
            
            falkor.execute_command('GRAPH.QUERY', graph_name, mention_cypher)
        
        # Create RELATES_TO relationships between entities (Graphiti compliant)
        for rel in analysis.relationships:
            subject_name = normalize_entity_name(rel.subject)
            object_name = normalize_entity_name(rel.object)
            predicate = safe_cypher_string(rel.predicate)
            fact = safe_cypher_string(rel.fact)

            # Use the same safe_group_id for consistency
            safe_group_id_rel = group_id if group_id and group_id.strip() else "huly-emergency"

            # Generate UUIDs for the entities we're trying to relate
            subject_uuid = generate_deterministic_uuid("entity", f"{subject_name}-{safe_group_id_rel}")
            object_uuid = generate_deterministic_uuid("entity", f"{object_name}-{safe_group_id_rel}")
            relates_uuid = generate_deterministic_uuid("relates", f"{subject_name}-{object_name}-{safe_group_id_rel}")

            relates_created_at = create_iso_timestamp()

            relates_cypher = f"""
            MATCH (e1:Entity {{uuid: '{subject_uuid}', name: '{safe_cypher_string(subject_name)}', group_id: '{safe_group_id_rel}'}}),
                  (e2:Entity {{uuid: '{object_uuid}', name: '{safe_cypher_string(object_name)}', group_id: '{safe_group_id_rel}'}})
            MERGE (e1)-[r:RELATES_TO {{uuid: '{relates_uuid}', group_id: '{safe_group_id_rel}'}}]->(e2)
            ON CREATE SET r.created_at = '{relates_created_at}'
            SET r.predicate = '{predicate}',
                r.fact = '{fact}'
            """
            
            falkor.execute_command('GRAPH.QUERY', graph_name, relates_cypher)
        
        logger.info(f"✅ Graphiti export complete: {len(analysis.entities)} entities, {len(analysis.relationships)} relationships")
        
    except Exception as e:
        logger.error(f"❌ Error exporting to FalkorDB: {e}")
    
    return analysis

# --- Main CocoIndex Flow ---
@cocoindex.flow_def(name="HulyGraphitiCompliant")
def huly_graphiti_flow(flow_builder: FlowBuilder, data_scope: DataScope) -> None:
    """Graphiti-compliant Huly to FalkorDB flow."""
    
    # Add source for Huly JSON files
    data_scope["documents"] = flow_builder.add_source(
        cocoindex.sources.LocalFile(
            path=os.environ.get("HULY_EXPORT_PATH", "huly_export_full"),
            included_patterns=["*.json"]
        ),
        refresh_interval=timedelta(minutes=2)
    )
    
    # Process each document
    with data_scope["documents"].row() as doc:
        # Parse JSON content
        doc["parsed"] = doc["content"].transform(cocoindex.functions.ParseJson())
        
        # Extract metadata from raw content
        doc["metadata"] = doc["content"].transform(extract_huly_metadata)
        
        # Log processing start
        doc["logged"] = doc["metadata"].transform(log_processing_start)
        
        # Extract clean text content
        doc["full_content"] = doc["metadata"].transform(extract_text_content)
        
        # Extract comprehensive analysis using Ollama
        doc["analysis"] = doc["full_content"].transform(
            cocoindex.functions.ExtractByLlm(
                llm_spec=cocoindex.LlmSpec(
                    api_type=cocoindex.LlmApiType.OLLAMA,
                    model="gemma3:12b",
                    address=os.environ.get("OLLAMA_URL", "http://100.81.139.20:11434")
                ),
                output_type=HulyAnalysis,
                instruction="""
                You are an expert knowledge graph entity extractor for project management data. Analyze this Huly project/issue data and extract:

                1. **Entities** (5-15 key concepts):
                   - TECHNOLOGY: Docker, GitHub Actions, Redis, FalkorDB, etc.
                   - COMPONENT: Pipeline, Container, Registry, Database, etc.
                   - CONCEPT: CI/CD, Deployment, Integration, Automation, etc.
                   - ORGANIZATION: GitHub, Project teams, etc.
                   - PROJECT: Applications, Services, Tools, etc.
                   - MILESTONE: Releases, Versions, Deadlines, etc.
                   - PERSON: Developers, Users, Stakeholders, etc.

                2. **Relationships** (3-8 connections):
                   - How technologies work together
                   - Process flows and dependencies
                   - Component interactions
                   - Deployment relationships

                3. **Summary**: Brief description of the issue/project content.

                Focus on technical entities and meaningful relationships. Normalize entity names to lowercase.
                Return a complete HulyAnalysis with summary, entities, and relationships.
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
    print("Graphiti-Compliant Huly to FalkorDB Flow")
    print("=" * 45)
    print("✅ Full Graphiti schema compliance")
    print("✅ Deterministic UUID generation")
    print("✅ Episodic nodes with all required fields")
    print("✅ Entity nodes with summary field")
    print("✅ Proper relationship UUIDs")
    print("\nRun with: cocoindex update --setup flows/huly_graphiti_compliant.py")
