#!/usr/bin/env python3
"""
Test the enhanced BookStack to FalkorDB pipeline with CocoIndex ExtractByLlm
for entity and relationship extraction
"""

import os
import re
import json
import uuid
import dataclasses
from pathlib import Path

# Set dry run mode
os.environ["DRY_RUN"] = "true"

# Import CocoIndex for LLM extraction
try:
    import cocoindex
    import cocoindex.functions
    COCOINDEX_AVAILABLE = True
    print("✅ CocoIndex imported successfully")
except ImportError as e:
    COCOINDEX_AVAILABLE = False
    print(f"❌ CocoIndex not available: {e}")

# Define data structures for extraction
@dataclasses.dataclass
class Entity:
    """An entity extracted from content."""
    name: str
    type: str  # PERSON, ORGANIZATION, CONCEPT, TECHNOLOGY, LOCATION, etc.
    description: str

@dataclasses.dataclass
class Relationship:
    """A relationship between two entities."""
    subject: str
    predicate: str
    object: str
    fact: str  # Supporting evidence/context

# Copy the helper functions from the original test
def html_to_text(html: str) -> str:
    from bs4 import BeautifulSoup
    return BeautifulSoup(html or "", "html.parser").get_text("\n")

def uuid5_ns(*parts: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "::".join(parts)))

def slugify(s: str) -> str:
    if not s:
        return "default"
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "default"

def normalize_entity_name(name: str) -> str:
    """Normalize entity names for deduplication"""
    return name.lower().strip()

def embed_qwen3(text: str) -> list[float]:
    print(f"[DRY RUN] Embedding text: {text[:100]}{'...' if len(text) > 100 else ''}")
    # Return fake 2560-dimensional embedding
    return [0.1] * 2560

# Enhanced Cypher templates for entities and relationships
Q_DOC = (
    "MERGE (d:Episodic {uuid:$doc_uuid})\n"
    "ON CREATE SET d.created_at=datetime()\n"
    "SET d.name=$title, d.content=$content, d.group_id=$gid,\n"
    "    d.valid_at=datetime($updated_at), d.source='text', d.source_description=$url,\n"
    "    d.name_embedding=$title_emb"
)

Q_ENT = (
    "MERGE (e:Entity {name:$ename, group_id:$gid})\n"
    "ON CREATE SET e.uuid=$e_uuid, e.created_at=datetime(), e.labels=['Entity'], e.name_embedding=$e_emb\n"
    "SET e.entity_type=$entity_type, e.description=$description"
)

Q_MENT = (
    "MATCH (d:Episodic {uuid:$doc_uuid}),(e:Entity {name:$ename,group_id:$gid})\n"
    "MERGE (d)-[r:MENTIONS {group_id:$gid}]->(e)\n"
    "ON CREATE SET r.uuid=$m_uuid, r.created_at=datetime()"
)

Q_REL = (
    "MATCH (e1:Entity {name:$subject, group_id:$gid}), (e2:Entity {name:$object, group_id:$gid})\n"
    "MERGE (e1)-[r:RELATES_TO {predicate:$predicate, group_id:$gid}]->(e2)\n"
    "ON CREATE SET r.uuid=$rel_uuid, r.created_at=datetime()\n"
    "SET r.fact=$fact, r.fact_embedding=$fact_emb"
)

_TAG_EMB_CACHE = {}
_ENTITY_EMB_CACHE = {}

def _embed_tag_cached(tag: str) -> list[float]:
    e = _TAG_EMB_CACHE.get(tag)
    if e is not None:
        return e
    e = embed_qwen3(tag)
    _TAG_EMB_CACHE[tag] = e
    return e

def _embed_entity_cached(entity_name: str) -> list[float]:
    e = _ENTITY_EMB_CACHE.get(entity_name)
    if e is not None:
        return e
    e = embed_qwen3(entity_name)
    _ENTITY_EMB_CACHE[entity_name] = e
    return e

def fake_query(cypher: str, params: dict = None):
    """Simulate database query with logging"""
    print(f"[DRY RUN] GRAPH.QUERY graphiti_migration")
    print(f"[DRY RUN] Cypher: {cypher}")
    if params:
        print(f"[DRY RUN] Params: {json.dumps(params, indent=2, default=str)}")
    print("-" * 60)

def deduplicate_entities_per_document(entities: list[Entity]) -> list[Entity]:
    """Deduplicate entities within a single document by normalized name"""
    seen = {}
    for entity in entities:
        key = normalize_entity_name(entity.name)
        if key not in seen:
            seen[key] = entity
        else:
            # Keep the entity with the longer description
            if len(entity.description) > len(seen[key].description):
                seen[key] = entity
    return list(seen.values())

