"""knowledge_entries: lo que el bot sabe de cada negocio (preguntas frecuentes)

Revision ID: d8b4f2a6c1e9
Revises: c3e7a19f5d2b
Create Date: 2026-09-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd8b4f2a6c1e9'
down_revision: Union[str, None] = 'c3e7a19f5d2b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'knowledge_entries',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('app_id', sa.String(length=64), nullable=False),
        sa.Column('business_id', sa.String(length=64), nullable=False),
        sa.Column('topic', sa.String(length=160), nullable=False),
        sa.Column('answer', sa.Text(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_knowledge_tenant', 'knowledge_entries', ['app_id', 'business_id'])


def downgrade() -> None:
    op.drop_index('ix_knowledge_tenant', table_name='knowledge_entries')
    op.drop_table('knowledge_entries')
