"""admin_module_additions: contexto de reintento en tool_invocation_logs y presupuesto en app_registrations

Revision ID: c3e7a19f5d2b
Revises: a7f3c9d21b4e
Create Date: 2026-08-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3e7a19f5d2b'
down_revision: Union[str, None] = 'a7f3c9d21b4e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('tool_invocation_logs', sa.Column('context', sa.JSON(), nullable=True))
    op.add_column('app_registrations', sa.Column('budget_limit_usd', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('app_registrations', 'budget_limit_usd')
    op.drop_column('tool_invocation_logs', 'context')
