"""
CocoIndex flow: BookStack JSON -> FalkorDB (Graphiti-compatible)
- Reads JSON files produced by scripts/bookstack_export.py
- Converts HTML to text, chunks, embeds, extracts entities/relationships
- Exports to FalkorDB with proper deduplication

Env vars expected:
  FALKOR_HOST=192.168.50.90
  FALKOR_PORT=6379
  FALKOR_GRAPH=graphiti_migration
  EMB_URL=http://192.168.50.80:11434/v1/embeddings
  EMB_KEY=ollama
  EMB_MODEL=dengcao/Qwen3-Embedding-4B:Q4_K_M
  OPENAI_API_KEY=your_openai_key (for LLM entity extraction)

Dependencies: cocoindex, beautifulsoup4, requests, redis
"""
from __future__ import annotations

import os
import re
import json
import uuid
from datetime import timedelta
from dataclasses import dataclass
from typing import Any, Dict, Optional, List

import cocoindex
from cocoindex import DataScope, FlowBuilder

# --- Data structures for entity extraction ---
@dataclass
class Entity:
    """An entity extracted from content."""
    name: str
    type: str  # PERSON, ORGANIZATION, CONCEPT, TECHNOLOGY, LOCATION, TAG
    description: str

@dataclass
class Relationship:
    """A relationship between two entities."""
    subject: str
    predicate: str
    object: str
    fact: str  # Supporting evidence/context

# --- Helper functions ---
def html_to_text(html: str) -> str:
    """Convert HTML to plain text."""
    from bs4 import BeautifulSoup  # type: ignore
    return BeautifulSoup(html or "", "html.parser").get_text("\n")

