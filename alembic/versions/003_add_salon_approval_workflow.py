"""Add salon approval workflow columns

Revision ID: 003
Revises: 002
Create Date: 2025-10-27

This migration adds columns needed for the salon approval workflow:
- status: pending/approved/rejected/draft
- submitted_by: HMR agent who submitted
- submission and review tracking
- detailed address fields
- image storage fields
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade():
    # Add status column with CHECK constraint
    op.add_column('salons', sa.Column('status', sa.String(), nullable=True, server_default='pending'))
    op.create_check_constraint(
        'ck_salons_status',
        'salons',
        "status IN ('pending', 'approved', 'rejected', 'draft')"
    )
    
    # Add submission tracking columns
    op.add_column('salons', sa.Column('submitted_by', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('salons', sa.Column('submitted_at', sa.TIMESTAMP(timezone=True), nullable=True))
    
    # Add review tracking columns
    op.add_column('salons', sa.Column('reviewed_by', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('salons', sa.Column('reviewed_at', sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column('salons', sa.Column('rejection_reason', sa.Text(), nullable=True))
    
    # Add detailed address fields
    op.add_column('salons', sa.Column('address_line1', sa.Text(), nullable=True))
    op.add_column('salons', sa.Column('address_line2', sa.Text(), nullable=True))
    op.add_column('salons', sa.Column('city', sa.String(100), nullable=True))
    op.add_column('salons', sa.Column('state', sa.String(100), nullable=True))
    op.add_column('salons', sa.Column('pincode', sa.String(10), nullable=True))
    
    # Add image storage fields
    op.add_column('salons', sa.Column('cover_image', sa.Text(), nullable=True))
    op.add_column('salons', sa.Column('logo_image', sa.Text(), nullable=True))
    op.add_column('salons', sa.Column('gallery_images', postgresql.ARRAY(sa.Text()), nullable=True))
    
    # Create foreign key constraints
    op.create_foreign_key(
        'fk_salons_submitted_by',
        'salons',
        'profiles',
        ['submitted_by'],
        ['id'],
        ondelete='SET NULL'
    )
    
    op.create_foreign_key(
        'fk_salons_reviewed_by',
        'salons',
        'profiles',
        ['reviewed_by'],
        ['id'],
        ondelete='SET NULL'
    )
    
    # Create indexes for better query performance
    op.create_index('idx_salons_status', 'salons', ['status'])
    op.create_index('idx_salons_submitted_by', 'salons', ['submitted_by'])
    op.create_index('idx_salons_city_state', 'salons', ['city', 'state'])
    
    # Update existing salons to have 'approved' status (backward compatibility)
    op.execute("UPDATE salons SET status = 'approved' WHERE status IS NULL OR status = 'pending'")
    
    # Add column comments for documentation
    op.execute("COMMENT ON COLUMN salons.status IS 'Salon approval status: pending (awaiting review), approved (live), rejected (declined), draft (incomplete)'")
    op.execute("COMMENT ON COLUMN salons.submitted_by IS 'UUID of the HMR agent who submitted this salon'")
    op.execute("COMMENT ON COLUMN salons.submitted_at IS 'Timestamp when salon was submitted for approval'")
    op.execute("COMMENT ON COLUMN salons.reviewed_by IS 'UUID of the admin who reviewed this salon'")
    op.execute("COMMENT ON COLUMN salons.reviewed_at IS 'Timestamp when salon was reviewed'")
    op.execute("COMMENT ON COLUMN salons.rejection_reason IS 'Reason provided when salon was rejected'")


def downgrade():
    # Remove indexes
    op.drop_index('idx_salons_city_state', table_name='salons')
    op.drop_index('idx_salons_submitted_by', table_name='salons')
    op.drop_index('idx_salons_status', table_name='salons')
    
    # Remove foreign key constraints
    op.drop_constraint('fk_salons_reviewed_by', 'salons', type_='foreignkey')
    op.drop_constraint('fk_salons_submitted_by', 'salons', type_='foreignkey')
    
    # Remove columns in reverse order
    op.drop_column('salons', 'gallery_images')
    op.drop_column('salons', 'logo_image')
    op.drop_column('salons', 'cover_image')
    op.drop_column('salons', 'pincode')
    op.drop_column('salons', 'state')
    op.drop_column('salons', 'city')
    op.drop_column('salons', 'address_line2')
    op.drop_column('salons', 'address_line1')
    op.drop_column('salons', 'rejection_reason')
    op.drop_column('salons', 'reviewed_at')
    op.drop_column('salons', 'reviewed_by')
    op.drop_column('salons', 'submitted_at')
    op.drop_column('salons', 'submitted_by')
    
    # Remove CHECK constraint and status column
    op.drop_constraint('ck_salons_status', 'salons', type_='check')
    op.drop_column('salons', 'status')
