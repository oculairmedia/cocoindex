"""
Minimal test to see if we can run the flow without CocoIndex CLI
"""
import os
os.environ["DRY_RUN"] = "true"

# Test just the core logic
from test_dry_run import test_pipeline

if __name__ == "__main__":
    test_pipeline()