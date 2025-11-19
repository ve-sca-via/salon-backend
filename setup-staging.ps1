#!/usr/bin/env pwsh
# =====================================================
# STAGING SETUP WIZARD
# =====================================================
# This script helps you set up staging environment
# Usage: .\setup-staging.ps1
# =====================================================

Write-Host ""
Write-Host "🎯 STAGING ENVIRONMENT SETUP WIZARD" -ForegroundColor Cyan
Write-Host "====================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Check if .env.staging exists
if (Test-Path ".env.staging") {
    Write-Host "✅ .env.staging already exists" -ForegroundColor Green
    $overwrite = Read-Host "Do you want to recreate it? (y/N)"
    if ($overwrite -ne "y" -and $overwrite -ne "Y") {
        Write-Host "Keeping existing .env.staging" -ForegroundColor Yellow
        Write-Host ""
        exit 0
    }
}

# Step 2: Copy example file
Write-Host ""
Write-Host "📋 Step 1: Creating .env.staging from template..." -ForegroundColor Cyan
Copy-Item .env.staging.example .env.staging -Force
Write-Host "✅ Created .env.staging" -ForegroundColor Green

# Step 3: Collect Supabase credentials
Write-Host ""
Write-Host "🗄️  Step 2: Supabase Staging Project" -ForegroundColor Cyan
Write-Host "Please provide your Supabase STAGING credentials" -ForegroundColor Yellow
Write-Host "(Get these from: https://supabase.com/dashboard/project/YOUR_PROJECT/settings/api)" -ForegroundColor Gray
Write-Host ""

$supabaseUrl = Read-Host "Supabase URL (e.g., https://xxxxx.supabase.co)"
$supabaseAnonKey = Read-Host "Supabase Anon Key"
$supabaseServiceKey = Read-Host "Supabase Service Role Key"
$dbPassword = Read-Host "Database Password" -AsSecureString
$dbPasswordPlain = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($dbPassword)
)

# Extract project ref from URL
$projectRef = $supabaseUrl -replace "https://", "" -replace ".supabase.co", ""
$databaseUrl = "postgresql://postgres:$dbPasswordPlain@db.$projectRef.supabase.co:5432/postgres"

# Step 4: Generate JWT secret
Write-Host ""
Write-Host "🔐 Step 3: Generating JWT Secret..." -ForegroundColor Cyan
$jwtSecret = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 40 | ForEach-Object {[char]$_})
Write-Host "✅ Generated secure JWT secret" -ForegroundColor Green

# Step 5: Email configuration
Write-Host ""
Write-Host "📧 Step 4: Email Configuration" -ForegroundColor Cyan
Write-Host "Choose email provider:" -ForegroundColor Yellow
Write-Host "1) Gmail (recommended for testing)"
Write-Host "2) SendGrid"
Write-Host "3) Skip (configure later)"
$emailChoice = Read-Host "Enter choice (1-3)"

$smtpHost = "smtp.gmail.com"
$smtpPort = "587"
$smtpUser = ""
$smtpPassword = ""
$emailEnabled = "True"

if ($emailChoice -eq "1") {
    Write-Host ""
    Write-Host "Gmail Setup:" -ForegroundColor Yellow
    Write-Host "1. Enable 2FA on your Gmail account" -ForegroundColor Gray
    Write-Host "2. Generate App Password: https://myaccount.google.com/apppasswords" -ForegroundColor Gray
    Write-Host ""
    $smtpUser = Read-Host "Gmail address"
    $smtpPassword = Read-Host "Gmail App Password (16 characters)"
    $smtpHost = "smtp.gmail.com"
    $smtpPort = "587"
} elseif ($emailChoice -eq "2") {
    $smtpUser = "apikey"
    $smtpPassword = Read-Host "SendGrid API Key"
    $smtpHost = "smtp.sendgrid.net"
    $smtpPort = "587"
} else {
    $emailEnabled = "False"
    Write-Host "⚠️  Email disabled - you can configure it later in .env.staging" -ForegroundColor Yellow
}

