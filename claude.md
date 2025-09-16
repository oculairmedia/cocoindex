# CocoIndex ↔ Graphiti FalkorDB Integration — Objectives & Plan

## 0) Project Information

**Huly Project Details:**
- **Project Name**: CocoIndex Data Pipelines
- **Project Code**: COCO
- **Issues**: 5 active issues
- **Description**: CocoIndex-based data transformation pipelines for knowledge extraction and graph ingestion. Manages multiple flows including BookStack-to-FalkorDB, LLM entity enhancement, and containerized processing workflows. Focused on batch processing, data quality, and scalable pipeline architecture.
- **Status**: Active (Public, Not Archived)
- **Huly URL**: Available via MCP server at http://192.168.50.90:3457/mcp

**Repository Information:**
- **Location**: /opt/stacks/cocoindex
- **Current Branch**: main
- **Git Status**: Modified files include flows, docker configs, and pipeline scripts

## 1) Executive Summary
We are building a fast, incremental ingestion pipeline that pulls BookStack knowledge-base content and deposits it into a Graphiti-compatible knowledge graph running on FalkorDB. We will use CocoIndex for high‑performance ingestion, normalization, chunking, and embeddings, and write directly to FalkorDB via Cypher in a way that strictly conforms to Graphiti’s schema and indexing expectations. This allows Graphiti to treat the new nodes/edges identically to existing data.

## 2) Primary Objectives (What success looks like)
- Seamless ingestion of BookStack pages into FalkorDB using Graphiti conventions
- Strict schema conformance (labels, properties, embeddings) so Graphiti is agnostic to source
- Deterministic IDs and partitioning (group_id) for idempotent re‑ingestion
- Incremental updates based on BookStack updated_at with small latency (< 5 minutes)
- Embedding alignment to Graphiti configuration (Qwen3-Embedding-4B, 2560‑dim)
- Operable with clear runbooks, safe failure modes, and easy validation queries

## 3) Non‑Goals (Explicitly out of scope for v1)
- Full semantic entity extraction beyond BookStack tags (can come in a later phase)
- Complex entity‑entity relationship mining (v2+)
- Heading‑aware chunking or section graph (optional v2)
- Webhook/event‑driven ingestion (start with polling; can add later)

## 4) System Context
- Source: BookStack (HTTPS API)
- Ingestion Runner: CocoIndex (Python API)
- Vector/Graph Store: FalkorDB (RedisGraph protocol)
- Consumer: Graphiti (your fork), downstream agents/services

## 5) Data Sources — BookStack
- API Base URL: BS_URL (env)
- Auth: BS_TOKEN_ID and BS_TOKEN_SECRET (read‑only)
- Scope: All published pages (exclude drafts/archived/deleted for v1)
- Export method: A small fetcher writes one JSON per page into ./bookstack_export/
  - Script: scripts/bookstack_export.py
  - Each file contains: id, title, slug, url, updated_at, body_html, tags[], book, chapter

## 6) Graph Schema Conformance (Graphiti‑compatible)
Node Labels & Props
- Entity (topics/concepts)
  - Required: uuid, name, group_id, created_at, labels
  - Optional: summary, name_embedding (2560), attributes (dict)
- Episodic (documents/content)
  - Required: uuid, name, group_id, created_at, content, source, source_description, valid_at
  - Optional: summary, name_embedding (2560), entity_edges
- Community (clusters; not used in v1)

Edge Labels & Props
- MENTIONS (Episodic → Entity)
  - Required: uuid, group_id, created_at
- RELATES_TO (Entity → Entity) — reserved for future
  - Required: uuid, name, fact, group_id, created_at; Optional: fact_embedding (2560), episodes[]
- HAS_MEMBER (Community → Entity) — reserved for future

Constraints / Merge Keys (must be pre‑created in DB)
- Unique Node UUIDs: Entity.uuid, Episodic.uuid, Community.uuid
- Entity dedupe: UNIQUE(name, group_id)
- Relationships: HAS_MEMBER.uuid unique (others not unique by design)

## 7) IDs, Partitioning, and Deduplication
- group_id: slugified Book name (lowercase, non‑alnum → '-')
- UUID strategy (deterministic):
  - Episodic: uuid5("doc", page_id)
  - Entity: uuid5("ent", entity_name, group_id)
  - MENTIONS: uuid5("ment", episodic_uuid, entity_uuid)
- MERGE semantics:
  - Episodic: MERGE on uuid
  - Entity: MERGE on (name, group_id) then set uuid on create
  - MENTIONS: CREATE (duplicates allowed)

## 8) Embedding Configuration (Alignment with Graphiti)
- Model: Qwen3‑Embedding‑4B (Ollama/OpenAI‑compatible), dimension 2560
- Endpoint: EMB_URL (HTTP), key: EMB_KEY, model: EMB_MODEL
- Storage properties:
  - Nodes: name_embedding
  - Edges: fact_embedding (for future RELATES_TO)

