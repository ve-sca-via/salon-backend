"""Add foreign keys for salon_id references

Revision ID: 002
Revises: 001
Create Date: 2025-10-27

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade():
    # Add foreign key constraint for bookings.salon_id
    # Using RESTRICT to prevent deletion of salons with bookings (business requirement)
    op.create_foreign_key(
        'fk_bookings_salon_id',
        'bookings',
        'salons',
        ['salon_id'],
        ['id'],
        ondelete='RESTRICT'
    )
    
    # Add foreign key constraint for user_carts.salon_id
    # Using CASCADE since carts are temporary and should be removed if salon is deleted
    op.create_foreign_key(
        'fk_user_carts_salon_id',
        'user_carts',
        'salons',
        ['salon_id'],
        ['id'],
        ondelete='CASCADE'
    )


def downgrade():
    # Remove foreign key constraints
    op.drop_constraint('fk_user_carts_salon_id', 'user_carts', type_='foreignkey')
    op.drop_constraint('fk_bookings_salon_id', 'bookings', type_='foreignkey')
