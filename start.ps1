# Starts the full RAG chatbot stack: Postgres, Ollama, backend, frontend.
# Usage: .\start.ps1

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

function Wait-Http($url, $name, $seconds = 60) {
    $deadline = (Get-Date).AddSeconds($seconds)
    do {
        Start-Sleep -Seconds 2
        try {
            Invoke-WebRequest $url -TimeoutSec 3 -UseBasicParsing | Out-Null
            Write-Host "[ok] $name" -ForegroundColor Green
            return $true
        } catch {}
    } until ((Get-Date) -gt $deadline)
    Write-Host "[!!] $name did not respond at $url" -ForegroundColor Red
    return $false
}

# 1. Postgres + pgvector
Write-Host "Starting Postgres..." -ForegroundColor Cyan
docker compose up -d db

# 2. Ollama
try {
    Invoke-WebRequest http://localhost:11434/api/version -TimeoutSec 3 -UseBasicParsing | Out-Null
    Write-Host "[ok] Ollama already running" -ForegroundColor Green
} catch {
    Write-Host "Starting Ollama..." -ForegroundColor Cyan
    $ollama = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
    if (-not (Test-Path $ollama)) { $ollama = "C:\Program Files\Ollama\ollama.exe" }
    Start-Process $ollama -ArgumentList "serve" -WindowStyle Hidden
    Wait-Http "http://localhost:11434/api/version" "Ollama" | Out-Null
}

# 3. Backend
Write-Host "Starting backend..." -ForegroundColor Cyan
Start-Process -FilePath "$root\.venv\Scripts\uvicorn.exe" `
    -ArgumentList "backend.main:app", "--port", "8000" `
    -WorkingDirectory $root -WindowStyle Hidden `
    -RedirectStandardOutput "$root\backend.log" `
    -RedirectStandardError "$root\backend.err.log"
Wait-Http "http://localhost:8000/documents" "Backend (http://localhost:8000)" | Out-Null

# 4. Frontend
Write-Host "Starting frontend..." -ForegroundColor Cyan
Start-Process -FilePath "cmd.exe" `
    -ArgumentList "/c", "npm run dev" `
    -WorkingDirectory "$root\frontend" -WindowStyle Hidden
Wait-Http "http://localhost:5173" "Frontend (http://localhost:5173)" | Out-Null

Write-Host ""
Write-Host "All set: http://localhost:5173" -ForegroundColor Green
Start-Process "http://localhost:5173"
