"""Add latitude and longitude to salons table

Revision ID: 001
Revises: 
Create Date: 2025-10-26

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Add latitude and longitude columns
    op.add_column('salons', sa.Column('latitude', sa.DECIMAL(precision=10, scale=7), nullable=True))
    op.add_column('salons', sa.Column('longitude', sa.DECIMAL(precision=10, scale=7), nullable=True))
    
    # Add indexes for better query performance
    op.create_index('idx_salons_lat', 'salons', ['latitude'])
    op.create_index('idx_salons_lon', 'salons', ['longitude'])


def downgrade():
    # Remove indexes
    op.drop_index('idx_salons_lon', table_name='salons')
    op.drop_index('idx_salons_lat', table_name='salons')
    
    # Remove columns
    op.drop_column('salons', 'longitude')
    op.drop_column('salons', 'latitude')
