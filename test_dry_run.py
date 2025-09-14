#!/usr/bin/env python3
"""
Test the BookStack to FalkorDB pipeline logic without CocoIndex dependencies
"""

import os
import re
import json
import uuid
from pathlib import Path

# Set dry run mode
os.environ["DRY_RUN"] = "true"

# Copy the helper functions from the flow
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

def embed_qwen3(text: str) -> list[float]:
    print(f"[DRY RUN] Embedding text: {text[:100]}{'...' if len(text) > 100 else ''}")
    # Return fake 2560-dimensional embedding
    return [0.1] * 2560

# Cypher templates
Q_DOC = (
    "MERGE (d:Episodic {uuid:$doc_uuid})\n"
    "ON CREATE SET d.created_at=datetime()\n"
    "SET d.name=$title, d.content=$content, d.group_id=$gid,\n"
    "    d.valid_at=datetime($updated_at), d.source='text', d.source_description=$url,\n"
    "    d.name_embedding=$title_emb"
)

Q_ENT = (
    "MERGE (e:Entity {name:$ename, group_id:$gid})\n"
    "ON CREATE SET e.uuid=$e_uuid, e.created_at=datetime(), e.labels=['Entity'], e.name_embedding=$e_emb"
)

Q_MENT = (
    "MATCH (d:Episodic {uuid:$doc_uuid}),(e:Entity {name:$ename,group_id:$gid})\n"
    "CREATE (d)-[:MENTIONS {uuid:$m_uuid, group_id:$gid, created_at:datetime()}]->(e)"
)

_TAG_EMB_CACHE = {}

def _embed_tag_cached(tag: str) -> list[float]:
    e = _TAG_EMB_CACHE.get(tag)
    if e is not None:
        return e
    e = embed_qwen3(tag)
    _TAG_EMB_CACHE[tag] = e
    return e

def fake_query(cypher: str, params: dict = None):
    """Simulate database query with logging"""
    print(f"[DRY RUN] GRAPH.QUERY graphiti_migration")
    print(f"[DRY RUN] Cypher: {cypher}")
    if params:
        print(f"[DRY RUN] Params: {json.dumps(params, indent=2, default=str)}")
    print("-" * 60)

def export_to_falkor(page: dict, chunk_text: str) -> None:
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

    # Entities from tags
    for tag in (page.get("tags") or []):
        ename = str(tag)
        e_uuid = uuid5_ns("ent", ename, gid)
        e_emb = _embed_tag_cached(ename)
        fake_query(Q_ENT, {"ename": ename, "gid": gid, "e_uuid": e_uuid, "e_emb": e_emb})
        m_uuid = uuid5_ns("ment", doc_uuid, e_uuid)
        fake_query(Q_MENT, {"doc_uuid": doc_uuid, "gid": gid, "ename": ename, "m_uuid": m_uuid})

def test_pipeline():
    print("=== Testing BookStack to FalkorDB Pipeline (DRY RUN) ===\n")
    
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
        
        # Process each chunk
        for i, chunk_text in enumerate(chunks):
            print(f"\n--- Processing Chunk {i+1} ---")
            export_to_falkor(page, chunk_text.strip())
        
        print("\n" + "="*80)

if __name__ == "__main__":
    test_pipeline()