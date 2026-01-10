"""
Agent Orchestrator
==================
Coordinates the execution of all agents in the financial assurance pipeline.
Manages agent sequencing, data flow, and pipeline state.
"""
from datetime import datetime
from typing import Any, Optional
import uuid
import structlog

from app.agents.base import BaseAgent
from app.agents.ingestion import IngestionAgent
from app.agents.validation import ValidationAgent
from app.agents.variance import VarianceReasoningAgent
from app.agents.decision import DecisionAgent
from app.agents.learning import LearningAgent
from app.models import (
    AgentType, AgentMessage, AuditEvent, Entity, Period, 
    PipelineRun, TrialBalance
)
from app.config import get_settings


class AgentOrchestrator:
    """
    Orchestrates the autonomous agent pipeline.
    
    Pipeline flow:
    1. Ingestion Agent: Load and parse trial balance data
    2. Validation Agent: Run validation checks
    3. Variance Agent: Analyze period-over-period changes
    4. Decision Agent: Make approval/escalation decisions
    5. Learning Agent: Process feedback and improve over time
    
    The orchestrator:
    - Manages agent lifecycle
    - Routes data between agents
    - Tracks pipeline state
    - Aggregates audit logs
    - Handles errors and retries
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.logger = structlog.get_logger().bind(component="orchestrator")
        
        # Initialize agents
        self.ingestion_agent = IngestionAgent()
        self.validation_agent = ValidationAgent()
        self.variance_agent = VarianceReasoningAgent()
        self.decision_agent = DecisionAgent()
        self.learning_agent = LearningAgent()
        
        # Pipeline state
        self.current_run: Optional[PipelineRun] = None
        self.audit_log: list[AuditEvent] = []
        self.message_queue: list[AgentMessage] = []
    
    async def run_pipeline(
        self,
        entity: Entity,
        period: Period,
        file_path: Optional[str] = None,
        dataframe: Optional[Any] = None,
        prior_period: Optional[Period] = None,
        prior_balances: Optional[list] = None,
        historical_balances: Optional[list] = None,
        account_mapping: Optional[dict] = None
    ) -> dict[str, Any]:
        """
        Run the full assurance pipeline.
        
        Args:
            entity: The legal entity being processed
            period: The current reporting period
            file_path: Path to trial balance file (optional if dataframe provided)
            dataframe: Pre-loaded DataFrame (optional if file_path provided)
            prior_period: Prior period for variance comparison
            prior_balances: Balances from prior period
            historical_balances: Historical balances for trend analysis
            account_mapping: Optional account code mapping
            
        Returns:
            Complete pipeline results including all agent outputs
        """
        run_id = str(uuid.uuid4())
        
        self.current_run = PipelineRun(
            id=run_id,
            entity_id=entity.id,
            period_id=period.id,
            status="running",
            started_at=datetime.utcnow()
        )
        
        self.logger.info(
            "pipeline_started",
            run_id=run_id,
            entity=entity.code,
            period=period.name
        )
        
        self._log_audit_event(
            event_type="pipeline_started",
            payload={
                "run_id": run_id,
                "entity_code": entity.code,
                "period_name": period.name
            },
            entity_id=entity.id,
            period_id=period.id
        )
        
        results = {
            "run_id": run_id,
            "entity": entity.model_dump(),
            "period": period.model_dump(),
            "agents": {},
            "summary": {},
            "audit_log": []
        }
        
        try:
            # ================================================================
            # Step 1: Ingestion
            # ================================================================
            self.logger.info("running_ingestion_agent")
            ingestion_result = await self.ingestion_agent.run({
                "file_path": file_path,
                "dataframe": dataframe,
                "entity": entity,
                "period": period,
                "account_mapping": account_mapping or {}
            })
            
            results["agents"]["ingestion"] = ingestion_result
            self._record_agent_run("ingestion", ingestion_result)
            
            if not ingestion_result.get("success"):
                raise Exception(f"Ingestion failed: {ingestion_result.get('error')}")
            
            # Extract data for next agents
            trial_balance = ingestion_result["result"]["trial_balance"]
            accounts = {a["id"]: a for a in ingestion_result["result"]["accounts"]}
            balances = [
                self._dict_to_balance(b) 
                for b in trial_balance["balances"]
            ]
            
            # ================================================================
            # Step 2: Validation
            # ================================================================
            self.logger.info("running_validation_agent")
            validation_result = await self.validation_agent.run({
                "trial_balance": trial_balance,
                "accounts": accounts,
                "entity_id": entity.id,
                "period_id": period.id
            })
            
            results["agents"]["validation"] = validation_result
            self._record_agent_run("validation", validation_result)
            
            validation_findings = validation_result["result"].get("findings", [])
            
            # ================================================================
            # Step 3: Variance Analysis
            # ================================================================
            variance_result = None
            if prior_balances:
                self.logger.info("running_variance_agent")
                variance_result = await self.variance_agent.run({
                    "current_balances": balances,
                    "prior_balances": prior_balances,
                    "historical_balances": historical_balances or [],
                    "accounts": accounts,
                    "entity_id": entity.id,
                    "current_period_id": period.id,
                    "prior_period_id": prior_period.id if prior_period else "unknown"
                })
                
                results["agents"]["variance"] = variance_result
                self._record_agent_run("variance", variance_result)
            else:
                self.logger.info("skipping_variance_agent", reason="no_prior_data")
                results["agents"]["variance"] = {
                    "skipped": True,
                    "reason": "No prior period data provided"
                }
            
            variance_analyses = []
            variance_findings = []
            if variance_result and variance_result.get("success"):
                variance_analyses = variance_result["result"].get("variance_analyses", [])
                variance_findings = variance_result["result"].get("findings", [])
            
            # ================================================================
            # Step 4: Decision Making
            # ================================================================
            self.logger.info("running_decision_agent")
            all_findings = validation_findings + variance_findings
            
            decision_result = await self.decision_agent.run({
                "balances": balances,
                "validation_results": validation_result["result"].get("validation_results", []),
                "variance_analyses": variance_analyses,
                "findings": all_findings,
                "accounts": accounts,
                "entity_id": entity.id,
                "period_id": period.id
            })
            
            results["agents"]["decision"] = decision_result
            self._record_agent_run("decision", decision_result)
            
            # ================================================================
            # Step 5: Record decisions for learning
            # ================================================================
            if decision_result.get("success"):
                decisions = decision_result["result"].get("decisions", [])
                await self.learning_agent.run({
                    "decisions": decisions,
                    "analyze": False
                })
            
            # ================================================================
            # Compile Summary
            # ================================================================
            results["summary"] = self._compile_summary(results)
            results["audit_log"] = [e.model_dump() for e in self.audit_log]
            
            # Mark pipeline complete
            self.current_run.status = "completed"
            self.current_run.completed_at = datetime.utcnow()
            self.current_run.summary = results["summary"]
            
            self._log_audit_event(
                event_type="pipeline_completed",
                payload=results["summary"],
                entity_id=entity.id,
                period_id=period.id
            )
            
            self.logger.info(
                "pipeline_completed",
                run_id=run_id,
                auto_approve_rate=results["summary"].get("auto_approve_rate")
            )
            
        except Exception as e:
            self.current_run.status = "failed"
            self.current_run.completed_at = datetime.utcnow()
            
            self._log_audit_event(
                event_type="pipeline_failed",
                payload={"error": str(e)},
                entity_id=entity.id,
                period_id=period.id
            )
            
            self.logger.error("pipeline_failed", run_id=run_id, error=str(e))
            
            results["error"] = str(e)
            results["status"] = "failed"
        
        results["pipeline_run"] = self.current_run.model_dump()
        return results
    
    async def process_feedback(self, feedback: dict) -> dict:
        """Process human feedback through the learning agent."""
        result = await self.learning_agent.run({
            "feedback": feedback,
            "analyze": True
        })
        
        self._log_audit_event(
            event_type="feedback_processed",
            payload={
                "feedback_id": feedback.get("id"),
                "feedback_type": feedback.get("feedback_type")
            }
        )
        
        return result
    
    async def get_learning_insights(self) -> dict:
        """Get current learning insights and suggestions."""
        result = await self.learning_agent.run({
            "analyze": True,
            "time_window_days": 30
        })
        return result
    
    def _dict_to_balance(self, d: dict):
        """Convert dict to Balance-like object for agent processing."""
        from app.models import Balance
        from decimal import Decimal
        
        return Balance(
            id=d.get("id", str(uuid.uuid4())),
            account_id=d.get("account_id"),
            period_id=d.get("period_id"),
            entity_id=d.get("entity_id"),
            debit_amount=Decimal(str(d.get("debit_amount", 0))),
            credit_amount=Decimal(str(d.get("credit_amount", 0))),
            net_amount=Decimal(str(d.get("net_amount", 0))),
            currency=d.get("currency", "USD")
        )
    
    def _record_agent_run(self, agent_name: str, result: dict):
        """Record an agent run in the pipeline."""
        if self.current_run:
            self.current_run.agent_runs.append({
                "agent": agent_name,
                "success": result.get("success"),
                "run_id": result.get("run_id"),
                "timestamp": result.get("timestamp")
            })
    
    def _compile_summary(self, results: dict) -> dict:
        """Compile overall pipeline summary."""
        summary = {
            "pipeline_status": "completed",
            "agents_run": len(results["agents"]),
        }
        
        # Ingestion summary
        if "ingestion" in results["agents"]:
            ing = results["agents"]["ingestion"]
            if ing.get("success") and "result" in ing:
                ing_summary = ing["result"].get("summary", {})
                summary["accounts_processed"] = ing_summary.get("total_accounts", 0)
                summary["is_balanced"] = ing_summary.get("is_balanced", False)
        
        # Validation summary
        if "validation" in results["agents"]:
            val = results["agents"]["validation"]
            if val.get("success") and "result" in val:
                val_summary = val["result"].get("summary", {})
                summary["validation_score"] = val_summary.get("overall_score", 0)
                summary["validation_findings"] = val_summary.get("findings_count", 0)
        
        # Variance summary
        if "variance" in results["agents"]:
            var = results["agents"]["variance"]
            if not var.get("skipped") and var.get("success") and "result" in var:
                var_summary = var["result"].get("summary", {})
                summary["anomalies_detected"] = var_summary.get("anomalies_detected", 0)
                summary["anomaly_rate"] = var_summary.get("anomaly_rate", 0)
        
        # Decision summary
        if "decision" in results["agents"]:
            dec = results["agents"]["decision"]
            if dec.get("success") and "result" in dec:
                dec_summary = dec["result"].get("summary", {})
                summary["total_decisions"] = dec_summary.get("total_decisions", 0)
                summary["auto_approved"] = dec_summary.get("auto_approved", 0)
                summary["escalated"] = dec_summary.get("escalated", 0)
                summary["pending_review"] = dec_summary.get("pending_review", 0)
                summary["auto_approve_rate"] = dec_summary.get("auto_approve_rate", 0)
                summary["average_risk_score"] = dec_summary.get("average_risk_score", 0)
        
        return summary
    
    def _log_audit_event(
        self,
        event_type: str,
        payload: dict,
        entity_id: Optional[str] = None,
        period_id: Optional[str] = None
    ):
        """Log an audit event."""
        event = AuditEvent(
            event_type=event_type,
            agent_type=AgentType.ORCHESTRATOR,
            entity_id=entity_id,
            period_id=period_id,
            payload=payload,
            version_refs={"orchestrator_version": "1.0.0"}
        )
        self.audit_log.append(event)
    
    def get_agent_states(self) -> dict[str, dict]:
        """Get current state of all agents."""
        return {
            "ingestion": self.ingestion_agent.state.model_dump(),
            "validation": self.validation_agent.state.model_dump(),
            "variance": self.variance_agent.state.model_dump(),
            "decision": self.decision_agent.state.model_dump(),
            "learning": self.learning_agent.state.model_dump()
        }
    
    def get_audit_log(self) -> list[dict]:
        """Get combined audit log from orchestrator and all agents."""
        combined = [e.model_dump() for e in self.audit_log]
        
        for agent in [
            self.ingestion_agent,
            self.validation_agent,
            self.variance_agent,
            self.decision_agent,
            self.learning_agent
        ]:
            combined.extend([e.model_dump() for e in agent.get_audit_log()])
        
        # Sort by timestamp
        combined.sort(key=lambda x: x.get("timestamp", ""))
        
        return combined
