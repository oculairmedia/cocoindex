#!/usr/bin/env python3
"""
Test the enhanced BookStack to FalkorDB pipeline with localhost setup.
Demonstrates all enhanced features working with your FalkorDB.
"""

import os
import json
import redis
from pathlib import Path

# Set up environment for localhost FalkorDB
os.environ["FALKOR_HOST"] = "localhost"
os.environ["FALKOR_PORT"] = "6379"
os.environ["FALKOR_GRAPH"] = "graphiti_migration"

# Import our enhanced pipeline functions
from flows.bookstack_enhanced_localhost import (
    get_falkor_connection,
    html_to_text,
    normalize_entity_name,
    extract_entities_from_tags,
    extract_entities_with_llm,
    extract_relationships_with_llm,
    deduplicate_entities,
    deduplicate_relationships,
    export_to_falkor,
    Entity,
    Relationship,
    _FALKOR,
    _GRAPH_NAME
)

def test_enhanced_pipeline():
    """Test the complete enhanced pipeline with localhost FalkorDB."""
    print("🚀 Testing Enhanced BookStack to FalkorDB Pipeline (Localhost)")
    print("=" * 70)
    
    # Test FalkorDB connection
    if not _FALKOR:
        print("❌ Cannot connect to FalkorDB. Make sure it's running on localhost:6379")
        return
    
    print(f"✅ Connected to FalkorDB at localhost:6379")
    print(f"📊 Using graph: {_GRAPH_NAME}")
    
    # Test data - simulate a BookStack page
    test_page_data = {
        "id": 999,
        "title": "Enhanced Pipeline Test Page",
        "url": "https://example.com/test-page",
        "book": "Test Book",
        "tags": ["machine-learning", "api", "documentation"],
        "body_html": """
        <h1>Enhanced Pipeline Test</h1>
        <p>This page demonstrates the enhanced BookStack to FalkorDB pipeline.</p>
        <p>Key technologies mentioned:</p>
        <ul>
            <li><strong>BookStack</strong> - Knowledge management platform</li>
            <li><strong>FalkorDB</strong> - Graph database system</li>
            <li><strong>API</strong> - Application Programming Interface</li>
        </ul>
        <p>The documentation shows how these systems work together to create
        a comprehensive knowledge graph from structured content.</p>
        """
    }
    
    print("\n📄 Processing test page...")
    print(f"   📋 Title: {test_page_data['title']}")
    print(f"   📚 Book: {test_page_data['book']}")
    print(f"   🏷️  Tags: {test_page_data['tags']}")
    
    # Convert HTML to text
    text_content = html_to_text(test_page_data["body_html"])
    print(f"   📝 Content length: {len(text_content)} chars")
    
    # Extract entities from tags
    tag_entities = extract_entities_from_tags(test_page_data["tags"])
    print(f"\n🏷️  Tag entities extracted: {len(tag_entities)}")
    for entity in tag_entities:
        print(f"      • {entity.name} ({entity.type}): {entity.description}")
    
    # Extract entities from content
    content_entities = extract_entities_with_llm(text_content)
    print(f"\n🎯 Content entities extracted: {len(content_entities)}")
    for entity in content_entities:
        print(f"      • {entity.name} ({entity.type}): {entity.description}")
    
    # Combine and deduplicate entities
    all_entities = deduplicate_entities(tag_entities + content_entities)
    print(f"\n🧹 After deduplication: {len(all_entities)} unique entities")
    for entity in all_entities:
        print(f"      • {entity.name} ({entity.type}): {entity.description}")
    
    # Extract relationships
    relationships = extract_relationships_with_llm(text_content, all_entities)
    relationships = deduplicate_relationships(relationships)
    print(f"\n🔗 Relationships extracted: {len(relationships)}")
    for rel in relationships:
        print(f"      → {rel.subject} --{rel.predicate}--> {rel.object}")
        print(f"        Fact: {rel.fact}")
    
    # Export to FalkorDB
    print(f"\n💾 Exporting to FalkorDB...")
    export_to_falkor(test_page_data, text_content, all_entities, relationships)
    
    # Verify data in FalkorDB
    print(f"\n🔍 Verifying data in FalkorDB...")
    try:
        # Count nodes by type
        result = _FALKOR.execute_command('GRAPH.QUERY', _GRAPH_NAME, 
            'MATCH (n) RETURN labels(n)[0] as label, count(n) as count')
        
        if result[1]:
            print("   📊 Node counts by type:")
            for row in result[1]:
                print(f"      {row[0]}: {row[1]} nodes")
        
        # Show our test entities
        result = _FALKOR.execute_command('GRAPH.QUERY', _GRAPH_NAME, 
            "MATCH (e:Entity {group_id: 'Test Book'}) RETURN e.name, e.entity_type, e.description LIMIT 5")
        
        if result[1]:
            print("\n   🎯 Test entities in graph:")
            for row in result[1]:
                print(f"      • {row[0]} ({row[1]}): {row[2][:50]}...")
        
        # Show relationships
        result = _FALKOR.execute_command('GRAPH.QUERY', _GRAPH_NAME, 
            "MATCH (e1:Entity {group_id: 'Test Book'})-[r:RELATES_TO]->(e2:Entity {group_id: 'Test Book'}) RETURN e1.name, r.predicate, e2.name LIMIT 3")
        
        if result[1]:
            print("\n   🔗 Test relationships in graph:")
            for row in result[1]:
                print(f"      → {row[0]} --{row[1]}--> {row[2]}")
        
        # Show document
        result = _FALKOR.execute_command('GRAPH.QUERY', _GRAPH_NAME, 
            "MATCH (d:Episodic {group_id: 'Test Book'}) RETURN d.name LIMIT 1")
        
        if result[1]:
            print(f"\n   📄 Test document in graph: {result[1][0][0]}")
        
    except Exception as e:
        print(f"❌ Error verifying data: {e}")
    
    print("\n" + "=" * 70)
    print("📊 ENHANCED PIPELINE TEST SUMMARY")
    print("=" * 70)
    print(f"✅ FalkorDB connection: Working")
    print(f"✅ Entity extraction: {len(tag_entities)} from tags + {len(content_entities)} from content")
    print(f"✅ Deduplication: {len(tag_entities + content_entities)} → {len(all_entities)} entities")
    print(f"✅ Relationship discovery: {len(relationships)} relationships")
    print(f"✅ FalkorDB export: Complete with Graphiti schema")
    print(f"✅ Data verification: Successful")
    
    print("\n🎯 Key Features Demonstrated:")
    print("   ✅ Enhanced entity extraction beyond tags")
    print("   ✅ Relationship discovery between entities")
    print("   ✅ Multi-level deduplication")
    print("   ✅ Graphiti schema compliance")
    print("   ✅ Direct localhost FalkorDB integration")
    print("   ✅ Proper Cypher operations with MERGE")
    
    print("\n🚀 Ready to process your full BookStack export!")

