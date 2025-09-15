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

# Export BookStack data first (if credentials provided)
if [ -n "$BS_URL" ] && [ -n "$BS_TOKEN_ID" ] && [ -n "$BS_TOKEN_SECRET" ]; then
    echo "📥 Exporting BookStack data..."
    python export_all_to_falkor.py || {
        echo "⚠️  Direct export failed, continuing with CocoIndex pipeline..."
    }
fi

# Setup CocoIndex flow
echo "🔧 Setting up CocoIndex flow..."
export COCOINDEX_DATABASE_URL="${COCOINDEX_DATABASE_URL:-postgresql://cocoindex:cocoindex@postgres:5432/cocoindex}"
echo "Using database: $COCOINDEX_DATABASE_URL"

# Initialize CocoIndex and create tables
echo "📊 Initializing database tables..."
cocoindex update --setup "$FLOW_FILE"

# Run one-time update to ensure everything works
echo "🔄 Running initial update..."
cocoindex update "$FLOW_FILE"

# Start the pipeline
echo "🚀 Starting continuous pipeline..."
exec cocoindex update "$FLOW_FILE" -L