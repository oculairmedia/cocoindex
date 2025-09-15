#!/usr/bin/env python3
"""
Wrapper to run cocoindex with proper environment setup
"""
import os
import sys
import subprocess

def setup_environment():
    """Set up environment variables"""
    # Add Scripts to PATH
    scripts_path = r"C:\Users\Emmanuel\AppData\Roaming\Python\Python312\Scripts"
    os.environ["PATH"] = os.environ.get("PATH", "") + os.pathsep + scripts_path
    
    # Set dry run mode for testing
    os.environ["DRY_RUN"] = "true"
    
    # Set BookStack credentials
    os.environ["BS_URL"] = "https://knowledge.oculair.ca"
    os.environ["BS_TOKEN_ID"] = "POnHR9Lbvm73T2IOcyRSeAqpA8bSGdMT"
    os.environ["BS_TOKEN_SECRET"] = "735wM5dScfUkcOy7qcrgqQ1eC5fBF7IE"
    
    # Set FalkorDB defaults (for dry run)
    os.environ["FALKOR_HOST"] = "localhost"
    os.environ["FALKOR_PORT"] = "6379"
    os.environ["FALKOR_GRAPH"] = "graphiti_migration"
    
    # Set Embedding defaults (for dry run)
    os.environ["EMB_URL"] = "http://192.168.50.80:11434/v1/embeddings"
    os.environ["EMB_KEY"] = "ollama"
    os.environ["EMB_MODEL"] = "dengcao/Qwen3-Embedding-4B:Q4_K_M"

    # Set CocoIndex database URL (required for operation)
    # Using PostgreSQL in Docker for CocoIndex metadata
    postgres_url = "postgresql://cocoindex:cocoindex@localhost:5433/cocoindex"
    os.environ["COCOINDEX_DATABASE_URL"] = postgres_url
    print(f"[INFO] Using CocoIndex database: {postgres_url}")
    print(f"[INFO] DRY_RUN mode: {os.environ.get('DRY_RUN', 'false')}")
    print(f"[INFO] Environment variables set for CocoIndex")
    print(f"[INFO] Make sure PostgreSQL is running: docker-compose -f docker-compose.cocoindex.yml up -d")

def main():
    setup_environment()
    
    # Get command line args
    if len(sys.argv) < 2:
        print("Usage: python run_cocoindex.py <command> [args...]")
        print("Example: python run_cocoindex.py update --setup flows/bookstack_to_falkor.py")
        return 1
    
    # Build cocoindex command
    cocoindex_exe = r"C:\Users\Emmanuel\AppData\Roaming\Python\Python312\Scripts\cocoindex.exe"
    cmd = [cocoindex_exe] + sys.argv[1:]
    
    print(f"Running: {' '.join(cmd)}")
    print("-" * 60)
    
    # Run cocoindex
    try:
        result = subprocess.run(cmd, check=True)
        return result.returncode
    except subprocess.CalledProcessError as e:
        print(f"Error running cocoindex: {e}")
        return e.returncode
    except FileNotFoundError:
        print(f"CocoIndex not found at: {cocoindex_exe}")
        print("Please ensure cocoindex is installed with: pip install --user cocoindex")
        return 1

if __name__ == "__main__":
    sys.exit(main())