from enum import Enum

from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, UniqueConstraint
)
from sqlalchemy.sql import func
from db.base import Base


class ExecutionStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"

    @classmethod
    def terminal_states(cls):
        return {cls.SUCCESS, cls.FAILED}


class Execution(Base):
    __tablename__ = "executions"

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)

    execution_id = Column(String(36), nullable=False)
    status = Column(String(20), nullable=False)  # pending, running, success, failed
    attempt = Column(Integer, default=1)

    started_at = Column(DateTime(timezone=True))
    finished_at = Column(DateTime(timezone=True))
    error = Column(String)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("execution_id", name="uq_execution_execution_id"),
    )

