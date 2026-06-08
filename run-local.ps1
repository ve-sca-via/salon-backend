# ============================================
# Run LOCAL development environment
# Lets you pick which apps to start.
# ============================================

# --- Project locations -----------------------------------------------------
$BackendDir   = "g:\vescavia\Projects\backend"
$AdminDir     = "g:\vescavia\Projects\salon-admin-panel"
$AppDir       = "g:\vescavia\Projects\salon-management-app"

Write-Host ""
Write-Host "Which apps do you want to start?" -ForegroundColor Green
Write-Host ""
Write-Host "  1) Backend            (FastAPI @ http://localhost:8000)" -ForegroundColor Cyan
Write-Host "  2) Salon Admin Panel  (Vite dev server)"                 -ForegroundColor Cyan
Write-Host "  3) Salon Management App (Vite dev server)"               -ForegroundColor Cyan
Write-Host "  4) All of the above"                                     -ForegroundColor Cyan
Write-Host ""
Write-Host "Enter your choice(s), e.g. '1', '1,3', or 'all'." -ForegroundColor Gray

$choice = Read-Host "Selection"
$choice = $choice.ToLower().Trim()

# Normalize selection into a set of tokens
$tokens = $choice -split '[,\s]+' | Where-Object { $_ -ne '' }
$startBackend = $false
$startAdmin   = $false
$startApp     = $false

foreach ($t in $tokens) {
    switch ($t) {
        '1'        { $startBackend = $true }
        'backend'  { $startBackend = $true }
        '2'        { $startAdmin = $true }
        'admin'    { $startAdmin = $true }
        '3'        { $startApp = $true }
        'app'      { $startApp = $true }
        '4'        { $startBackend = $true; $startAdmin = $true; $startApp = $true }
        'all'      { $startBackend = $true; $startAdmin = $true; $startApp = $true }
        default    { Write-Host "Ignoring unknown option: $t" -ForegroundColor Yellow }
    }
}

if (-not ($startBackend -or $startAdmin -or $startApp)) {
    Write-Host ""
    Write-Host "Nothing selected. Exiting." -ForegroundColor Yellow
    return
}

# --- Launch helpers --------------------------------------------------------
# Each app runs in its own PowerShell window so they run concurrently and
# their logs stay separate.

function Start-InWindow {
    param(
        [string]$Title,
        [string]$WorkingDir,
        [string]$Command
    )
    $full = "Set-Location -LiteralPath '$WorkingDir'; `$Host.UI.RawUI.WindowTitle = '$Title'; $Command"
    Start-Process powershell -ArgumentList @('-NoExit', '-Command', $full)
    Write-Host "  -> Launched $Title" -ForegroundColor Green
}

Write-Host ""

if ($startBackend) {
    Write-Host "Preparing Backend..." -ForegroundColor Cyan
    # Switch to local environment before starting
    Copy-Item (Join-Path $BackendDir '.env.local') (Join-Path $BackendDir '.env') -Force
    Write-Host "  Environment: LOCAL (Supabase http://127.0.0.1:54321, Studio http://127.0.0.1:54323)" -ForegroundColor Gray
    $backendCmd = '& .\.venv\Scripts\Activate.ps1; uvicorn main:app --host 0.0.0.0 --port 8000 --reload'
    Start-InWindow -Title 'Backend (FastAPI)' -WorkingDir $BackendDir -Command $backendCmd
}

if ($startAdmin) {
    Write-Host "Preparing Salon Admin Panel..." -ForegroundColor Cyan
    if (-not (Test-Path (Join-Path $AdminDir 'node_modules'))) {
        Write-Host "  node_modules missing - will run 'npm install' first." -ForegroundColor Yellow
        $adminCmd = 'npm install; npm run dev'
    } else {
        $adminCmd = 'npm run dev'
    }
    Start-InWindow -Title 'Salon Admin Panel' -WorkingDir $AdminDir -Command $adminCmd
}

if ($startApp) {
    Write-Host "Preparing Salon Management App..." -ForegroundColor Cyan
    if (-not (Test-Path (Join-Path $AppDir 'node_modules'))) {
        Write-Host "  node_modules missing - will run 'npm install' first." -ForegroundColor Yellow
        $appCmd = 'npm install; npm run dev'
    } else {
        $appCmd = 'npm run dev'
    }
    Start-InWindow -Title 'Salon Management App' -WorkingDir $AppDir -Command $appCmd
}

Write-Host ""
Write-Host "Done. Selected apps are starting in separate windows." -ForegroundColor Green
Write-Host ""
