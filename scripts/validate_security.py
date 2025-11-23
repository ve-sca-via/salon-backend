#!/usr/bin/env python3
"""
Security Validation Script

Validates critical security configurations before deployment
"""
import os
import sys
from pathlib import Path

def check_env_file(env_path: Path) -> list:
    """Check environment file for security issues"""
    issues = []
    
    if not env_path.exists():
        return [f"❌ {env_path.name} not found"]
    
    content = env_path.read_text(encoding='utf-8')
    lines = content.split('\n')
    
    # Check for service_role key exposure
    if 'VITE_' in content and 'SERVICE_ROLE' in content:
        issues.append(f"❌ CRITICAL: Service role key might be exposed in {env_path.name}")
    
    # Check for default/weak secrets
    weak_patterns = [
        'your-super-secret',
        'change-this',
        'example',
        'test-key',
        '12345',
    ]
    
    for line_num, line in enumerate(lines, 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        
        if '=' in line:
            key, value = line.split('=', 1)
            value = value.strip().strip('"').strip("'")
            
            # Check JWT secret
            if 'JWT_SECRET_KEY' in key:
                if any(pattern in value.lower() for pattern in weak_patterns):
                    issues.append(f"⚠️  Line {line_num}: Weak JWT_SECRET_KEY in {env_path.name}")
                elif len(value) < 32:
                    issues.append(f"⚠️  Line {line_num}: JWT_SECRET_KEY too short (min 32 chars) in {env_path.name}")
            
            # Check for accidentally committed real credentials
            if key in ['SUPABASE_SERVICE_ROLE_KEY', 'RAZORPAY_KEY_SECRET', 'JWT_SECRET_KEY']:
                if value and not any(pattern in value.lower() for pattern in ['example', 'your-', 'change']):
                    if env_path.name not in ['.env.example', '.env.staging.example', '.env.production.example']:
                        issues.append(f"⚠️  Line {line_num}: Real {key} might be in tracked file {env_path.name}")
    
    return issues

def check_frontend_env():
    """Check frontend environment files"""
    issues = []
    
    frontend_dirs = [
        Path('../salon-admin-panel'),
        Path('../salon-management-app'),
        Path('../../salon-admin-panel'),
        Path('../../salon-management-app'),
    ]
    
    for frontend_dir in frontend_dirs:
        if not frontend_dir.exists():
            continue
        
        # Check for .env files
        for env_file in frontend_dir.glob('.env*'):
            if env_file.is_file():
                content = env_file.read_text(encoding='utf-8')
                
                # CRITICAL: Service role in frontend
                if 'SERVICE_ROLE' in content:
                    issues.append(f"❌ CRITICAL: SERVICE_ROLE_KEY found in frontend file: {env_file}")
                
                # Check for backend JWT secret in frontend
                if 'JWT_SECRET_KEY' in content:
                    issues.append(f"❌ CRITICAL: JWT_SECRET_KEY found in frontend file: {env_file}")
    
    return issues

def check_gitignore():
    """Check if sensitive files are in .gitignore"""
    issues = []
    gitignore_path = Path('.gitignore')
    
    if not gitignore_path.exists():
        return ["❌ .gitignore not found"]
    
    content = gitignore_path.read_text(encoding='utf-8')
    
    required_patterns = [
        '.env',
        '.env.local',
        '.env.production',
        '.env.staging',
    ]
    
    for pattern in required_patterns:
        if pattern not in content:
            issues.append(f"⚠️  {pattern} not in .gitignore")
    
    return issues

def check_cors_config():
    """Check CORS configuration"""
    issues = []
    
    # Read config.py
    config_path = Path('app/core/config.py')
    if not config_path.exists():
        return ["❌ config.py not found"]
    
    content = config_path.read_text(encoding='utf-8')
    
    # Check for wildcard CORS in production
    if '"*"' in content or "'*'" in content:
        issues.append("⚠️  Wildcard (*) found in config.py - ensure CORS is restricted in production")
    
    return issues

def check_rls_status():
    """Check if RLS migration exists"""
    issues = []
    
    migrations_dir = Path('supabase/migrations')
    if migrations_dir.exists():
        disable_rls = list(migrations_dir.glob('*disable_rls*.sql'))
        if disable_rls:
            issues.append(f"✅ RLS disable migration found: {disable_rls[0].name}")
        else:
            issues.append("⚠️  No RLS disable migration found - RLS might still be enabled")
    
    return issues

def main():
    print("🔒 Security Validation Check")
    print("=" * 70)
    
    all_issues = []
    
    # Check backend .env files
    print("\n📁 Checking backend environment files...")
    for env_file in Path('.').glob('.env*'):
        if env_file.is_file():
            issues = check_env_file(env_file)
            if issues:
                all_issues.extend(issues)
            else:
                print(f"✅ {env_file.name} - OK")
    
    # Check frontend
    print("\n📁 Checking frontend environment files...")
    frontend_issues = check_frontend_env()
    if frontend_issues:
        all_issues.extend(frontend_issues)
    else:
        print("✅ No frontend environment issues found")
    
    # Check .gitignore
    print("\n📁 Checking .gitignore...")
    gitignore_issues = check_gitignore()
    if gitignore_issues:
        all_issues.extend(gitignore_issues)
    else:
        print("✅ .gitignore - OK")
    
    # Check CORS
    print("\n🌐 Checking CORS configuration...")
    cors_issues = check_cors_config()
    if cors_issues:
        all_issues.extend(cors_issues)
    else:
        print("✅ CORS configuration - OK")
    
    # Check RLS
    print("\n🔐 Checking RLS status...")
    rls_issues = check_rls_status()
    if rls_issues:
        for issue in rls_issues:
            print(issue)
    
    # Summary
    print("\n" + "=" * 70)
    if all_issues:
        print(f"⚠️  Found {len(all_issues)} security issues:\n")
        for issue in all_issues:
            print(issue)
        print("\n" + "=" * 70)
        print("⚠️  Please fix these issues before deployment!")
        return 1
    else:
        print("✅ All security checks passed!")
        print("=" * 70)
        print("\n✓ Service role key not exposed")
        print("✓ JWT secrets properly configured")
        print("✓ Sensitive files in .gitignore")
        print("✓ No obvious security misconfigurations")
        print("\n🚀 Ready for deployment")
        return 0

if __name__ == '__main__':
    exit(main())
