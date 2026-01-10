"""
Learning Agent
==============
Observes human overrides and feedback to continuously refine
validation rules, thresholds, and decision logic.
"""
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from collections import defaultdict
import numpy as np

from app.agents.base import BaseAgent
from app.models import (
    AgentType, Decision, DecisionAction, Feedback, FeedbackType
)
from app.config import get_settings


class LearningAgent(BaseAgent):
    """
    Autonomous agent for learning from human feedback.
    
    Responsibilities:
    - Collect and analyze human override patterns
    - Identify systematic errors in agent decisions
    - Suggest threshold adjustments
    - Track decision accuracy over time
    - Generate improvement recommendations
    """
    
    def __init__(self):
        super().__init__(AgentType.LEARNING)
        self.settings = get_settings()
        
        # In-memory storage for learning data (would be persisted in production)
        self.feedback_history: list[dict] = []
        self.decision_outcomes: dict[str, list[dict]] = defaultdict(list)
        self.threshold_suggestions: dict[str, float] = {}
    
    def validate_input(self, context: dict[str, Any]) -> bool:
        """Validate that required inputs are present."""
        # Can work with feedback, decisions, or both
        return "feedback" in context or "decisions" in context or "analyze" in context
    
    async def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        """
        Execute learning operations.
        
        Context can contain:
        - feedback: New Feedback object to process
        - decisions: List of Decision objects to analyze
        - analyze: If True, run full analysis on historical data
        - time_window_days: Days to consider for analysis (default 30)
        """
        results = {}
        
        # Process new feedback
        if "feedback" in context:
            feedback_result = await self._process_feedback(context["feedback"])
            results["feedback_processed"] = feedback_result
        
        # Record decisions for tracking
        if "decisions" in context:
            await self._record_decisions(context["decisions"])
            results["decisions_recorded"] = len(context["decisions"])
        
        # Run analysis if requested
        if context.get("analyze", False):
            analysis = await self._analyze_patterns(
                time_window_days=context.get("time_window_days", 30)
            )
            results["analysis"] = analysis
        
        # Generate improvement suggestions
        suggestions = await self._generate_suggestions()
        results["suggestions"] = suggestions
        
        # Calculate learning metrics
        metrics = self._calculate_metrics()
        results["metrics"] = metrics
        
        # Log audit event
        self.log_audit_event(
            event_type="learning_completed",
            payload={
                "feedback_count": len(self.feedback_history),
                "suggestions_generated": len(suggestions),
                "metrics": metrics
            }
        )
        
        return results
    
    async def _process_feedback(self, feedback: dict | Feedback) -> dict:
        """Process a single piece of feedback."""
        
        if isinstance(feedback, Feedback):
            feedback_dict = feedback.model_dump()
        else:
            feedback_dict = feedback
        
        # Store feedback
        self.feedback_history.append({
            **feedback_dict,
            "processed_at": datetime.utcnow().isoformat()
        })
        
        # Analyze the feedback
        feedback_type = feedback_dict.get("feedback_type")
        decision_id = feedback_dict.get("decision_id")
        
        is_override = feedback_type in (
            FeedbackType.OVERRIDE_APPROVED.value if isinstance(feedback_type, str) else None,
            FeedbackType.OVERRIDE_REJECTED.value if isinstance(feedback_type, str) else None,
            "override_approved",
            "override_rejected"
        )
        
        result = {
            "feedback_id": feedback_dict.get("id"),
            "decision_id": decision_id,
            "is_override": is_override,
            "feedback_type": feedback_type
        }
        
        if is_override:
            # Track override patterns
            self.log_audit_event(
                event_type="override_detected",
                payload={
                    "decision_id": decision_id,
                    "original_action": feedback_dict.get("corrected_action"),
                    "reason": feedback_dict.get("reason")
                }
            )
        
        return result
    
    async def _record_decisions(self, decisions: list[dict | Decision]):
        """Record decisions for outcome tracking."""
        for decision in decisions:
            if isinstance(decision, Decision):
                decision_dict = decision.model_dump()
            else:
                decision_dict = decision
            
            account_id = decision_dict.get("account_id")
            self.decision_outcomes[account_id].append({
                **decision_dict,
                "recorded_at": datetime.utcnow().isoformat()
            })
    
    async def _analyze_patterns(self, time_window_days: int = 30) -> dict:
        """Analyze feedback patterns to identify systematic issues."""
        
        if not self.feedback_history:
            return {
                "status": "insufficient_data",
                "message": "No feedback data available for analysis"
            }
        
        # Analyze override patterns
        overrides = [
            f for f in self.feedback_history
            if f.get("feedback_type") in ("override_approved", "override_rejected")
        ]
        
        override_rate = len(overrides) / len(self.feedback_history) if self.feedback_history else 0
        
        # Analyze by decision type
        override_by_original_action = defaultdict(int)
        for override in overrides:
            original = override.get("corrected_action", "unknown")
            override_by_original_action[original] += 1
        
        # Identify accounts with repeated overrides
        override_by_account = defaultdict(int)
        for feedback in self.feedback_history:
            if feedback.get("feedback_type") in ("override_approved", "override_rejected"):
                # Would need to look up account from decision
                pass
        
        # Analyze agreement rate
        agreements = [
            f for f in self.feedback_history
            if f.get("feedback_type") in ("approved", "rejected")
        ]
        agreement_rate = len(agreements) / len(self.feedback_history) if self.feedback_history else 0
        
        return {
            "status": "completed",
            "time_window_days": time_window_days,
            "total_feedback": len(self.feedback_history),
            "override_count": len(overrides),
            "override_rate": override_rate,
            "agreement_rate": agreement_rate,
            "override_by_action": dict(override_by_original_action),
            "patterns_detected": self._detect_patterns(overrides)
        }
    
    def _detect_patterns(self, overrides: list[dict]) -> list[dict]:
        """Detect patterns in override behavior."""
        patterns = []
        
        if not overrides:
            return patterns
        
        # Pattern: Too many false escalations
        escalation_overrides = [
            o for o in overrides 
            if o.get("corrected_action") == "escalated" and 
               o.get("feedback_type") == "override_approved"
        ]
        if len(escalation_overrides) > len(overrides) * 0.3:
            patterns.append({
                "pattern": "excessive_escalation",
                "description": "System is escalating items that humans approve without changes",
                "frequency": len(escalation_overrides) / len(overrides),
                "recommendation": "Consider lowering escalation_risk_threshold"
            })
        
        # Pattern: Too many false auto-approvals
        approval_overrides = [
            o for o in overrides
            if o.get("corrected_action") == "auto_approved" and
               o.get("feedback_type") == "override_rejected"
        ]
        if len(approval_overrides) > len(overrides) * 0.1:
            patterns.append({
                "pattern": "risky_auto_approval",
                "description": "System is auto-approving items that humans reject",
                "frequency": len(approval_overrides) / len(overrides),
                "recommendation": "Consider raising auto_approve_confidence_threshold"
            })
        
        return patterns
    
    async def _generate_suggestions(self) -> list[dict]:
        """Generate threshold adjustment suggestions based on learning."""
        suggestions = []
        
        if len(self.feedback_history) < 10:
            return [{
                "type": "insufficient_data",
                "message": "Need at least 10 feedback items to generate suggestions",
                "current_count": len(self.feedback_history)
            }]
        
        # Analyze override patterns
        analysis = await self._analyze_patterns()
        patterns = analysis.get("patterns_detected", [])
        
        for pattern in patterns:
            if pattern["pattern"] == "excessive_escalation":
                current = self.settings.escalation_risk_threshold
                suggested = min(0.9, current + 0.05)
                suggestions.append({
                    "type": "threshold_adjustment",
                    "parameter": "escalation_risk_threshold",
                    "current_value": current,
                    "suggested_value": suggested,
                    "reason": pattern["description"],
                    "confidence": 0.7
                })
                self.threshold_suggestions["escalation_risk_threshold"] = suggested
            
            elif pattern["pattern"] == "risky_auto_approval":
                current = self.settings.auto_approve_confidence_threshold
                suggested = min(0.95, current + 0.03)
                suggestions.append({
                    "type": "threshold_adjustment",
                    "parameter": "auto_approve_confidence_threshold",
                    "current_value": current,
                    "suggested_value": suggested,
                    "reason": pattern["description"],
                    "confidence": 0.8
                })
                self.threshold_suggestions["auto_approve_confidence_threshold"] = suggested
        
        # Suggest variance threshold adjustments if many variance-related overrides
        variance_overrides = [
            f for f in self.feedback_history
            if "variance" in str(f.get("reason", "")).lower()
        ]
        if len(variance_overrides) > len(self.feedback_history) * 0.2:
            suggestions.append({
                "type": "threshold_adjustment",
                "parameter": "variance_zscore_threshold",
                "current_value": self.settings.variance_zscore_threshold,
                "suggested_value": self.settings.variance_zscore_threshold * 1.1,
                "reason": "Many overrides related to variance detection",
                "confidence": 0.6
            })
        
        return suggestions
    
    def _calculate_metrics(self) -> dict:
        """Calculate learning and accuracy metrics."""
        
        total_feedback = len(self.feedback_history)
        
        if total_feedback == 0:
            return {
                "total_feedback": 0,
                "override_rate": 0,
                "agreement_rate": 0,
                "accuracy_estimate": None
            }
        
        overrides = sum(
            1 for f in self.feedback_history
            if f.get("feedback_type") in ("override_approved", "override_rejected")
        )
        
        agreements = sum(
            1 for f in self.feedback_history
            if f.get("feedback_type") in ("approved", "rejected")
        )
        
        override_rate = overrides / total_feedback
        agreement_rate = agreements / total_feedback
        
        # Accuracy = 1 - override_rate (simplified)
        accuracy_estimate = 1 - override_rate
        
        return {
            "total_feedback": total_feedback,
            "override_count": overrides,
            "agreement_count": agreements,
            "override_rate": override_rate,
            "agreement_rate": agreement_rate,
            "accuracy_estimate": accuracy_estimate,
            "suggested_thresholds": self.threshold_suggestions
        }
    
    def get_adjusted_thresholds(self) -> dict[str, float]:
        """Get current suggested threshold adjustments."""
        return self.threshold_suggestions.copy()
    
    def reset_learning(self):
        """Reset learning data (for testing or new deployment)."""
        self.feedback_history.clear()
        self.decision_outcomes.clear()
        self.threshold_suggestions.clear()
        
        self.log_audit_event(
            event_type="learning_reset",
            payload={"reason": "manual_reset"}
        )
