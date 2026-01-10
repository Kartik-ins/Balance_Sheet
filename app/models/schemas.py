"""
Core Data Models
================
Pydantic models for the financial assurance domain.
"""
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, Any
from pydantic import BaseModel, Field
import uuid


# ============================================================================
# Enums
# ============================================================================

class AccountType(str, Enum):
    """Financial account classification."""
    ASSET = "asset"
    LIABILITY = "liability"
    EQUITY = "equity"
    REVENUE = "revenue"
    EXPENSE = "expense"
    CONTRA = "contra"


class MaterialityBand(str, Enum):
    """Materiality classification for risk assessment."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    IMMATERIAL = "immaterial"


class ValidationStatus(str, Enum):
    """Status of a validation check."""
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    SKIPPED = "skipped"


class DecisionAction(str, Enum):
    """Decision outcome for a line item."""
    AUTO_APPROVED = "auto_approved"
    ESCALATED = "escalated"
    PENDING_REVIEW = "pending_review"
    REJECTED = "rejected"


class FeedbackType(str, Enum):
    """Type of human feedback on a decision."""
    APPROVED = "approved"
    REJECTED = "rejected"
    OVERRIDE_APPROVED = "override_approved"
    OVERRIDE_REJECTED = "override_rejected"
    COMMENT = "comment"


class FindingType(str, Enum):
    """Type of finding/anomaly detected."""
    ZERO_BALANCE_VIOLATION = "zero_balance_violation"
    VARIANCE_SPIKE = "variance_spike"
    VARIANCE_DROP = "variance_drop"
    MAPPING_INCONSISTENCY = "mapping_inconsistency"
    MISSING_DOCUMENTATION = "missing_documentation"
    SIGN_VIOLATION = "sign_violation"
    CLASSIFICATION_ERROR = "classification_error"
    UNUSUAL_PATTERN = "unusual_pattern"


class AgentType(str, Enum):
    """Types of autonomous agents in the system."""
    INGESTION = "ingestion"
    VALIDATION = "validation"
    VARIANCE = "variance"
    DECISION = "decision"
    LEARNING = "learning"
    ORCHESTRATOR = "orchestrator"


# ============================================================================
# Core Domain Models
# ============================================================================

class Account(BaseModel):
    """Chart of Accounts entry."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    code: str = Field(..., description="Account code (e.g., '1010')")
    name: str = Field(..., description="Account name")
    account_type: AccountType
    materiality_band: MaterialityBand = MaterialityBand.MEDIUM
    parent_code: Optional[str] = None
    mapping_key: Optional[str] = None  # For consolidation mapping
    expected_sign: Optional[str] = None  # "debit" or "credit"
    metadata: dict[str, Any] = Field(default_factory=dict)


class Period(BaseModel):
    """Reporting period definition."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(..., description="Period name (e.g., '2025-Q4')")
    start_date: datetime
    end_date: datetime
    entity_id: str
    is_closed: bool = False
    fx_rate_group: Optional[str] = None


class Entity(BaseModel):
    """Legal entity / reporting unit."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    code: str
    name: str
    currency: str = "USD"
    parent_entity_id: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Balance(BaseModel):
    """Trial balance line item."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    account_id: str
    period_id: str
    entity_id: str
    debit_amount: Decimal = Decimal("0")
    credit_amount: Decimal = Decimal("0")
    net_amount: Decimal = Decimal("0")
    currency: str = "USD"
    source_system: Optional[str] = None
    imported_at: datetime = Field(default_factory=datetime.utcnow)


class TrialBalance(BaseModel):
    """Complete trial balance for a period/entity."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    entity_id: str
    period_id: str
    balances: list[Balance] = Field(default_factory=list)
    total_debits: Decimal = Decimal("0")
    total_credits: Decimal = Decimal("0")
    is_balanced: bool = False
    imported_at: datetime = Field(default_factory=datetime.utcnow)
    source_file: Optional[str] = None


# ============================================================================
# Agent Output Models
# ============================================================================

class ValidationResult(BaseModel):
    """Result of a single validation check."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    check_name: str
    status: ValidationStatus
    message: str
    confidence: float = Field(ge=0.0, le=1.0)
    affected_accounts: list[str] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class Finding(BaseModel):
    """Anomaly or issue detected by agents."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    finding_type: FindingType
    account_id: str
    period_id: str
    entity_id: str
    severity: float = Field(ge=0.0, le=1.0, description="0=info, 1=critical")
    magnitude: Optional[float] = None  # Quantitative measure
    description: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    detected_by: AgentType
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class VarianceAnalysis(BaseModel):
    """Period-over-period variance analysis result."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    account_id: str
    current_period_id: str
    prior_period_id: str
    current_amount: Decimal
    prior_amount: Decimal
    absolute_variance: Decimal
    percent_variance: Optional[float] = None
    zscore: Optional[float] = None
    is_anomaly: bool = False
    trend_direction: str = "stable"  # "up", "down", "stable"
    seasonality_adjusted: bool = False
    explanation: Optional[str] = None
    evidence: dict[str, Any] = Field(default_factory=dict)


class RiskScore(BaseModel):
    """Composite risk assessment for a line item."""
    account_id: str
    period_id: str
    entity_id: str
    overall_risk: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    components: dict[str, float] = Field(default_factory=dict)
    # Component examples: validation_risk, variance_risk, materiality_risk, data_quality_risk


class Decision(BaseModel):
    """Agent decision on a line item."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    account_id: str
    period_id: str
    entity_id: str
    action: DecisionAction
    risk_score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    evidence_pack: dict[str, Any] = Field(default_factory=dict)
    policy_version: str = "v1.0"
    decided_by: AgentType = AgentType.DECISION
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    requires_human_review: bool = False


class Feedback(BaseModel):
    """Human feedback on an agent decision."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    decision_id: str
    user_id: str
    feedback_type: FeedbackType
    reason: Optional[str] = None
    corrected_action: Optional[DecisionAction] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ============================================================================
# Audit & Logging Models
# ============================================================================

class AuditEvent(BaseModel):
    """Immutable audit log entry."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str
    agent_type: Optional[AgentType] = None
    entity_id: Optional[str] = None
    period_id: Optional[str] = None
    account_id: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)
    version_refs: dict[str, str] = Field(default_factory=dict)  # model/rule versions
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class EvidencePack(BaseModel):
    """Structured evidence supporting a decision or finding."""
    current_balance: Optional[Decimal] = None
    prior_balance: Optional[Decimal] = None
    variance_amount: Optional[Decimal] = None
    variance_percent: Optional[float] = None
    historical_trend: list[Decimal] = Field(default_factory=list)
    validation_results: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    supporting_documents: list[str] = Field(default_factory=list)
    comparable_accounts: list[dict[str, Any]] = Field(default_factory=list)
    policy_thresholds: dict[str, float] = Field(default_factory=dict)


# ============================================================================
# Agent State & Message Models
# ============================================================================

class AgentState(BaseModel):
    """Current state of an agent."""
    agent_type: AgentType
    status: str = "idle"  # idle, running, completed, failed
    last_run: Optional[datetime] = None
    current_task_id: Optional[str] = None
    metrics: dict[str, Any] = Field(default_factory=dict)


class AgentMessage(BaseModel):
    """Message passed between agents."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    from_agent: AgentType
    to_agent: AgentType
    message_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    correlation_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class PipelineRun(BaseModel):
    """A complete pipeline execution record."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    entity_id: str
    period_id: str
    status: str = "pending"  # pending, running, completed, failed
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    agent_runs: list[dict[str, Any]] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
