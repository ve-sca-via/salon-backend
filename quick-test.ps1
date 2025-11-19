# ================================
#   Quick Test Setup
# ================================

Write-Host ""
Write-Host "================================" -ForegroundColor Blue
Write-Host "  Quick Test Setup" -ForegroundColor Blue
Write-Host "================================" -ForegroundColor Blue
Write-Host ""

$ErrorActionPreference = "Stop"

# ---- Create Virtual Environment if Missing ----
if (-not (Test-Path ".\venv")) {
    Write-Host "Creating virtual environment..." -ForegroundColor Yellow
    python -m venv venv
}

# ---- Activate Virtual Environment ----
Write-Host "Activating virtual environment..." -ForegroundColor Cyan
$venvActivate = Join-Path $PWD "venv\Scripts\Activate.ps1"

if (Test-Path $venvActivate) {
    & $venvActivate
} else {
    Write-Host "ERROR: Could not activate virtual environment." -ForegroundColor Red
    exit
}

# ---- Install Dependencies ----
Write-Host "Installing dependencies..." -ForegroundColor Cyan
pip install -r requirements.txt -q
pip install httpx -q

Write-Host ""
Write-Host "Setup complete!" -ForegroundColor Green
Write-Host ""

# ---- Menu ----
Write-Host "What would you like to do?" -ForegroundColor Yellow
Write-Host ""
Write-Host "  1. Start backend server only"
Write-Host "  2. Seed database (requires server running)"
Write-Host "  3. Start server AND seed database"
Write-Host "  4. Run tests"
Write-Host "  5. Exit"
Write-Host ""

$choice = Read-Host "Enter your choice (1-5)"

switch ($choice) {

    "1" {
        Write-Host ""
        Write-Host "Starting backend server..." -ForegroundColor Green
        Write-Host "Visit http://localhost:8000/docs" -ForegroundColor Cyan
        python main.py
    }

    "2" {
        Write-Host ""
        Write-Host "Make sure your backend server is running!" -ForegroundColor Yellow
        Start-Sleep -Seconds 2

        Write-Host "Seeding database..." -ForegroundColor Green
        python seed_database.py

        Write-Host "Database seeded successfully." -ForegroundColor Green
    }

    "3" {
        Write-Host ""
        Write-Host "Starting backend server in background..." -ForegroundColor Green

        $job = Start-Job -ScriptBlock {
            Set-Location $using:PWD
            & "$using:PWD\venv\Scripts\Activate.ps1"
            python main.py
        }

        Write-Host "Waiting for server to start..." -ForegroundColor Yellow
        Start-Sleep -Seconds 5

        Write-Host "Seeding database..." -ForegroundColor Green
        python seed_database.py

        Write-Host ""
        Write-Host "Done! Server is running in the background." -ForegroundColor Green
        Write-Host "Server job ID: $($job.Id)" -ForegroundColor Cyan
        Write-Host "To stop server: Stop-Job -Id $($job.Id)" -ForegroundColor Cyan
        Write-Host ""

        Write-Host "Press any key to stop server and exit..." -ForegroundColor Yellow
        $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")

        Stop-Job $job.Id
        Remove-Job $job.Id
    }

    "4" {
        Write-Host ""
        Write-Host "Running tests..." -ForegroundColor Green

        if (Test-Path "requirements-test.txt") {
            pip install -r requirements-test.txt -q
        }

        pytest tests/ -v
    }

    "5" {
        Write-Host ""
        Write-Host "Goodbye!" -ForegroundColor Green
        exit
    }

    default {
        Write-Host ""
        Write-Host "Invalid choice. Please run the script again." -ForegroundColor Red
    }
}
