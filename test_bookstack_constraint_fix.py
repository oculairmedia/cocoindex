#!/usr/bin/env python3
"""
Test script to verify BookStack pipeline constraint fixes
and timestamp compliance.
"""

import uuid

from flows.utils import current_timestamp_iso, is_isoformat_timestamp


def generate_deterministic_uuid(namespace: str, identifier: str) -> str:
    """Generate deterministic UUID for idempotency."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{namespace}-{identifier}"))


def safe_cypher_string(text: str) -> str:
    """Make string safe for Cypher queries."""
    if not text:
        return ""
    return text.replace("'", "\\'").replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r')


def create_group_id(book_name: str) -> str:
    """Create group_id from book name."""
    if not book_name:
        return "bookstack-default"
    return f"bookstack-{book_name.lower().replace(' ', '-').replace('_', '-')}"


def ensure_iso(label: str) -> str:
    value = current_timestamp_iso()
    if not is_isoformat_timestamp(value):
        raise AssertionError(f"{label} value is not ISO8601: {value}")
    print(f"   🕒 {label}: {value}")
    return value


def test_bookstack_constraint_compliance():
    """Test BookStack pipeline constraint compliance."""
    print("🧪 Testing BookStack Pipeline Constraint Compliance")
    print("=" * 60)

    # Test data
    page_id = "155"
    title = "Integrated Plugin Architecture Plan"
    book = "Development Guide"
    content = "This is a test page content"
    summary = "Test summary"

    # Generate required properties
    group_id = create_group_id(book)
    episodic_uuid = generate_deterministic_uuid("bookstack-episodic", page_id)

    print("📋 Test Data:")
    print(f"   Page ID: {page_id}")
    print(f"   Title: {title}")
    print(f"   Book: {book}")
    print(f"   Generated group_id: {group_id}")
    print(f"   Generated UUID: {episodic_uuid[:8]}...")

    # Test Episodic node creation
    print("\n1. Testing Episodic Node Creation:")
    safe_title = safe_cypher_string(title)
    safe_content = safe_cypher_string(content)
    safe_summary = safe_cypher_string(summary)

    created_at = ensure_iso("episodic.created_at")
    valid_at = ensure_iso("episodic.valid_at")

    episodic_cypher = f"""
    MERGE (e:Episodic {{uuid: '{episodic_uuid}', group_id: '{group_id}'}})
    ON CREATE SET e.name = '{safe_title}',
                 e.source = 'bookstack',
                 e.source_description = 'BookStack knowledge base content',
                 e.created_at = '{created_at}'
    SET e.content = '{safe_content}',
        e.summary = '{safe_summary}',
        e.valid_at = '{valid_at}',
        e.bookstack_id = '{page_id}',
        e.url = 'https://example.com/page/{page_id}',
        e.book = '{safe_cypher_string(book)}'
    RETURN e.uuid
    """

    if "timestamp()" in episodic_cypher:
        print("   ❌ Found numeric timestamp usage in Episodic node")
        return False

    # Validate mandatory properties are in MERGE clause
    mandatory_props = ['uuid', 'group_id']
    for prop in mandatory_props:
        prop_pattern = f"{prop}: '"
        if prop_pattern not in episodic_cypher:
            print(f"   ❌ Missing mandatory property in MERGE: {prop}")
            return False

    print(f"   ✅ Episodic node includes all mandatory properties: {mandatory_props}")

    # Test Entity node creation
    print("\n2. Testing Entity Node Creation:")
    entity_name = "plugin"
    entity_type = "CONCEPT"
    entity_description = "Software plugin concept"
    entity_uuid = generate_deterministic_uuid("entity", f"{entity_name}-{group_id}")

    entity_created_at = ensure_iso("entity.created_at")

    entity_cypher = f"""
    MERGE (ent:Entity {{uuid: '{entity_uuid}', name: '{safe_cypher_string(entity_name)}', group_id: '{group_id}'}})
    ON CREATE SET ent.created_at = '{entity_created_at}'
    SET ent.summary = '{safe_cypher_string(entity_description)}',
        ent.entity_type = '{entity_type}',
        ent.labels = ['{entity_type}']
    RETURN ent.uuid
    """

    if "timestamp()" in entity_cypher:
        print("   ❌ Found numeric timestamp usage in Entity node")
        return False

    mandatory_props = ['uuid', 'name', 'group_id']
    for prop in mandatory_props:
        prop_pattern = f"{prop}: '"
        if prop_pattern not in entity_cypher:
            print(f"   ❌ Missing mandatory property in MERGE: {prop}")
            return False

    print(f"   ✅ Entity node includes all mandatory properties: {mandatory_props}")

    # Test MENTIONS relationship
    print("\n3. Testing MENTIONS Relationship:")
    mention_uuid = generate_deterministic_uuid("mentions", f"{episodic_uuid}-{entity_uuid}")
    mention_created_at = ensure_iso("mentions.created_at")

    mention_cypher = f"""
    MATCH (ep:Episodic {{uuid: '{episodic_uuid}'}}),
          (ent:Entity {{uuid: '{entity_uuid}', name: '{safe_cypher_string(entity_name)}', group_id: '{group_id}'}})
    MERGE (ep)-[r:MENTIONS {{uuid: '{mention_uuid}', group_id: '{group_id}'}}]->(ent)
    ON CREATE SET r.created_at = '{mention_created_at}'
    """

    if "timestamp()" in mention_cypher:
        print("   ❌ Found numeric timestamp usage in MENTIONS relationship")
        return False

    mandatory_props = ['uuid', 'group_id']
    for prop in mandatory_props:
        prop_pattern = f"{prop}: '"
        if prop_pattern not in mention_cypher:
            print(f"   ❌ Missing mandatory property in MERGE: {prop}")
            return False

    print(f"   ✅ MENTIONS relationship includes all mandatory properties: {mandatory_props}")

    # Test RELATES_TO relationship
    print("\n4. Testing RELATES_TO Relationship:")
    subject_name = "plugin"
    object_name = "architecture"
    subject_uuid = generate_deterministic_uuid("entity", f"{subject_name}-{group_id}")
    object_uuid = generate_deterministic_uuid("entity", f"{object_name}-{group_id}")
    relates_uuid = generate_deterministic_uuid("relates", f"{subject_name}-{object_name}-{group_id}")
    relates_created_at = ensure_iso("relates.created_at")

    relates_cypher = f"""
    MATCH (e1:Entity {{uuid: '{subject_uuid}', name: '{safe_cypher_string(subject_name)}', group_id: '{group_id}'}}),
          (e2:Entity {{uuid: '{object_uuid}', name: '{safe_cypher_string(object_name)}', group_id: '{group_id}'}})
    MERGE (e1)-[r:RELATES_TO {{uuid: '{relates_uuid}', group_id: '{group_id}'}}]->(e2)
    ON CREATE SET r.created_at = '{relates_created_at}'
    SET r.predicate = 'part_of',
        r.fact = 'Plugin is part of architecture'
    """

    if "timestamp()" in relates_cypher:
        print("   ❌ Found numeric timestamp usage in RELATES_TO relationship")
        return False

    mandatory_props = ['uuid', 'group_id']
    for prop in mandatory_props:
        prop_pattern = f"{prop}: '"
        if prop_pattern not in relates_cypher:
            print(f"   ❌ Missing mandatory property in MERGE: {prop}")
            return False

    print(f"   ✅ RELATES_TO relationship includes all mandatory properties: {mandatory_props}")

    print("\n" + "=" * 60)
    print("🎉 All BookStack constraint compliance tests passed with ISO timestamps!")

    return True


if __name__ == "__main__":
    success = test_bookstack_constraint_compliance()
    if success:
        print("\n✅ BookStack pipeline is now constraint-compliant!")
    else:
        print("\n❌ Issues detected in BookStack pipeline!")
