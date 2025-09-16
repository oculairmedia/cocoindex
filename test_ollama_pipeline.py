#!/usr/bin/env python3
"""
Test script for the corrected Ollama entity extraction pipeline.
Validates CocoIndex conventions and Ollama connectivity.
"""

import os
import sys
import json
import requests
from pathlib import Path

def setup_test_environment():
    """Set up environment variables for testing."""
    # Ollama configuration
    os.environ["OLLAMA_URL"] = "http://100.81.139.20:11434"
    
    # FalkorDB configuration
    os.environ["FALKOR_HOST"] = "localhost"
    os.environ["FALKOR_PORT"] = "6379"
    os.environ["FALKOR_GRAPH"] = "graphiti_migration"
    
    # CocoIndex database
    os.environ["COCOINDEX_DATABASE_URL"] = "postgresql://cocoindex:cocoindex@localhost:5433/cocoindex"
    
    print("✅ Environment variables configured")

def test_ollama_connectivity():
    """Test Ollama server connectivity and model availability."""
    ollama_url = os.environ.get("OLLAMA_URL", "http://100.81.139.20:11434")
    
    try:
        # Test basic connectivity
        response = requests.get(f"{ollama_url}/api/tags", timeout=10)
        if response.status_code == 200:
            models = response.json().get("models", [])
            model_names = [model["name"] for model in models]
            
            print(f"✅ Ollama server accessible at {ollama_url}")
            print(f"📋 Available models: {model_names}")
            
            # Check if gemma3:12b is available
            if "gemma3:12b" in model_names:
                print("✅ gemma3:12b model is available")
                return True
            else:
                print("⚠️  gemma3:12b model not found. Available models:")
                for model in model_names:
                    print(f"   - {model}")
                return False
        else:
            print(f"❌ Ollama server returned status {response.status_code}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Cannot connect to Ollama server: {e}")
        return False

def test_falkor_connectivity():
    """Test FalkorDB connectivity."""
    try:
        from flows.falkordb_export import test_falkor_connection
        return test_falkor_connection()
    except ImportError as e:
        print(f"❌ Cannot import FalkorDB test function: {e}")
        return False

def test_bookstack_data():
    """Test BookStack export data availability."""
    export_dir = Path("bookstack_export_full")
    
    if not export_dir.exists():
        print(f"❌ BookStack export directory not found: {export_dir}")
        return False
    
    json_files = list(export_dir.glob("*.json"))
    if not json_files:
        print(f"❌ No JSON files found in {export_dir}")
        return False
    
    print(f"✅ Found {len(json_files)} BookStack JSON files")
    
    # Test parsing a sample file
    try:
        sample_file = json_files[0]
        with open(sample_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        required_fields = ['id', 'title', 'body_html', 'book']
        missing_fields = [field for field in required_fields if field not in data]
        
        if missing_fields:
            print(f"⚠️  Sample file missing fields: {missing_fields}")
        else:
            print("✅ Sample JSON file has required fields")
            
        return len(missing_fields) == 0
        
    except Exception as e:
        print(f"❌ Error parsing sample JSON file: {e}")
        return False

def test_cocoindex_installation():
    """Test CocoIndex installation and basic functionality."""
    try:
        import cocoindex
        print(f"✅ CocoIndex imported successfully (version: {getattr(cocoindex, '__version__', 'unknown')})")
        
        # Test basic classes
        from cocoindex import DataScope, FlowBuilder
        print("✅ CocoIndex core classes available")
        
        # Test LLM functions
        from cocoindex.functions import ExtractByLlm
        from cocoindex import LlmSpec, LlmApiType
        print("✅ CocoIndex LLM functions available")
        
        return True
        
    except ImportError as e:
        print(f"❌ CocoIndex import failed: {e}")
        return False

def test_dataclass_definitions():
    """Test that our dataclass definitions are valid."""
    try:
        from flows.bookstack_ollama_corrected import Entity, Relationship, DocumentSummary, DocumentAnalysis
        
        # Test Entity
        entity = Entity(name="test", type="TECHNOLOGY", description="test entity")
        print("✅ Entity dataclass works")
        
        # Test Relationship
        rel = Relationship(subject="A", predicate="uses", object="B", fact="test fact")
        print("✅ Relationship dataclass works")
        
        # Test DocumentSummary
        summary = DocumentSummary(title="Test", summary="Test summary")
        print("✅ DocumentSummary dataclass works")
        
        # Test DocumentAnalysis
        analysis = DocumentAnalysis(entities=[entity], relationships=[rel], summary=summary)
        print("✅ DocumentAnalysis dataclass works")
        
        return True
        
    except Exception as e:
        print(f"❌ Dataclass definition error: {e}")
        return False

def test_flow_syntax():
    """Test that the flow definition is syntactically correct."""
    try:
        from flows.bookstack_ollama_corrected import bookstack_ollama_corrected_flow
        print("✅ Flow function imports successfully")
        
        # Check if it's properly decorated
        if hasattr(bookstack_ollama_corrected_flow, '__cocoindex_flow_name__'):
            print(f"✅ Flow properly decorated with name: {bookstack_ollama_corrected_flow.__cocoindex_flow_name__}")
        else:
            print("⚠️  Flow decoration may be missing")
        
        return True
        
    except Exception as e:
        print(f"❌ Flow syntax error: {e}")
        return False

def run_comprehensive_test():
    """Run all tests and provide a summary."""
    print("🧪 CocoIndex Ollama Pipeline Test Suite")
    print("=" * 50)
    
    setup_test_environment()
    
    tests = [
        ("CocoIndex Installation", test_cocoindex_installation),
        ("Dataclass Definitions", test_dataclass_definitions),
        ("Flow Syntax", test_flow_syntax),
        ("BookStack Data", test_bookstack_data),
        ("Ollama Connectivity", test_ollama_connectivity),
        ("FalkorDB Connectivity", test_falkor_connectivity),
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        print(f"\n🔍 Testing {test_name}...")
        try:
            results[test_name] = test_func()
        except Exception as e:
            print(f"❌ Test {test_name} failed with exception: {e}")
            results[test_name] = False
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 TEST SUMMARY")
    print("=" * 50)
    
    passed = sum(results.values())
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {test_name}")
    
    print(f"\n🎯 Overall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Pipeline should work correctly.")
        print("\nNext steps:")
        print("1. Run: python run_cocoindex.py update --setup flows/bookstack_ollama_corrected.py")
        print("2. Run: python run_cocoindex.py update flows/bookstack_ollama_corrected.py")
    else:
        print("⚠️  Some tests failed. Please fix the issues before running the pipeline.")
    
    return passed == total

if __name__ == "__main__":
    success = run_comprehensive_test()
    sys.exit(0 if success else 1)
