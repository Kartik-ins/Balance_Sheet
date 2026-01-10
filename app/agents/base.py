"""
Base Agent Interface
====================
Abstract base class for all autonomous agents in the system.
"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Optional
import structlog
import uuid

from app.models import AgentType, AgentState, AuditEvent


class BaseAgent(ABC):
    """
    Abstract base class for autonomous agents.
    
    Each agent:
    - Has a unique type identifier
    - Maintains internal state
    - Produces structured outputs
    - Logs all actions for auditability
    - Can communicate with other agents via messages
    """
    
    def __init__(self, agent_type: AgentType):
        self.agent_type = agent_type
        self.agent_id = str(uuid.uuid4())
        self.logger = structlog.get_logger().bind(
            agent_type=agent_type.value,
            agent_id=self.agent_id
        )
        self.state = AgentState(
            agent_type=agent_type,
            status="idle"
        )
        self._audit_log: list[AuditEvent] = []
    
    @abstractmethod
    async def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        """
        Execute the agent's primary task.
        
        Args:
            context: Input data and configuration for the agent.
            
        Returns:
            Structured output containing results and metadata.
        """
        pass
    
    @abstractmethod
    def validate_input(self, context: dict[str, Any]) -> bool:
        """Validate that the input context is sufficient for execution."""
        pass
    
    def log_audit_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        entity_id: Optional[str] = None,
        period_id: Optional[str] = None,
        account_id: Optional[str] = None,
    ) -> AuditEvent:
        """Log an immutable audit event."""
        event = AuditEvent(
            event_type=event_type,
            agent_type=self.agent_type,
            entity_id=entity_id,
            period_id=period_id,
            account_id=account_id,
            payload=payload,
            version_refs={"agent_version": "1.0.0"},
            timestamp=datetime.utcnow()
        )
        self._audit_log.append(event)
        self.logger.info(
            "audit_event",
            event_type=event_type,
            event_id=event.id
        )
        return event
    
    def get_audit_log(self) -> list[AuditEvent]:
        """Return the agent's audit log."""
        return self._audit_log.copy()
    
    def update_state(self, status: str, metrics: Optional[dict[str, Any]] = None):
        """Update agent state."""
        self.state.status = status
        self.state.last_run = datetime.utcnow()
        if metrics:
            self.state.metrics.update(metrics)
    
    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """
        Run the agent with full lifecycle management.
        
        This is the main entry point that handles:
        - Input validation
        - State management
        - Execution
        - Error handling
        - Audit logging
        """
        run_id = str(uuid.uuid4())
        self.state.current_task_id = run_id
        
        self.log_audit_event(
            event_type="agent_started",
            payload={"run_id": run_id, "context_keys": list(context.keys())}
        )
        
        try:
            # Validate input
            self.update_state("validating")
            if not self.validate_input(context):
                raise ValueError(f"Invalid input for {self.agent_type.value} agent")
            
            # Execute
            self.update_state("running")
            self.logger.info("executing", run_id=run_id)
            
            result = await self.execute(context)
            
            # Complete
            self.update_state("completed", metrics={
                "last_run_id": run_id,
                "last_run_success": True
            })
            
            self.log_audit_event(
                event_type="agent_completed",
                payload={"run_id": run_id, "result_keys": list(result.keys())}
            )
            
            return {
                "success": True,
                "run_id": run_id,
                "agent_type": self.agent_type.value,
                "result": result,
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            self.update_state("failed", metrics={
                "last_run_id": run_id,
                "last_run_success": False,
                "last_error": str(e)
            })
            
            self.log_audit_event(
                event_type="agent_failed",
                payload={"run_id": run_id, "error": str(e)}
            )
            
            self.logger.error("execution_failed", run_id=run_id, error=str(e))
            
            return {
                "success": False,
                "run_id": run_id,
                "agent_type": self.agent_type.value,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
