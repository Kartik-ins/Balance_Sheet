"""
Audit Service
=============
Manages immutable audit logging and evidence tracking for the assurance platform.
Now with database persistence.
"""
from datetime import datetime
from typing import Any, Optional
import json
from pathlib import Path
import structlog

from app.models import AuditEvent, AgentType
from app.models.database import AuditLogModel, DecisionModel, FeedbackModel
from app.services.db import get_db


class AuditService:
    """
    Service for managing audit logs and evidence.
    
    Features:
    - Immutable event logging (persisted to database)
    - Evidence pack management
    - Query and retrieval
    - Export capabilities
    """
    
    def __init__(self, storage_path: Optional[str] = None):
        self.logger = structlog.get_logger().bind(service="audit")
        self.storage_path = Path(storage_path) if storage_path else Path("./data/audit")
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # In-memory cache for fast queries (backed by DB)
        self._events: list[AuditEvent] = []
        self._evidence_store: dict[str, dict] = {}
        
        # Load recent events from database
        self._load_from_db()
    
    def _load_from_db(self):
        """Load recent events from database into memory cache."""
        try:
            with get_db() as db:
                recent_logs = db.query(AuditLogModel).order_by(
                    AuditLogModel.created_at.desc()
                ).limit(1000).all()
                
                for log in reversed(recent_logs):
                    event = AuditEvent(
                        id=log.id,
                        event_type=log.event_type,
                        agent_type=AgentType(log.agent_name) if log.agent_name else None,
                        entity_id=log.entity_id,
                        period_id=log.period_id,
                        account_id=log.account_code,
                        payload=log.details or {},
                        timestamp=log.created_at
                    )
                    self._events.append(event)
                
                self.logger.info("audit_events_loaded", count=len(recent_logs))
        except Exception as e:
            self.logger.warning("failed_to_load_audit_events", error=str(e))
    
    def log_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        agent_type: Optional[AgentType] = None,
        entity_id: Optional[str] = None,
        period_id: Optional[str] = None,
        account_id: Optional[str] = None,
        version_refs: Optional[dict[str, str]] = None,
        user_id: Optional[str] = None
    ) -> AuditEvent:
        """Log an immutable audit event to database."""
        event = AuditEvent(
            event_type=event_type,
            agent_type=agent_type,
            entity_id=entity_id,
            period_id=period_id,
            account_id=account_id,
            payload=payload,
            version_refs=version_refs or {},
            timestamp=datetime.utcnow()
        )
        
        # Persist to database
        try:
            with get_db() as db:
                db_log = AuditLogModel(
                    id=event.id,
                    event_type=event_type,
                    agent_name=agent_type.value if agent_type else None,
                    entity_id=entity_id,
                    period_id=period_id,
                    account_code=account_id,
                    action=payload.get("action"),
                    details=payload,
                    user_id=user_id,
                    created_at=event.timestamp
                )
                db.add(db_log)
        except Exception as e:
            self.logger.error("failed_to_persist_audit", error=str(e))
        
        # Add to in-memory cache
        self._events.append(event)
        
        # Also persist to file for backup
        self._persist_event(event)
        
        self.logger.info(
            "audit_event_logged",
            event_id=event.id,
            event_type=event_type
        )
        
        return event
    
    def store_evidence(
        self,
        evidence_id: str,
        evidence_data: dict[str, Any],
        decision_id: Optional[str] = None,
        account_id: Optional[str] = None
    ) -> str:
        """Store evidence pack for a decision or finding."""
        evidence_record = {
            "id": evidence_id,
            "data": evidence_data,
            "decision_id": decision_id,
            "account_id": account_id,
            "stored_at": datetime.utcnow().isoformat()
        }
        
        self._evidence_store[evidence_id] = evidence_record
        self._persist_evidence(evidence_id, evidence_record)
        
        return evidence_id
    
    def get_evidence(self, evidence_id: str) -> Optional[dict]:
        """Retrieve stored evidence by ID."""
        return self._evidence_store.get(evidence_id)
    
    def query_events(
        self,
        event_type: Optional[str] = None,
        agent_type: Optional[AgentType] = None,
        entity_id: Optional[str] = None,
        period_id: Optional[str] = None,
        account_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> list[AuditEvent]:
        """Query audit events with filters."""
        results = []
        
        for event in reversed(self._events):  # Most recent first
            if len(results) >= limit:
                break
            
            if event_type and event.event_type != event_type:
                continue
            if agent_type and event.agent_type != agent_type:
                continue
            if entity_id and event.entity_id != entity_id:
                continue
            if period_id and event.period_id != period_id:
                continue
            if account_id and event.account_id != account_id:
                continue
            if start_time and event.timestamp < start_time:
                continue
            if end_time and event.timestamp > end_time:
                continue
            
            results.append(event)
        
        return results
    
    def get_decision_trail(
        self,
        account_id: str,
        period_id: str
    ) -> list[dict]:
        """Get complete audit trail for a specific decision."""
        events = self.query_events(
            account_id=account_id,
            period_id=period_id,
            limit=1000
        )
        
        trail = []
        for event in events:
            trail.append({
                "timestamp": event.timestamp.isoformat(),
                "event_type": event.event_type,
                "agent": event.agent_type.value if event.agent_type else None,
                "payload": event.payload,
                "versions": event.version_refs
            })
        
        # Sort chronologically
        trail.sort(key=lambda x: x["timestamp"])
        
        return trail
    
    def export_audit_log(
        self,
        entity_id: Optional[str] = None,
        period_id: Optional[str] = None,
        format: str = "json"
    ) -> str:
        """Export audit log to file."""
        events = self.query_events(
            entity_id=entity_id,
            period_id=period_id,
            limit=10000
        )
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"audit_export_{timestamp}.{format}"
        filepath = self.storage_path / filename
        
        if format == "json":
            with open(filepath, "w") as f:
                json.dump(
                    [e.model_dump() for e in events],
                    f,
                    indent=2,
                    default=str
                )
        
        self.logger.info("audit_exported", filepath=str(filepath), events=len(events))
        
        return str(filepath)
    
    def _persist_event(self, event: AuditEvent):
        """Persist event to storage."""
        date_str = event.timestamp.strftime("%Y-%m-%d")
        log_file = self.storage_path / f"events_{date_str}.jsonl"
        
        with open(log_file, "a") as f:
            f.write(json.dumps(event.model_dump(), default=str) + "\n")
    
    def _persist_evidence(self, evidence_id: str, evidence: dict):
        """Persist evidence to storage."""
        evidence_dir = self.storage_path / "evidence"
        evidence_dir.mkdir(exist_ok=True)
        
        evidence_file = evidence_dir / f"{evidence_id}.json"
        with open(evidence_file, "w") as f:
            json.dump(evidence, f, indent=2, default=str)
    
    def get_statistics(self) -> dict:
        """Get audit statistics."""
        event_counts = {}
        agent_counts = {}
        
        for event in self._events:
            event_counts[event.event_type] = event_counts.get(event.event_type, 0) + 1
            if event.agent_type:
                agent_counts[event.agent_type.value] = agent_counts.get(event.agent_type.value, 0) + 1
        
        return {
            "total_events": len(self._events),
            "evidence_packs": len(self._evidence_store),
            "events_by_type": event_counts,
            "events_by_agent": agent_counts
        }


# Global audit service instance
_audit_service: Optional[AuditService] = None


def get_audit_service() -> AuditService:
    """Get global audit service instance."""
    global _audit_service
    if _audit_service is None:
        _audit_service = AuditService()
    return _audit_service
