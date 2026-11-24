"""add job_dependencies table

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-11-24 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: str | Sequence[str] = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job_dependencies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "job_id",
            sa.Integer(),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "depends_on_job_id",
            sa.Integer(),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("job_id", "depends_on_job_id", name="uq_job_dependency"),
        sa.CheckConstraint("job_id != depends_on_job_id", name="chk_no_self_dep"),
    )

    op.create_index("ix_job_dependencies_job_id", "job_dependencies", ["job_id"])
    op.create_index("ix_job_dependencies_depends_on", "job_dependencies", ["depends_on_job_id"])

    # Partial index for BLOCKED execution sweep
    op.create_index(
        "ix_executions_status_blocked",
        "executions",
        ["status"],
        postgresql_where=sa.text("status = 'BLOCKED'"),
    )


def downgrade() -> None:
    op.drop_index("ix_executions_status_blocked", table_name="executions")
    op.drop_index("ix_job_dependencies_depends_on", table_name="job_dependencies")
    op.drop_index("ix_job_dependencies_job_id", table_name="job_dependencies")
    op.drop_table("job_dependencies")
