@echo off
REM Add Python Scripts to PATH for cocoindex
set PATH=%PATH%;C:\Users\Emmanuel\AppData\Roaming\Python\Python312\Scripts

REM Set dry run mode for testing
set DRY_RUN=true

REM Set BookStack credentials (already provided)
set BS_URL=https://knowledge.oculair.ca
set BS_TOKEN_ID=POnHR9Lbvm73T2IOcyRSeAqpA8bSGdMT
set BS_TOKEN_SECRET=735wM5dScfUkcOy7qcrgqQ1eC5fBF7IE

REM Set FalkorDB defaults (for dry run)
set FALKOR_HOST=192.168.50.90
set FALKOR_PORT=6379
set FALKOR_GRAPH=graphiti_migration

REM Set Embedding defaults (for dry run)
set EMB_URL=http://192.168.50.80:11434/v1/embeddings
set EMB_KEY=ollama
set EMB_MODEL=dengcao/Qwen3-Embedding-4B:Q4_K_M

echo Environment configured!
echo.
echo To test the pipeline:
echo   cocoindex update --setup flows/bookstack_to_falkor.py
echo.
echo To run without dry-run, edit this file and set DRY_RUN=false