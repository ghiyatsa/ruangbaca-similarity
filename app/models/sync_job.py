from sqlalchemy import Column, DateTime, Integer, String, Text, func

from app.models.base import Base


class SyncJob(Base):
    __tablename__ = "sync_jobs"

    id = Column(String(36), primary_key=True, index=True)
    status = Column(String(20), nullable=False, index=True)
    payload_json = Column(Text, nullable=False)
    total_received = Column(Integer, nullable=False, default=0)
    total_processed = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
