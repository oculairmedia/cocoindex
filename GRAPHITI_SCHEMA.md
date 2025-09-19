# Graphiti Schema Specification

This document defines the required structure for nodes and relationships to comply with the Graphiti knowledge graph schema.

## Node Types

### 1. Episodic Nodes

Episodic nodes represent temporal events, messages, conversations, or any time-bound information.

#### Required Fields
```cypher
{
  uuid: "string",              // Unique identifier (UUID v4)
  name: "string",              // Short descriptive name (max 100 chars)
  group_id: "string",          // Group identifier for related items
  source: "string",            // Source type (e.g., "message", "issue", "document")
  source_description: "string", // Detailed source description
  content: "string",           // Full content/text of the episode
  created_at: timestamp,       // Creation timestamp
  valid_at: timestamp          // Validity timestamp
}
```

#### Optional Fields
```cypher
{
  entity_edges: ["uuid1", "uuid2", ...],  // Array of connected entity UUIDs

  // Centrality Metrics (calculated post-creation)
  pagerank_centrality: float,
  eigenvector_centrality: float,
  degree_centrality: float,
  betweenness_centrality: float,
  importance_score: float,

  // Additional metadata
  [custom_field]: "value"     // e.g., huly_id, status, priority
}
```

#### Example Sources
- `"message"` - Chat messages, emails, communications
- `"issue"` - Project management issues, tickets
- `"document"` - Document snapshots, wiki pages
- `"event"` - System events, logs

### 2. Entity Nodes

Entity nodes represent persistent concepts, people, technologies, organizations, or any stable knowledge elements.

#### Required Fields
```cypher
{
  uuid: "string",              // Unique identifier (UUID v4)
  name: "string",              // Entity name (lowercase, normalized)
  group_id: "string",          // Group identifier for scoping
  summary: "string",           // Detailed description/summary
  created_at: timestamp        // Creation timestamp
}
```

#### Optional Fields
```cypher
{
  entity_type: "string",       // Type classification (TECHNOLOGY, PERSON, ORGANIZATION, etc.)

  // Centrality Metrics (calculated post-creation)
  pagerank_centrality: float,
  eigenvector_centrality: float,
  degree_centrality: float,
  betweenness_centrality: float,
  importance_score: float,

  // Vector Embedding (for similarity search)
  name_embedding: [float array],  // Vector embedding of the entity name

  // Additional metadata
  labels: ["label1", "label2"],   // Array of labels/tags
  [custom_field]: "value"          // e.g., huly_type, project_id
}
```

#### Entity Types
- `TECHNOLOGY` - Software, frameworks, tools
- `PERSON` - Individuals, users, agents
- `ORGANIZATION` - Companies, teams, departments
- `CONCEPT` - Abstract concepts, methodologies
- `COMPONENT` - System components, modules
- `MILESTONE` - Project milestones, releases
- `PROJECT` - Projects, initiatives

## Relationship Types

### 1. MENTIONS Relationship

Connects Episodic nodes to Entity nodes they reference.

```cypher
(episodic:Episodic)-[r:MENTIONS]->(entity:Entity)
```

#### Required Fields
```cypher
{
  uuid: "string",              // Unique identifier
  created_at: timestamp        // Creation timestamp
}
```

#### Optional Fields
```cypher
{
  group_id: "string",          // Group identifier (inherited from nodes)
  confidence: float,           // Extraction confidence score
  context: "string"            // Context around the mention
}
```

### 2. RELATES_TO Relationship

Connects Entity nodes to other Entity nodes.

```cypher
(entity1:Entity)-[r:RELATES_TO]->(entity2:Entity)
```

#### Required Fields
```cypher
{
  uuid: "string",              // Unique identifier
  created_at: timestamp        // Creation timestamp
}
```

#### Optional Fields
```cypher
{
  group_id: "string",          // Group identifier
  predicate: "string",         // Relationship type (uses, implements, contains, etc.)
  fact: "string",              // Descriptive fact about the relationship
  confidence: float            // Extraction confidence score
}
```

### 3. OCCURRED_BEFORE/OCCURRED_AFTER Relationships

Temporal relationships between Episodic nodes.

```cypher
(earlier:Episodic)-[r:OCCURRED_BEFORE]->(later:Episodic)
(later:Episodic)-[r:OCCURRED_AFTER]->(earlier:Episodic)
```

## Best Practices

### 1. UUID Generation
- Always use UUID v4 for unique identifiers
- Store as string format (e.g., "8f43d2ee-7d82-44ba-b0af-26aa46435e50")

### 2. Group ID Management
- Use consistent group_id for related items
- Format: lowercase, hyphenated (e.g., "project-name", "user-123")
- Enables scoped queries and multi-tenancy

### 3. Name Normalization
- Entity names should be lowercase, trimmed
- Remove special characters where appropriate
- Use consistent naming for deduplication

### 4. Content Storage
- Escape special characters in content fields
- Use safe_cypher_string() function for query safety
- Store markdown or plain text in content field

### 5. Timestamp Format
- Use ISO 8601 format for timestamps
- Store as native timestamp type in FalkorDB
- Example: `2025-09-17T23:39:18.887279+00:00`

## Query Examples

### Find all entities mentioned in recent episodes
```cypher
MATCH (e:Episodic)-[:MENTIONS]->(n:Entity)
WHERE e.created_at > timestamp() - 86400000  // Last 24 hours
RETURN n.name, count(e) as mention_count
ORDER BY mention_count DESC
```

### Get entity relationships with facts
```cypher
MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity)
WHERE r.fact IS NOT NULL
RETURN a.name, r.predicate, b.name, r.fact
```

### Find episodes by source and group
```cypher
MATCH (e:Episodic)
WHERE e.source = 'issue'
  AND e.group_id = 'huly'
RETURN e.name, e.content, e.created_at
ORDER BY e.created_at DESC
LIMIT 10
```

## Migration Notes

When migrating from other schemas:

1. **Issues/Tickets** → Episodic nodes with `source: "issue"`
2. **Projects** → Entity nodes with `entity_type: "PROJECT"`
3. **Components** → Entity nodes with `entity_type: "COMPONENT"`
4. **Milestones** → Entity nodes with `entity_type: "MILESTONE"`
5. **Comments** → Episodic nodes with `source: "message"`

## Validation Checklist

- [ ] All nodes have UUID field
- [ ] All nodes have created_at timestamp
- [ ] All nodes have group_id for scoping
- [ ] Episodic nodes have source and source_description
- [ ] Entity nodes have summary field
- [ ] Relationships have UUID and created_at
- [ ] Entity names are normalized (lowercase)
- [ ] Content fields are properly escaped
- [ ] Timestamps follow ISO 8601 format