def deduplicate_relationships_per_document(relationships: list[Relationship]) -> list[Relationship]:
    """Deduplicate relationships within a single document"""
    seen = {}
    for rel in relationships:
        # Normalize subject and object names for comparison
        subject_norm = normalize_entity_name(rel.subject)
        object_norm = normalize_entity_name(rel.object)
        predicate_norm = rel.predicate.lower().strip()

        key = (subject_norm, predicate_norm, object_norm)
        if key not in seen:
            seen[key] = rel
        else:
            # Keep the relationship with the longer fact description
            if len(rel.fact) > len(seen[key].fact):
                seen[key] = rel
    return list(seen.values())

def extract_entities_with_llm(content: str) -> list[Entity]:
    """Extract entities using CocoIndex ExtractByLlm or fallback to mock data"""
    if not COCOINDEX_AVAILABLE:
        print("[FALLBACK] Using mock entity extraction")
        # Return some mock entities for testing (with some duplicates to test deduplication)
        raw_entities = [
            Entity(name="Machine Learning", type="CONCEPT", description="A field of artificial intelligence"),
            Entity(name="machine learning", type="CONCEPT", description="AI field focused on learning from data"),  # Duplicate with different case
            Entity(name="Python", type="TECHNOLOGY", description="Programming language"),
            Entity(name="Data Science", type="CONCEPT", description="Interdisciplinary field using scientific methods"),
            Entity(name="PYTHON", type="TECHNOLOGY", description="High-level programming language")  # Duplicate with different case
        ]
        # Apply deduplication
        return deduplicate_entities_per_document(raw_entities)

    try:
        # Use CocoIndex ExtractByLlm for real entity extraction
        print("[LLM] Extracting entities from content...")

        # Create a mock transform operation (in real CocoIndex flow this would be different)
        # For testing, we'll simulate the LLM extraction
        instruction = (
            "Extract named entities from this text. Focus on:\n"
            "- PERSON: People, authors, researchers\n"
            "- ORGANIZATION: Companies, institutions\n"
            "- CONCEPT: Technical concepts, methodologies\n"
            "- TECHNOLOGY: Tools, frameworks, programming languages\n"
            "- LOCATION: Places, regions\n"
            "Provide a brief description for each entity."
        )

        print(f"[LLM] Instruction: {instruction}")
        print(f"[LLM] Content preview: {content[:200]}...")

        # For now, return mock data since we can't easily test LLM extraction outside a flow
        raw_entities = [
            Entity(name="BookStack", type="TECHNOLOGY", description="Knowledge management platform"),
            Entity(name="FalkorDB", type="TECHNOLOGY", description="Graph database system"),
            Entity(name="Documentation", type="CONCEPT", description="Written material providing information"),
            Entity(name="bookstack", type="TECHNOLOGY", description="Knowledge management system"),  # Duplicate test
        ]
        # Apply deduplication
        return deduplicate_entities_per_document(raw_entities)

    except Exception as e:
        print(f"[ERROR] LLM extraction failed: {e}")
        return []

def extract_relationships_with_llm(content: str, entities: list[Entity]) -> list[Relationship]:
    """Extract relationships using CocoIndex ExtractByLlm or fallback to mock data"""
    if not COCOINDEX_AVAILABLE or not entities:
        print("[FALLBACK] Using mock relationship extraction")
        raw_relationships = [
            Relationship(
                subject="BookStack",
                predicate="integrates_with",
                object="FalkorDB",
                fact="BookStack data can be exported to FalkorDB for graph analysis"
            ),
            Relationship(
                subject="bookstack",  # Duplicate with different case
                predicate="integrates_with",
                object="falkordb",
                fact="BookStack exports data to FalkorDB"  # Similar but different fact
            )
        ]
        return deduplicate_relationships_per_document(raw_relationships)

    try:
        print("[LLM] Extracting relationships from content...")

        entity_names = [e.name for e in entities]
        instruction = (
            f"Extract relationships between these entities: {entity_names}\n"
            "Focus on how they relate to each other in the context of this text.\n"
            "Provide supporting evidence (fact) for each relationship."
        )

        print(f"[LLM] Instruction: {instruction}")

        # Mock relationships for testing (with some duplicates)
        raw_relationships = []
        if len(entities) >= 2:
            raw_relationships = [
                Relationship(
                    subject=entities[0].name,
                    predicate="relates_to",
                    object=entities[1].name,
                    fact=f"Both {entities[0].name} and {entities[1].name} are mentioned in the same context"
                ),
                Relationship(
                    subject=entities[0].name.upper(),  # Test case variation
                    predicate="relates_to",
                    object=entities[1].name.lower(),
                    fact=f"{entities[0].name} and {entities[1].name} appear together"  # Similar relationship
                )
            ]

        return deduplicate_relationships_per_document(raw_relationships)

    except Exception as e:
        print(f"[ERROR] Relationship extraction failed: {e}")
        return []

