# Navigate to backend directory
Set-Location "G:\vescavia\Projects\backend"

# Activate virtual environment
if (Test-Path ".venv\Scripts\Activate.ps1") {
    Write-Host "✅ Activating virtual environment..."
    .\.venv\Scripts\Activate.ps1
} else {
    Write-Host "❌ Virtual environment not found in $PWD"
    exit
}

# Run the FastAPI app
Write-Host "🚀 Starting FastAPI server..."
uvicorn main:app --reload --host 0.0.0.0 --port 8000
