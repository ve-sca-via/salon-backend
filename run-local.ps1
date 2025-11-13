# ============================================
# Run backend with LOCAL Supabase
# ============================================

Write-Host "Starting LOCAL development environment..." -ForegroundColor Green
Write-Host ""

# Check if Docker is running
$dockerRunning = docker ps 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Docker Desktop is not running!" -ForegroundColor Red
    Write-Host "Please start Docker Desktop and try again." -ForegroundColor Yellow
    exit 1
}

# Check if Supabase is running
Write-Host "Checking Supabase local status..." -ForegroundColor Cyan
$supabaseStatus = supabase status 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Supabase is not running. Starting..." -ForegroundColor Yellow
    supabase start
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Failed to start Supabase!" -ForegroundColor Red
        exit 1
    }
}

# Use local environment
Write-Host "Switching to local environment..." -ForegroundColor Cyan
Copy-Item .env.local .env -Force

Write-Host ""
Write-Host "Environment: LOCAL" -ForegroundColor Green
Write-Host "Supabase: http://127.0.0.1:54321" -ForegroundColor Gray
Write-Host "Studio:   http://127.0.0.1:54323" -ForegroundColor Gray
Write-Host ""

# Activate virtual environment and run
Write-Host "Starting FastAPI server..." -ForegroundColor Cyan
Write-Host ""

& .\.venv\Scripts\Activate.ps1
python main.py
