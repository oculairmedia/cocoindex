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
    return datetime.now(timezone.utc).isoformat()

def normalize_entity_name(name: str) -> str:
    """Normalize entity names for consistency."""
    return name.lower().strip()

def create_group_id(project_name: str) -> str:
    """Create group_id from project name."""
    if not project_name:
        return "huly-default"
    return f"huly-{project_name.lower().replace(' ', '-').replace('_', '-')}"

def safe_cypher_string(text: str) -> str:
    """Make string safe for Cypher queries."""
    if not text:
        return ""
    return text.replace("'", "\\'").replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r')

# --- CocoIndex transform functions ---
@cocoindex.op.function()
def extract_huly_metadata(content: str) -> Dict[str, Any]:
    """Extract metadata from Huly JSON content."""
    try:
        data = json.loads(content) if isinstance(content, str) else content
        
        return {
            "type": data.get("type", "unknown"),
            "id": data.get("id", ""),
            "name": data.get("name", data.get("title", "")),
            "description": data.get("description", ""),
            "project_id": data.get("project_id", ""),
            "status": data.get("status", ""),
            "priority": data.get("priority", ""),
            "component": data.get("component", ""),
            "milestone": data.get("milestone", ""),
            "raw_data": data.get("raw_data", {})
        }
    except Exception as e:
        logger.error(f"Error extracting Huly metadata: {e}")
        return {
            "type": "unknown",
            "id": "",
            "name": "",
            "description": "",
            "project_id": "",
            "status": "",
            "priority": "",
            "component": "",
            "milestone": "",
            "raw_data": {}
        }

@cocoindex.op.function()
def extract_text_content(metadata: Dict[str, Any]) -> str:
    """Extract clean text content from Huly data."""
    content_parts = []
    
    # Add title/name
    if metadata.get("name"):
        content_parts.append(f"Title: {metadata['name']}")
    
    # Add description
    if metadata.get("description"):
        content_parts.append(f"Description: {metadata['description']}")
    
    # Add project context
    if metadata.get("project_id"):
        content_parts.append(f"Project: {metadata['project_id']}")
    
    # Add status and priority
    if metadata.get("status"):
        content_parts.append(f"Status: {metadata['status']}")
    if metadata.get("priority"):
        content_parts.append(f"Priority: {metadata['priority']}")
    
    # Add component and milestone
    if metadata.get("component"):
        content_parts.append(f"Component: {metadata['component']}")
    if metadata.get("milestone"):
        content_parts.append(f"Milestone: {metadata['milestone']}")
    
    return "\n".join(content_parts)

@cocoindex.op.function()
def log_processing_start(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Log when starting to process a Huly item."""
    name = metadata.get("name", "Untitled")
    item_type = metadata.get("type", "unknown")
    item_id = metadata.get("id", "unknown")
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
def export_to_falkor_graphiti(analysis: HulyAnalysis, metadata: Dict[str, Any], full_content: str) -> HulyAnalysis:
    """Export analysis results to FalkorDB with full Graphiti schema compliance."""
    falkor = get_falkor_connection()
    if not falkor:
        logger.error("❌ No FalkorDB connection available")
        return analysis

    graph_name = os.environ.get('FALKOR_GRAPH', 'graphiti_migration')
    
    try:
        # Create group_id based on project
        project_name = metadata.get("project_id") or metadata.get("name", "")
        group_id = create_group_id(project_name)
        
        # Generate deterministic UUID for episodic node
        item_id = metadata.get("id", str(uuid.uuid4()))
        episodic_uuid = generate_deterministic_uuid("huly-episodic", item_id)
        
        # Create Episodic node (Graphiti compliant)
        title = safe_cypher_string(metadata.get("name", "Untitled"))
        content = safe_cypher_string(full_content)
        content_type = metadata.get("type", "unknown")
        
        episodic_cypher = f"""
        MERGE (e:Episodic {{uuid: '{episodic_uuid}'}})
        ON CREATE SET e.name = '{title}',
                     e.group_id = '{group_id}',
                     e.source = 'huly',
                     e.source_description = 'Huly project management data',
                     e.created_at = timestamp()
        SET e.content = '{content}',
            e.valid_at = timestamp(),
            e.huly_type = '{content_type}',
            e.huly_id = '{safe_cypher_string(item_id)}',
            e.project_id = '{safe_cypher_string(metadata.get("project_id", ""))}',
            e.status = '{safe_cypher_string(metadata.get("status", ""))}',
            e.priority = '{safe_cypher_string(metadata.get("priority", ""))}'
        RETURN e.uuid
        """
        
        falkor.execute_command('GRAPH.QUERY', graph_name, episodic_cypher)
        logger.info(f"📄 Created Episodic node: {title[:50]}...")
        
        # Create Entity nodes with Graphiti compliance
        for entity in analysis.entities:
            entity_name = normalize_entity_name(entity.name)
            entity_summary = safe_cypher_string(entity.description)  # Use description as summary
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
@cocoindex.flow_def(name="HulyGraphitiCompliant")
def huly_graphiti_flow(flow_builder: FlowBuilder, data_scope: DataScope) -> None:
    """Graphiti-compliant Huly to FalkorDB flow."""
    
    # Add source for Huly JSON files
    data_scope["documents"] = flow_builder.add_source(
        cocoindex.sources.LocalFile(
            path="huly_export_mock",  # Will be changed to huly_export_full when API works
            included_patterns=["*.json"]
        ),
        refresh_interval=timedelta(minutes=2)
    )
    
    # Process each document
    with data_scope["documents"].row() as doc:
        # Parse JSON content
        doc["parsed"] = doc["content"].transform(cocoindex.functions.ParseJson())
        
        # Extract metadata
        doc["metadata"] = doc["parsed"].transform(extract_huly_metadata)
        
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
