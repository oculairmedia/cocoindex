# Add Python Scripts to PATH for cocoindex
$env:PATH += ";C:\Users\Emmanuel\AppData\Roaming\Python\Python312\Scripts"

# Set dry run mode for testing
$env:DRY_RUN = "true"

# Set BookStack credentials
$env:BS_URL = "https://knowledge.oculair.ca"
$env:BS_TOKEN_ID = "POnHR9Lbvm73T2IOcyRSeAqpA8bSGdMT"
$env:BS_TOKEN_SECRET = "735wM5dScfUkcOy7qcrgqQ1eC5fBF7IE"

# Set FalkorDB defaults (for dry run)
$env:FALKOR_HOST = "192.168.50.90"
$env:FALKOR_PORT = "6379"
$env:FALKOR_GRAPH = "graphiti_migration"

# Set Embedding defaults (for dry run)
$env:EMB_URL = "http://192.168.50.80:11434/v1/embeddings"
$env:EMB_KEY = "ollama"
$env:EMB_MODEL = "dengcao/Qwen3-Embedding-4B:Q4_K_M"

Write-Host "Environment configured!" -ForegroundColor Green
Write-Host ""
Write-Host "To test the pipeline:" -ForegroundColor Yellow
Write-Host "  cocoindex update --setup flows/bookstack_to_falkor.py"
Write-Host ""
Write-Host "To run without dry-run, edit this file and set DRY_RUN=false" -ForegroundColor Cyan

# Test if cocoindex is accessible
Write-Host ""
Write-Host "Testing cocoindex availability..." -ForegroundColor Yellow
try {
    cocoindex --version
    Write-Host "CocoIndex is available!" -ForegroundColor Green
} catch {
    Write-Host "CocoIndex not found in PATH" -ForegroundColor Red
}