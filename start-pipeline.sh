#!/bin/bash
# Pipeline startup script - runs inside the container

set -e

echo "🚀 Starting BookStack to FalkorDB Pipeline"
echo "Pipeline Mode: ${PIPELINE_MODE:-enhanced}"
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

# Test database connection if PostgreSQL is configured
if [ -n "$COCOINDEX_DATABASE_URL" ]; then
    echo "⏳ Waiting for PostgreSQL..."
    until python -c "
import psycopg2
import os
try:
    conn = psycopg2.connect(os.environ['COCOINDEX_DATABASE_URL'])
    conn.close()
    print('✅ PostgreSQL is ready')
except Exception as e:
    print(f'   PostgreSQL not ready: {e}')
    exit(1)
"; do
        echo "   PostgreSQL not ready, waiting 5s..."
        sleep 5
    done
fi

# Choose pipeline based on mode
case "${PIPELINE_MODE:-enhanced}" in
    "simple")
        FLOW_FILE="flows/bookstack_ollama_simple.py"
        echo "🏃 Using Simple Pipeline (keyword-based extraction)"
        ;;
    "enhanced"|*)
        FLOW_FILE="flows/bookstack_enhanced_ollama.py"
        echo "🧠 Using Enhanced Pipeline (Ollama LLM + CocoIndex integration)"
        ;;
esac

# Test Ollama connectivity (optional)
if [ -n "$OLLAMA_URL" ]; then
    echo "🤖 Testing Ollama connectivity..."
    if curl -s "$OLLAMA_URL/api/tags" > /dev/null; then
        echo "✅ Ollama is available"
    else
        echo "⚠️  Ollama not available, will use fallback extraction"
    fi
fi

# Export BookStack JSON files only if directory is empty (no direct FalkorDB export)
if [ -n "$BS_URL" ] && [ -n "$BS_TOKEN_ID" ] && [ -n "$BS_TOKEN_SECRET" ]; then
    if [ ! -d "bookstack_export" ] || [ -z "$(ls -A bookstack_export 2>/dev/null)" ]; then
        echo "📥 Exporting BookStack JSON files for CocoIndex processing..."
        python scripts/bookstack_export.py --limit 200 --out bookstack_export_full || {
            echo "⚠️  BookStack export failed, check credentials"
            echo "⏩  Continuing with existing files if available..."
        }
    else
        echo "📂 Using existing BookStack export files ($(ls bookstack_export/*.json 2>/dev/null | wc -l) files)"
    fi
fi

# Setup CocoIndex flow ONLY - no direct export
echo "🔧 Setting up CocoIndex flow..."
export COCOINDEX_DATABASE_URL="${COCOINDEX_DATABASE_URL:-postgresql://cocoindex:cocoindex@postgres:5432/cocoindex}"
echo "Using database: $COCOINDEX_DATABASE_URL"

# Setup CocoIndex flow (non-interactive)
echo "📊 Setting up CocoIndex flow..."
cocoindex update --setup --force "$FLOW_FILE" || {
    echo "⚠️  CocoIndex setup failed, retrying in 60s..."
    sleep 60
}

# Run the enhanced pipeline once
echo "🔄 Running enhanced pipeline..."
cocoindex update "$FLOW_FILE" || {
    echo "⚠️  Pipeline failed, retrying in 60s..."
    sleep 60
}

# Start continuous monitoring
echo "🚀 Starting continuous enhanced pipeline..."
exec cocoindex update "$FLOW_FILE" -L