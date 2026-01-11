"""
Supervisor Agent
================
Monitors all agents, enforces policies, detects anomalies,
and can intervene when necessary.
"""
from datetime import datetime, timedelta
from typing import Any, Optional
from collections import defaultdict

from app.agents.agentic_base import AgenticBase, AgentCapability, Goal
from app.models import AgentType


class SupervisorAgent(AgenticBase):
    """
    The Supervisor Agent acts as a quality controller:
    - Monitors agent performance
    - Enforces policies and constraints
    - Detects anomalies in agent behavior
    - Can pause/intervene in agent operations
    - Escalates to humans when necessary
    """
    
    def __init__(self):
        super().__init__(
            agent_type=AgentType.LEARNING,  # Using LEARNING type for supervisor
            capabilities=[
                AgentCapability.REASONING,
                AgentCapability.REFLECTION,
                AgentCapability.COMMUNICATION,
                AgentCapability.MEMORY
            ]
        )
        self.agent_name = f"supervisor_{self.agent_id[:8]}"
        
        # Monitoring state
        self.agent_metrics: dict[str, dict] = defaultdict(lambda: {
            "runs": 0,
            "successes": 0,
            "failures": 0,
            "avg_duration": 0.0,
            "last_run": None,
            "alerts": []
        })
        
        # Policies
        self.policies = {
            "max_auto_approve_rate": 0.95,  # Max 95% auto-approval
            "min_escalation_rate": 0.02,    # At least 2% should be escalated
            "max_consecutive_failures": 3,   # Alert after 3 failures
            "require_evidence": True,        # All decisions need evidence
            "require_audit_trail": True      # All actions must be logged
        }
        
        # Intervention history
        self.interventions: list[dict] = []
        
        # Alerts
        self.active_alerts: list[dict] = []
        
        # Goals
        self.add_goal("Ensure all agents operate within policy", priority=0.95)
        self.add_goal("Detect and prevent systematic errors", priority=0.9)
        self.add_goal("Maintain audit compliance", priority=0.85)
    
    def validate_input(self, context: dict[str, Any]) -> bool:
        return True  # Supervisor can work with any context
    
    async def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        """
        Execute supervision tasks:
        1. Check agent health
        2. Analyze recent decisions
        3. Enforce policies
        4. Generate alerts if needed
        """
        
        # Get data to analyze
        decisions = context.get("decisions", [])
        agent_states = context.get("agent_states", {})
        pipeline_result = context.get("pipeline_result", {})
        
        # Analyze decisions
        decision_analysis = await self._analyze_decisions(decisions)
        
        # Check policies
        policy_violations = self._check_policies(decisions, pipeline_result)
        
        # Monitor agent health
        health_report = self._check_agent_health(agent_states)
        
        # Generate alerts
        alerts = []
        
        if policy_violations:
            alert = {
                "type": "policy_violation",
                "severity": "high",
                "details": policy_violations,
                "timestamp": datetime.utcnow().isoformat(),
                "recommendation": await self._get_recommendation(policy_violations)
            }
            alerts.append(alert)
            self.active_alerts.append(alert)
        
        if health_report.get("unhealthy_agents"):
            alert = {
                "type": "agent_health",
                "severity": "medium",
                "details": health_report["unhealthy_agents"],
                "timestamp": datetime.utcnow().isoformat()
            }
            alerts.append(alert)
            self.active_alerts.append(alert)
        
        # Check if intervention is needed
        should_intervene, intervention_reason = self._should_intervene(
            decision_analysis, policy_violations, health_report
        )
        
        if should_intervene:
            intervention = await self._intervene(intervention_reason, context)
            self.interventions.append(intervention)
        
        # Broadcast status to all agents
        self.broadcast_message(
            message_type="supervisor_status",
            content={
                "alerts_count": len(alerts),
                "policy_status": "OK" if not policy_violations else "VIOLATION",
                "intervention_active": should_intervene
            },
            priority=0.7
        )
        
        return {
            "decision_analysis": decision_analysis,
            "policy_violations": policy_violations,
            "health_report": health_report,
            "alerts": alerts,
            "intervention": self.interventions[-1] if should_intervene else None,
            "summary": {
                "agents_monitored": len(agent_states),
                "decisions_analyzed": len(decisions),
                "alerts_raised": len(alerts),
                "intervention_triggered": should_intervene
            }
        }
    
    async def _analyze_decisions(self, decisions: list) -> dict:
        """Use AI to analyze decision patterns."""
        if not decisions:
            return {"status": "no_decisions"}
        
        # Calculate metrics
        total = len(decisions)
        auto_approved = sum(1 for d in decisions if d.get("action") == "auto_approved")
        escalated = sum(1 for d in decisions if d.get("action") == "escalated")
        pending = sum(1 for d in decisions if d.get("action") == "pending_review")
        
        auto_rate = auto_approved / total if total > 0 else 0
        escalation_rate = escalated / total if total > 0 else 0
        
        # Get AI analysis
        prompt = f"""Analyze these financial decision metrics:

Total Decisions: {total}
Auto-Approved: {auto_approved} ({auto_rate:.1%})
Escalated: {escalated} ({escalation_rate:.1%})
Pending Review: {pending}

Average Risk Score: {sum(d.get('risk_score', 0) for d in decisions) / total if total else 0:.2f}

High-risk decisions (risk > 0.7): {sum(1 for d in decisions if d.get('risk_score', 0) > 0.7)}

Is this distribution healthy? Are there any concerns?
Provide a brief assessment (2-3 sentences).
"""
        
        ai_analysis = await self._call_llm(prompt, temperature=0.5)
        
        return {
            "total": total,
            "auto_approved": auto_approved,
            "escalated": escalated,
            "pending": pending,
            "auto_rate": auto_rate,
            "escalation_rate": escalation_rate,
            "ai_analysis": ai_analysis
        }
    
    def _check_policies(self, decisions: list, pipeline_result: dict) -> list[dict]:
        """Check if any policies are violated."""
        violations = []
        
        if not decisions:
            return violations
        
        total = len(decisions)
        auto_approved = sum(1 for d in decisions if d.get("action") == "auto_approved")
        escalated = sum(1 for d in decisions if d.get("action") == "escalated")
        
        auto_rate = auto_approved / total if total > 0 else 0
        escalation_rate = escalated / total if total > 0 else 0
        
        # Check auto-approve rate
        if auto_rate > self.policies["max_auto_approve_rate"]:
            violations.append({
                "policy": "max_auto_approve_rate",
                "limit": self.policies["max_auto_approve_rate"],
                "actual": auto_rate,
                "message": f"Auto-approval rate ({auto_rate:.1%}) exceeds maximum ({self.policies['max_auto_approve_rate']:.1%})"
            })
        
        # Check minimum escalation rate
        if escalation_rate < self.policies["min_escalation_rate"] and total >= 10:
            violations.append({
                "policy": "min_escalation_rate",
                "limit": self.policies["min_escalation_rate"],
                "actual": escalation_rate,
                "message": f"Escalation rate ({escalation_rate:.1%}) below minimum ({self.policies['min_escalation_rate']:.1%})"
            })
        
        # Check for missing evidence
        if self.policies["require_evidence"]:
            no_evidence = [d for d in decisions if not d.get("evidence_pack")]
            if no_evidence:
                violations.append({
                    "policy": "require_evidence",
                    "count": len(no_evidence),
                    "message": f"{len(no_evidence)} decisions missing evidence pack"
                })
        
        return violations
    
    def _check_agent_health(self, agent_states: dict) -> dict:
        """Check health of all agents."""
        unhealthy = []
        
        for agent_name, state in agent_states.items():
            issues = []
            
            # Check for too many pending messages
            if state.get("pending_messages", 0) > 20:
                issues.append("message_backlog")
            
            # Check for recent failures
            metrics = self.agent_metrics.get(agent_name, {})
            if metrics.get("failures", 0) > 0:
                failure_rate = metrics["failures"] / max(metrics["runs"], 1)
                if failure_rate > 0.3:
                    issues.append("high_failure_rate")
            
            if issues:
                unhealthy.append({
                    "agent": agent_name,
                    "issues": issues
                })
        
        return {
            "total_agents": len(agent_states),
            "healthy": len(agent_states) - len(unhealthy),
            "unhealthy_agents": unhealthy
        }
    
    def _should_intervene(self, decision_analysis: dict, violations: list, health: dict) -> tuple[bool, str]:
        """Determine if supervisor intervention is needed."""
        
        # High severity violations require intervention
        if violations and any(v.get("policy") == "max_auto_approve_rate" for v in violations):
            return True, "Auto-approval rate too high - potential rubber-stamping"
        
        # Too many unhealthy agents
        if len(health.get("unhealthy_agents", [])) >= 2:
            return True, "Multiple agents unhealthy"
        
        # Very low escalation (might be missing risks)
        if decision_analysis.get("escalation_rate", 1) < 0.01 and decision_analysis.get("total", 0) > 20:
            return True, "Suspiciously low escalation rate - may be missing risks"
        
        return False, ""
    
    async def _intervene(self, reason: str, context: dict) -> dict:
        """Take intervention action."""
        
        intervention = {
            "id": f"int_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            "reason": reason,
            "timestamp": datetime.utcnow().isoformat(),
            "action_taken": None,
            "resolution": None
        }
        
        # Determine intervention action
        prompt = f"""As a supervisor agent, I need to intervene.

REASON: {reason}

CONTEXT:
- Decisions made: {context.get('decisions', []).__len__()}
- Agents active: {list(context.get('agent_states', {}).keys())}

What action should I take?
Options:
1. PAUSE - Pause auto-approvals temporarily
2. ALERT - Send alert to human supervisors
3. ADJUST - Adjust agent thresholds
4. REVIEW - Flag recent decisions for review

Respond with: ACTION: [choice] | DETAILS: [specifics]
"""
        
        response = await self._call_llm(prompt, temperature=0.3)
        
        intervention["ai_recommendation"] = response
        
        # Parse and execute action
        if "PAUSE" in response.upper():
            intervention["action_taken"] = "pause_auto_approvals"
            self.broadcast_message(
                message_type="supervisor_command",
                content={"command": "pause_auto_approvals", "duration": 300},
                priority=1.0
            )
        elif "ALERT" in response.upper():
            intervention["action_taken"] = "human_alert"
            # In real system, would send email/notification
        elif "ADJUST" in response.upper():
            intervention["action_taken"] = "threshold_adjustment"
            self.broadcast_message(
                message_type="threshold_update",
                content={"escalation_threshold": 0.6},  # Lower threshold = more escalations
                priority=0.9
            )
        else:
            intervention["action_taken"] = "flag_for_review"
        
        self.log_action("intervention_executed", intervention)
        
        return intervention
    
    async def _get_recommendation(self, violations: list) -> str:
        """Get AI recommendation for policy violations."""
        prompt = f"""These policy violations were detected:

{violations}

Provide a brief recommendation (1-2 sentences) on how to address these issues.
"""
        return await self._call_llm(prompt, temperature=0.5)
    
    def record_agent_run(self, agent_name: str, success: bool, duration: float = 0):
        """Record an agent run for monitoring."""
        metrics = self.agent_metrics[agent_name]
        metrics["runs"] += 1
        if success:
            metrics["successes"] += 1
        else:
            metrics["failures"] += 1
        
        # Update average duration
        n = metrics["runs"]
        metrics["avg_duration"] = ((n - 1) * metrics["avg_duration"] + duration) / n
        metrics["last_run"] = datetime.utcnow().isoformat()
    
    def get_alerts(self, severity: str = None) -> list[dict]:
        """Get active alerts, optionally filtered by severity."""
        if severity:
            return [a for a in self.active_alerts if a.get("severity") == severity]
        return self.active_alerts.copy()
    
    def clear_alert(self, alert_id: str):
        """Clear a resolved alert."""
        self.active_alerts = [a for a in self.active_alerts if a.get("id") != alert_id]