## 9) CocoIndex Pipeline Responsibilities
- Input: bookstack_export/*.json via LocalFile source (refresh ~2m)
- Normalize: HTML → text
- Chunk: SplitRecursively(language="markdown", size=1200, overlap=300)
- Embed: Title (node name embedding) and tag names (entity name embedding)
- Export: Cypher to FalkorDB (GRAPH.QUERY)
  - MERGE Episodic with up‑to‑date content and metadata
  - MERGE Entity for each tag
  - CREATE MENTIONS from doc to tag entities

Files Added
- scripts/bookstack_export.py — API → JSON per page
- flows/bookstack_to_falkor.py — CocoIndex flow, embedding & export ops

## 10) Environment Variables (Expected)
BookStack
- BS_URL
- BS_TOKEN_ID
- BS_TOKEN_SECRET

FalkorDB
- FALKOR_HOST (e.g., 192.168.50.90)
- FALKOR_PORT (6379)
- FALKOR_GRAPH (graphiti_migration)

Embeddings
- EMB_URL (e.g., http://192.168.50.80:11434/v1/embeddings)
- EMB_KEY (e.g., ollama)
- EMB_MODEL (e.g., dengcao/Qwen3-Embedding-4B:Q4_K_M)

## 11) Performance & Scalability Targets
- Exporter: ≤ 2 QPS to BookStack by default; configurable sleep between calls
- Ingestion: End‑to‑end freshness target < 5 minutes under normal load
- Embeddings: cache tag embeddings in‑process; consider Redis caching if needed
- Batch/pipe GRAPH.QUERY calls in future to reduce RTTs

## 12) Data Quality & Idempotency
- Deterministic IDs guarantee safe re‑runs
- MERGE patterns ensure upsert semantics
- Soft failures (missing embeddings) should not block ingestion; set embeddings to null and proceed

## 13) Error Handling & Retries
- HTTP timeouts with retry/backoff at the export script layer (can be extended)
- Defensive JSON parsing (fields may vary across BookStack versions)
- Cypher execution errors are surfaced and should be logged with parameters

## 14) Observability & Validation
- Log: counts of exported pages, ingested chunks, entities created/merged
- Sampling queries:
  - Verify a page:
    - MATCH (d:Episodic {uuid:$uuid}) RETURN d
  - Verify tags:
    - MATCH (d:Episodic {uuid:$uuid})-[:MENTIONS]->(e:Entity {group_id:$gid}) RETURN e LIMIT 10
  - Verify embeddings exist:
    - MATCH (d:Episodic) WHERE exists(d.name_embedding) RETURN count(d)

## 15) Runbooks
A) Export BookStack pages (manual)
- Ensure BS_* env vars are set
- Run: `python scripts/bookstack_export.py --limit 100`

B) Run CocoIndex flow (manual)
- Ensure Falkor and Embeddings env vars are set
- Run: `cocoindex update --setup flows/bookstack_to_falkor.py`

C) Re‑ingest a single page
- Delete its JSON and re‑export (or touch the file)
- CocoIndex LocalFile refresh will pick up changes

## 16) Testing Strategy
- Unit: HTML→text parser, slugify, uuid5ns helpers
- Integration: export 5 pages, ingest, assert:
  - (:Episodic {uuid}) exists with expected properties
  - (:Entity {name, group_id}) exists for tags with name_embedding set
  - (Episodic)-[:MENTIONS]->(Entity) edges created
- Smoke: end‑to‑end run with limit=5 and manual sampling queries

## 17) Rollout Plan
- Dev: local or isolated Falkor graph key (e.g., graphiti_migration_dev)
- Staging: constraints applied, small subset of books
- Prod: run exporter + flow, monitor metrics, then widen scope

## 18) Backfill / Reindex
- To rebuild a graph cleanly, create a new graph key (namespace) and ingest fresh
- Alternatively, clear target graph and re‑run exporter + flow

## 19) Roadmap / Future Enhancements
- Entity‑Entity RELATES_TO from co‑occurrence or link graph (with fact + fact_embedding)
- Heading aware chunking; Section nodes and CONTAINS edges
- Webhook/event driven updates from BookStack
- Redis pipelining for Cypher batches; async concurrency controls
- Richer ontologies (custom entity/edge types) per Graphiti’s extension model

## 20) Risks & Mitigations
- Embedding service latency/outage → allow null embeddings, retry later
- Schema drift → keep a single source of truth doc (this file) and version changes
- BookStack API rate limits → configurable sleep and backoff
- Duplicate entities due to case/whitespace → normalize tag names rigorously

## 21) Acceptance Criteria
- After running exporter (limit ≥ 50) and flow:
  - ≥ 95% of pages produce an Episodic node with non‑empty content
  - Entities for tags created with correct (name, group_id)
  - MENTIONS edges present and queryable
  - Title embeddings present (length 2560) for ≥ 90% of Episodic
  - Sampling Graphiti searches return meaningful results using newly ingested data

## 22) Open Questions
- Should group_id be Book name or slug in all cases? (currently: slug)
- Any shelves/books/chapters to exclude for v1?
- Deletions/archives: should we mark Episodic nodes or leave as‑is?
- Do we want heading‑aware chunking enabled by default?
- Do we need to ingest attachments/images in v1?

