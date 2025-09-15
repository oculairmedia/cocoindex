#!/usr/bin/env python3
"""
Test BookStack API connectivity
"""

import os
import requests

# Configuration
BOOKSTACK_URL = "https://knowledge.oculair.ca"
BOOKSTACK_TOKEN_ID = "POnHR9Lbvm73T2IOcyRSeAqpA8bSGdMT"
BOOKSTACK_TOKEN_SECRET = "735wM5dScfUkcOy7qcrgqQ1eC5fBF7IE"

def test_bookstack_connection():
    """Test basic BookStack API connectivity."""
    print("Testing BookStack API Connection")
    print("=" * 40)
    
    headers = {
        "Authorization": f"Token {BOOKSTACK_TOKEN_ID}:{BOOKSTACK_TOKEN_SECRET}",
        "Accept": "application/json",
        "User-Agent": "cocoindex-test/1.0"
    }
    
    try:
        # Test basic connection
        print(f"Connecting to: {BOOKSTACK_URL}")
        
        # Try to fetch user info first (usually a quick endpoint)
        url = f"{BOOKSTACK_URL}/api/users/me"
        print("Testing authentication...")
        response = requests.get(url, headers=headers, timeout=5)
        
        if response.status_code == 200:
            user_data = response.json()
            print(f"[SUCCESS] Authentication successful! User: {user_data.get('name', 'Unknown')}")
        else:
            print(f"[ERROR] Authentication failed: {response.status_code}")
            print(f"Response: {response.text}")
            return False
        
        # Test pages endpoint
        print("Testing pages endpoint...")
        url = f"{BOOKSTACK_URL}/api/pages?count=1"
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            pages = data.get('data', [])
            total = data.get('total', 0)
            print(f"[SUCCESS] Pages endpoint working! Found {total} total pages")
            
            if pages:
                print(f"  Sample page: {pages[0].get('name', 'Unknown')}")
                
                # Test getting page details
                page_id = pages[0]['id']
                detail_url = f"{BOOKSTACK_URL}/api/pages/{page_id}?include=book,chapter,tags"
                detail_response = requests.get(detail_url, headers=headers, timeout=10)
                
                if detail_response.status_code == 200:
                    print(f"[SUCCESS] Page details endpoint working!")
                    page_detail = detail_response.json()
                    print(f"  Page has {len(page_detail.get('html', ''))} chars of HTML")
                    print(f"  Tags: {len(page_detail.get('tags', []))}")
                else:
                    print(f"[ERROR] Page details failed: {detail_response.status_code}")
        else:
            print(f"[ERROR] Pages endpoint failed: {response.status_code}")
            print(f"Response: {response.text}")
            return False
        
        print("\n[SUCCESS] All API tests passed!")
        return True
        
    except requests.exceptions.Timeout:
        print("[ERROR] Connection timed out - server may be slow or unreachable")
        return False
    except requests.exceptions.ConnectionError as e:
        print(f"[ERROR] Connection error: {e}")
        return False
    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}")
        return False

if __name__ == "__main__":
    test_bookstack_connection()