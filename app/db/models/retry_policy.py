from sqlalchemy import Column, Integer, ForeignKey
from db.base import Base

class RetryPolicy(Base):
    __tablename__ = "retry_policies"

    job_id = Column(Integer, ForeignKey("jobs.id"), primary_key=True)
    max_retries = Column(Integer, default=3)
    base_delay_seconds = Column(Integer, default=30)
