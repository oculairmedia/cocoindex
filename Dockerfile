# BookStack to FalkorDB Enhanced Pipeline Container
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install additional dependencies for the pipeline
RUN pip install --no-cache-dir \
    redis \
    beautifulsoup4 \
    requests \
    python-dotenv

# Copy application code
COPY . .

# Create data directories
RUN mkdir -p bookstack_export_full logs

# Set environment variables with defaults
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Default environment variables (override with docker run -e)
ENV FALKOR_HOST=falkordb
ENV FALKOR_PORT=6379
ENV FALKOR_GRAPH=graphiti_migration
ENV BS_URL=""
ENV BS_TOKEN_ID=""
ENV BS_TOKEN_SECRET=""

# Copy and setup scripts
COPY docker-healthcheck.sh start-pipeline.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-healthcheck.sh /usr/local/bin/start-pipeline.sh
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD /usr/local/bin/docker-healthcheck.sh

# Expose ports (if needed for monitoring)
EXPOSE 8000

# Default command - run the pipeline startup script
CMD ["/usr/local/bin/start-pipeline.sh"]