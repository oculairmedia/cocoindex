# PowerShell script to start CocoIndex with PostgreSQL
# Usage: .\start-cocoindex.ps1

Write-Host "Starting CocoIndex with PostgreSQL..." -ForegroundColor Green

# Check if Docker is running
try {
    docker version | Out-Null
    Write-Host "Docker is running" -ForegroundColor Green
} catch {
    Write-Host "Docker is not running. Please start Docker Desktop first." -ForegroundColor Red
    exit 1
}

# Start PostgreSQL for CocoIndex
Write-Host "Starting PostgreSQL database..." -ForegroundColor Yellow
docker-compose -f docker-compose.cocoindex.yml up -d

# Wait for PostgreSQL to be ready
Write-Host "Waiting for PostgreSQL to be ready..." -ForegroundColor Yellow
$maxAttempts = 30
$attempt = 0

do {
    $attempt++
    Start-Sleep -Seconds 2
    
    try {
        $result = docker-compose -f docker-compose.cocoindex.yml exec -T cocoindex-postgres pg_isready -U cocoindex -d cocoindex
        if ($LASTEXITCODE -eq 0) {
            Write-Host "PostgreSQL is ready!" -ForegroundColor Green
            break
        }
    } catch {
        # Continue waiting
    }

    if ($attempt -ge $maxAttempts) {
        Write-Host "PostgreSQL failed to start within 60 seconds" -ForegroundColor Red
        Write-Host "Check logs with: docker-compose -f docker-compose.cocoindex.yml logs" -ForegroundColor Yellow
        exit 1
    }

    Write-Host "Attempt $attempt/$maxAttempts - PostgreSQL not ready yet..." -ForegroundColor Yellow
} while ($true)

# Test database connection
Write-Host "Testing database connection..." -ForegroundColor Yellow
try {
    $testResult = docker-compose -f docker-compose.cocoindex.yml exec -T cocoindex-postgres psql -U cocoindex -d cocoindex -c "SELECT 'Connection successful!' as status;"
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Database connection successful!" -ForegroundColor Green
    } else {
        Write-Host "Database connection failed" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "Database connection test failed" -ForegroundColor Red
    exit 1
}

# Show connection info
Write-Host ""
Write-Host "CocoIndex PostgreSQL Database Info:" -ForegroundColor Cyan
Write-Host "  Host: localhost" -ForegroundColor White
Write-Host "  Port: 5433" -ForegroundColor White
Write-Host "  Database: cocoindex" -ForegroundColor White
Write-Host "  Username: cocoindex" -ForegroundColor White
Write-Host "  Password: cocoindex" -ForegroundColor White
Write-Host "  URL: postgresql://cocoindex:cocoindex@localhost:5433/cocoindex" -ForegroundColor White

Write-Host ""
Write-Host "Ready to run CocoIndex!" -ForegroundColor Green
Write-Host "Run: python run_cocoindex.py update --setup flows/bookstack_to_falkor.py" -ForegroundColor Yellow

Write-Host ""
Write-Host "Useful commands:" -ForegroundColor Cyan
Write-Host "  Stop database: docker-compose -f docker-compose.cocoindex.yml down" -ForegroundColor White
Write-Host "  View logs: docker-compose -f docker-compose.cocoindex.yml logs -f" -ForegroundColor White
Write-Host "  Access pgAdmin: http://localhost:8080 (admin@cocoindex.local / admin)" -ForegroundColor White
