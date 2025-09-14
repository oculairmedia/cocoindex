#!/usr/bin/env python3
"""
Check all dependencies and environment variables for BookStack to FalkorDB pipeline
"""

import os
import sys
import importlib
from typing import Dict, List, Tuple

# Python package dependencies
REQUIRED_PACKAGES = {
    "requests": "HTTP client for BookStack API",
    "beautifulsoup4": "HTML parsing for content extraction", 
    "redis": "FalkorDB client connection",
    "cocoindex": "Core indexing framework"
}

# Environment variables
ENV_VARS = {
    # BookStack
    "BS_URL": ("BookStack API URL", "https://knowledge.oculair.ca", True),
    "BS_TOKEN_ID": ("BookStack API token ID", "***", True),
    "BS_TOKEN_SECRET": ("BookStack API token secret", "***", True),
    
    # FalkorDB
    "FALKOR_HOST": ("FalkorDB host", "192.168.50.90", True),
    "FALKOR_PORT": ("FalkorDB port", "6379", True),
    "FALKOR_GRAPH": ("FalkorDB graph name", "graphiti_migration", True),
    
    # Embeddings
    "EMB_URL": ("Embedding service URL", "http://192.168.50.80:11434/v1/embeddings", True),
    "EMB_KEY": ("Embedding API key", "ollama", True),
    "EMB_MODEL": ("Embedding model name", "dengcao/Qwen3-Embedding-4B:Q4_K_M", True),
    
    # Optional
    "DRY_RUN": ("Dry run mode", "false", False),
    "OUT_DIR": ("BookStack export directory", "bookstack_export", False)
}

def check_python_packages() -> List[Tuple[str, bool, str]]:
    """Check if required Python packages are installed"""
    results = []
    
    for package, description in REQUIRED_PACKAGES.items():
        try:
            if package == "beautifulsoup4":
                importlib.import_module("bs4")
            else:
                importlib.import_module(package)
            results.append((package, True, description))
        except ImportError:
            results.append((package, False, description))
    
    return results

def check_env_vars() -> List[Tuple[str, bool, str, str]]:
    """Check environment variables"""
    results = []
    
    for var, (description, default, required) in ENV_VARS.items():
        value = os.getenv(var)
        
        if value:
            # Mask sensitive values
            if "TOKEN" in var or "SECRET" in var or "KEY" in var:
                display_value = value[:4] + "***" if len(value) > 4 else "***"
            else:
                display_value = value
            results.append((var, True, description, display_value))
        else:
            results.append((var, False, description, f"Not set (default: {default})"))
    
    return results

def check_connectivity():
    """Check if services are reachable (when not in dry run)"""
    print("\n=== Service Connectivity ===")
    
    if os.getenv("DRY_RUN", "").lower() in ("true", "1", "yes"):
        print("DRY RUN mode enabled - skipping connectivity checks")
        return
    
    # Check BookStack
    print("\n1. BookStack API:")
    bs_url = os.getenv("BS_URL")
    if bs_url:
        try:
            import requests
            r = requests.get(f"{bs_url}/api/docs", timeout=5)
            print(f"   [OK] Reachable at {bs_url} (status: {r.status_code})")
        except Exception as e:
            print(f"   [FAIL] Cannot reach {bs_url}: {type(e).__name__}")
    else:
        print("   - BS_URL not set")
    
    # Check FalkorDB
    print("\n2. FalkorDB:")
    falkor_host = os.getenv("FALKOR_HOST")
    falkor_port = os.getenv("FALKOR_PORT", "6379")
    if falkor_host:
        try:
            import redis
            r = redis.Redis(host=falkor_host, port=int(falkor_port), socket_connect_timeout=5)
            r.ping()
            print(f"   [OK] Reachable at {falkor_host}:{falkor_port}")
        except Exception as e:
            print(f"   [FAIL] Cannot reach {falkor_host}:{falkor_port}: {type(e).__name__}")
    else:
        print("   - FALKOR_HOST not set")
    
    # Check Embedding service
    print("\n3. Embedding Service:")
    emb_url = os.getenv("EMB_URL")
    if emb_url:
        try:
            import requests
            # Try to get model list or health endpoint
            base_url = emb_url.replace("/v1/embeddings", "")
            r = requests.get(f"{base_url}/v1/models", timeout=5)
            print(f"   [OK] Reachable at {emb_url}")
        except Exception as e:
            print(f"   [FAIL] Cannot reach {emb_url}: {type(e).__name__}")
    else:
        print("   - EMB_URL not set")

def main():
    print("=== BookStack to FalkorDB Pipeline Dependency Check ===\n")
    
    # Check Python packages
    print("=== Python Packages ===")
    packages = check_python_packages()
    all_packages_ok = True
    
    for package, installed, description in packages:
        status = "[OK]" if installed else "[MISSING]"
        print(f"{status} {package:<20} - {description}")
        if not installed:
            all_packages_ok = False
    
    if not all_packages_ok:
        print("\nTo install missing packages:")
        print("pip install " + " ".join([p[0] for p in packages if not p[1]]))
    
    # Check environment variables
    print("\n=== Environment Variables ===")
    env_vars = check_env_vars()
    required_missing = []
    
    for var, set_status, description, value in env_vars:
        status = "[SET]" if set_status else "[NOT SET]"
        required = ENV_VARS[var][2]
        req_marker = "*" if required else " "
        print(f"{status}{req_marker} {var:<20} - {description:<35} [{value}]")
        
        if required and not set_status:
            required_missing.append(var)
    
    if required_missing:
        print(f"\n[WARNING] Missing {len(required_missing)} required environment variables: {', '.join(required_missing)}")
    
    print("\n* = Required variable")
    
    # Check connectivity
    check_connectivity()
    
    # Summary
    print("\n=== Summary ===")
    if all_packages_ok and not required_missing:
        print("[OK] All dependencies satisfied!")
        if os.getenv("DRY_RUN", "").lower() in ("true", "1", "yes"):
            print("[OK] DRY RUN mode is enabled - no data will be written")
    else:
        print("[ERROR] Some dependencies are missing")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())