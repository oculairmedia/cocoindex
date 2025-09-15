#!/bin/bash
# Health check script for the BookStack pipeline container

# Check if Python process is running
if ! pgrep -f "python.*bookstack" > /dev/null; then
    echo "Pipeline process not running"
    exit 1
fi

# Check FalkorDB connection if configured
if [ -n "$FALKOR_HOST" ]; then
    if ! timeout 5 bash -c "</dev/tcp/$FALKOR_HOST/$FALKOR_PORT" 2>/dev/null; then
        echo "Cannot connect to FalkorDB at $FALKOR_HOST:$FALKOR_PORT"
        exit 1
    fi
fi

# Check if recent activity exists (optional)
if [ -d "logs" ]; then
    # Look for recent log activity (within last hour)
    if find logs -name "*.log" -mmin -60 | grep -q .; then
        echo "Recent pipeline activity detected"
    fi
fi

echo "Health check passed"
exit 0