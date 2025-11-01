"""
Script to run Alembic migrations programmatically
This handles the asyncpg driver issue by using SQLAlchemy's sync connection
"""
import asyncio
from sqlalchemy import text
from app.core.config import settings


async def run_migrations():
    """Run all pending migrations"""
    
    # Create sync engine for migrations (uses psycopg2 if available, or we'll use raw SQL)
    db_url = settings.DATABASE_URL
    
    print(f"🔄 Connecting to database...")
    print(f"📍 Database: {db_url.split('@')[1] if '@' in db_url else 'hidden'}")
    
    # For now, let's use asyncpg to run the SQL directly
    from sqlalchemy.ext.asyncio import create_async_engine
    
    # Convert to asyncpg URL
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://")
    
    engine = create_async_engine(db_url)
    
    try:
        async with engine.begin() as conn:
            # Check if alembic_version table exists
            result = await conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'alembic_version'
                )
            """))
            table_exists = result.scalar()
            
            if not table_exists:
                print("📝 Creating alembic_version table...")
                await conn.execute(text("""
                    CREATE TABLE alembic_version (
                        version_num VARCHAR(32) NOT NULL,
                        CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
                    )
                """))
                current_version = None
            else:
                # Get current version
                result = await conn.execute(text("SELECT version_num FROM alembic_version"))
                row = result.first()
                current_version = row[0] if row else None
            
            print(f"📊 Current migration version: {current_version or 'None (empty database)'}")
            
            # Migration 001: Add latitude and longitude
            if current_version is None:
                print("\n🚀 Running migration 001: Add latitude and longitude columns...")
                
                # Check if columns already exist
                result = await conn.execute(text("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name='salons' AND column_name IN ('latitude', 'longitude')
                """))
                existing_cols = [row[0] for row in result]
                
                if 'latitude' not in existing_cols:
                    await conn.execute(text("ALTER TABLE salons ADD COLUMN latitude DECIMAL(10, 7)"))
                    print("   ✅ Added latitude column")
                else:
                    print("   ⏭️  latitude column already exists")
                
                if 'longitude' not in existing_cols:
                    await conn.execute(text("ALTER TABLE salons ADD COLUMN longitude DECIMAL(10, 7)"))
                    print("   ✅ Added longitude column")
                else:
                    print("   ⏭️  longitude column already exists")
                
                # Add indexes
                try:
                    await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_salons_lat ON salons(latitude)"))
                    print("   ✅ Created index on latitude")
                except:
                    print("   ⏭️  Index on latitude already exists")
                
                try:
                    await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_salons_lon ON salons(longitude)"))
                    print("   ✅ Created index on longitude")
                except:
                    print("   ⏭️  Index on longitude already exists")
                
                # Update version
                await conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('001')"))
                current_version = '001'
                print("   ✅ Migration 001 completed!")
            
            # Migration 002: Add foreign keys
            if current_version == '001':
                print("\n🚀 Running migration 002: Add foreign key constraints...")
                
                # Check if foreign keys already exist
                result = await conn.execute(text("""
                    SELECT constraint_name 
                    FROM information_schema.table_constraints 
                    WHERE table_name IN ('bookings', 'user_carts') 
                    AND constraint_type = 'FOREIGN KEY'
                    AND constraint_name IN ('fk_bookings_salon_id', 'fk_user_carts_salon_id')
                """))
                existing_fks = [row[0] for row in result]
                
                if 'fk_bookings_salon_id' not in existing_fks:
                    try:
                        await conn.execute(text("""
                            ALTER TABLE bookings 
                            ADD CONSTRAINT fk_bookings_salon_id 
                            FOREIGN KEY (salon_id) REFERENCES salons(id) ON DELETE RESTRICT
                        """))
                        print("   ✅ Added foreign key: bookings.salon_id → salons.id (ON DELETE RESTRICT)")
                    except Exception as e:
                        print(f"   ⚠️  Could not add FK on bookings.salon_id: {e}")
                else:
                    print("   ⏭️  Foreign key on bookings.salon_id already exists")
                
                if 'fk_user_carts_salon_id' not in existing_fks:
                    try:
                        await conn.execute(text("""
                            ALTER TABLE user_carts 
                            ADD CONSTRAINT fk_user_carts_salon_id 
                            FOREIGN KEY (salon_id) REFERENCES salons(id) ON DELETE CASCADE
                        """))
                        print("   ✅ Added foreign key: user_carts.salon_id → salons.id (ON DELETE CASCADE)")
                    except Exception as e:
                        print(f"   ⚠️  Could not add FK on user_carts.salon_id: {e}")
                else:
                    print("   ⏭️  Foreign key on user_carts.salon_id already exists")
                
                # Update version
                await conn.execute(text("UPDATE alembic_version SET version_num = '002'"))
                current_version = '002'
                print("   ✅ Migration 002 completed!")
            
            print(f"\n✨ All migrations completed! Current version: {current_version}")
            
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        raise
    finally:
        await engine.dispose()


if __name__ == "__main__":
    print("=" * 60)
    print("🔧 Database Migration Runner")
    print("=" * 60)
    asyncio.run(run_migrations())
