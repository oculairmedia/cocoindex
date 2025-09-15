# 🐳 Docker Deployment Guide

Complete containerized deployment of the BookStack to FalkorDB enhanced pipeline.

## 🚀 Quick Start

### Prerequisites
- Docker 20.10+
- Docker Compose 2.0+
- BookStack instance with API access

### One-Command Deployment
```bash
git clone <repository>
cd cocoindex
chmod +x deploy.sh
./deploy.sh
```

The script will guide you through:
1. Environment configuration
2. Deployment mode selection
3. Automatic service startup
4. Health verification

## 📋 Manual Deployment

### 1. Environment Setup
```bash
# Copy environment template
cp .env.example .env

# Edit with your BookStack credentials
nano .env
```

Required variables:
```bash
BS_URL=https://your-bookstack.example.com
BS_TOKEN_ID=your_token_id_here
BS_TOKEN_SECRET=your_token_secret_here
```

### 2. Choose Deployment Mode

**Option A: Simple Pipeline (Fastest)**
```bash
export PIPELINE_MODE=simple
docker-compose up -d
```

**Option B: Enhanced Pipeline (Ollama + Fallback)**
```bash
export PIPELINE_MODE=enhanced
docker-compose up -d
```

**Option C: Enhanced + Local Ollama (Complete)**
```bash
export PIPELINE_MODE=enhanced
docker-compose --profile ollama up -d

# Setup Ollama model
docker-compose exec ollama ollama pull gemma3:12b
```

## 🏗️ Architecture

The deployment includes:

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   BookStack     │────│     Pipeline    │────│    FalkorDB     │
│   (External)    │    │   (Container)   │    │   (Container)   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │
                       ┌─────────────────┐
                       │   PostgreSQL    │
                       │   (Container)   │
                       └─────────────────┘
                              │
                       ┌─────────────────┐
                       │     Ollama      │
                       │   (Optional)    │
                       └─────────────────┘
```

## 🔧 Configuration

### Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `BS_URL` | BookStack instance URL | - | ✅ |
| `BS_TOKEN_ID` | BookStack API token ID | - | ✅ |
| `BS_TOKEN_SECRET` | BookStack API token secret | - | ✅ |
| `PIPELINE_MODE` | Pipeline type (simple/enhanced) | enhanced | ❌ |
| `FALKOR_HOST` | FalkorDB hostname | falkordb | ❌ |
| `FALKOR_PORT` | FalkorDB port | 6379 | ❌ |
| `FALKOR_GRAPH` | Graph database name | graphiti_migration | ❌ |
| `LOG_LEVEL` | Logging level | INFO | ❌ |
| `OLLAMA_URL` | External Ollama URL | http://ollama:11434 | ❌ |

### Volume Mounts

```yaml
volumes:
  - ./logs:/app/logs                    # Pipeline logs
  - ./bookstack_export_full:/app/bookstack_export_full  # Data cache
```

## 📊 Monitoring

### Health Checks
```bash
# Check all services
docker-compose ps

# View pipeline logs
docker-compose logs -f bookstack-pipeline

# Check FalkorDB
docker-compose logs falkordb
```

### Pipeline Status
```bash
# Real-time pipeline logs
docker-compose exec bookstack-pipeline tail -f logs/pipeline.log

# Check extracted entities
docker-compose exec falkordb redis-cli GRAPH.QUERY graphiti_migration "MATCH (e:Entity) RETURN count(e)"
```

### Resource Usage
```bash
# Container resource usage
docker stats

# Disk usage
docker system df
```

## 🔧 Operations

### Start/Stop Services
```bash
# Start all services
docker-compose up -d

# Stop all services
docker-compose down

# Restart just the pipeline
docker-compose restart bookstack-pipeline

# Stop and remove everything (including data)
docker-compose down -v
```

### Pipeline Operations
```bash
# Force pipeline restart
docker-compose restart bookstack-pipeline

# Run one-time export
docker-compose exec bookstack-pipeline python export_all_to_falkor.py

# Switch pipeline mode
export PIPELINE_MODE=simple
docker-compose up -d bookstack-pipeline
```

### Data Management
```bash
# Backup FalkorDB data
docker-compose exec falkordb redis-cli --rdb /data/backup.rdb

# Clear and restart pipeline
docker-compose exec bookstack-pipeline python -c "
import redis
r = redis.Redis(host='falkordb', port=6379)
r.execute_command('GRAPH.DELETE', 'graphiti_migration')
"
docker-compose restart bookstack-pipeline
```

## 🐞 Troubleshooting

### Common Issues

**Pipeline not starting**
```bash
# Check logs
docker-compose logs bookstack-pipeline

# Verify environment
docker-compose exec bookstack-pipeline env | grep BS_
```

**Can't connect to BookStack**
```bash
# Test connectivity
docker-compose exec bookstack-pipeline curl -I "$BS_URL"

# Test API access
docker-compose exec bookstack-pipeline python -c "
import requests
resp = requests.get('$BS_URL/api/docs')
print(resp.status_code)
"
```

**FalkorDB connection issues**
```bash
# Test FalkorDB
docker-compose exec bookstack-pipeline redis-cli -h falkordb ping

# Check FalkorDB logs
docker-compose logs falkordb
```

**Ollama not working**
```bash
# Check Ollama status
docker-compose exec ollama ollama list

# Test Ollama API
curl http://localhost:11434/api/tags
```

### Performance Optimization

**Increase processing speed**
```yaml
# In docker-compose.yml, add:
bookstack-pipeline:
  deploy:
    resources:
      limits:
        cpus: '2.0'
        memory: 4G
```

**Reduce memory usage**
```bash
# Use simple pipeline mode
export PIPELINE_MODE=simple
```

## 🔄 Updates

### Update Pipeline Code
```bash
# Pull latest changes
git pull

# Rebuild and restart
docker-compose build bookstack-pipeline
docker-compose up -d bookstack-pipeline
```

### Update Container Images
```bash
# Pull latest base images
docker-compose pull

# Restart with new images
docker-compose up -d
```

## 📈 Scaling

### Horizontal Scaling
```yaml
# Run multiple pipeline instances
bookstack-pipeline:
  deploy:
    replicas: 3
  environment:
    INSTANCE_ID: ${HOSTNAME}
```

### External Services
```bash
# Use external FalkorDB
export FALKOR_HOST=external-falkor.example.com
export FALKOR_PORT=6379

# Use external PostgreSQL
export COCOINDEX_DATABASE_URL=postgresql://user:pass@external-db:5432/cocoindex
```

## 🔒 Security

### Production Deployment
```yaml
# docker-compose.prod.yml
services:
  bookstack-pipeline:
    restart: always
    environment:
      - LOG_LEVEL=WARNING
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

### Secrets Management
```bash
# Use Docker secrets
echo "your_token_secret" | docker secret create bs_token_secret -

# Reference in compose
services:
  bookstack-pipeline:
    secrets:
      - bs_token_secret
```

## 🎯 Use Cases

### Development
```bash
# Quick local testing
docker-compose up -d falkordb postgres
export PIPELINE_MODE=simple
python run_cocoindex.py update flows/bookstack_ollama_simple.py
```

### Staging
```bash
# Full environment with monitoring
docker-compose --profile ollama up -d
# Add monitoring stack (Grafana, Prometheus)
```

### Production
```bash
# Optimized for reliability
export PIPELINE_MODE=enhanced
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```