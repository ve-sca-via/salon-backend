from supabase import create_client
from app.core.config import settings

supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

# Check vendor_join_requests
result = supabase.table('vendor_join_requests').select('*').eq('status', 'pending').execute()

print(f'\n=== PENDING VENDOR REQUESTS ===')
print(f'Found {len(result.data)} pending requests\n')

rm_ids = set()
for r in result.data:
    rm_ids.add(r['rm_id'])

# Check RM profiles
print(f'\n=== RM PROFILES CHECK ===')
for rm_id in rm_ids:
    print(f"\nChecking RM ID: {rm_id}")
    print("-" * 50)
    
    rm_result = supabase.table('rm_profiles').select('*').eq('id', rm_id).execute()
    if rm_result.data:
        print(f"✅ RM Profile exists")
        print(f"   Total Score: {rm_result.data[0].get('total_score', 0)}")
        print(f"   Active: {rm_result.data[0].get('is_active', False)}")
    else:
        print(f"❌ No RM Profile found")
    
    # Check profiles table
    profile_result = supabase.table('profiles').select('*').eq('id', rm_id).execute()
    if profile_result.data:
        print(f"✅ User Profile exists")
        print(f"   Full Name: {profile_result.data[0].get('full_name', 'N/A')}")
        print(f"   Email: {profile_result.data[0].get('email', 'N/A')}")
        print(f"   Role: {profile_result.data[0].get('role', 'N/A')}")
    else:
        print(f"❌ No User Profile found in profiles table")
        
    # Try to query with single()
    try:
        single_profile = supabase.table('profiles').select('*').eq('id', rm_id).single().execute()
        print(f"✅ Single query worked: {single_profile.data}")
    except Exception as e:
        print(f"❌ Single query failed: {str(e)}")


