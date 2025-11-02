from sqlalchemy import (
    Column, String, Integer, DateTime, Text, func
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from database import Base
import uuid

class Task(Base):
    __tablename__ = "tasks"

    task_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_type = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="pending")
    payload = Column(JSONB, nullable=False)
    result = Column(JSONB, nullable=True)
    error = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0, nullable=False)
    max_retries = Column(Integer, default=3, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now(), nullable=False)
    scheduled_for = Column(DateTime(timezone=True), nullable=True)
    meta_data = Column(JSONB, nullable=False, default=dict)
