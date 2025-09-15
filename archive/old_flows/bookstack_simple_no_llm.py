"""
Simple BookStack to FalkorDB sync without LLM processing for testing
"""

import os
import dataclasses
from datetime import timedelta

import cocoindex
from cocoindex import DataScope, FlowBuilder

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
    
    return text[:500]  # Limit for testing

@cocoindex.op.function()
def extract_html_content(parsed_json: dict) -> str:
    """Extract and convert HTML content to text from parsed JSON."""
    return html_to_text(parsed_json.get("body_html", ""))

@cocoindex.op.function()
def extract_title(parsed_json: dict) -> str:
    """Extract title from parsed JSON."""
    return parsed_json.get("title", "Untitled")

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

# Main flow definition 
@cocoindex.flow_def(name="BookStackToKGSimple")
def docs_to_kg_flow(flow_builder: FlowBuilder, data_scope: DataScope) -> None:
    """BookStack documents to knowledge graph without LLM processing."""
    
    # Add documents as source (just first 5 files for testing)
    data_scope["documents"] = flow_builder.add_source(
        cocoindex.sources.LocalFile(
            path="bookstack_export_full",
            included_patterns=["*.json"]
        ),
        refresh_interval=timedelta(minutes=2)
    )
    
    # Add data collectors
    document_node = data_scope.add_collector()
    
    # Process each document
    with data_scope["documents"].row() as doc:
        # Parse the JSON content
        doc["parsed"] = doc["content"].transform(cocoindex.functions.ParseJson())
        
        # Convert HTML to text 
        doc["text_content"] = doc["parsed"].transform(extract_html_content)
        
        # Collect document node with basic info
        document_node.collect(
            filename=doc["filename"],
            title=doc["parsed"].transform(extract_title),
            content=doc["text_content"], 
            book=doc["parsed"].transform(extract_book_name),
            url=doc["parsed"].transform(extract_url)
        )
    
    # Export to FalkorDB
    if use_falkor:
        # Export Document nodes
        document_node.export(
            "document_node",
            cocoindex.targets.Neo4j(
                connection=falkor_conn_spec,
                mapping=cocoindex.targets.Nodes(label="Document")
            ),
            primary_key_fields=["filename"],
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
    print("Simple BookStack to Knowledge Graph Flow defined!")
    print("Run with: cocoindex update --setup flows/bookstack_simple_no_llm.py")