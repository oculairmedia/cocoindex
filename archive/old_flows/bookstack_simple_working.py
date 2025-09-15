"""
Simple BookStack to FalkorDB sync using CocoIndex
Uses the existing full export and proper CocoIndex patterns
"""

import os
import dataclasses
from datetime import timedelta
from typing import List

import cocoindex
from cocoindex import DataScope, FlowBuilder

# Data structures following the docs pattern
@dataclasses.dataclass
class DocumentSummary:
    """Summary of a BookStack page."""
    title: str
    summary: str

@dataclasses.dataclass
class Relationship:
    """A relationship between two entities."""
    subject: str
    predicate: str
    object: str

# Helper functions
@cocoindex.op.function()
def html_to_text(html_content: str) -> str:
    """Convert HTML to clean text."""
    from bs4 import BeautifulSoup
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
def extract_html_content(parsed_json: dict) -> str:
    """Extract and convert HTML content to text from parsed JSON."""
    return html_to_text(parsed_json.get("body_html", ""))

@cocoindex.op.function()
def extract_book_name(parsed_json: dict) -> str:
    """Extract book name from parsed JSON."""
    return parsed_json.get("book", "Unknown")

@cocoindex.op.function()
def extract_url(parsed_json: dict) -> str:
    """Extract URL from parsed JSON."""
    return parsed_json.get("url", "")

# FalkorDB connection setup
try:
    falkor_conn_spec = cocoindex.add_auth_entry(
        "FalkorDBConnection",
        cocoindex.targets.Neo4jConnection(
            uri=f"bolt://{os.environ.get('FALKOR_HOST', 'localhost')}:{os.environ.get('FALKOR_PORT', '6379')}",
            user="",
            password="",
        ),
    )
    use_falkor = True
except Exception as e:
    print(f"FalkorDB connection failed: {e}")
    use_falkor = False

# Main flow definition following the docs pattern exactly
@cocoindex.flow_def(name="BookStackToKG")
def docs_to_kg_flow(flow_builder: FlowBuilder, data_scope: DataScope) -> None:
    """BookStack documents to knowledge graph following CocoIndex docs pattern."""
    
    # Add documents as source
    data_scope["documents"] = flow_builder.add_source(
        cocoindex.sources.LocalFile(
            path="bookstack_export_full",
            included_patterns=["*.json"]
        ),
        refresh_interval=timedelta(minutes=2)  # Check for updates every 2 minutes
    )
    
    # Add data collectors
    document_node = data_scope.add_collector()
    entity_relationship = data_scope.add_collector()
    entity_mention = data_scope.add_collector()
    
    # Process each document
    with data_scope["documents"].row() as doc:
        # Parse the JSON content
        doc["parsed"] = doc["content"].transform(cocoindex.functions.ParseJson())
        
        # Convert HTML to text for LLM processing
        doc["text_content"] = doc["parsed"].transform(extract_html_content)
        
        # Extract summary using LLM
        doc["summary"] = doc["text_content"].transform(
            cocoindex.functions.ExtractByLlm(
                llm_spec=cocoindex.LlmSpec(
                    api_type=cocoindex.LlmApiType.OPENAI, 
                    model="gpt-4o"
                ),
                output_type=DocumentSummary,
                instruction="Please summarize the content of this BookStack document."
            )
        )
        
        # Extract relationships using LLM
        doc["relationships"] = doc["text_content"].transform(
            cocoindex.functions.ExtractByLlm(
                llm_spec=cocoindex.LlmSpec(
                    api_type=cocoindex.LlmApiType.OPENAI,
                    model="gpt-4o"
                ),
                output_type=List[Relationship],
                instruction=(
                    "Please extract relationships from this BookStack document. "
                    "Focus on concepts and technologies, ignore examples and code. "
                    "Subject and object should be core concepts from the content."
                )
            )
        )
        
        # Collect document node
        document_node.collect(
            filename=doc["filename"],
            title=doc["summary"]["title"],
            summary=doc["summary"]["summary"],
            book=doc["parsed"].transform(extract_book_name),
            url=doc["parsed"].transform(extract_url)
        )
        
        # Collect relationships and mentions
        with doc["relationships"].row() as relationship:
            # Relationship between two entities
            entity_relationship.collect(
                id=cocoindex.GeneratedField.UUID,
                subject=relationship["subject"],
                object=relationship["object"],
                predicate=relationship["predicate"],
            )
            
            # Mention of an entity in a document, for subject
            entity_mention.collect(
                id=cocoindex.GeneratedField.UUID,
                entity=relationship["subject"],
                filename=doc["filename"],
            )
            
            # Mention of an entity in a document, for object
            entity_mention.collect(
                id=cocoindex.GeneratedField.UUID,
                entity=relationship["object"],
                filename=doc["filename"],
            )
    
    # Build knowledge graph
    if use_falkor:
        # Export to FalkorDB using the exact pattern from docs
        
        # Export Document nodes
        document_node.export(
            "document_node",
            cocoindex.targets.Neo4j(
                connection=falkor_conn_spec,
                mapping=cocoindex.targets.Nodes(label="Document")
            ),
            primary_key_fields=["filename"],
        )
        
        # Declare Entity nodes
        flow_builder.declare(
            cocoindex.targets.Neo4jDeclaration(
                connection=falkor_conn_spec,
                nodes_label="Entity",
                primary_key_fields=["value"],
            )
        )
        
        # Export relationships
        entity_relationship.export(
            "entity_relationship",
            cocoindex.targets.Neo4j(
                connection=falkor_conn_spec,
                mapping=cocoindex.targets.Relationships(
                    rel_type="RELATIONSHIP",
                    source=cocoindex.targets.NodeFromFields(
                        label="Entity",
                        fields=[
                            cocoindex.targets.TargetFieldMapping(
                                source="subject", target="value"),
                        ]
                    ),
                    target=cocoindex.targets.NodeFromFields(
                        label="Entity",
                        fields=[
                            cocoindex.targets.TargetFieldMapping(
                                source="object", target="value"),
                        ]
                    ),
                ),
            ),
            primary_key_fields=["id"],
        )
        
        # Export mentions
        entity_mention.export(
            "entity_mention",
            cocoindex.targets.Neo4j(
                connection=falkor_conn_spec,
                mapping=cocoindex.targets.Relationships(
                    rel_type="MENTION",
                    source=cocoindex.targets.NodeFromFields(
                        label="Document",
                        fields=[cocoindex.targets.TargetFieldMapping("filename")],
                    ),
                    target=cocoindex.targets.NodeFromFields(
                        label="Entity",
                        fields=[
                            cocoindex.targets.TargetFieldMapping(
                                source="entity", target="value"),
                        ],
                    ),
                ),
            ),
            primary_key_fields=["id"],
        )
    else:
        # Fallback to PostgreSQL
        document_node.export(
            "bookstack_documents",
            cocoindex.targets.Postgres(
                connection=cocoindex.targets.PostgresConnection.from_sqlalchemy_url(
                    os.environ.get("COCOINDEX_DB", "postgresql://cocoindex:cocoindex@localhost:5433/cocoindex")
                ),
                primary_key_fields=["filename"]
            )
        )

if __name__ == "__main__":
    print("BookStack to Knowledge Graph Flow defined!")
    print("Based on CocoIndex docs pattern")
    print("Run with: cocoindex update --setup flows/bookstack_simple_working.py")