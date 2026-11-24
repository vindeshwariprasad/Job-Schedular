from db.base import Base
from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.sql import func


class JobDependency(Base):
    __tablename__ = "job_dependencies"

    id = Column(Integer, primary_key=True)
    job_id = Column(
        Integer,
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    depends_on_job_id = Column(
        Integer,
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("job_id", "depends_on_job_id", name="uq_job_dependency"),
        CheckConstraint("job_id != depends_on_job_id", name="chk_no_self_dep"),
    )