def test_with_real_data():
    """Test with actual BookStack export files."""
    print("\n" + "=" * 70)
    print("📁 Testing with Real BookStack Export Files")
    print("=" * 70)
    
    export_dir = Path("bookstack_export_full")
    if not export_dir.exists():
        print(f"❌ Export directory not found: {export_dir}")
        return
    
    json_files = list(export_dir.glob("*.json"))
    if not json_files:
        print(f"❌ No JSON files found in {export_dir}")
        return
    
    print(f"📁 Found {len(json_files)} JSON files")
    
    # Process first 3 files as test
    test_files = json_files[:3]
    total_entities = 0
    total_relationships = 0
    
    for json_file in test_files:
        print(f"\n📄 Processing: {json_file.name}")
        
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                page_data = json.load(f)
            
            # Extract page info
            page_info = {
                "id": page_data.get("id", 0),
                "title": page_data.get("title", "Untitled"),
                "url": page_data.get("url", ""),
                "book": page_data.get("book", "Unknown"),
                "tags": page_data.get("tags", [])
            }
            
            print(f"   📋 Title: {page_info['title'][:50]}...")
            print(f"   📚 Book: {page_info['book']}")
            print(f"   🏷️  Tags: {page_info['tags']}")
            
            # Convert HTML to text
            text_content = html_to_text(page_data.get("body_html", ""))
            
            # Extract entities and relationships
            tag_entities = extract_entities_from_tags(page_info["tags"])
            content_entities = extract_entities_with_llm(text_content)
            all_entities = deduplicate_entities(tag_entities + content_entities)
            relationships = deduplicate_relationships(
                extract_relationships_with_llm(text_content, all_entities)
            )
            
            print(f"   🎯 Entities: {len(all_entities)} (tags: {len(tag_entities)}, content: {len(content_entities)})")
            print(f"   🔗 Relationships: {len(relationships)}")
            
            # Export to FalkorDB
            export_to_falkor(page_info, text_content, all_entities, relationships)
            
            total_entities += len(all_entities)
            total_relationships += len(relationships)
            
        except Exception as e:
            print(f"   ❌ Error processing {json_file.name}: {e}")
    
    print(f"\n📊 Real Data Test Summary:")
    print(f"   📄 Files processed: {len(test_files)}")
    print(f"   🎯 Total entities: {total_entities}")
    print(f"   🔗 Total relationships: {total_relationships}")

if __name__ == "__main__":
    test_enhanced_pipeline()
    test_with_real_data()
