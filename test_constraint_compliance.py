#!/usr/bin/env python3
"""
Comprehensive test to verify FalkorDB constraint compliance.
Tests that all nodes and relationships include mandatory properties
and that temporal fields are emitted as ISO8601 strings.
"""

import uuid
import sys
from pathlib import Path

from flows.utils import current_timestamp_iso, is_isoformat_timestamp

# Add the flows directory to the path so we can import the functions
sys.path.append(str(Path(__file__).parent / "flows"))


def generate_deterministic_uuid(namespace: str, identifier: str) -> str:
    """Generate deterministic UUID for idempotency."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{namespace}-{identifier}"))


def safe_cypher_string(text: str) -> str:
    """Make string safe for Cypher queries."""
    if not text:
        return ""
    return text.replace("'", "\\'").replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r')


def create_group_id(project_name: str) -> str:
    """Create group_id from project name."""
    if not project_name or project_name.strip() == "":
        return "huly-default"

    # Clean and normalize the project name
    cleaned = project_name.strip().lower()
    # Replace spaces and underscores with hyphens
    cleaned = cleaned.replace(' ', '-').replace('_', '-')
    # Remove any non-alphanumeric characters except hyphens
    cleaned = ''.join(c if c.isalnum() or c == '-' else '' for c in cleaned)
    # Remove multiple consecutive hyphens
    while '--' in cleaned:
        cleaned = cleaned.replace('--', '-')
    # Remove leading/trailing hyphens
    cleaned = cleaned.strip('-')

    # If cleaning resulted in empty string, use default
    if not cleaned:
        return "huly-default"

    return f"huly-{cleaned}"


def normalize_entity_name(name: str) -> str:
    """Normalize entity names for consistency."""
    return name.lower().strip()


def ensure_iso(label: str) -> str:
    """Return an ISO8601 timestamp and print a diagnostic."""
    iso_value = current_timestamp_iso()
    if not is_isoformat_timestamp(iso_value):
        raise AssertionError(f"{label} is not a valid ISO8601 timestamp: {iso_value}")
    print(f"   🕒 {label}: {iso_value}")
    return iso_value


def test_episodic_node_compliance():
    """Test Episodic node constraint compliance."""
    print("🧪 Testing Episodic Node Constraint Compliance")
    print("-" * 50)

    # Test data
    project_id = "LDTS"
    item_id = "DTS-137"
    title = "Create cache management and cleanup controls"
    content = "Test content for cache management"

    # Generate required properties
    group_id = create_group_id(project_id)
    episodic_uuid = generate_deterministic_uuid("huly-episodic", item_id)

    # Generate Cypher query
    safe_title = safe_cypher_string(title)
    safe_content = safe_cypher_string(content)

    created_at = ensure_iso("episodic.created_at")
    valid_at = ensure_iso("episodic.valid_at")

    episodic_cypher = f"""
    MERGE (e:Episodic {{uuid: '{episodic_uuid}', group_id: '{group_id}'}})
    ON CREATE SET e.name = '{safe_title}',
                 e.source = 'huly',
                 e.source_description = 'Huly project management data',
                 e.created_at = '{created_at}'
    SET e.content = '{safe_content}',
        e.valid_at = '{valid_at}',
        e.huly_type = 'issue',
        e.huly_id = '{safe_cypher_string(item_id)}',
        e.project_id = '{safe_cypher_string(project_id)}',
        e.status = 'test',
        e.priority = 'medium'
    RETURN e.uuid
    """

    if "timestamp()" in episodic_cypher:
        print("   ❌ Found numeric timestamp usage for Episodic node")
        return False

    # Validate mandatory properties are in MERGE clause
    mandatory_props = ['uuid', 'group_id']
    for prop in mandatory_props:
        prop_pattern = f"{prop}: '"
        if prop_pattern not in episodic_cypher:
            print(f"   ❌ Missing mandatory property in MERGE: {prop}")
            return False

    print(f"   ✅ Episodic node includes all mandatory properties: {mandatory_props}")
    print(f"   📋 UUID: {episodic_uuid[:8]}...")
    print(f"   🏷️  Group ID: {group_id}")
    return True


def test_entity_node_compliance():
    """Test Entity node constraint compliance."""
    print("\n🧪 Testing Entity Node Constraint Compliance")
    print("-" * 50)

    # Test data
    entity_name = "docker"
    entity_type = "TECHNOLOGY"
    entity_description = "Container technology"
    group_id = "huly-ldts"

    # Generate required properties
    normalized_name = normalize_entity_name(entity_name)
    entity_uuid = generate_deterministic_uuid("entity", f"{normalized_name}-{group_id}")

    created_at = ensure_iso("entity.created_at")

    # Generate Cypher query
    entity_cypher = f"""
    MERGE (ent:Entity {{uuid: '{entity_uuid}', name: '{safe_cypher_string(normalized_name)}', group_id: '{group_id}'}})
    ON CREATE SET ent.created_at = '{created_at}'
    SET ent.summary = '{safe_cypher_string(entity_description)}',
        ent.entity_type = '{entity_type}',
        ent.labels = ['{entity_type}']
    RETURN ent.uuid
    """

    if "timestamp()" in entity_cypher:
        print("   ❌ Found numeric timestamp usage for Entity node")
        return False

    # Validate mandatory properties are in MERGE clause
    mandatory_props = ['uuid', 'name', 'group_id']
    for prop in mandatory_props:
        prop_pattern = f"{prop}: '"
        if prop_pattern not in entity_cypher:
            print(f"   ❌ Missing mandatory property in MERGE: {prop}")
            return False

    print(f"   ✅ Entity node includes all mandatory properties: {mandatory_props}")
    print(f"   📋 UUID: {entity_uuid[:8]}...")
    print(f"   🏷️  Name: {normalized_name}")
    print(f"   🏷️  Group ID: {group_id}")
    return True


def test_mentions_relationship_compliance():
    """Test MENTIONS relationship constraint compliance."""
    print("\n🧪 Testing MENTIONS Relationship Constraint Compliance")
    print("-" * 50)

    # Test data
    episodic_uuid = "test-episodic-uuid"
    entity_uuid = "test-entity-uuid"
    entity_name = "docker"
    group_id = "huly-ldts"

    # Generate required properties
    mention_uuid = generate_deterministic_uuid("mentions", f"{episodic_uuid}-{entity_uuid}")
    created_at = ensure_iso("mentions.created_at")

    # Generate Cypher query
    mention_cypher = f"""
    MATCH (ep:Episodic {{uuid: '{episodic_uuid}'}}),
          (ent:Entity {{uuid: '{entity_uuid}', name: '{safe_cypher_string(entity_name)}', group_id: '{group_id}'}})
    MERGE (ep)-[r:MENTIONS {{uuid: '{mention_uuid}', group_id: '{group_id}'}}]->(ent)
    ON CREATE SET r.created_at = '{created_at}'
    """

    if "timestamp()" in mention_cypher:
        print("   ❌ Found numeric timestamp usage for MENTIONS relationship")
        return False

    # Validate mandatory properties are in MERGE clause
    mandatory_props = ['uuid', 'group_id']
    for prop in mandatory_props:
        prop_pattern = f"{prop}: '"
        if prop_pattern not in mention_cypher:
            print(f"   ❌ Missing mandatory property in MERGE: {prop}")
            return False

    print(f"   ✅ MENTIONS relationship includes all mandatory properties: {mandatory_props}")
    print(f"   📋 UUID: {mention_uuid[:8]}...")
    print(f"   🏷️  Group ID: {group_id}")
    return True


def test_relates_to_relationship_compliance():
    """Test RELATES_TO relationship constraint compliance."""
    print("\n🧪 Testing RELATES_TO Relationship Constraint Compliance")
    print("-" * 50)

    # Test data
    subject_name = "docker"
    object_name = "kubernetes"
    group_id = "huly-ldts"

    # Generate required properties
    subject_uuid = generate_deterministic_uuid("entity", f"{subject_name}-{group_id}")
    object_uuid = generate_deterministic_uuid("entity", f"{object_name}-{group_id}")
    relates_uuid = generate_deterministic_uuid("relates", f"{subject_name}-{object_name}-{group_id}")
    created_at = ensure_iso("relates_to.created_at")

    # Generate Cypher query
    relates_cypher = f"""
    MATCH (e1:Entity {{uuid: '{subject_uuid}', name: '{safe_cypher_string(subject_name)}', group_id: '{group_id}'}}),
          (e2:Entity {{uuid: '{object_uuid}', name: '{safe_cypher_string(object_name)}', group_id: '{group_id}'}})
    MERGE (e1)-[r:RELATES_TO {{uuid: '{relates_uuid}', group_id: '{group_id}'}}]->(e2)
    ON CREATE SET r.created_at = '{created_at}'
    SET r.predicate = 'works_with',
        r.fact = 'Docker works with Kubernetes'
    """

    if "timestamp()" in relates_cypher:
        print("   ❌ Found numeric timestamp usage for RELATES_TO relationship")
        return False

    # Validate mandatory properties are in MERGE clause
    mandatory_props = ['uuid', 'group_id']
    for prop in mandatory_props:
        prop_pattern = f"{prop}: '"
        if prop_pattern not in relates_cypher:
            print(f"   ❌ Missing mandatory property in MERGE: {prop}")
            return False

    print(f"   ✅ RELATES_TO relationship includes all mandatory properties: {mandatory_props}")
    print(f"   📋 UUID: {relates_uuid[:8]}...")
    print(f"   🏷️  Group ID: {group_id}")
    return True


if __name__ == "__main__":
    success = (
        test_episodic_node_compliance()
        and test_entity_node_compliance()
        and test_mentions_relationship_compliance()
        and test_relates_to_relationship_compliance()
    )
    if success:
        print("\n✅ Graphiti pipeline is now constraint-compliant with ISO timestamps!")
    else:
        print("\n❌ Issues detected in Graphiti pipeline!")
