#!/usr/bin/env python3
"""
Test Ollama Gemma3 connection and entity extraction.
"""

import requests
import json

def test_ollama():
    """Test Ollama API with Gemma3."""
    print("Testing Ollama Gemma3 12B Connection")
    print("=" * 50)
    
    # Check if Ollama is running
    try:
        response = requests.get("http://localhost:11434/api/tags")
        models = response.json()
        
        print("Available models:")
        for model in models.get('models', []):
            print(f"  - {model['name']}")
        
        # Check for Gemma3
        has_gemma3 = any('gemma3' in m['name'] for m in models.get('models', []))
        if not has_gemma3:
            print("\nERROR: Gemma3 model not found!")
            print("Install with: ollama pull gemma3:12b")
            return False
            
    except Exception as e:
        print(f"ERROR: Cannot connect to Ollama: {e}")
        print("Make sure Ollama is running: ollama serve")
        return False
    
    # Test entity extraction
    print("\nTesting entity extraction...")
    
    test_text = """
    BookStack is a documentation platform that integrates with FalkorDB, 
    a graph database built on Redis. The system uses Docker for deployment 
    and PostgreSQL for metadata storage. CocoIndex handles the data pipeline.
    """
    
    prompt = f"""Extract entities from this text. Return a JSON array of entities with name, type, and description.
Types: TECHNOLOGY, CONCEPT, PERSON, ORGANIZATION, LOCATION

Text: {test_text}

Entities:"""
    
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "gemma3:12b",
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "num_predict": 500
                }
            }
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"\nOllama response:")
            print(result['response'])
            return True
        else:
            print(f"ERROR: Generation failed: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"ERROR: {e}")
        return False

if __name__ == "__main__":
    test_ollama()