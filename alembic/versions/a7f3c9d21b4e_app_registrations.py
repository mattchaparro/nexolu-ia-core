"""app_registrations: persistencia de apps cliente en BD

Revision ID: a7f3c9d21b4e
Revises: 1cdf62c060e0
Create Date: 2026-08-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7f3c9d21b4e'
down_revision: Union[str, None] = '1cdf62c060e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'app_registrations',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('app_id', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('api_key', sa.String(length=255), nullable=False),
        sa.Column('api_key_hash', sa.String(length=64), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('base_url', sa.String(length=512), nullable=False),
        sa.Column('site_url', sa.String(length=512), nullable=True),
        sa.Column('site_name', sa.String(length=128), nullable=True),
        sa.Column('provider', sa.String(length=32), nullable=True),
        sa.Column('model', sa.String(length=128), nullable=True),
        sa.Column('provider_api_key', sa.String(length=255), nullable=True),
        sa.Column('provider_preferences', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('app_id', name='uq_app_registrations_app_id'),
        sa.UniqueConstraint('api_key_hash', name='uq_app_registrations_api_key_hash'),
    )


def downgrade() -> None:
    op.drop_table('app_registrations')