# Step 6: Razorpay
Write-Host ""
Write-Host "💳 Step 5: Razorpay Configuration (TEST mode)" -ForegroundColor Cyan
Write-Host "Get TEST keys from: https://dashboard.razorpay.com/app/keys" -ForegroundColor Gray
Write-Host "(Make sure you're in TEST mode!)" -ForegroundColor Yellow
Write-Host ""
$configureRazorpay = Read-Host "Configure Razorpay now? (y/N)"

$razorpayKeyId = "rzp_test_your_key_id"
$razorpayKeySecret = "your_test_secret_key"

if ($configureRazorpay -eq "y" -or $configureRazorpay -eq "Y") {
    $razorpayKeyId = Read-Host "Razorpay Key ID (starts with rzp_test_)"
    $razorpayKeySecret = Read-Host "Razorpay Key Secret"
}

# Step 7: Update .env.staging
Write-Host ""
Write-Host "💾 Step 6: Writing configuration..." -ForegroundColor Cyan

$envContent = Get-Content .env.staging
$envContent = $envContent -replace 'SUPABASE_URL=".*"', "SUPABASE_URL=`"$supabaseUrl`""
$envContent = $envContent -replace 'SUPABASE_ANON_KEY=".*"', "SUPABASE_ANON_KEY=`"$supabaseAnonKey`""
$envContent = $envContent -replace 'SUPABASE_SERVICE_ROLE_KEY=".*"', "SUPABASE_SERVICE_ROLE_KEY=`"$supabaseServiceKey`""
$envContent = $envContent -replace 'DATABASE_URL=".*"', "DATABASE_URL=`"$databaseUrl`""
$envContent = $envContent -replace 'JWT_SECRET_KEY=".*"', "JWT_SECRET_KEY=`"$jwtSecret`""
$envContent = $envContent -replace 'EMAIL_ENABLED=.*', "EMAIL_ENABLED=$emailEnabled"
$envContent = $envContent -replace 'SMTP_HOST=".*"', "SMTP_HOST=`"$smtpHost`""
$envContent = $envContent -replace 'SMTP_PORT=.*', "SMTP_PORT=$smtpPort"
$envContent = $envContent -replace 'SMTP_USER=".*"', "SMTP_USER=`"$smtpUser`""
$envContent = $envContent -replace 'SMTP_PASSWORD=".*"', "SMTP_PASSWORD=`"$smtpPassword`""
$envContent = $envContent -replace 'RAZORPAY_KEY_ID=".*"', "RAZORPAY_KEY_ID=`"$razorpayKeyId`""
$envContent = $envContent -replace 'RAZORPAY_KEY_SECRET=".*"', "RAZORPAY_KEY_SECRET=`"$razorpayKeySecret`""

$envContent | Set-Content .env.staging

Write-Host "✅ Configuration saved to .env.staging" -ForegroundColor Green

# Step 8: Apply migrations to Supabase
Write-Host ""
Write-Host "✅ Configuration saved to .env.staging" -ForegroundColor Green
Write-Host ""
Write-Host "🗄️  Step 7: Apply Database Migrations" -ForegroundColor Cyan
Write-Host "Now we need to apply migrations to your staging Supabase project" -ForegroundColor Yellow
Write-Host ""

$applyMigrations = Read-Host "Do you want to apply migrations now? (Y/n)"

