from db.base import Base
from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.sql import func


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    name = Column(String(255), nullable=False)
    task_type = Column(String(50), nullable=False)  # api_call / script
    payload = Column(JSON, nullable=False)
    priority = Column(String(10), nullable=False, default="MEDIUM", server_default="MEDIUM")

    rate_limit_per_min = Column(Integer, default=60)
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
