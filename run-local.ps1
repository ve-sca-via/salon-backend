# ============================================
# Run backend with LOCAL Supabase
# ============================================

Write-Host "Starting LOCAL development environment..." -ForegroundColor Green
Write-Host ""


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
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