def export_to_falkor_enhanced(page: dict, chunk_text: str) -> None:
    """Enhanced export with entity and relationship extraction"""
    # Prepare doc values
    gid = slugify(page.get("book", ""))
    doc_uuid = uuid5_ns("doc", str(page.get("id")))
    title = page.get("title") or "Untitled"
    url = page.get("url") or ""
    updated_at = page.get("updated_at") or "1970-01-01T00:00:00Z"

    # Embed title once per page
    title_emb = embed_qwen3(title)

    # Upsert document with this chunk content
    fake_query(Q_DOC, {
        "doc_uuid": doc_uuid,
        "title": title,
        "content": chunk_text,
        "gid": gid,
        "updated_at": updated_at,
        "url": url,
        "title_emb": title_emb,
    })

    # Extract entities from content using LLM
    print("\n🔍 EXTRACTING ENTITIES...")
    entities = extract_entities_with_llm(chunk_text)
    print(f"Found {len(entities)} entities")
    
    # Create entity nodes
    for entity in entities:
        # Use normalized name for database operations but keep original for display
        ename_normalized = normalize_entity_name(entity.name)
        ename_display = entity.name  # Keep original case for display
        e_uuid = uuid5_ns("ent", ename_normalized, gid)
        e_emb = _embed_entity_cached(ename_normalized)
        fake_query(Q_ENT, {
            "ename": ename_normalized,  # Use normalized name as key
            "gid": gid,
            "e_uuid": e_uuid,
            "e_emb": e_emb,
            "entity_type": entity.type,
            "description": entity.description
        })

        # Create mention relationship
        m_uuid = uuid5_ns("ment", doc_uuid, e_uuid)
        fake_query(Q_MENT, {
            "doc_uuid": doc_uuid,
            "gid": gid,
            "ename": ename_normalized,  # Use normalized name
            "m_uuid": m_uuid
        })

    # Extract relationships between entities
    print("\n🔗 EXTRACTING RELATIONSHIPS...")
    relationships = extract_relationships_with_llm(chunk_text, entities)
    print(f"Found {len(relationships)} relationships")
    
    # Create relationship edges
    for rel in relationships:
        # Normalize entity names for consistent relationships
        subject_normalized = normalize_entity_name(rel.subject)
        object_normalized = normalize_entity_name(rel.object)
        predicate_normalized = rel.predicate.lower().strip()

        rel_uuid = uuid5_ns("rel", subject_normalized, predicate_normalized, object_normalized, gid)
        fact_emb = embed_qwen3(rel.fact)
        fake_query(Q_REL, {
            "subject": subject_normalized,
            "object": object_normalized,
            "gid": gid,
            "rel_uuid": rel_uuid,
            "predicate": predicate_normalized,
            "fact": rel.fact,
            "fact_emb": fact_emb
        })

    # Also handle original tag-based entities
    print("\n🏷️  PROCESSING TAGS...")
    for tag in (page.get("tags") or []):
        ename_original = str(tag)
        ename_normalized = normalize_entity_name(ename_original)
        e_uuid = uuid5_ns("ent", ename_normalized, gid)
        e_emb = _embed_tag_cached(ename_normalized)
        fake_query(Q_ENT, {
            "ename": ename_normalized,
            "gid": gid,
            "e_uuid": e_uuid,
            "e_emb": e_emb,
            "entity_type": "TAG",
            "description": f"BookStack tag: {ename_original}"  # Keep original for description
        })
        m_uuid = uuid5_ns("ment", doc_uuid, e_uuid)
        fake_query(Q_MENT, {
            "doc_uuid": doc_uuid,
            "gid": gid,
            "ename": ename_normalized,
            "m_uuid": m_uuid
        })

def test_enhanced_pipeline():
    print("=== Testing Enhanced BookStack to FalkorDB Pipeline ===")
    print("🚀 With Entity & Relationship Extraction\n")
    
    # Process each JSON file
    for json_file in Path("bookstack_export").glob("*.json"):
        print(f"\n[FILE] Processing: {json_file.name}")
        
        # Load the page data
        with open(json_file, 'r', encoding='utf-8') as f:
            page = json.load(f)
        
        print(f"Title: {page.get('title', 'N/A')}")
        print(f"Tags: {page.get('tags', [])}")
        print(f"Book: {page.get('book', 'N/A')}")
        
        # Convert HTML to text
        html_content = page.get('body_html', '')
        text_content = html_to_text(html_content)
        print(f"Content length: {len(text_content)} chars")
        
        # Simulate chunking (simple version)
        chunk_size = 1200
        chunks = [text_content[i:i+chunk_size] for i in range(0, len(text_content), chunk_size-300)]
        print(f"Generated {len(chunks)} chunk(s)")
        
        # Process each chunk with enhanced extraction
        for i, chunk_text in enumerate(chunks):
            print(f"\n--- Processing Chunk {i+1} with Enhanced Extraction ---")
            export_to_falkor_enhanced(page, chunk_text.strip())
        
        print("\n" + "="*80)

if __name__ == "__main__":
    test_enhanced_pipeline()
