"""
Live BookStack to FalkorDB sync with CocoIndex
Continuously monitors BookStack API and syncs to Graphiti-compatible schema
Based on the enhanced pipeline documentation and CocoIndex patterns
"""

import os
import dataclasses
import requests
from datetime import timedelta
from typing import List, Optional

import cocoindex
from cocoindex import DataScope, FlowBuilder

# Configuration from environment
BOOKSTACK_URL = os.environ.get("BS_URL", "https://knowledge.oculair.ca")
BOOKSTACK_TOKEN_ID = os.environ.get("BS_TOKEN_ID", "POnHR9Lbvm73T2IOcyRSeAqpA8bSGdMT")
BOOKSTACK_TOKEN_SECRET = os.environ.get("BS_TOKEN_SECRET", "735wM5dScfUkcOy7qcrgqQ1eC5fBF7IE")

# Data structures for LLM extraction (following docs example)
@dataclasses.dataclass
class Entity:
    """An entity extracted from content."""
    name: str
    type: str  # PERSON, ORGANIZATION, CONCEPT, TECHNOLOGY, LOCATION
    description: str

@dataclasses.dataclass
class Relationship:
    """
    Describe a relationship between two entities.
    Subject and object should be core concepts from BookStack content.
    """
    subject: str
    predicate: str
    object: str
    fact: str  # Supporting evidence/context

@dataclasses.dataclass 
class DocumentSummary:
    """Summary of a BookStack page."""
    title: str
    summary: str
    key_topics: List[str]

# Custom source for BookStack API
@cocoindex.op.source_connector()
class BookStackAPISource:
    """Source connector for BookStack API."""
    
    def __init__(self, refresh_interval: timedelta = timedelta(minutes=5)):
        self.refresh_interval = refresh_interval
        self.headers = {
            "Authorization": f"Token {BOOKSTACK_TOKEN_ID}:{BOOKSTACK_TOKEN_SECRET}",
            "Accept": "application/json"
        }
    
    def get_items(self) -> List[dict]:
        """Fetch all pages from BookStack API."""
        all_pages = []
        offset = 0
        count = 50
        
        while True:
            url = f"{BOOKSTACK_URL}/api/pages?count={count}&offset={offset}"
            
            try:
                response = requests.get(url, headers=self.headers, timeout=15)
                response.raise_for_status()
                data = response.json()
                pages = data.get('data', [])
                
                if not pages:
                    break
                
                # Get detailed data for each page
                for page_summary in pages:
                    page_id = page_summary['id']
                    detail_url = f"{BOOKSTACK_URL}/api/pages/{page_id}?include=book,chapter,tags"
                    detail_response = requests.get(detail_url, headers=self.headers, timeout=10)
                    
                    if detail_response.status_code == 200:
                        page_detail = detail_response.json()
                        
                        # Transform to our schema
                        page_data = {
                            "id": str(page_detail['id']),
                            "title": page_detail.get('name', 'Untitled'),
                            "content": page_detail.get('html', ''),
                            "book": page_detail.get('book', {}).get('name', 'Unknown'),
                            "chapter": page_detail.get('chapter', {}).get('name', '') if page_detail.get('chapter') else "",
                            "tags": [tag['name'] for tag in page_detail.get('tags', [])],
                            "url": f"{BOOKSTACK_URL}/books/{page_detail.get('book_slug', 'unknown')}/page/{page_detail.get('slug', page_detail['id'])}",
                            "updated_at": page_detail.get('updated_at', ''),
                            "filename": f"page_{page_id}.json"  # For compatibility
                        }
                        all_pages.append(page_data)
                
                offset += len(pages)
                
                # Break if we got less than requested (last page)
                if len(pages) < count:
                    break
                    
            except Exception as e:
                print(f"Error fetching BookStack pages: {e}")
                break
        
        return all_pages

