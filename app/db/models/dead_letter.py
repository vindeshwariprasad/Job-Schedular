from db.base import Base
from sqlalchemy import JSON, Column, DateTime, Integer, String
from sqlalchemy.sql import func


class DeadLetterJob(Base):
    __tablename__ = "dead_letter_jobs"

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer)
    execution_id = Column(String(36))

    payload = Column(JSON)
    error = Column(String)

    failed_at = Column(DateTime(timezone=True), server_default=func.now())
