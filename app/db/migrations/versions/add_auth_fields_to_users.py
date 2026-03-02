"""add auth fields to users

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-02-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str]] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('username', sa.String(length=150), nullable=True))
    op.add_column('users', sa.Column('hashed_password', sa.String(length=255), nullable=True))

    # Backfill existing rows with defaults so we can make columns NOT NULL
    op.execute("UPDATE users SET username = 'user_' || id WHERE username IS NULL")
    op.execute("UPDATE users SET hashed_password = 'migrated' WHERE hashed_password IS NULL")

    op.alter_column('users', 'username', nullable=False)
    op.alter_column('users', 'hashed_password', nullable=False)
    op.create_unique_constraint('uq_users_username', 'users', ['username'])


def downgrade() -> None:
    op.drop_constraint('uq_users_username', 'users', type_='unique')
    op.drop_column('users', 'hashed_password')
    op.drop_column('users', 'username')
