#!/usr/bin/env python3
"""
Simple BookStack API test - just try to get pages
"""

import requests

BOOKSTACK_URL = "https://knowledge.oculair.ca"
BOOKSTACK_TOKEN_ID = "POnHR9Lbvm73T2IOcyRSeAqpA8bSGdMT"
BOOKSTACK_TOKEN_SECRET = "735wM5dScfUkcOy7qcrgqQ1eC5fBF7IE"

def test_pages():
    headers = {
        "Authorization": f"Token {BOOKSTACK_TOKEN_ID}:{BOOKSTACK_TOKEN_SECRET}",
        "Accept": "application/json"
    }
    
    try:
        print("Testing pages endpoint...")
        url = f"{BOOKSTACK_URL}/api/pages?count=5"
        response = requests.get(url, headers=headers, timeout=15)
        
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Success! Found {data.get('total', 0)} pages")
            
            pages = data.get('data', [])
            for page in pages[:3]:  # Show first 3
                print(f"  - {page.get('name', 'Unknown')} (ID: {page.get('id')})")
            return True
        else:
            print(f"Error: {response.text}")
            return False
            
    except Exception as e:
        print(f"Exception: {e}")
        return False

if __name__ == "__main__":
    test_pages()