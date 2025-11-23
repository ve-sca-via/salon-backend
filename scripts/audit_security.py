#!/usr/bin/env python3
"""
Security Audit Script
Checks all API endpoints for proper authorization
"""

import os
import re
from pathlib import Path
from typing import List, Dict, Tuple

# Patterns to detect authorization
AUTH_PATTERNS = [
    r'Depends\(get_current_user\)',
    r'Depends\(require_admin\)',
    r'Depends\(require_vendor\)',
    r'Depends\(require_customer\)',
    r'Depends\(require_rm\)',
    r'Depends\(RoleChecker',
]

# Public endpoints that don't need auth
PUBLIC_ENDPOINTS = [
    '/login',
    '/signup',
    '/password-reset',
    '/public',
    '/geocode',
    '/reverse-geocode',
    '/webhook',
]

def should_be_public(route_path: str, method: str) -> bool:
    """Check if endpoint should be public"""
    route_lower = route_path.lower()
    
    # Known public patterns
    if any(pattern in route_lower for pattern in PUBLIC_ENDPOINTS):
        return True
    
    # GET requests to browse/search might be public
    if method == 'GET' and any(x in route_lower for x in ['/salons', '/services', '/nearby']):
        return True
    
    return False

def extract_routes(file_path: Path) -> List[Dict]:
    """Extract all routes from a Python file"""
    content = file_path.read_text(encoding='utf-8')
    
    routes = []
    
    # Find all @router decorators
    pattern = r'@router\.(get|post|put|patch|delete)\(["\']([^"\']+)["\']'
    matches = re.finditer(pattern, content, re.MULTILINE)
    
    for match in matches:
        method = match.group(1).upper()
        path = match.group(2)
        
        # Get the function code (next ~20 lines after decorator)
        start = match.end()
        end = start + 1000
        func_code = content[start:end]
        
        # Check if any auth pattern is present
        has_auth = any(re.search(pattern, func_code) for pattern in AUTH_PATTERNS)
        
        routes.append({
            'file': file_path.name,
            'method': method,
            'path': path,
            'has_auth': has_auth,
            'line': content[:match.start()].count('\n') + 1
        })
    
    return routes

def audit_api_security() -> Tuple[List[Dict], List[Dict]]:
    """Audit all API endpoints for security"""
    api_dir = Path('app/api')
    
    if not api_dir.exists():
        print("❌ API directory not found")
        return [], []
    
    all_routes = []
    
    # Scan all Python files
    for py_file in api_dir.rglob('*.py'):
        if py_file.name == '__init__.py':
            continue
        
        routes = extract_routes(py_file)
        all_routes.extend(routes)
    
    # Categorize routes
    secure = []
    insecure = []
    
    for route in all_routes:
        is_public = should_be_public(route['path'], route['method'])
        
        if is_public and not route['has_auth']:
            # Public endpoint without auth - OK
            secure.append(route)
        elif not is_public and route['has_auth']:
            # Protected endpoint with auth - OK
            secure.append(route)
        elif not is_public and not route['has_auth']:
            # Protected endpoint WITHOUT auth - DANGEROUS
            insecure.append(route)
        else:
            # Public endpoint with auth - Redundant but safe
            secure.append(route)
    
    return secure, insecure

def main():
    print("🔒 Security Audit - API Endpoint Authorization Check")
    print("=" * 70)
    
    secure, insecure = audit_api_security()
    
    print(f"\n✅ Secure Endpoints: {len(secure)}")
    print(f"⚠️  Insecure Endpoints: {len(insecure)}")
    
    if insecure:
        print("\n" + "=" * 70)
        print("⚠️  ENDPOINTS MISSING AUTHORIZATION")
        print("=" * 70)
        
        for route in insecure:
            print(f"\n❌ {route['method']} {route['path']}")
            print(f"   File: {route['file']}:{route['line']}")
            print(f"   Issue: No Depends(get_current_user) or role check found")
            
            # Suggest fix
            if 'admin' in route['path']:
                print(f"   Fix: Add Depends(require_admin)")
            elif 'vendor' in route['path']:
                print(f"   Fix: Add Depends(require_vendor)")
            else:
                print(f"   Fix: Add Depends(get_current_user)")
        
        print("\n" + "=" * 70)
        print("⚠️  ACTION REQUIRED: Fix these endpoints immediately!")
        print("=" * 70)
        return 1
    else:
        print("\n" + "=" * 70)
        print("✅ All endpoints have proper authorization checks!")
        print("=" * 70)
        
        print("\n📊 Summary by file:")
        file_counts = {}
        for route in secure:
            file_counts[route['file']] = file_counts.get(route['file'], 0) + 1
        
        for file, count in sorted(file_counts.items()):
            print(f"   {file}: {count} endpoints")
        
        return 0

if __name__ == '__main__':
    exit(main())