if ($applyMigrations -eq "" -or $applyMigrations -eq "y" -or $applyMigrations -eq "Y") {
    Write-Host ""
    Write-Host "📡 Linking to Supabase project..." -ForegroundColor Green
    
    # Check if supabase CLI is installed
    try {
        $supabaseVersion = supabase --version 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✅ Supabase CLI found" -ForegroundColor Green
        }
    } catch {
        Write-Host "❌ Supabase CLI not found!" -ForegroundColor Red
        Write-Host ""
        Write-Host "Please install Supabase CLI first:" -ForegroundColor Yellow
        Write-Host "  scoop bucket add supabase https://github.com/supabase/scoop-bucket.git" -ForegroundColor Gray
        Write-Host "  scoop install supabase" -ForegroundColor Gray
        Write-Host ""
        Write-Host "After installation, run this command manually:" -ForegroundColor Yellow
        Write-Host "  supabase link --project-ref $projectRef" -ForegroundColor Gray
        Write-Host "  supabase db push" -ForegroundColor Gray
        Write-Host ""
        $applyMigrations = "skip"
    }
    
    if ($applyMigrations -ne "skip") {
        # Link to project
        Write-Host "Linking to project: $projectRef" -ForegroundColor Gray
        supabase link --project-ref $projectRef
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✅ Successfully linked to Supabase project" -ForegroundColor Green
            Write-Host ""
            Write-Host "📤 Pushing migrations to staging database..." -ForegroundColor Green
            
            # Push migrations
            supabase db push
            
            if ($LASTEXITCODE -eq 0) {
                Write-Host "✅ Migrations applied successfully!" -ForegroundColor Green
            } else {
                Write-Host "⚠️  Migration failed. Please check errors above." -ForegroundColor Yellow
                Write-Host "You can retry manually with: supabase db push" -ForegroundColor Gray
            }
        } else {
            Write-Host "⚠️  Link failed. You may need to login first:" -ForegroundColor Yellow
            Write-Host "  supabase login" -ForegroundColor Gray
            Write-Host "  supabase link --project-ref $projectRef" -ForegroundColor Gray
        }
    }
} else {
    Write-Host "⚠️  Skipping migrations. Remember to run these commands later:" -ForegroundColor Yellow
    Write-Host "  supabase link --project-ref $projectRef" -ForegroundColor Gray
    Write-Host "  supabase db push" -ForegroundColor Gray
}

# Step 9: Frontend URLs configuration
Write-Host ""
Write-Host "🌐 Step 8: Frontend URLs Configuration" -ForegroundColor Cyan
Write-Host "If you've already deployed your frontend, let's update the URLs" -ForegroundColor Yellow
Write-Host ""

$configureFrontend = Read-Host "Have you deployed frontend to Vercel/Netlify? (y/N)"

