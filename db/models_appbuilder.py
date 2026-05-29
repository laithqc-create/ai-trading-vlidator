"""
db/models_appbuilder.py
Add these models to db/models.py (or import in db/models.py with:
  from db.models_appbuilder import AppProject, AppBuildStep
)
"""

import enum
import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Text, DateTime, Boolean,
    ForeignKey, Enum as SAEnum, JSON
)
from sqlalchemy.types import TypeDecorator, CHAR
from sqlalchemy.orm import relationship
from db.database import Base


class UUID(TypeDecorator):
    """Platform-independent UUID type — uses CHAR(36) for SQLite, native UUID for Postgres."""
    impl = CHAR(36)
    cache_ok = True

    def __init__(self, as_uuid: bool = True, *args, **kwargs):
        self.as_uuid = as_uuid
        super().__init__(*args, **kwargs)

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        try:
            return uuid.UUID(str(value)) if self.as_uuid else str(value)
        except (ValueError, AttributeError):
            return value


class BuildStatus(str, enum.Enum):
    IDLE        = "idle"
    PLANNING    = "planning"
    CODING      = "coding"
    REVIEWING   = "reviewing"
    DONE        = "done"
    ERROR       = "error"


class AppProject(Base):
    """One app-builder project per user (many allowed)."""
    __tablename__ = "app_projects"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id         = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name            = Column(String(120), nullable=False)
    description     = Column(Text, nullable=True)
    platform        = Column(String(40), default="mql5")   # mql5 | pine | python
    status          = Column(SAEnum(BuildStatus), default=BuildStatus.IDLE)
    disclaimer_agreed = Column(Boolean, default=False)
    agreed_at       = Column(DateTime(timezone=True), nullable=True)

    current_code    = Column(Text, nullable=True)
    current_version = Column(Integer, default=0)

    listed_on_marketplace  = Column(Boolean, default=False)
    marketplace_listing_id = Column(UUID(as_uuid=True), nullable=True)

    created_at  = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at  = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    steps = relationship("AppBuildStep", back_populates="project", cascade="all, delete-orphan")


class AppBuildStep(Base):
    """Each agentic turn in the build conversation."""
    __tablename__ = "app_build_steps"

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id   = Column(UUID(as_uuid=True), ForeignKey("app_projects.id"), nullable=False, index=True)
    step_number  = Column(Integer, nullable=False)

    user_message = Column(Text, nullable=False)
    agent_plan   = Column(Text, nullable=True)
    code_diff    = Column(Text, nullable=True)
    full_code    = Column(Text, nullable=True)
    agent_notes  = Column(Text, nullable=True)
    warnings     = Column(JSON, default=list)

    status        = Column(SAEnum(BuildStatus), default=BuildStatus.IDLE)
    error_message = Column(Text, nullable=True)
    created_at    = Column(DateTime(timezone=True), default=datetime.utcnow)

    project = relationship("AppProject", back_populates="steps")
