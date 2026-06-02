"""db/models_indicator_prefs.py — per-user indicator preferences."""
import uuid
from datetime import datetime
from sqlalchemy import Column, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSON, ARRAY, TEXT
from db.database import Base

class UserIndicatorPrefs(Base):
    __tablename__ = "user_indicator_prefs"
    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id         = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    enabled_indicators = Column(ARRAY(TEXT), nullable=True)   # None = all enabled
    custom_settings    = Column(JSON, default=dict)           # {name: {param: val}}
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
