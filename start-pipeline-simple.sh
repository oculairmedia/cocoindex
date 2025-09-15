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

# Continuous export loop
while true; do
    echo "📥 Starting BookStack export..."
    python export_all_to_falkor.py || {
        echo "⚠️  Export failed, retrying in 60s..."
        sleep 60
        continue
    }
    
    echo "✅ Export complete, waiting 2 minutes before next sync..."
    sleep 120
done