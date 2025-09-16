#!/bin/bash
# Simplified pipeline startup script - runs direct export only

set -e

echo "🚀 Starting BookStack to FalkorDB Pipeline (Direct Export Mode)"
echo "BookStack URL: ${BS_URL}"
echo "FalkorDB: ${FALKOR_HOST}:${FALKOR_PORT}"
echo "Graph: ${FALKOR_GRAPH}"

# Wait for dependencies
echo "⏳ Waiting for FalkorDB..."
while ! timeout 5 bash -c "</dev/tcp/${FALKOR_HOST}/${FALKOR_PORT}" 2>/dev/null; do
    echo "   FalkorDB not ready, waiting 5s..."
    sleep 5
done
echo "✅ FalkorDB is ready"

# Export BookStack data first using scripts (if credentials provided)
if [ -n "$BS_URL" ] && [ -n "$BS_TOKEN_ID" ] && [ -n "$BS_TOKEN_SECRET" ]; then
    echo "📥 Exporting BookStack JSON files..."
    python scripts/bookstack_export.py --limit 200 || {
        echo "⚠️  BookStack export failed, check credentials"
        exit 1
    }
fi

# Continuous export loop using simple pipeline
while true; do
    echo "📥 Running simple CocoIndex pipeline..."
    echo "y" | cocoindex update --setup flows/bookstack_ollama_simple.py || {
        echo "⚠️  Setup failed, retrying in 60s..."
        sleep 60
        continue
    }
    
    cocoindex update flows/bookstack_ollama_simple.py || {
        echo "⚠️  Pipeline failed, retrying in 60s..."
        sleep 60
        continue
    }
    
    echo "✅ Pipeline complete, waiting 2 minutes before next sync..."
    sleep 120
done