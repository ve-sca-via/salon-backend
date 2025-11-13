# ============================================
# Run backend with PRODUCTION Supabase
# ============================================

Write-Host "Starting PRODUCTION environment..." -ForegroundColor Yellow
Write-Host ""
Write-Host "WARNING: You are connecting to REAL PRODUCTION DATA!" -ForegroundColor Red
Write-Host ""

# Ask for confirmation
$confirmation = Read-Host "Are you sure you want to connect to production? (yes/no)"
if ($confirmation -ne "yes") {
    Write-Host "Cancelled." -ForegroundColor Yellow
    exit 0
}

# Check if .env.production exists
if (-Not (Test-Path ".env.production")) {
    Write-Host ".env.production file not found!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please create .env.production with your production credentials:" -ForegroundColor Yellow
    Write-Host "  SUPABASE_URL=https://your-project.supabase.co" -ForegroundColor Gray
    Write-Host "  SUPABASE_ANON_KEY=your_production_anon_key" -ForegroundColor Gray
    Write-Host "  SUPABASE_SERVICE_ROLE_KEY=your_production_service_role_key" -ForegroundColor Gray
    Write-Host ""
    exit 1
}

# Use production environment
Write-Host "Switching to production environment..." -ForegroundColor Cyan
Copy-Item .env.production .env -Force

Write-Host ""
Write-Host "Environment: PRODUCTION" -ForegroundColor Red
Write-Host "Supabase: CLOUD (Real Data)" -ForegroundColor Gray
Write-Host ""

# Activate virtual environment and run
Write-Host "Starting FastAPI server..." -ForegroundColor Cyan
Write-Host ""

& .\.venv\Scripts\Activate.ps1
python main.py