if ($configureFrontend -eq "y" -or $configureFrontend -eq "Y") {
    Write-Host ""
    Write-Host "Please provide your deployed frontend URLs:" -ForegroundColor Yellow
    Write-Host "(Press Enter to skip and use localhost defaults)" -ForegroundColor Gray
    Write-Host ""
    
    $frontendUrl = Read-Host "Salon App URL (e.g., https://staging-salon-app.vercel.app)"
    $adminPanelUrl = Read-Host "Admin Panel URL (e.g., https://staging-admin-panel.vercel.app)"
    
    if ($frontendUrl -ne "") {
        # Update frontend URLs in .env.staging
        $envContent = Get-Content .env.staging
        
        if ($frontendUrl -ne "") {
            $envContent = $envContent -replace 'FRONTEND_URL=".*"', "FRONTEND_URL=`"$frontendUrl`""
            $envContent = $envContent -replace 'VENDOR_PORTAL_URL=".*"', "VENDOR_PORTAL_URL=`"$frontendUrl/vendor`""
            $envContent = $envContent -replace 'RM_PORTAL_URL=".*"', "RM_PORTAL_URL=`"$frontendUrl/rm`""
        }
        
        if ($adminPanelUrl -ne "") {
            $envContent = $envContent -replace 'ADMIN_PANEL_URL=".*"', "ADMIN_PANEL_URL=`"$adminPanelUrl`""
        }
        
        # Update CORS origins
        $allowedOrigins = "http://localhost:5173,http://localhost:5174"
        if ($frontendUrl -ne "") {
            $allowedOrigins += ",$frontendUrl"
        }
        if ($adminPanelUrl -ne "") {
            $allowedOrigins += ",$adminPanelUrl"
        }
        
        $envContent = $envContent -replace 'ALLOWED_ORIGINS=".*"', "ALLOWED_ORIGINS=`"$allowedOrigins`""
        
        $envContent | Set-Content .env.staging
        
        Write-Host "✅ Frontend URLs updated in .env.staging" -ForegroundColor Green
    }
} else {
    Write-Host "ℹ️  Using localhost URLs for now" -ForegroundColor Cyan
    Write-Host "You can update these later in .env.staging after deploying frontend" -ForegroundColor Gray
}

# Step 10: Test staging environment
Write-Host ""
Write-Host "🧪 Step 9: Test Staging Environment" -ForegroundColor Cyan
Write-Host "Let's test if everything is working!" -ForegroundColor Yellow
Write-Host ""

$testNow = Read-Host "Do you want to test the backend now? (Y/n)"

if ($testNow -eq "" -or $testNow -eq "y" -or $testNow -eq "Y") {
    Write-Host ""
    Write-Host "🚀 Starting backend with staging configuration..." -ForegroundColor Green
    Write-Host "Press Ctrl+C to stop the server when done testing" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Test URLs after server starts:" -ForegroundColor Cyan
    Write-Host "  • Health check: http://localhost:8000/health" -ForegroundColor Gray
    Write-Host "  • API docs: http://localhost:8000/docs" -ForegroundColor Gray
    Write-Host ""
    Start-Sleep -Seconds 2
    
    # Run staging environment
    & ".\run-staging.ps1"
} else {
    Write-Host "ℹ️  Skipping test. You can test later with: .\run-staging.ps1" -ForegroundColor Cyan
}

# Step 11: Git branch setup
Write-Host ""
Write-Host "📋 Step 10: Git Branch Setup" -ForegroundColor Cyan
Write-Host "Final step: Set up staging branch on GitHub" -ForegroundColor Yellow
Write-Host ""

$currentBranch = git branch --show-current 2>$null

Write-Host "Current branch: $currentBranch" -ForegroundColor Gray
Write-Host ""

$setupBranch = Read-Host "Do you want to create staging branch now? (y/N)"

if ($setupBranch -eq "y" -or $setupBranch -eq "Y") {
    Write-Host ""
    
    # Check if staging branch already exists
    $stagingExists = git branch --list staging
    
    if ($stagingExists) {
        Write-Host "✅ Staging branch already exists" -ForegroundColor Green
        $switchBranch = Read-Host "Switch to staging branch? (y/N)"
        
        if ($switchBranch -eq "y" -or $switchBranch -eq "Y") {
            git checkout staging
            Write-Host "✅ Switched to staging branch" -ForegroundColor Green
        }
    } else {
        Write-Host "Creating staging branch from current branch ($currentBranch)..." -ForegroundColor Green
        git checkout -b staging
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✅ Created staging branch" -ForegroundColor Green
            Write-Host ""
            
            $pushBranch = Read-Host "Push staging branch to GitHub? (Y/n)"
            
            if ($pushBranch -eq "" -or $pushBranch -eq "y" -or $pushBranch -eq "Y") {
                git push -u origin staging
                
                if ($LASTEXITCODE -eq 0) {
                    Write-Host "✅ Staging branch pushed to GitHub!" -ForegroundColor Green
                } else {
                    Write-Host "⚠️  Push failed. You can push manually later with:" -ForegroundColor Yellow
                    Write-Host "  git push -u origin staging" -ForegroundColor Gray
                }
            }
        }
    }
} else {
    Write-Host "ℹ️  Skipping branch setup. Create it manually when ready:" -ForegroundColor Cyan
    Write-Host "  git checkout -b staging" -ForegroundColor Gray
    Write-Host "  git push -u origin staging" -ForegroundColor Gray
}

# Final summary
Write-Host ""
Write-Host "═══════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "✨ STAGING ENVIRONMENT SETUP COMPLETE!" -ForegroundColor Green
Write-Host "═══════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

Write-Host "📝 SUMMARY:" -ForegroundColor Cyan
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Gray
Write-Host "  ✅ Configuration saved to .env.staging" -ForegroundColor White
Write-Host "  ✅ Supabase project: $projectRef" -ForegroundColor White
Write-Host "  ✅ Email enabled: $emailEnabled" -ForegroundColor White
Write-Host "  ✅ JWT secret generated" -ForegroundColor White
Write-Host ""

Write-Host "🚀 QUICK COMMANDS:" -ForegroundColor Cyan
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Gray
Write-Host "  Test staging locally:" -ForegroundColor White
Write-Host "    .\run-staging.ps1" -ForegroundColor Gray
Write-Host ""
Write-Host "  Deploy to staging:" -ForegroundColor White
Write-Host "    git checkout staging" -ForegroundColor Gray
Write-Host "    git merge dev" -ForegroundColor Gray
Write-Host "    git push origin staging" -ForegroundColor Gray
Write-Host ""
Write-Host "  View staging logs:" -ForegroundColor White
Write-Host "    vercel logs --follow" -ForegroundColor Gray
Write-Host ""

Write-Host "📋 TODO CHECKLIST:" -ForegroundColor Cyan
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Gray

$checklistItems = @()

# Check if migrations were applied
try {
    $linkedProject = Get-Content ".\.supabase\config.toml" 2>$null | Select-String "project_id"
    if ($linkedProject -and $linkedProject -match $projectRef) {
        Write-Host "  ✅ Migrations applied to Supabase" -ForegroundColor Green
    } else {
        Write-Host "  ⬜ Apply migrations to Supabase" -ForegroundColor Yellow
        Write-Host "     supabase link --project-ref $projectRef" -ForegroundColor Gray
        Write-Host "     supabase db push" -ForegroundColor Gray
        $checklistItems += "Apply migrations"
    }
} catch {
    Write-Host "  ⬜ Apply migrations to Supabase" -ForegroundColor Yellow
    Write-Host "     supabase link --project-ref $projectRef" -ForegroundColor Gray
    Write-Host "     supabase db push" -ForegroundColor Gray
    $checklistItems += "Apply migrations"
}

# Check frontend URLs
$envCheck = Get-Content .env.staging | Select-String "FRONTEND_URL"
if ($envCheck -match "localhost|vercel|netlify") {
    if ($envCheck -match "localhost") {
        Write-Host "  ⬜ Deploy frontend and update URLs in .env.staging" -ForegroundColor Yellow
        $checklistItems += "Deploy frontend"
    } else {
        Write-Host "  ✅ Frontend URLs configured" -ForegroundColor Green
    }
}

# Check branch
try {
    $remoteStagingExists = git ls-remote --heads origin staging 2>$null
    if ($remoteStagingExists) {
        Write-Host "  ✅ Staging branch exists on GitHub" -ForegroundColor Green
    } else {
        Write-Host "  ⬜ Push staging branch to GitHub" -ForegroundColor Yellow
        Write-Host "     git push -u origin staging" -ForegroundColor Gray
        $checklistItems += "Push staging branch"
    }
} catch {
    Write-Host "  ⬜ Create and push staging branch" -ForegroundColor Yellow
    $checklistItems += "Create staging branch"
}

Write-Host ""

if ($checklistItems.Count -eq 0) {
    Write-Host "🎉 ALL DONE! Your staging environment is ready!" -ForegroundColor Green
} else {
    Write-Host "⚡ NEXT ACTIONS:" -ForegroundColor Yellow
    foreach ($item in $checklistItems) {
        Write-Host "   • $item" -ForegroundColor White
    }
}

Write-Host ""
Write-Host "📚 DOCUMENTATION:" -ForegroundColor Cyan
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Gray
Write-Host "  • STAGING_DEPLOYMENT_GUIDE.md - Complete guide" -ForegroundColor White
Write-Host "  • STAGING_CHECKLIST.md - Quick reference" -ForegroundColor White
Write-Host "  • STAGING_QUICK_START.md - 5-min setup" -ForegroundColor White
Write-Host "  • DEPLOYMENT_FLOW.md - Workflow overview" -ForegroundColor White
Write-Host ""
Write-Host "Need help? Check the docs above! 🚀" -ForegroundColor Cyan
Write-Host ""
