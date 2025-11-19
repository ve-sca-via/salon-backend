#!/usr/bin/env pwsh
# =====================================================
# STAGING ENVIRONMENT RUNNER
# =====================================================
# Purpose: Run backend with staging Supabase and real integrations
# Usage: .\run-staging.ps1
# =====================================================

Write-Host "🚀 Starting Salon Management Backend - STAGING MODE" -ForegroundColor Cyan
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host ""

# Check if .env.staging exists
if (-not (Test-Path ".env.staging")) {
    Write-Host "❌ Error: .env.staging not found!" -ForegroundColor Red
    Write-Host ""
    Write-Host "📋 Setup Instructions:" -ForegroundColor Yellow
    Write-Host "1. Copy the example file:" -ForegroundColor White
    Write-Host "   Copy-Item .env.staging.example .env.staging" -ForegroundColor Gray
    Write-Host ""
    Write-Host "2. Edit .env.staging with your STAGING Supabase credentials" -ForegroundColor White
    Write-Host "   - Get credentials from: https://supabase.com/dashboard" -ForegroundColor Gray
    Write-Host "   - Use your STAGING project (not production!)" -ForegroundColor Gray
    Write-Host ""
    Write-Host "3. Configure real SMTP for email testing" -ForegroundColor White
    Write-Host "   - Use Gmail or another email provider" -ForegroundColor Gray
    Write-Host "   - Set EMAIL_ENABLED=True" -ForegroundColor Gray
    Write-Host ""
    exit 1
}

# Copy staging config to active .env
Write-Host "📝 Loading staging configuration..." -ForegroundColor Green
Copy-Item .env.staging .env -Force

Write-Host "✅ Staging config loaded" -ForegroundColor Green
Write-Host ""

# Activate virtual environment if it exists
if (Test-Path ".venv\Scripts\Activate.ps1") {
    Write-Host "🐍 Activating Python virtual environment..." -ForegroundColor Green
    & .\.venv\Scripts\Activate.ps1
}

# Display environment info
Write-Host "🌍 Environment: STAGING" -ForegroundColor Magenta
Write-Host "📧 Emails: ENABLED (real emails will be sent)" -ForegroundColor Yellow
Write-Host "💳 Payments: TEST MODE (Razorpay test keys)" -ForegroundColor Yellow
Write-Host "🗄️  Database: STAGING Supabase (online)" -ForegroundColor Yellow
Write-Host ""
Write-Host "⚠️  WARNING: This uses REAL online services!" -ForegroundColor Yellow
Write-Host "   - Real emails will be sent" -ForegroundColor Gray
Write-Host "   - Data stored in staging Supabase" -ForegroundColor Gray
Write-Host "   - Use test payment cards only" -ForegroundColor Gray
Write-Host ""
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host ""

# Start the application
Write-Host "🚀 Starting FastAPI server..." -ForegroundColor Green
Write-Host ""

python main.py
