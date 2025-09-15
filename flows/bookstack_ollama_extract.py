#!/usr/bin/env python3
"""
BookStack to FalkorDB pipeline with Ollama Gemma3 12B using CocoIndex ExtractByLlm.
Following the exact pattern from CocoIndex documentation.
"""

import os
import uuid
from datetime import timedelta
import dataclasses
from typing import List

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

# --- Helper functions ---
@cocoindex.op.function()
def html_to_text(body_html: str) -> str:
    """Convert HTML to clean text."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(body_html, "html.parser")
    
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
def generate_doc_uuid(page_id: str) -> str:
    """Generate deterministic UUID for document."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"doc:{page_id}"))

@cocoindex.op.function()
def generate_entity_uuid(entity_name: str, group_id: str) -> str:
    """Generate deterministic UUID for entity."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"ent:{entity_name.lower()}:{group_id}"))

@cocoindex.op.function()
def slugify(text: str) -> str:
    """Convert text to slug."""
    return text.lower().replace(" ", "-").replace("_", "-")

@cocoindex.op.function()
def get_id(parsed: dict) -> str:
    """Extract ID from parsed JSON."""
    return str(parsed["id"])

@cocoindex.op.function()
def get_title(parsed: dict) -> str:
    """Extract title from parsed JSON."""
    return parsed.get("title", "Untitled")

@cocoindex.op.function()
def get_book(parsed: dict) -> str:
    """Extract book from parsed JSON."""
    return parsed.get("book", "Unknown")

@cocoindex.op.function()
def get_url(parsed: dict) -> str:
    """Extract URL from parsed JSON."""
    return parsed.get("url", "")

@cocoindex.op.function()
def get_tags(parsed: dict) -> List[str]:
    """Extract tags from parsed JSON."""
    return parsed.get("tags", [])

@cocoindex.op.function()
def get_body_html(parsed: dict) -> str:
    """Extract and convert body HTML to text."""
    return html_to_text(parsed.get("body_html", ""))

# --- FalkorDB Connection ---
try:
    falkor_conn_spec = cocoindex.add_auth_entry(
        "FalkorDBGemma",
        cocoindex.targets.Neo4jConnection(
            uri=f"bolt://{os.environ.get('FALKOR_HOST', 'localhost')}:{os.environ.get('FALKOR_PORT', '6379')}",
            user="",
            password="",
        ),
    )
    use_falkor = True
except Exception as e:
    print(f"FalkorDB connection setup failed: {e}")
    use_falkor = False

# --- Main CocoIndex Flow ---
@cocoindex.flow_def(name="BookStackOllamaExtract")
def bookstack_ollama_extract_flow(flow_builder: FlowBuilder, data_scope: DataScope) -> None:
    """BookStack to FalkorDB flow using Ollama Gemma3 12B with ExtractByLlm."""
    
    # Add source for BookStack JSON files
    data_scope["documents"] = flow_builder.add_source(
        cocoindex.sources.LocalFile(
            path="bookstack_export_full", 
            included_patterns=["*.json"]
        ),
        refresh_interval=timedelta(minutes=2)
    )
    
    # Add collectors
    episodic_nodes = data_scope.add_collector()
    entity_nodes = data_scope.add_collector()
    mentions_edges = data_scope.add_collector()
    relates_edges = data_scope.add_collector()
    
    # Process each document
    with data_scope["documents"].row() as doc:
        # Parse JSON
        doc["parsed"] = doc["content"].transform(cocoindex.functions.ParseJson())
        
        # Extract fields using transform functions
        doc["page_id"] = doc["parsed"].transform(get_id)
        doc["title"] = doc["parsed"].transform(get_title)
        doc["book"] = doc["parsed"].transform(get_book)
        doc["url"] = doc["parsed"].transform(get_url)
        doc["tags"] = doc["parsed"].transform(get_tags)
        
        # Convert HTML to text
        doc["text_content"] = doc["parsed"].transform(get_body_html)
        
        # Extract document analysis using Ollama Gemma3 12B
        doc["analysis"] = doc["text_content"].transform(
            cocoindex.functions.ExtractByLlm(
                llm_spec=cocoindex.LlmSpec(
                    api_type=cocoindex.LlmApiType.OLLAMA,
                    model="gemma3:12b"
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

                3. SUMMARY: Create a brief 2-3 sentence summary.

                Focus on technical and domain-specific entities. Normalize entity names to lowercase.
                """
            )
        )
        
        # Generate IDs
        doc["doc_uuid"] = doc["page_id"].transform(generate_doc_uuid)
        doc["group_id"] = doc["book"].transform(slugify)
        
        # Collect Episodic node
        episodic_nodes.collect(
            uuid=doc["doc_uuid"],
            name=doc["title"],
            content=doc["text_content"],
            summary=doc["analysis"]["summary"],
            source="BookStack",
            source_description=doc["book"],
            group_id=doc["group_id"]
        )
        
        # Process entities from analysis
        with doc["analysis"]["entities"].row() as entity:
            entity_uuid = cocoindex.GeneratedField.UUID
            
            # Collect entity node
            entity_nodes.collect(
                uuid=entity_uuid,
                name=entity["name"],
                labels=[entity["type"]],
                summary=entity["description"],
                group_id=doc["group_id"]
            )
            
            # Create MENTIONS relationship
            mentions_edges.collect(
                uuid=cocoindex.GeneratedField.UUID,
                source_uuid=doc["doc_uuid"],
                target_uuid=entity_uuid,
                group_id=doc["group_id"]
            )
        
        # Process relationships from analysis
        with doc["analysis"]["relationships"].row() as rel:
            relates_edges.collect(
                uuid=cocoindex.GeneratedField.UUID,
                name=rel["predicate"],
                fact=rel["fact"],
                source_name=rel["subject"],
                target_name=rel["object"],
                group_id=doc["group_id"]
            )
    
    # Export to FalkorDB if available
    if use_falkor:
        # Export Episodic nodes
        episodic_nodes.export(
            "episodic_nodes",
            cocoindex.targets.Neo4j(
                connection=falkor_conn_spec,
                mapping=cocoindex.targets.Nodes(label="Episodic")
            ),
            primary_key_fields=["uuid"]
        )
        
        # Export Entity nodes
        entity_nodes.export(
            "entity_nodes",
            cocoindex.targets.Neo4j(
                connection=falkor_conn_spec,
                mapping=cocoindex.targets.Nodes(label="Entity")
            ),
            primary_key_fields=["name", "group_id"]
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
                    )
                )
            ),
            primary_key_fields=["uuid"]
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
                        fields=[
                            cocoindex.targets.TargetFieldMapping("source_name", "name"),
                            cocoindex.targets.TargetFieldMapping("group_id", "group_id")
                        ]
                    ),
                    target=cocoindex.targets.NodeFromFields(
                        label="Entity",
                        fields=[
                            cocoindex.targets.TargetFieldMapping("target_name", "name"),
                            cocoindex.targets.TargetFieldMapping("group_id", "group_id")
                        ]
                    )
                )
            ),
            primary_key_fields=["uuid"]
        )
    else:
        # Fallback to PostgreSQL
        episodic_nodes.export(
            "bookstack_ollama_episodic",
            cocoindex.targets.Postgres(),
            primary_key_fields=["uuid"]
        )

if __name__ == "__main__":
    print("BookStack to FalkorDB with Ollama Gemma3 12B ExtractByLlm")
    print("=" * 60)
    print("Using proper CocoIndex ExtractByLlm pattern from documentation")
    print("Run with: python run_cocoindex.py update --setup flows/bookstack_ollama_extract.py")