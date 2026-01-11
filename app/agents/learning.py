"""
Learning Agent (Agentic AI)
===========================
Observes human overrides and feedback to continuously refine
validation rules, thresholds, and decision logic.

AGENTIC FEATURES:
- AI-powered pattern analysis
- Self-improving threshold recommendations
- Broadcasts learning insights to other agents
- Maintains long-term memory of patterns
"""
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Optional
from collections import defaultdict
import numpy as np

from app.agents.agentic_base import AgenticBase, AgentCapability
from app.models import (
    AgentType, Decision, DecisionAction, Feedback, FeedbackType
)
from app.config import get_settings


class LearningAgent(AgenticBase):
    """
    AGENTIC Learning Agent.
    
    Agentic Capabilities:
    - Uses LLM to analyze feedback patterns
    - Generates AI-powered improvement suggestions
    - Broadcasts insights to other agents
    - Self-reflects on learning effectiveness
    
    Responsibilities:
    - Collect and analyze human override patterns
    - Identify systematic errors in agent decisions
    - Suggest threshold adjustments
    - Track decision accuracy over time
    - Generate improvement recommendations
    """
    
    def __init__(self):
        super().__init__(
            AgentType.LEARNING,
            capabilities=[
                AgentCapability.REASONING,
                AgentCapability.LEARNING,
                AgentCapability.MEMORY,
                AgentCapability.COMMUNICATION,
                AgentCapability.REFLECTION
            ]
        )
        self.settings = get_settings()
        
        # In-memory storage for learning data (backed by DB)
        self.feedback_history: list[dict] = []
        self.decision_outcomes: dict[str, list[dict]] = defaultdict(list)
        self.threshold_suggestions: dict[str, float] = {}
        
        # Agentic goals
        self.add_goal("Learn from human feedback to improve accuracy", priority=0.9)
        self.add_goal("Reduce override rate over time", priority=0.8)
        self.add_goal("Identify systematic decision errors", priority=0.85)
        
        # Initialize beliefs
        self.update_belief("current_accuracy", 0.0, confidence=0.5)
        self.update_belief("learning_rate", 0.1, confidence=0.7)
        
        # Load from database on init
        self._load_from_db()
    
    def _load_from_db(self):
        """Load feedback and decisions from database."""
        try:
            from app.services.db import get_db
            from app.models.database import FeedbackModel, DecisionModel
            
            with get_db() as db:
                # Load recent feedback (last 90 days)
                cutoff = datetime.utcnow() - timedelta(days=90)
                feedback_records = db.query(FeedbackModel).filter(
                    FeedbackModel.created_at >= cutoff
                ).order_by(FeedbackModel.created_at.desc()).limit(500).all()
                
                for fb in feedback_records:
                    self.feedback_history.append({
                        "id": fb.id,
                        "decision_id": fb.decision_id,
                        "user_id": fb.user_id,
                        "feedback_type": fb.feedback_type,
                        "reason": fb.reason,
                        "was_override": fb.was_override,
                        "original_action": fb.original_action,
                        "created_at": fb.created_at.isoformat() if fb.created_at else None,
                        "processed_at": fb.created_at.isoformat() if fb.created_at else None
                    })
                
                # Load recent decisions
                decision_records = db.query(DecisionModel).filter(
                    DecisionModel.created_at >= cutoff
                ).order_by(DecisionModel.created_at.desc()).limit(1000).all()
                
                for dec in decision_records:
                    self.decision_outcomes[dec.account_code].append({
                        "id": dec.id,
                        "account_code": dec.account_code,
                        "action": dec.action,
                        "risk_score": dec.risk_score,
                        "confidence_score": dec.confidence_score,
                        "rationale": dec.rationale,
                        "created_at": dec.created_at.isoformat() if dec.created_at else None
                    })
                
                self.log_audit_event(
                    event_type="learning_data_loaded",
                    payload={
                        "feedback_loaded": len(self.feedback_history),
                        "decisions_loaded": len(decision_records)
                    }
                )
                
        except Exception as e:
            # If DB not available, continue with empty data
            self.logger.warning("failed_to_load_learning_data", error=str(e))
    
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

    async def generate_ai_insights(self) -> dict:
        """
        Use LLM to analyze feedback patterns and generate actionable insights.
        This is the AGENTIC AI feature.
        """
        metrics = self._calculate_metrics()
        
        if metrics["total_feedback"] == 0:
            return {
                "insights": "Not enough feedback data to generate insights.",
                "recommendations": [],
                "confidence": 0.0
            }
        
        # Analyze override patterns
        override_by_type = defaultdict(int)
        for fb in self.feedback_history:
            if fb.get("was_override"):
                original = fb.get("original_action", "unknown")
                override_by_type[original] += 1
        
        prompt = f"""You are an AI learning agent analyzing feedback patterns for a financial audit system.

FEEDBACK METRICS:
- Total feedback received: {metrics['total_feedback']}
- Override rate: {metrics['override_rate']*100:.1f}%
- Agreement rate: {metrics['agreement_rate']*100:.1f}%
- Estimated accuracy: {metrics['accuracy_estimate']*100:.1f}%

OVERRIDE PATTERNS BY ORIGINAL DECISION:
{self._format_override_patterns(override_by_type)}

CURRENT THRESHOLD SUGGESTIONS:
{self.threshold_suggestions}

As an AI learning agent, analyze these patterns and provide:
1. KEY INSIGHT: What's the main learning from this data?
2. ROOT CAUSE: Why are overrides happening?
3. RECOMMENDATIONS: 2-3 specific changes to improve accuracy
4. CONFIDENCE: How confident are you in these insights? (0-100%)

Be specific and actionable.
"""
        
        response = await self._call_llm(prompt, temperature=0.5)
        
        # Parse the response
        insights = {
            "raw_analysis": response,
            "override_rate": metrics["override_rate"],
            "accuracy": metrics["accuracy_estimate"],
            "recommendations": self._extract_recommendations(response),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Update beliefs based on learning
        self.update_belief("current_accuracy", metrics["accuracy_estimate"], confidence=0.8)
        self.update_belief("override_rate", metrics["override_rate"], confidence=0.9)
        
        # Remember this analysis
        self.remember({
            "type": "ai_learning_analysis",
            "accuracy": metrics["accuracy_estimate"],
            "override_rate": metrics["override_rate"]
        }, importance=0.8)
        
        # Broadcast insights to other agents
        self.broadcast_message(
            message_type="learning_update",
            content={
                "accuracy": metrics["accuracy_estimate"],
                "override_rate": metrics["override_rate"],
                "suggestions": list(self.threshold_suggestions.keys())
            },
            priority=0.6
        )
        
        return insights
    
    def _format_override_patterns(self, patterns: dict) -> str:
        """Format override patterns for AI prompt."""
        if not patterns:
            return "No override patterns recorded yet."
        
        lines = []
        for action, count in patterns.items():
            lines.append(f"- {action}: {count} overrides")
        return "\n".join(lines)
    
    def _extract_recommendations(self, ai_response: str) -> list[str]:
        """Extract recommendations from AI response."""
        recommendations = []
        lines = ai_response.split("\n")
        
        in_recommendations = False
        for line in lines:
            line_lower = line.lower()
            if "recommendation" in line_lower:
                in_recommendations = True
                continue
            if in_recommendations and line.strip().startswith(("-", "•", "*", "1", "2", "3")):
                rec = line.strip().lstrip("-•*123456789. ")
                if rec:
                    recommendations.append(rec)
            if in_recommendations and line.strip() == "":
                in_recommendations = False
        
        return recommendations[:5]  # Max 5 recommendations
    
    async def self_improve(self) -> dict:
        """
        Agentic self-improvement: reflect on learning effectiveness
        and adjust learning strategies.
        """
        # Get current state
        metrics = self._calculate_metrics()
        
        prompt = f"""As an AI learning agent, reflect on your learning effectiveness.

YOUR GOALS:
1. Reduce override rate (currently {metrics['override_rate']*100:.1f}%)
2. Improve accuracy (currently {metrics['accuracy_estimate']*100:.1f}% estimated)
3. Provide better threshold suggestions

YOUR CURRENT SUGGESTIONS:
{self.threshold_suggestions}

RECENT FEEDBACK COUNT: {metrics['total_feedback']}

Questions to answer:
1. Are your threshold suggestions being effective?
2. What should you learn faster/slower?
3. What patterns are you missing?
4. How can you improve your learning strategy?

Provide specific, actionable self-improvement suggestions.
"""
        
        reflection = await self._call_llm(prompt, temperature=0.7)
        
        # Store reflection
        self.reflection_insights.append({
            "timestamp": datetime.utcnow().isoformat(),
            "reflection": reflection,
            "metrics_at_time": metrics
        })
        
        # Update performance metrics
        self.performance_metrics["accuracy"] = metrics["accuracy_estimate"] or 0
        self.performance_metrics["override_rate"] = metrics["override_rate"]
        self.performance_metrics["learning_cycles"] = len(self.reflection_insights)
        
        return {
            "reflection": reflection,
            "metrics": metrics,
            "improvement_cycle": len(self.reflection_insights)
        }
