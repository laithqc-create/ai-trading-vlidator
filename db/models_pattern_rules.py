"""
db/models_pattern_rules.py — UserPatternRule model.
Add to db/models.py imports.
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from db.database import Base

class UserPatternRule(Base):
    """Per-user candle pattern rule override."""
    __tablename__ = "user_pattern_rules"
    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id      = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    pattern_name = Column(String(80), nullable=False)
    enabled      = Column(Boolean, default=True)
    min_body_ratio   = Column(Float, nullable=True)
    max_wick_ratio   = Column(Float, nullable=True)
    min_engulf_ratio = Column(Float, nullable=True)
    created_at   = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at   = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