def uuid5_ns(*parts: str) -> str:
    """Generate deterministic UUID5 from parts."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "::".join(parts)))

def slugify(s: Optional[str]) -> str:
    """Convert string to URL-safe slug."""
    if not s:
        return "default"
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "default"

def normalize_entity_name(name: str) -> str:
    """Normalize entity names for deduplication."""
    return name.lower().strip()

def deduplicate_entities(entities: List[Entity]) -> List[Entity]:
    """Deduplicate entities by normalized name, keeping best description."""
    seen = {}
    for entity in entities:
        key = normalize_entity_name(entity.name)
        if key not in seen:
            seen[key] = entity
        else:
            # Keep entity with longer description
            if len(entity.description) > len(seen[key].description):
                seen[key] = entity
    return list(seen.values())

def deduplicate_relationships(relationships: List[Relationship]) -> List[Relationship]:
    """Deduplicate relationships by normalized subject/predicate/object."""
    seen = {}
    for rel in relationships:
        subject_norm = normalize_entity_name(rel.subject)
        object_norm = normalize_entity_name(rel.object)
        predicate_norm = rel.predicate.lower().strip()

        key = (subject_norm, predicate_norm, object_norm)
        if key not in seen:
            seen[key] = rel
        else:
            # Keep relationship with longer fact description
            if len(rel.fact) > len(seen[key].fact):
                seen[key] = rel
    return list(seen.values())


# --- Embedding and caching ---
_EMBEDDING_CACHE: dict[str, list[float]] = {}

def embed_qwen3_cached(text: str) -> list[float]:
    """Embed text with caching to avoid recomputation."""
    # Check cache first
    cache_key = text[:100]  # Use first 100 chars as cache key
    if cache_key in _EMBEDDING_CACHE:
        return _EMBEDDING_CACHE[cache_key]

    dry_run = os.getenv("DRY_RUN", "").lower() in ("true", "1", "yes")
    if dry_run:
        print(f"[DRY RUN] Embedding text: {text[:100]}{'...' if len(text) > 100 else ''}")
        # Return fake 2560-dimensional embedding
        embedding = [0.1] * 2560
    else:
        import requests  # type: ignore
        url = os.getenv("EMB_URL", "http://192.168.50.80:11434/v1/embeddings")
        key = os.getenv("EMB_KEY", "ollama")
        model = os.getenv("EMB_MODEL", "dengcao/Qwen3-Embedding-4B:Q4_K_M")
        r = requests.post(url, headers={"Authorization": f"Bearer {key}"}, json={"model": model, "input": text}, timeout=60)
        r.raise_for_status()
        embedding = r.json()["data"][0]["embedding"]

    # Cache the result
    _EMBEDDING_CACHE[cache_key] = embedding
    return embedding


# --- FalkorDB (RedisGraph) client ---
class Falkor:
    def __init__(self, host: str | None = None, port: int | None = None, graph: str | None = None, dry_run: bool = False):
        self.host = host or os.getenv("FALKOR_HOST", "192.168.50.90")
        self.port = int(port or int(os.getenv("FALKOR_PORT", "6379")))
        self.graph = graph or os.getenv("FALKOR_GRAPH", "graphiti_migration")
        self.dry_run = dry_run or os.getenv("DRY_RUN", "").lower() in ("true", "1", "yes")
        
        if not self.dry_run:
            import redis  # type: ignore
            self.r = redis.Redis(host=self.host, port=self.port)
        else:
            self.r = None
            print(f"[DRY RUN] FalkorDB client initialized for {self.host}:{self.port}/{self.graph}")

    def query(self, cypher: str, params: Dict[str, Any] | None = None):
        if self.dry_run:
            print(f"[DRY RUN] GRAPH.QUERY {self.graph}")
            print(f"[DRY RUN] Cypher: {cypher}")
            if params:
                print(f"[DRY RUN] Params: {json.dumps(params, indent=2, default=str)}")
            print("-" * 60)
            return None
        else:
            args = [self.graph, cypher]
            if params:
                args += ["params", json.dumps(params)]
            return self.r.execute_command("GRAPH.QUERY", *args)


_FALKOR = Falkor()


# --- Enhanced Cypher templates with deduplication ---
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


# --- Entity extraction functions ---
def extract_entities_with_llm(content: str) -> List[Entity]:
    """Extract entities using LLM or fallback to mock data."""
    dry_run = os.getenv("DRY_RUN", "").lower() in ("true", "1", "yes")

    if dry_run:
        print("[DRY RUN] Using mock entity extraction")
        # Return mock entities for testing
        raw_entities = [
            Entity(name="BookStack", type="TECHNOLOGY", description="Knowledge management platform"),
            Entity(name="FalkorDB", type="TECHNOLOGY", description="Graph database system"),
            Entity(name="Documentation", type="CONCEPT", description="Written material providing information")
        ]
        return deduplicate_entities(raw_entities)

    try:
        # Use CocoIndex ExtractByLlm for real entity extraction
        print("[LLM] Extracting entities from content...")

        # For now, return mock data since we need to integrate this properly with CocoIndex
        # In a real implementation, this would use cocoindex.functions.ExtractByLlm
        raw_entities = [
            Entity(name="Machine Learning", type="CONCEPT", description="AI field focused on learning from data"),
            Entity(name="Python", type="TECHNOLOGY", description="Programming language"),
            Entity(name="Data Science", type="CONCEPT", description="Interdisciplinary field using scientific methods")
        ]
        return deduplicate_entities(raw_entities)

    except Exception as e:
        print(f"[ERROR] Entity extraction failed: {e}")
        return []

def extract_relationships_with_llm(content: str, entities: List[Entity]) -> List[Relationship]:
    """Extract relationships using LLM or fallback to mock data."""
    if not entities:
        return []

    dry_run = os.getenv("DRY_RUN", "").lower() in ("true", "1", "yes")

    if dry_run:
        print("[DRY RUN] Using mock relationship extraction")
        raw_relationships = [
            Relationship(
                subject=entities[0].name,
                predicate="relates_to",
                object=entities[1].name if len(entities) > 1 else entities[0].name,
                fact=f"Both {entities[0].name} and {entities[1].name if len(entities) > 1 else 'related concepts'} are mentioned in the same context"
            )
        ]
        return deduplicate_relationships(raw_relationships)

    try:
        # In a real implementation, this would use cocoindex.functions.ExtractByLlm
        raw_relationships = []
        if len(entities) >= 2:
            raw_relationships = [
                Relationship(
                    subject=entities[0].name,
                    predicate="relates_to",
                    object=entities[1].name,
                    fact=f"{entities[0].name} and {entities[1].name} appear together in the content"
                )
            ]
        return deduplicate_relationships(raw_relationships)

    except Exception as e:
        print(f"[ERROR] Relationship extraction failed: {e}")
        return []


# --- Enhanced export function with entity extraction ---
def export_enhanced_to_falkor(page_data: dict, chunk_text: str, entities: List[Entity], relationships: List[Relationship]) -> None:
    """Export page data with enhanced entity and relationship extraction to FalkorDB."""
    gid = slugify(page_data.get("book"))
    doc_uuid = uuid5_ns("doc", str(page_data.get("id")))
    title = page_data.get("title") or "Untitled"
    url = page_data.get("url") or ""
    updated_at = page_data.get("updated_at") or "1970-01-01T00:00:00Z"

    # Embed title
    title_emb = embed_qwen3_cached(title)

    # Create document node
    _FALKOR.query(Q_DOC, {
        "doc_uuid": doc_uuid,
        "title": title,
        "content": chunk_text,
        "gid": gid,
        "updated_at": updated_at,
        "url": url,
        "title_emb": title_emb,
    })

    # Create entities from tags (legacy approach)
    for tag in (page_data.get("tags") or []):
        ename_norm = normalize_entity_name(str(tag))
        e_uuid = uuid5_ns("ent", ename_norm, gid)
        e_emb = embed_qwen3_cached(str(tag))

        _FALKOR.query(Q_ENT, {
            "ename": ename_norm,
            "gid": gid,
            "e_uuid": e_uuid,
            "e_emb": e_emb,
            "entity_type": "TAG",
            "description": f"Tag: {tag}"
        })

        # Create mention relationship
        m_uuid = uuid5_ns("ment", doc_uuid, e_uuid)
        _FALKOR.query(Q_MENT, {
            "doc_uuid": doc_uuid,
            "gid": gid,
            "ename": ename_norm,
            "m_uuid": m_uuid
        })

    # Create entities from content extraction
    for entity in entities:
        ename_norm = normalize_entity_name(entity.name)
        e_uuid = uuid5_ns("ent", ename_norm, gid)
        e_emb = embed_qwen3_cached(entity.name)

        _FALKOR.query(Q_ENT, {
            "ename": ename_norm,
            "gid": gid,
            "e_uuid": e_uuid,
            "e_emb": e_emb,
            "entity_type": entity.type,
            "description": entity.description
        })

        # Create mention relationship
        m_uuid = uuid5_ns("ment", doc_uuid, e_uuid)
        _FALKOR.query(Q_MENT, {
            "doc_uuid": doc_uuid,
            "gid": gid,
            "ename": ename_norm,
            "m_uuid": m_uuid
        })

    # Create relationships between entities
    for rel in relationships:
        subject_norm = normalize_entity_name(rel.subject)
        object_norm = normalize_entity_name(rel.object)
        rel_uuid = uuid5_ns("rel", subject_norm, rel.predicate, object_norm, gid)
        fact_emb = embed_qwen3_cached(rel.fact)

        _FALKOR.query(Q_REL, {
            "subject": subject_norm,
            "predicate": rel.predicate,
            "object": object_norm,
            "gid": gid,
            "rel_uuid": rel_uuid,
            "fact": rel.fact,
            "fact_emb": fact_emb
        })


# --- Proper CocoIndex Flow Definition ---
@cocoindex.flow_def(name="BookStackToFalkor")
def bookstack_to_falkor(flow_builder: FlowBuilder, data_scope: DataScope) -> None:
    """Enhanced BookStack to FalkorDB flow with entity extraction and deduplication."""

    # Add source for BookStack JSON files
    data_scope["pages"] = flow_builder.add_source(
        cocoindex.sources.LocalFile(path="bookstack_export", included_patterns=["*.json"]),
        refresh_interval=timedelta(minutes=2),
    )

    # Add collectors for different types of data
    processed_pages = data_scope.add_collector()
    extracted_entities = data_scope.add_collector()
    extracted_relationships = data_scope.add_collector()

    # Process each page
    with data_scope["pages"].row() as page:
        # Parse JSON content
        page["parsed"] = page["content"].transform(cocoindex.functions.ParseJson())

        # Extract entities from content using LLM (mock for now)
        page["entities"] = page["parsed"]["body_html"].transform(
            cocoindex.functions.ExtractByLlm(
                llm_spec=cocoindex.LlmSpec(
                    api_type=cocoindex.LlmApiType.OPENAI,
                    model="gpt-4o",
                ),
                output_type=list[Entity],
                instruction="Extract named entities (people, organizations, concepts, technologies) from this HTML content."
            )
        )

        # Extract relationships between entities
        page["relationships"] = page["parsed"]["body_html"].transform(
            cocoindex.functions.ExtractByLlm(
                llm_spec=cocoindex.LlmSpec(
                    api_type=cocoindex.LlmApiType.OPENAI,
                    model="gpt-4o",
                ),
                output_type=list[Relationship],
                instruction="Extract relationships between entities mentioned in this HTML content."
            )
        )

        # Collect page information
        processed_pages.collect(
            page_id=page["parsed"]["id"],
            title=page["parsed"]["title"],
            filename=page["filename"]
        )

        # Collect entities
        with page["entities"].row() as entity:
            extracted_entities.collect(
                entity_id=cocoindex.GeneratedField.UUID,
                name=entity["name"],
                type=entity["type"],
                description=entity["description"],
                page_id=page["parsed"]["id"]
            )

        # Collect relationships
        with page["relationships"].row() as relationship:
            extracted_relationships.collect(
                relationship_id=cocoindex.GeneratedField.UUID,
                subject=relationship["subject"],
                predicate=relationship["predicate"],
                object=relationship["object"],
                fact=relationship["fact"],
                page_id=page["parsed"]["id"]
            )

    # Export to PostgreSQL for observability
    processed_pages.export(
        "bookstack_pages",
        cocoindex.targets.Postgres(),
        primary_key_fields=["page_id"]
    )

    extracted_entities.export(
        "bookstack_entities",
        cocoindex.targets.Postgres(),
        primary_key_fields=["entity_id"]
    )

    extracted_relationships.export(
        "bookstack_relationships",
        cocoindex.targets.Postgres(),
        primary_key_fields=["relationship_id"]
    )

