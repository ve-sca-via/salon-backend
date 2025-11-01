"""
Run Salon Approval Workflow Migration

This script runs the Alembic migration to add salon approval workflow columns.
"""
import sys
import os

# Add the backend directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from alembic.config import Config
from alembic import command

def run_migration():
    """Run the Alembic migration to upgrade to the latest version."""
    print("=" * 70)
    print("Running Salon Approval Workflow Migration")
    print("=" * 70)
    print()
    
    # Create Alembic config
    alembic_cfg = Config("alembic.ini")
    
    # Show current version
    print("Checking current database version...")
    try:
        command.current(alembic_cfg)
    except Exception as e:
        print(f"Warning: Could not determine current version: {e}")
    
    print()
    print("Upgrading database to latest version...")
    print()
    
    try:
        # Run upgrade
        command.upgrade(alembic_cfg, "head")
        print()
        print("=" * 70)
        print("✅ Migration completed successfully!")
        print("=" * 70)
        print()
        print("Changes applied:")
        print("  ✓ Added 'status' column (pending/approved/rejected/draft)")
        print("  ✓ Added 'submitted_by' column (HMR agent tracking)")
        print("  ✓ Added 'submitted_at' column (submission timestamp)")
        print("  ✓ Added 'reviewed_by' column (admin reviewer tracking)")
        print("  ✓ Added 'reviewed_at' column (review timestamp)")
        print("  ✓ Added 'rejection_reason' column (for rejected salons)")
        print("  ✓ Added address fields (address_line1, address_line2, city, state, pincode)")
        print("  ✓ Added image fields (cover_image, logo_image, gallery_images)")
        print("  ✓ Created foreign key constraints")
        print("  ✓ Created indexes for better performance")
        print("  ✓ Existing salons set to 'approved' status")
        print()
        print("Your admin panel should now work without 400 errors!")
        print()
        
    except Exception as e:
        print()
        print("=" * 70)
        print("❌ Migration failed!")
        print("=" * 70)
        print()
        print(f"Error: {e}")
        print()
        print("Troubleshooting:")
        print("1. Check your database connection in .env file")
        print("2. Ensure PostgreSQL is running")
        print("3. Verify you have the correct database permissions")
        print("4. Check the error message above for specific details")
        print()
        sys.exit(1)

if __name__ == "__main__":
    run_migration()
