#!/usr/bin/env python3
"""
Minimal test to verify FalkorDB connection and data insertion works
"""
import redis
import json
import os

def test_falkor_basic():
    """Test basic FalkorDB connection and node creation"""
    try:
        # Connect to FalkorDB
        r = redis.Redis(
            host='localhost',
            port=6379,
            decode_responses=True
        )
        r.ping()
        print("✅ Connected to FalkorDB")

        graph_name = "graphiti_migration"

        # Create a simple test node
        cypher = """
        CREATE (n:TestNode {
            title: 'Basic Test Node',
            content: 'Testing direct FalkorDB insertion',
            created_at: timestamp(),
            group_id: 'test'
        })
        RETURN n.title
        """

        result = r.execute_command('GRAPH.QUERY', graph_name, cypher)
        print(f"✅ Created test node: {result}")

        # Count all nodes
        count_cypher = "MATCH (n) RETURN count(n)"
        result = r.execute_command('GRAPH.QUERY', graph_name, count_cypher)
        node_count = result[1][0][0]
        print(f"📊 Total nodes in graph: {node_count}")

        # Read a sample BookStack file and create a real node
        sample_file = "bookstack_export_full/page_10.json"
        if os.path.exists(sample_file):
            with open(sample_file, 'r') as f:
                data = json.load(f)

            title = data.get('title', 'No Title').replace("'", "\\'")
            page_id = data.get('id', 0)

            book_cypher = f"""
            CREATE (n:BookStackPage {{
                title: '{title}',
                page_id: {page_id},
                created_at: timestamp(),
                group_id: 'bookstack_test'
            }})
            RETURN n.title
            """

            result = r.execute_command('GRAPH.QUERY', graph_name, book_cypher)
            print(f"✅ Created BookStack node: {title}")

            # Final count
            result = r.execute_command('GRAPH.QUERY', graph_name, count_cypher)
            node_count = result[1][0][0]
            print(f"📊 Final node count: {node_count}")

        print("\n🎉 Basic FalkorDB test successful!")
        print("Check the web UI at http://localhost:3001")

    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_falkor_basic()