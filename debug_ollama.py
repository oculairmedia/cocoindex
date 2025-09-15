#!/usr/bin/env python3
"""
Debug Ollama responses.
"""

import requests
import json

prompt = "What is 2+2?"

response = requests.post(
    "http://localhost:11434/api/generate",
    json={
        "model": "gemma3:270m",
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_predict": 200,
            "stop": ["\n\n", "```"]
        }
    },
    timeout=30
)

print(f"Status: {response.status_code}")
if response.status_code == 200:
    result = response.json()
    print(f"Response: '{result['response']}'")
    print(f"Length: {len(result['response'])}")
else:
    print(f"Error: {response.text}")