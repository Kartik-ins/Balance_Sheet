"""
SQLAlchemy Database Models
==========================
Persistent storage for all financial assurance data.
"""
from datetime import datetime
from typing import Optional
import uuid
from sqlalchemy import (
    Column, String, Float, DateTime, JSON, Text, Boolean,
    ForeignKey, Integer, Enum as SQLEnum, Index
)
from sqlalchemy.orm import relationship, declarative_base
from enum import Enum

Base = declarative_base()


def generate_uuid() -> str:
    return str(uuid.uuid4())


# Enums
class AccountType(str, Enum):
    ASSET = "asset"
    LIABILITY = "liability"
    EQUITY = "equity"
    REVENUE = "revenue"
    EXPENSE = "expense"


class DecisionAction(str, Enum):
    AUTO_APPROVED = "auto_approved"
    ESCALATED = "escalated"
    PENDING_REVIEW = "pending_review"
    MANUALLY_APPROVED = "manually_approved"
    MANUALLY_REJECTED = "manually_rejected"


class PeriodStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


# Models
class EntityModel(Base):
    """Entity/Company being audited."""
    __tablename__ = "entities"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    code = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    currency = Column(String(3), default="USD")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    periods = relationship("PeriodModel", back_populates="entity", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Entity {self.code}: {self.name}>"


class PeriodModel(Base):
    """Reporting period (e.g., Q4 2025)."""
    __tablename__ = "periods"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    entity_id = Column(String(36), ForeignKey("entities.id"), nullable=False, index=True)
    name = Column(String(50), nullable=False)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    status = Column(String(20), default=PeriodStatus.PENDING.value)
    
    # Processing stats
    total_accounts = Column(Integer, default=0)
    auto_approved = Column(Integer, default=0)
    escalated = Column(Integer, default=0)
    pending_review = Column(Integer, default=0)
    
    # Scores
    validation_score = Column(Float, default=0.0)
    avg_risk_score = Column(Float, default=0.0)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    
    # Relationships
    entity = relationship("EntityModel", back_populates="periods")
    balances = relationship("BalanceModel", back_populates="period", cascade="all, delete-orphan")
    decisions = relationship("DecisionModel", back_populates="period", cascade="all, delete-orphan")
    findings = relationship("FindingModel", back_populates="period", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('ix_period_entity_name', 'entity_id', 'name'),
    )
    
    def __repr__(self):
        return f"<Period {self.name} ({self.status})>"


class BalanceModel(Base):
    """Trial balance line item."""
    __tablename__ = "balances"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    period_id = Column(String(36), ForeignKey("periods.id"), nullable=False, index=True)
    
    account_code = Column(String(50), nullable=False)
    account_name = Column(String(255), nullable=False)
    account_type = Column(String(20), nullable=False)
    
    debit = Column(Float, default=0.0)
    credit = Column(Float, default=0.0)
    net_balance = Column(Float, default=0.0)
    currency = Column(String(3), default="USD")
    
    # Variance data (from prior period)
    prior_balance = Column(Float, nullable=True)
    variance_amount = Column(Float, nullable=True)
    variance_percent = Column(Float, nullable=True)
    zscore = Column(Float, nullable=True)
    is_anomaly = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    period = relationship("PeriodModel", back_populates="balances")
    
    __table_args__ = (
        Index('ix_balance_period_account', 'period_id', 'account_code'),
    )
    
    def __repr__(self):
        return f"<Balance {self.account_code}: {self.net_balance}>"


class DecisionModel(Base):
    """Agent decision for an account."""
    __tablename__ = "decisions"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    period_id = Column(String(36), ForeignKey("periods.id"), nullable=False, index=True)
    account_code = Column(String(50), nullable=False)
    
    action = Column(String(30), nullable=False)
    risk_score = Column(Float, nullable=False)
    confidence_score = Column(Float, nullable=False)
    
    # Risk components
    validation_risk = Column(Float, default=0.0)
    variance_risk = Column(Float, default=0.0)
    materiality_risk = Column(Float, default=0.0)
    data_quality_risk = Column(Float, default=0.0)
    
    rationale = Column(Text, nullable=True)
    evidence = Column(JSON, nullable=True)
    
    # Review tracking
    reviewed_by = Column(String(100), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    review_action = Column(String(30), nullable=True)
    review_comment = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    period = relationship("PeriodModel", back_populates="decisions")
    feedback = relationship("FeedbackModel", back_populates="decision", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('ix_decision_period_action', 'period_id', 'action'),
    )
    
    def __repr__(self):
        return f"<Decision {self.account_code}: {self.action} (risk={self.risk_score:.2f})>"


class FindingModel(Base):
    """Validation finding/issue."""
    __tablename__ = "findings"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    period_id = Column(String(36), ForeignKey("periods.id"), nullable=False, index=True)
    account_code = Column(String(50), nullable=True)
    
    finding_type = Column(String(50), nullable=False)
    severity = Column(Float, nullable=False)
    description = Column(Text, nullable=False)
    evidence = Column(JSON, nullable=True)
    
    # Resolution
    is_resolved = Column(Boolean, default=False)
    resolved_by = Column(String(100), nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    resolution_note = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    period = relationship("PeriodModel", back_populates="findings")
    
    def __repr__(self):
        return f"<Finding {self.finding_type}: {self.description[:50]}>"


class FeedbackModel(Base):
    """Human feedback on decisions."""
    __tablename__ = "feedback"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    decision_id = Column(String(36), ForeignKey("decisions.id"), nullable=False, index=True)
    
    user_id = Column(String(100), nullable=False)
    feedback_type = Column(String(30), nullable=False)  # approved, rejected, modified
    reason = Column(Text, nullable=True)
    
    # For learning
    was_override = Column(Boolean, default=False)
    original_action = Column(String(30), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    decision = relationship("DecisionModel", back_populates="feedback")
    
    def __repr__(self):
        return f"<Feedback {self.feedback_type} by {self.user_id}>"


class AuditLogModel(Base):
    """Immutable audit trail."""
    __tablename__ = "audit_logs"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    
    event_type = Column(String(50), nullable=False, index=True)
    agent_name = Column(String(50), nullable=True)
    entity_id = Column(String(36), nullable=True, index=True)
    period_id = Column(String(36), nullable=True, index=True)
    account_code = Column(String(50), nullable=True)
    
    action = Column(String(100), nullable=True)
    details = Column(JSON, nullable=True)
    
    user_id = Column(String(100), nullable=True)
    ip_address = Column(String(50), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    __table_args__ = (
        Index('ix_audit_entity_period', 'entity_id', 'period_id'),
    )
    
    def __repr__(self):
        return f"<AuditLog {self.event_type} at {self.created_at}>"


class ThresholdHistoryModel(Base):
    """Learning agent threshold adjustments."""
    __tablename__ = "threshold_history"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    
    parameter = Column(String(100), nullable=False)
    old_value = Column(Float, nullable=False)
    new_value = Column(Float, nullable=False)
    reason = Column(Text, nullable=True)
    confidence = Column(Float, default=0.0)
    
    # Context
    feedback_count = Column(Integer, default=0)
    override_rate = Column(Float, default=0.0)
    
    applied = Column(Boolean, default=False)
    applied_at = Column(DateTime, nullable=True)
    applied_by = Column(String(100), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<ThresholdHistory {self.parameter}: {self.old_value} -> {self.new_value}>"
