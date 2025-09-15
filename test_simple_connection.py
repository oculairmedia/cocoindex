#!/usr/bin/env python3
"""
Simple test to verify FalkorDB connection
"""

import os
import redis

# Set up environment for testing
os.environ["FALKOR_HOST"] = "localhost"
os.environ["FALKOR_PORT"] = "6379"
os.environ["FALKOR_GRAPH"] = "graphiti_migration"

def test_falkor_connection():
    """Test basic FalkorDB connection."""
    print("Testing FalkorDB Connection")
    print("=" * 40)
    
    try:
        # Connect to FalkorDB
        r = redis.Redis(host='localhost', port=6379, decode_responses=True)
        
        # Test basic connection
        result = r.ping()
        print(f"Ping result: {result}")
        
        # Test graph operation
        query = "CREATE (n:Test {name: 'Connection Test'}) RETURN n"
        result = r.execute_command("GRAPH.QUERY", "graphiti_migration", query)
        print(f"Graph query result: {result}")
        
        # Test graph read
        query = "MATCH (n:Test) RETURN n.name"
        result = r.execute_command("GRAPH.QUERY", "graphiti_migration", query)
        print(f"Graph read result: {result}")
        
        print("\nConnection test successful!")
        return True
        
    except Exception as e:
        print(f"Connection failed: {e}")
        return False

if __name__ == "__main__":
    test_falkor_connection()