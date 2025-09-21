#!/bin/bash
# Pipeline startup script - runs inside the container

set -e

echo "🚀 Starting Graphiti-Compliant Data Pipeline"
echo "Pipeline Type: ${PIPELINE_TYPE:-bookstack}"
echo "Pipeline Mode: ${PIPELINE_MODE:-graphiti}"
echo "BookStack URL: ${BS_URL}"
echo "Huly API: ${HULY_API_URL:-${HULY_URL:-"(not set)"}}"
echo "FalkorDB: ${FALKOR_HOST}:${FALKOR_PORT}"
echo "Graph: ${FALKOR_GRAPH}"

export HULY_EXPORT_PATH="${HULY_EXPORT_PATH:-huly_export_full}"

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

# Function to setup and run a pipeline
run_pipeline() {
    local flow_file=$1
    local pipeline_name=$2

    echo "📊 Setting up $pipeline_name pipeline..."
    cocoindex update --setup --force "$flow_file" || {
        echo "⚠️  $pipeline_name setup failed, retrying in 60s..."
        sleep 60
        cocoindex update --setup --force "$flow_file"
    }

    echo "🔄 Running $pipeline_name pipeline..."
    cocoindex update "$flow_file" || {
        echo "⚠️  $pipeline_name pipeline failed, retrying in 60s..."
        sleep 60
    }
}

# Test Ollama connectivity (optional)
if [ -n "$OLLAMA_URL" ]; then
    echo "🤖 Testing Ollama connectivity..."
    if curl -s "$OLLAMA_URL/api/tags" > /dev/null; then
        echo "✅ Ollama is available"
    else
        echo "⚠️  Ollama not available, will use fallback extraction"
    fi
fi

# Export data based on pipeline type
case "${PIPELINE_TYPE:-bookstack}" in
    "bookstack"|"both")
        # Export BookStack JSON files only if directory is empty
        if [ -n "$BS_URL" ] && [ -n "$BS_TOKEN_ID" ] && [ -n "$BS_TOKEN_SECRET" ]; then
            if [ ! -d "bookstack_export_full" ] || [ -z "$(ls -A bookstack_export_full 2>/dev/null)" ]; then
                echo "📥 Exporting BookStack JSON files for CocoIndex processing..."
                python scripts/bookstack_export.py --limit 200 --out bookstack_export_full || {
                    echo "⚠️  BookStack export failed, check credentials"
                    echo "⏩  Continuing with existing files if available..."
                }
            else
                echo "📂 Using existing BookStack export files ($(ls bookstack_export_full/*.json 2>/dev/null | wc -l) files)"
            fi
        fi
        ;;
esac

case "${PIPELINE_TYPE:-bookstack}" in
    "huly"|"both")
        # Export Huly data if API configured
        HULY_DATA_URL="${HULY_API_URL:-}"
        if [ -z "$HULY_DATA_URL" ] && [ -n "$HULY_URL" ]; then
            HULY_DATA_URL="${HULY_URL%/mcp}/api"
        fi
        if [ -n "$HULY_DATA_URL" ]; then
            if [ ! -d "huly_export_full" ] || [ -z "$(ls -A huly_export_full 2>/dev/null)" ]; then
                echo "📥 Exporting Huly data for CocoIndex processing..."
                HULY_API_URL="$HULY_DATA_URL" python scripts/huly_export.py --out huly_export_full || {
                    echo "⚠️  Huly export failed, check API connectivity"
                    echo "⏩  Using mock data if available..."
                }
            else
                echo "📂 Using existing Huly export files ($(ls huly_export_full/*.json 2>/dev/null | wc -l) files)"
            fi
        else
            echo "⏩ Using Huly mock data (HULY_API_URL not configured)"
        fi
        ;;
esac

# Setup CocoIndex database
echo "🔧 Setting up CocoIndex database..."
export COCOINDEX_DATABASE_URL="${COCOINDEX_DATABASE_URL:-postgresql://cocoindex:cocoindex@postgres:5432/cocoindex}"
echo "Using database: $COCOINDEX_DATABASE_URL"

# Run pipelines based on type
case "${PIPELINE_TYPE:-bookstack}" in
    "bookstack")
        FLOW_FILE="flows/bookstack_graphiti_compliant.py"
        echo "📚 Running BookStack Graphiti-compliant pipeline"
        run_pipeline "$FLOW_FILE" "BookStack"
        # Start continuous monitoring for BookStack
        echo "🚀 Starting continuous BookStack pipeline..."
        exec cocoindex update "$FLOW_FILE" -L
        ;;
    "huly")
        FLOW_FILE="flows/huly_graphiti_compliant.py"
        echo "📋 Running Huly Graphiti-compliant pipeline"
        run_pipeline "$FLOW_FILE" "Huly"
        # Start continuous monitoring for Huly
        echo "🚀 Starting continuous Huly pipeline..."
        exec cocoindex update "$FLOW_FILE" -L
        ;;
    "both")
        echo "🔄 Running both BookStack and Huly pipelines"
        # Setup and run BookStack first
        BOOKSTACK_FLOW="flows/bookstack_graphiti_compliant.py"
        run_pipeline "$BOOKSTACK_FLOW" "BookStack"

        # Setup and run Huly
        HULY_FLOW="flows/huly_graphiti_compliant.py"
        run_pipeline "$HULY_FLOW" "Huly"

        # Run both in continuous mode (alternating)
        echo "🚀 Starting continuous monitoring for both pipelines..."
        while true; do
            echo "📚 Running BookStack update..."
            cocoindex update "$BOOKSTACK_FLOW"
            echo "📋 Running Huly update..."
            cocoindex update "$HULY_FLOW"
            echo "⏳ Waiting 60 seconds before next cycle..."
            sleep 60
        done
        ;;
    *)
        echo "❌ Unknown pipeline type: ${PIPELINE_TYPE}"
        echo "   Valid options: bookstack, huly, both"
        exit 1
        ;;
esac