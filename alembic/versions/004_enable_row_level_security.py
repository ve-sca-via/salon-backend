"""Enable Row Level Security (RLS) on all tables

Revision ID: 004
Revises: 003
Create Date: 2025-10-28

This migration enables Row Level Security (RLS) on all tables
and creates security policies to control data access at the database level.

Benefits:
- Automatic security enforcement (no manual auth checks needed)
- Protection against SQL injection
- Prevents data leaks even if code has bugs
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade():
    # Enable Row Level Security on all tables
    op.execute("ALTER TABLE salons ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE bookings ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE salon_services ENABLE ROW LEVEL SECURITY;")
    
    # Note: profiles table might not exist yet, so we'll create it if needed
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'profiles') THEN
                ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
            END IF;
        END $$;
    """)
    
    # ========================================
    # SALONS TABLE POLICIES
    # ========================================
    
    # Policy 1: Anyone can view approved salons (public browsing)
    op.execute("""
        CREATE POLICY "Public can view approved salons"
        ON salons
        FOR SELECT
        USING (status = 'approved');
    """)
    
    # Policy 2: Salon owners can view and edit their own salons
    op.execute("""
        CREATE POLICY "Owners can manage their salons"
        ON salons
        FOR ALL
        USING (
            auth.uid()::text = owner_id::text
            OR EXISTS (
                SELECT 1 FROM profiles
                WHERE profiles.id = auth.uid()
                AND profiles.role IN ('admin', 'hmr_agent')
            )
        );
    """)
    
    # Policy 3: Admins and HMR agents can create salons
    op.execute("""
        CREATE POLICY "Admins can create salons"
        ON salons
        FOR INSERT
        WITH CHECK (
            EXISTS (
                SELECT 1 FROM profiles
                WHERE profiles.id = auth.uid()
                AND profiles.role IN ('admin', 'hmr_agent')
            )
        );
    """)
    
    # ========================================
    # BOOKINGS TABLE POLICIES
    # ========================================
    
    # Policy 1: Users can only see their own bookings
    op.execute("""
        CREATE POLICY "Users see own bookings"
        ON bookings
        FOR SELECT
        USING (auth.uid()::text = user_id::text);
    """)
    
    # Policy 2: Users can create their own bookings
    op.execute("""
        CREATE POLICY "Users create own bookings"
        ON bookings
        FOR INSERT
        WITH CHECK (auth.uid()::text = user_id::text);
    """)
    
    # Policy 3: Users can update their own bookings (cancel, etc.)
    op.execute("""
        CREATE POLICY "Users update own bookings"
        ON bookings
        FOR UPDATE
        USING (auth.uid()::text = user_id::text);
    """)
    
    # Policy 4: Salon owners and admins can see all bookings for their salons
    op.execute("""
        CREATE POLICY "Salon owners see salon bookings"
        ON bookings
        FOR SELECT
        USING (
            EXISTS (
                SELECT 1 FROM salons
                WHERE salons.id = bookings.salon_id
                AND (
                    salons.owner_id::text = auth.uid()::text
                    OR EXISTS (
                        SELECT 1 FROM profiles
                        WHERE profiles.id = auth.uid()
                        AND profiles.role = 'admin'
                    )
                )
            )
        );
    """)
    
    # ========================================
    # SALON_SERVICES TABLE POLICIES
    # ========================================
    
    # Policy 1: Anyone can view services for approved salons
    op.execute("""
        CREATE POLICY "Public can view salon services"
        ON salon_services
        FOR SELECT
        USING (
            EXISTS (
                SELECT 1 FROM salons
                WHERE salons.id = salon_services.salon_id
                AND salons.status = 'approved'
            )
        );
    """)
    
    # Policy 2: Only salon owners and admins can manage services
    op.execute("""
        CREATE POLICY "Admins manage services"
        ON salon_services
        FOR ALL
        USING (
            EXISTS (
                SELECT 1 FROM salons
                WHERE salons.id = salon_services.salon_id
                AND (
                    salons.owner_id::text = auth.uid()::text
                    OR EXISTS (
                        SELECT 1 FROM profiles
                        WHERE profiles.id = auth.uid()
                        AND profiles.role IN ('admin', 'hmr_agent')
                    )
                )
            )
        );
    """)
    
    # ========================================
    # PROFILES TABLE POLICIES (if exists)
    # ========================================
    
    # Policy: Users can view their own profile
    op.execute("""
        CREATE POLICY "Users view own profile"
        ON profiles
        FOR SELECT
        USING (id = auth.uid());
    """)
    
    # Policy: Admins can view all profiles
    op.execute("""
        CREATE POLICY "Admins view all profiles"
        ON profiles
        FOR SELECT
        USING (
            EXISTS (
                SELECT 1 FROM profiles
                WHERE profiles.id = auth.uid()
                AND profiles.role = 'admin'
            )
        );
    """)
    
    # Policy: Users can update their own profile
    op.execute("""
        CREATE POLICY "Users update own profile"
        ON profiles
        FOR UPDATE
        USING (id = auth.uid());
    """)
    
    # Create index for better policy performance
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_profiles_role 
        ON profiles(role);
    """)


def downgrade():
    # Drop all policies
    op.execute("DROP POLICY IF EXISTS 'Public can view approved salons' ON salons;")
    op.execute("DROP POLICY IF EXISTS 'Owners can manage their salons' ON salons;")
    op.execute("DROP POLICY IF EXISTS 'Admins can create salons' ON salons;")
    
    op.execute("DROP POLICY IF EXISTS 'Users see own bookings' ON bookings;")
    op.execute("DROP POLICY IF EXISTS 'Users create own bookings' ON bookings;")
    op.execute("DROP POLICY IF EXISTS 'Users update own bookings' ON bookings;")
    op.execute("DROP POLICY IF EXISTS 'Salon owners see salon bookings' ON bookings;")
    
    op.execute("DROP POLICY IF EXISTS 'Public can view salon services' ON salon_services;")
    op.execute("DROP POLICY IF EXISTS 'Admins manage services' ON salon_services;")
    
    op.execute("DROP POLICY IF EXISTS 'Users view own profile' ON profiles;")
    op.execute("DROP POLICY IF EXISTS 'Admins view all profiles' ON profiles;")
    op.execute("DROP POLICY IF EXISTS 'Users update own profile' ON profiles;")
    
    # Drop index
    op.execute("DROP INDEX IF EXISTS idx_profiles_role;")
    
    # Disable RLS
    op.execute("ALTER TABLE salons DISABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE bookings DISABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE salon_services DISABLE ROW LEVEL SECURITY;")
    
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'profiles') THEN
                ALTER TABLE profiles DISABLE ROW LEVEL SECURITY;
            END IF;
        END $$;
    """)


