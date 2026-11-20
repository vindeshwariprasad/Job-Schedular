"""add status, max_runs, run_count to schedules

Revision ID: a1b2c3d4e5f6
Revises: 9d2699d4fb68
Create Date: 2026-02-19

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: str | Sequence[str] | None = '9d2699d4fb68'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('schedules', sa.Column('status', sa.String(length=20), nullable=False, server_default='active'))
    op.add_column('schedules', sa.Column('max_runs', sa.Integer(), nullable=True))
    op.add_column('schedules', sa.Column('run_count', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('schedules', 'run_count')
    op.drop_column('schedules', 'max_runs')
    op.drop_column('schedules', 'status')