# Helper functions
@cocoindex.op.function()
def html_to_text(html_content: str) -> str:
    """Convert HTML to clean text."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html_content, "html.parser")
    
    # Remove script and style elements
    for script in soup(["script", "style"]):
        script.decompose()
    
    # Get text with proper spacing
    text = soup.get_text(separator="\n", strip=True)
    
    # Clean up whitespace
    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    text = "\n".join(chunk for chunk in chunks if chunk)
    
    return text

# FalkorDB connection setup (Graphiti-compatible)
falkor_conn_spec = cocoindex.add_auth_entry(
    "FalkorDBConnection",
    cocoindex.targets.Neo4jConnection(  # FalkorDB is Neo4j-compatible
        uri=f"bolt://{os.environ.get('FALKOR_HOST', 'localhost')}:{os.environ.get('FALKOR_PORT', '6379')}",
        user="",  # FalkorDB doesn't require auth by default
        password="",
    ),
)

# Main flow definition
@cocoindex.flow_def(name="BookStackLiveSync")
def bookstack_live_sync(flow_builder: FlowBuilder, data_scope: DataScope) -> None:
    """Live sync from BookStack to FalkorDB with Graphiti schema."""
    
    # Add BookStack API source with continuous monitoring
    data_scope["pages"] = flow_builder.add_source(
        BookStackAPISource(),
        refresh_interval=timedelta(minutes=5)  # Check every 5 minutes
    )
    
    # Add collectors (following docs pattern)
    document_node = data_scope.add_collector()
    entity_relationship = data_scope.add_collector()
    entity_mention = data_scope.add_collector()
    
    # Process each page
    with data_scope["pages"].row() as page:
        # Convert HTML to text for processing
        page["text_content"] = page["content"].transform(html_to_text)
        
        # Extract document summary using LLM
        page["summary"] = page["text_content"].transform(
            cocoindex.functions.ExtractByLlm(
                llm_spec=cocoindex.LlmSpec(
                    api_type=cocoindex.LlmApiType.OPENAI, 
                    model="gpt-4o"
                ),
                output_type=DocumentSummary,
                instruction="Summarize this BookStack page content, identifying key topics and concepts."
            )
        )
        
        # Extract entities and relationships using LLM
        page["entities"] = page["text_content"].transform(
            cocoindex.functions.ExtractByLlm(
                llm_spec=cocoindex.LlmSpec(
                    api_type=cocoindex.LlmApiType.OPENAI,
                    model="gpt-4o"
                ),
                output_type=List[Entity],
                instruction="Extract named entities (people, organizations, technologies, concepts, locations) from this content."
            )
        )
        
        page["relationships"] = page["text_content"].transform(
            cocoindex.functions.ExtractByLlm(
                llm_spec=cocoindex.LlmSpec(
                    api_type=cocoindex.LlmApiType.OPENAI,
                    model="gpt-4o"
                ),
                output_type=List[Relationship],
                instruction="Extract relationships between entities mentioned in this content. Focus on meaningful connections."
            )
        )
        
        # Collect document nodes (Episodic in Graphiti schema)
        document_node.collect(
            uuid=page["id"],  # Use page ID as UUID
            name=page["summary"]["title"],
            content=page["text_content"],
            group_id=page["book"],
            valid_at=page["updated_at"],
            source="BookStack",
            source_description=page["url"],
            filename=page["filename"]  # For tracking
        )
        
        # Collect entity relationships
        with page["relationships"].row() as relationship:
            entity_relationship.collect(
                id=cocoindex.GeneratedField.UUID,
                subject=relationship["subject"],
                object=relationship["object"],
                predicate=relationship["predicate"],
                fact=relationship["fact"],
                group_id=page["book"]
            )
            
            # Collect entity mentions for both subject and object
            entity_mention.collect(
                id=cocoindex.GeneratedField.UUID,
                entity=relationship["subject"],
                document_id=page["id"],
                group_id=page["book"]
            )
            entity_mention.collect(
                id=cocoindex.GeneratedField.UUID,
                entity=relationship["object"],
                document_id=page["id"],
                group_id=page["book"]
            )
        
        # Collect individual entities
        with page["entities"].row() as entity:
            entity_mention.collect(
                id=cocoindex.GeneratedField.UUID,
                entity=entity["name"],
                document_id=page["id"],
                group_id=page["book"]
            )
    
    # Export to FalkorDB using Graphiti-compatible schema
    
    # Export Episodic nodes (Documents)
    document_node.export(
        "episodic_nodes",
        cocoindex.targets.Neo4j(
            connection=falkor_conn_spec,
            mapping=cocoindex.targets.Nodes(label="Episodic")
        ),
        primary_key_fields=["uuid"]
    )
    
    # Declare Entity nodes
    flow_builder.declare(
        cocoindex.targets.Neo4jDeclaration(
            connection=falkor_conn_spec,
            nodes_label="Entity",
            primary_key_fields=["name", "group_id"],
        )
    )
    
    # Export entity relationships
    entity_relationship.export(
        "entity_relationships",
        cocoindex.targets.Neo4j(
            connection=falkor_conn_spec,
            mapping=cocoindex.targets.Relationships(
                rel_type="RELATES_TO",
                source=cocoindex.targets.NodeFromFields(
                    label="Entity",
                    fields=[
                        cocoindex.targets.TargetFieldMapping(source="subject", target="name"),
                        cocoindex.targets.TargetFieldMapping(source="group_id", target="group_id"),
                    ]
                ),
                target=cocoindex.targets.NodeFromFields(
                    label="Entity",
                    fields=[
                        cocoindex.targets.TargetFieldMapping(source="object", target="name"),
                        cocoindex.targets.TargetFieldMapping(source="group_id", target="group_id"),
                    ]
                ),
            ),
        ),
        primary_key_fields=["id"],
    )
    
    # Export entity mentions (documents mentioning entities)
    entity_mention.export(
        "entity_mentions",
        cocoindex.targets.Neo4j(
            connection=falkor_conn_spec,
            mapping=cocoindex.targets.Relationships(
                rel_type="MENTIONS",
                source=cocoindex.targets.NodeFromFields(
                    label="Episodic",
                    fields=[
                        cocoindex.targets.TargetFieldMapping(source="document_id", target="uuid"),
                    ]
                ),
                target=cocoindex.targets.NodeFromFields(
                    label="Entity",
                    fields=[
                        cocoindex.targets.TargetFieldMapping(source="entity", target="name"),
                        cocoindex.targets.TargetFieldMapping(source="group_id", target="group_id"),
                    ]
                ),
            ),
        ),
        primary_key_fields=["id"],
    )

if __name__ == "__main__":
    print("BookStack Live Sync Flow defined!")
    print(f"Will sync from: {BOOKSTACK_URL}")
    print(f"To FalkorDB at: {os.environ.get('FALKOR_HOST', 'localhost')}:{os.environ.get('FALKOR_PORT', '6379')}")
    print("Run with: cocoindex update --setup flows/bookstack_live_sync.py")