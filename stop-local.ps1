# ============================================
# Stop LOCAL development environment
# Lets you pick which apps to stop.
# ============================================

# --- Project locations -----------------------------------------------------
$BackendDir   = "g:\vescavia\Projects\backend"
$AdminDir     = "g:\vescavia\Projects\salon-admin-panel"
$AppDir       = "g:\vescavia\Projects\salon-management-app"

Write-Host ""
Write-Host "Which apps do you want to stop?" -ForegroundColor Green
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
$stopBackend = $false
$stopAdmin   = $false
$stopApp     = $false

foreach ($t in $tokens) {
    switch ($t) {
        '1'        { $stopBackend = $true }
        'backend'  { $stopBackend = $true }
        '2'        { $stopAdmin = $true }
        'admin'    { $stopAdmin = $true }
        '3'        { $stopApp = $true }
        'app'      { $stopApp = $true }
        '4'        { $stopBackend = $true; $stopAdmin = $true; $stopApp = $true }
        'all'      { $stopBackend = $true; $stopAdmin = $true; $stopApp = $true }
        default    { Write-Host "Ignoring unknown option: $t" -ForegroundColor Yellow }
    }
}

if (-not ($stopBackend -or $stopAdmin -or $stopApp)) {
    Write-Host ""
    Write-Host "Nothing selected. Exiting." -ForegroundColor Yellow
    return
}

# --- Stop helpers ----------------------------------------------------------
# Each app is started in its own PowerShell window with a distinct title, so
# we stop the matching console process and its child process tree.

function Stop-InWindow {
    param(
        [string]$Title,
        [string]$WorkingDir
    )

    # MainWindowTitle is unreliable (empty in Windows Terminal / background), 
    # so we search the original command-line arguments used to launch it.
    $processes = Get-CimInstance Win32_Process -Filter "Name = 'powershell.exe' OR Name = 'pwsh.exe'" | Where-Object {
        $_.CommandLine -like "*WindowTitle = '$Title'*"
    }

    if (-not $processes) {
        Write-Host "  -> No running window found for $Title" -ForegroundColor Yellow
        return
    }

    foreach ($process in $processes) {
        try {
            & taskkill /PID $process.ProcessId /T /F | Out-Null
            Write-Host "  -> Stopped $Title (PID $($process.ProcessId))" -ForegroundColor Green
        }
        catch {
            Write-Host "  -> Failed to stop $Title (PID $($process.ProcessId)): $($_.Exception.Message)" -ForegroundColor Red
        }
    }
}

Write-Host ""

if ($stopBackend) {
    Write-Host "Stopping Backend..." -ForegroundColor Cyan
    Stop-InWindow -Title 'Backend (FastAPI)' -WorkingDir $BackendDir
}

if ($stopAdmin) {
    Write-Host "Stopping Salon Admin Panel..." -ForegroundColor Cyan
    Stop-InWindow -Title 'Salon Admin Panel' -WorkingDir $AdminDir
}

if ($stopApp) {
    Write-Host "Stopping Salon Management App..." -ForegroundColor Cyan
    Stop-InWindow -Title 'Salon Management App' -WorkingDir $AppDir
}

Write-Host ""
Write-Host "Done. Selected apps are stopping." -ForegroundColor Green
Write-Host ""