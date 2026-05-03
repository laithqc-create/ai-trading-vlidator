"""
Database models for AI Trade Validator.
Tables: users, subscriptions, validations, user_rules, ea_logs
"""
from datetime import datetime, date
from enum import Enum as PyEnum
from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, Float, Boolean,
    DateTime, Date, Enum, ForeignKey, JSON, UniqueConstraint
)
from sqlalchemy.orm import relationship, DeclarativeBase
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class PlanTier(str, PyEnum):
    FREE = "free"
    PRODUCT1 = "product1"   # Indicator Validator $29
    PRODUCT2 = "product2"   # EA Analyzer $49
    PRODUCT3 = "product3"   # Manual Validator $19
    PRO = "pro"             # All products $79


class ValidationStatus(str, PyEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class SignalType(str, PyEnum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String(64), nullable=True)
    first_name = Column(String(64), nullable=True)
    last_name = Column(String(64), nullable=True)
    plan = Column(Enum(PlanTier, values_callable=lambda x: [e.value for e in x]), default=PlanTier.FREE, nullable=False)

    # Whop billing
    whop_user_id = Column(String(64), unique=True, nullable=True)
    whop_membership_id = Column(String(64), unique=True, nullable=True)
    plan_expires_at = Column(DateTime, nullable=True)

    # Browser extension user tracking
    ext_user_id = Column(String(64), unique=True, nullable=True, index=True)
    linked_telegram_id = Column(BigInteger, nullable=True)

    # RAGFlow integration
    ragflow_dataset_id = Column(String(128), nullable=True)

    # Webhook tokens for Product 1 & 2
    indicator_webhook_token = Column(String(64), unique=True, nullable=True)
    ea_webhook_token = Column(String(64), unique=True, nullable=True)

    # Usage tracking (free tier)
    daily_validation_count = Column(Integer, default=0)
    daily_validation_date = Column(Date, nullable=True)

    # DeepSeek generation tracking (loss leader budget)
    total_generations = Column(Integer, default=0)
    total_generation_cost = Column(Float, default=0.0)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    validations = relationship("Validation", back_populates="user", lazy="select")
    rules = relationship("UserRule", back_populates="user", lazy="select")

    def __repr__(self):
        return f"<User telegram_id={self.telegram_id} plan={self.plan}>"

    def can_validate(self, free_limit: int = 5) -> bool:
        """Check if user can perform a validation (free tier limit)."""
        if self.plan != PlanTier.FREE:
            return True
        today = date.today()
        if self.daily_validation_date != today:
            return True  # New day resets
        return (self.daily_validation_count or 0) < free_limit


class Validation(Base):
    __tablename__ = "validations"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # What was validated
    product = Column(Integer, nullable=False)  # 1, 2, or 3
    ticker = Column(String(20), nullable=False)
    signal = Column(Enum(SignalType, values_callable=lambda x: [e.value for e in x]), nullable=True)
    price = Column(Float, nullable=True)

    # Source data
    source_payload = Column(JSON, nullable=True)   # raw webhook or user input

    # Results
    status = Column(Enum(ValidationStatus, values_callable=lambda x: [e.value for e in x]), default=ValidationStatus.PENDING)
    confidence_score = Column(Float, nullable=True)        # 0.0 - 1.0
    verdict = Column(String(20), nullable=True)            # CONFIRM / REJECT / CAUTION
    trader_analysis = Column(JSON, nullable=True)          # OpenTrade.ai full result
    mentor_context = Column(Text, nullable=True)           # RAGFlow retrieved context
    final_message = Column(Text, nullable=True)            # Message sent to user
    error_message = Column(Text, nullable=True)

    # Outcome tracking (user can report)
    user_outcome = Column(String(20), nullable=True)       # WIN / LOSS / SKIP
    user_outcome_pnl = Column(Float, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    user = relationship("User", back_populates="validations")

    def __repr__(self):
        return f"<Validation {self.ticker} {self.signal} verdict={self.verdict}>"


class UserRule(Base):
    __tablename__ = "user_rules"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    rule_text = Column(Text, nullable=False)        # e.g. "No AMD before 10am EST"
    is_active = Column(Boolean, default=True)
    ragflow_doc_id = Column(String(128), nullable=True)  # ID in RAGFlow dataset

    created_at = Column(DateTime, server_default=func.now())

    user = relationship("User", back_populates="rules")

    def __repr__(self):
        return f"<UserRule '{self.rule_text[:40]}...'>"


class EALog(Base):
    __tablename__ = "ea_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    ea_name = Column(String(128), nullable=True)
    ticker = Column(String(20), nullable=False)
    action = Column(String(10), nullable=False)      # BUY / SELL
    result = Column(String(10), nullable=True)       # WIN / LOSS / OPEN
    pnl = Column(Float, nullable=True)
    trade_time = Column(DateTime, nullable=True)

    raw_payload = Column(JSON, nullable=True)
    analysis_id = Column(Integer, ForeignKey("validations.id"), nullable=True)

    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self):
        return f"<EALog {self.ea_name} {self.ticker} {self.result}>"
