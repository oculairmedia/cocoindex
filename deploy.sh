#!/bin/bash
# BookStack to FalkorDB Pipeline Deployment Script

set -e

echo "🚀 BookStack to FalkorDB Enhanced Pipeline Deployment"
echo "====================================================="

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "📝 Creating .env file from template..."
    cp .env.example .env
    echo "⚠️  Please edit .env file with your BookStack credentials:"
    echo "   - BS_URL: Your BookStack instance URL"
    echo "   - BS_TOKEN_ID: Your BookStack API token ID"
    echo "   - BS_TOKEN_SECRET: Your BookStack API token secret"
    echo ""
    read -p "Press Enter after editing .env file to continue..."
fi

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Validate required environment variables
if [ -z "$BS_URL" ] || [ -z "$BS_TOKEN_ID" ] || [ -z "$BS_TOKEN_SECRET" ]; then
    echo "❌ Missing required BookStack configuration in .env file"
    echo "   Please set BS_URL, BS_TOKEN_ID, and BS_TOKEN_SECRET"
    exit 1
fi

# Create required directories
echo "📁 Creating required directories..."
mkdir -p bookstack_export_full logs

# Deployment mode selection
echo ""
echo "🔧 Select deployment mode:"
echo "1) Simple Pipeline (keyword-based extraction, fastest)"
echo "2) Enhanced Pipeline (Ollama + fallback, more intelligent)"
echo "3) Enhanced Pipeline + Local Ollama (includes Ollama container)"
echo ""
read -p "Enter choice (1-3): " DEPLOY_MODE

case $DEPLOY_MODE in
    1)
        echo "🏃 Deploying Simple Pipeline..."
        PIPELINE_MODE="simple"
        COMPOSE_PROFILES=""
        ;;
    2)
        echo "🧠 Deploying Enhanced Pipeline..."
        PIPELINE_MODE="enhanced"
        COMPOSE_PROFILES=""
        echo "⚠️  Make sure Ollama is running externally or this will use fallback extraction"
        ;;
    3)
        echo "🤖 Deploying Enhanced Pipeline + Local Ollama..."
        PIPELINE_MODE="enhanced"
        COMPOSE_PROFILES="--profile ollama"
        echo "📥 This will download Ollama and Gemma3:12b model (~6GB)"
        ;;
    *)
        echo "❌ Invalid choice. Exiting."
        exit 1
        ;;
esac

# Export mode for docker-compose
export PIPELINE_MODE

# Pull latest images
echo "📦 Pulling Docker images..."
if [ -n "$COMPOSE_PROFILES" ]; then
    docker-compose $COMPOSE_PROFILES pull
else
    docker-compose pull
fi

# Start services
echo "🚀 Starting services..."
if [ -n "$COMPOSE_PROFILES" ]; then
    docker-compose $COMPOSE_PROFILES up -d
else
    docker-compose up -d
fi

# Wait for services to be ready
echo "⏳ Waiting for services to start..."
sleep 30

# Setup Ollama if included
if [ "$DEPLOY_MODE" = "3" ]; then
    echo "🤖 Setting up Ollama with Gemma3:12b..."
    docker-compose exec ollama ollama pull gemma3:12b
fi

# Health check
echo "🏥 Performing health checks..."
for i in {1..10}; do
    if docker-compose ps | grep -q "Up.*healthy"; then
        echo "✅ Services are healthy!"
        break
    fi
    if [ $i -eq 10 ]; then
        echo "❌ Services failed to start properly. Check logs:"
        echo "   docker-compose logs"
        exit 1
    fi
    echo "   Attempt $i/10... waiting 10s"
    sleep 10
done

# Show status
echo ""
echo "🎉 Deployment completed successfully!"
echo ""
echo "📊 Service Status:"
docker-compose ps

echo ""
echo "🔍 Useful Commands:"
echo "   View logs:           docker-compose logs -f"
echo "   Stop services:       docker-compose down"
echo "   Restart pipeline:    docker-compose restart bookstack-pipeline"
echo "   View FalkorDB:       redis-cli -h localhost -p 6379"
echo ""
echo "📈 Monitor Progress:"
echo "   docker-compose logs -f bookstack-pipeline"
echo ""
echo "🌐 Access Points:"
echo "   FalkorDB:    localhost:6379"
echo "   PostgreSQL:  localhost:5433"
if [ "$DEPLOY_MODE" = "3" ]; then
    echo "   Ollama:      localhost:11434"
fi

echo ""
echo "✨ Your BookStack documentation will now be continuously synchronized"
echo "   to FalkorDB as an intelligent knowledge graph!"