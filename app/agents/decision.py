"""
Decision Agent (Agentic AI)
===========================
Assigns confidence and risk scores to each financial line item
and determines whether it can be auto-approved or must be escalated.

AGENTIC FEATURES:
- Goal-driven decision making
- AI-powered reasoning for each decision
- Inter-agent communication
- Self-reflection and learning
- Memory of past decisions
"""
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
import numpy as np

from app.agents.agentic_base import AgenticBase, AgentCapability, Goal
from app.models import (
    AgentType, Balance, Decision, DecisionAction, EvidencePack,
    Finding, FindingType, MaterialityBand, RiskScore,
    ValidationResult, ValidationStatus, VarianceAnalysis
)
from app.config import get_settings


class DecisionAgent(AgenticBase):
    """
    AGENTIC Decision Agent for making approval/escalation decisions.
    
    Agentic Capabilities:
    - Uses LLM to reason about each decision
    - Maintains beliefs about risk levels
    - Communicates with other agents
    - Reflects on decision patterns
    - Learns from feedback
    
    Responsibilities:
    - Aggregate signals from validation and variance agents
    - Calculate composite risk scores
    - Apply decision policies based on materiality and risk
    - Generate evidence-backed rationales
    - Determine auto-approve vs escalate actions
    """
    
    # Risk weights for different signal types
    RISK_WEIGHTS = {
        "validation_risk": 0.25,
        "variance_risk": 0.30,
        "materiality_risk": 0.20,
        "data_quality_risk": 0.15,
        "historical_risk": 0.10
    }
    
    def __init__(self):
        super().__init__(
            AgentType.DECISION,
            capabilities=[
                AgentCapability.REASONING,
                AgentCapability.LEARNING,
                AgentCapability.COMMUNICATION,
                AgentCapability.MEMORY,
                AgentCapability.REFLECTION
            ]
        )
        self.settings = get_settings()
        self.policy_version = "v2.0-agentic"
        
        # Agentic goals
        self.add_goal("Maximize accuracy of approval decisions", priority=0.9)
        self.add_goal("Minimize false positives (unnecessary escalations)", priority=0.7)
        self.add_goal("Ensure all high-risk items are escalated", priority=0.95)
        
        # Initialize beliefs
        self.update_belief("default_risk_threshold", 0.7, confidence=0.8)
        self.update_belief("conservative_mode", False, confidence=0.9)
    
    def validate_input(self, context: dict[str, Any]) -> bool:
        """Validate that required inputs are present."""
        has_balances = "balances" in context or "trial_balance" in context
        return has_balances
    
    async def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        """
        Execute decision-making for all line items.
        
        Context should contain:
        - balances: List of Balance objects
        - validation_results: List of ValidationResult from ValidationAgent
        - variance_analyses: List of VarianceAnalysis from VarianceAgent
        - findings: List of Finding objects
        - accounts: Dict mapping account_id to Account
        - entity_id: Entity identifier
        - period_id: Period identifier
        """
        balances = context.get("balances", [])
        validation_results = context.get("validation_results", [])
        variance_analyses = context.get("variance_analyses", [])
        findings = context.get("findings", [])
        accounts = context.get("accounts", {})
        entity_id = context.get("entity_id")
        period_id = context.get("period_id")
        
        # Build lookups
        validation_by_account = self._build_validation_lookup(validation_results)
        variance_by_account = {v["account_id"]: v for v in variance_analyses}
        findings_by_account = self._build_findings_lookup(findings)
        
        # Process each balance
        decisions = []
        risk_scores = []
        
        for balance in balances:
            account_id = balance.account_id
            account = accounts.get(account_id, {})
            
            # Calculate risk score
            risk_score = await self._calculate_risk_score(
                balance=balance,
                account=account,
                validation_issues=validation_by_account.get(account_id, []),
                variance=variance_by_account.get(account_id),
                findings=findings_by_account.get(account_id, [])
            )
            risk_scores.append(risk_score)
            
            # Make decision
            decision = await self._make_decision(
                balance=balance,
                account=account,
                risk_score=risk_score,
                validation_issues=validation_by_account.get(account_id, []),
                variance=variance_by_account.get(account_id),
                findings=findings_by_account.get(account_id, []),
                entity_id=entity_id,
                period_id=period_id
            )
            decisions.append(decision)
        
        # Calculate summary metrics
        auto_approved = sum(1 for d in decisions if d.action == DecisionAction.AUTO_APPROVED)
        escalated = sum(1 for d in decisions if d.action == DecisionAction.ESCALATED)
        pending = sum(1 for d in decisions if d.action == DecisionAction.PENDING_REVIEW)
        
        auto_approve_rate = auto_approved / len(decisions) if decisions else 0
        avg_risk = np.mean([r.overall_risk for r in risk_scores]) if risk_scores else 0
        avg_confidence = np.mean([d.confidence for d in decisions]) if decisions else 0
        
        # Log audit event
        self.log_audit_event(
            event_type="decisions_completed",
            payload={
                "total_decisions": len(decisions),
                "auto_approved": auto_approved,
                "escalated": escalated,
                "pending_review": pending,
                "auto_approve_rate": auto_approve_rate,
                "avg_risk_score": float(avg_risk),
                "avg_confidence": float(avg_confidence),
                "policy_version": self.policy_version
            },
            entity_id=entity_id,
            period_id=period_id
        )
        
        return {
            "decisions": [d.model_dump() for d in decisions],
            "risk_scores": [r.model_dump() for r in risk_scores],
            "summary": {
                "total_decisions": len(decisions),
                "auto_approved": auto_approved,
                "escalated": escalated,
                "pending_review": pending,
                "auto_approve_rate": auto_approve_rate,
                "average_risk_score": float(avg_risk),
                "average_confidence": float(avg_confidence),
                "policy_version": self.policy_version
            }
        }
    
    def _build_validation_lookup(
        self, 
        validation_results: list[dict]
    ) -> dict[str, list[dict]]:
        """Build lookup of validation issues by account."""
        result: dict[str, list[dict]] = {}
        
        for vr in validation_results:
            if isinstance(vr, dict):
                affected = vr.get("affected_accounts", [])
                if vr.get("status") in ("failed", "warning"):
                    for account_id in affected:
                        if account_id not in result:
                            result[account_id] = []
                        result[account_id].append(vr)
        
        return result
    
    def _build_findings_lookup(
        self, 
        findings: list[dict]
    ) -> dict[str, list[dict]]:
        """Build lookup of findings by account."""
        result: dict[str, list[dict]] = {}
        
        for finding in findings:
            if isinstance(finding, dict):
                account_id = finding.get("account_id")
                if account_id:
                    if account_id not in result:
                        result[account_id] = []
                    result[account_id].append(finding)
        
        return result
    
    async def _calculate_risk_score(
        self,
        balance: Balance,
        account: dict,
        validation_issues: list[dict],
        variance: Optional[dict],
        findings: list[dict]
    ) -> RiskScore:
        """Calculate composite risk score for an account."""
        
        components = {}
        
        # Validation risk (0-1)
        if validation_issues:
            failed = sum(1 for v in validation_issues if v.get("status") == "failed")
            warnings = sum(1 for v in validation_issues if v.get("status") == "warning")
            components["validation_risk"] = min(1.0, failed * 0.5 + warnings * 0.2)
        else:
            components["validation_risk"] = 0.0
        
        # Variance risk (0-1)
        if variance:
            pct_var = abs(variance.get("percent_variance") or 0)
            zscore = abs(variance.get("zscore") or 0)
            
            if variance.get("is_anomaly"):
                # Anomalies should have HIGH variance risk to trigger escalation
                # Base risk of 0.7 for any anomaly, plus contributions from zscore/pct
                components["variance_risk"] = min(1.0, 0.7 + zscore / 10.0 + pct_var / 2)
            elif pct_var > 0.5:  # >50% variance without anomaly flag
                components["variance_risk"] = min(1.0, 0.6 + pct_var * 0.3)
            elif pct_var > 0.25:  # >25% variance
                components["variance_risk"] = min(1.0, 0.4 + pct_var)
            else:
                components["variance_risk"] = min(1.0, pct_var * 2)  # Scale up small variances
        else:
            components["variance_risk"] = 0.1  # Small risk for no comparison data
        
        # Materiality risk (0-1)
        materiality = account.get("materiality_band", MaterialityBand.MEDIUM)
        if isinstance(materiality, str):
            try:
                materiality = MaterialityBand(materiality)
            except ValueError:
                materiality = MaterialityBand.MEDIUM
        
        materiality_scores = {
            MaterialityBand.HIGH: 0.8,
            MaterialityBand.MEDIUM: 0.4,
            MaterialityBand.LOW: 0.2,
            MaterialityBand.IMMATERIAL: 0.05
        }
        components["materiality_risk"] = materiality_scores.get(materiality, 0.4)
        
        # Data quality risk (0-1)
        # Based on findings related to data quality
        quality_findings = [
            f for f in findings 
            if f.get("finding_type") in ("missing_documentation", "unusual_pattern")
        ]
        components["data_quality_risk"] = min(1.0, len(quality_findings) * 0.3)
        
        # Historical risk (0-1)
        # Could be enhanced with actual historical data
        if findings:
            severity_sum = sum(f.get("severity", 0.5) for f in findings)
            components["historical_risk"] = min(1.0, severity_sum / len(findings))
        else:
            components["historical_risk"] = 0.1
        
        # Calculate weighted overall risk
        overall_risk = sum(
            components.get(key, 0) * weight 
            for key, weight in self.RISK_WEIGHTS.items()
        )
        
        # Calculate confidence (inverse of uncertainty)
        # Higher confidence when we have more data and fewer edge cases
        data_completeness = 1.0 if variance else 0.7
        validation_clarity = 1.0 - (len(validation_issues) * 0.1)
        confidence = min(1.0, max(0.5, (data_completeness + validation_clarity) / 2))
        
        return RiskScore(
            account_id=balance.account_id,
            period_id=balance.period_id,
            entity_id=balance.entity_id,
            overall_risk=min(1.0, overall_risk),
            confidence=confidence,
            components=components
        )
    
    async def _make_decision(
        self,
        balance: Balance,
        account: dict,
        risk_score: RiskScore,
        validation_issues: list[dict],
        variance: Optional[dict],
        findings: list[dict],
        entity_id: str,
        period_id: str
    ) -> Decision:
        """Make approval/escalation decision for an account."""
        
        # Build evidence pack
        evidence_pack = self._build_evidence_pack(
            balance=balance,
            variance=variance,
            validation_issues=validation_issues,
            findings=findings
        )
        
        # Apply decision logic
        action, rationale = await self._apply_decision_policy(
            risk_score=risk_score,
            balance=balance,
            account=account,
            validation_issues=validation_issues,
            variance=variance,
            findings=findings,
            evidence_pack=evidence_pack
        )
        
        requires_review = action in (DecisionAction.ESCALATED, DecisionAction.PENDING_REVIEW)
        
        # Log individual decision
        self.log_audit_event(
            event_type="decision_made",
            payload={
                "action": action.value,
                "risk_score": risk_score.overall_risk,
                "confidence": risk_score.confidence,
                "requires_review": requires_review
            },
            entity_id=entity_id,
            period_id=period_id,
            account_id=balance.account_id
        )
        
        return Decision(
            account_id=balance.account_id,
            period_id=period_id,
            entity_id=entity_id,
            action=action,
            risk_score=risk_score.overall_risk,
            confidence=risk_score.confidence,
            rationale=rationale,
            evidence_pack=evidence_pack,
            policy_version=self.policy_version,
            requires_human_review=requires_review
        )
    
    def _build_evidence_pack(
        self,
        balance: Balance,
        variance: Optional[dict],
        validation_issues: list[dict],
        findings: list[dict]
    ) -> dict[str, Any]:
        """Build structured evidence supporting the decision."""
        
        evidence = {
            "current_balance": {
                "debit": float(balance.debit_amount),
                "credit": float(balance.credit_amount),
                "net": float(balance.net_amount)
            },
            "validation_results": [
                {
                    "check": v.get("check_name"),
                    "status": v.get("status"),
                    "message": v.get("message")
                }
                for v in validation_issues
            ],
            "findings": [
                {
                    "type": f.get("finding_type"),
                    "severity": f.get("severity"),
                    "description": f.get("description")
                }
                for f in findings
            ],
            "policy_thresholds": {
                "auto_approve_confidence": self.settings.auto_approve_confidence_threshold,
                "escalation_risk": self.settings.escalation_risk_threshold
            }
        }
        
        if variance:
            evidence["variance"] = {
                "prior_amount": variance.get("prior_amount"),
                "current_amount": variance.get("current_amount"),
                "absolute_variance": variance.get("absolute_variance"),
                "percent_variance": variance.get("percent_variance"),
                "zscore": variance.get("zscore"),
                "is_anomaly": variance.get("is_anomaly"),
                "explanation": variance.get("explanation")
            }
        
        return evidence
    
    async def _apply_decision_policy(
        self,
        risk_score: RiskScore,
        balance: Balance,
        account: dict,
        validation_issues: list[dict],
        variance: Optional[dict],
        findings: list[dict],
        evidence_pack: dict
    ) -> tuple[DecisionAction, str]:
        """Apply decision policy to determine action."""
        
        risk = risk_score.overall_risk
        confidence = risk_score.confidence
        
        # Get materiality
        materiality = account.get("materiality_band", MaterialityBand.MEDIUM)
        if isinstance(materiality, str):
            try:
                materiality = MaterialityBand(materiality)
            except ValueError:
                materiality = MaterialityBand.MEDIUM
        
        # Check for critical failures that always require escalation
        critical_failures = [
            v for v in validation_issues 
            if v.get("status") == "failed" and v.get("check_name") == "zero_balance"
        ]
        if critical_failures:
            return (
                DecisionAction.ESCALATED,
                "Critical validation failure: Trial balance is out of balance. Manual review required."
            )
        
        # Check for high-severity findings on high-materiality accounts
        high_severity_findings = [f for f in findings if f.get("severity", 0) > 0.7]
        if high_severity_findings and materiality == MaterialityBand.HIGH:
            finding_types = [f.get("finding_type") for f in high_severity_findings]
            return (
                DecisionAction.ESCALATED,
                f"High-severity findings on material account: {', '.join(finding_types)}. "
                f"Risk score: {risk:.2f}. Requires human review."
            )
        
        # Check for variance anomalies - these should ALWAYS require review
        if variance and variance.get("is_anomaly"):
            pct_var = abs(variance.get("percent_variance") or 0)
            zscore = abs(variance.get("zscore") or 0)
            return (
                DecisionAction.ESCALATED,
                f"Variance anomaly detected: {pct_var*100:.1f}% change (z-score: {zscore:.2f}). "
                f"Exceeds threshold. Requires human verification."
            )
        
        # Apply threshold-based decisions
        if risk >= self.settings.escalation_risk_threshold:
            # High risk - escalate
            components = risk_score.components
            top_risks = sorted(components.items(), key=lambda x: x[1], reverse=True)[:2]
            risk_factors = ", ".join([f"{k}: {v:.2f}" for k, v in top_risks])
            
            return (
                DecisionAction.ESCALATED,
                f"Risk score ({risk:.2f}) exceeds threshold ({self.settings.escalation_risk_threshold}). "
                f"Key risk factors: {risk_factors}. Human review recommended."
            )
        
        elif confidence >= self.settings.auto_approve_confidence_threshold and risk < 0.3:
            # High confidence, low risk - auto-approve
            return (
                DecisionAction.AUTO_APPROVED,
                f"Auto-approved: Low risk ({risk:.2f}) with high confidence ({confidence:.2f}). "
                f"All validation checks passed. Variance within normal ranges."
            )
        
        elif confidence >= 0.7 and risk < 0.4:
            # Moderate confidence and LOW risk - auto-approve
            # Note: Anomalies are already handled above, so if we get here there's no anomaly
            return (
                DecisionAction.AUTO_APPROVED,
                f"Auto-approved: Acceptable risk ({risk:.2f}) with adequate confidence ({confidence:.2f}). "
                f"No significant anomalies detected."
            )
        
        elif risk < 0.5:
            # Borderline risk - pending review
            return (
                DecisionAction.PENDING_REVIEW,
                f"Pending review: Risk ({risk:.2f}) is borderline. Human verification recommended."
            )
        
        else:
            # Low confidence or borderline risk - pending review
            return (
                DecisionAction.PENDING_REVIEW,
                f"Pending review: Risk score ({risk:.2f}) or confidence ({confidence:.2f}) "
                f"requires human verification before approval."
            )

    async def _get_ai_reasoning(
        self,
        account: dict,
        risk_score: RiskScore,
        variance: Optional[dict],
        validation_issues: list[dict],
        findings: list[dict]
    ) -> dict:
        """
        Use LLM to reason about the decision - TRUE AGENTIC AI.
        
        The AI considers all factors and provides:
        - Recommended action
        - Confidence level
        - Detailed reasoning
        - Risk factors identified
        """
        account_name = account.get("name", account.get("account_name", "Unknown"))
        account_type = account.get("account_type", "Unknown")
        
        prompt = f"""You are an autonomous AI auditor agent making a decision about a financial account.

ACCOUNT: {account_name} (Type: {account_type})

RISK ANALYSIS:
- Overall Risk Score: {risk_score.overall_risk:.2f}
- Confidence: {risk_score.confidence:.2f}
- Risk Components: {risk_score.components}

VARIANCE DATA:
{self._format_variance_for_ai(variance) if variance else "No prior period data available"}

VALIDATION ISSUES:
{self._format_validation_for_ai(validation_issues)}

FINDINGS:
{self._format_findings_for_ai(findings)}

YOUR GOALS:
1. Maximize accuracy - don't approve truly risky items
2. Minimize unnecessary escalations - don't escalate low-risk items
3. Ensure all anomalies get human review

Based on this evidence, what is your decision?

Respond in this exact format:
DECISION: [AUTO_APPROVE or ESCALATE or PENDING_REVIEW]
CONFIDENCE: [0.0 to 1.0]
KEY_FACTORS: [list the top 2-3 factors that drove your decision]
REASONING: [2-3 sentences explaining your decision]
"""
        
        response = await self._call_llm(prompt, temperature=0.3)
        
        # Parse response
        result = {
            "decision": "PENDING_REVIEW",
            "confidence": 0.5,
            "key_factors": [],
            "reasoning": response,
            "raw_response": response
        }
        
        lines = response.split('\n')
        for line in lines:
            line_upper = line.upper()
            if line_upper.startswith("DECISION:"):
                decision_text = line.split(":", 1)[1].strip().upper()
                if "AUTO" in decision_text or "APPROVE" in decision_text:
                    result["decision"] = "AUTO_APPROVED"
                elif "ESCALATE" in decision_text:
                    result["decision"] = "ESCALATED"
                else:
                    result["decision"] = "PENDING_REVIEW"
            elif line_upper.startswith("CONFIDENCE:"):
                try:
                    result["confidence"] = float(line.split(":", 1)[1].strip())
                except:
                    pass
            elif line_upper.startswith("KEY_FACTORS:"):
                result["key_factors"] = line.split(":", 1)[1].strip()
            elif line_upper.startswith("REASONING:"):
                result["reasoning"] = line.split(":", 1)[1].strip()
        
        # Remember this reasoning for learning
        self.remember({
            "type": "ai_reasoning",
            "account": account_name,
            "decision": result["decision"],
            "confidence": result["confidence"]
        }, importance=0.7)
        
        # Update beliefs based on AI analysis
        if result["confidence"] > 0.8:
            self.update_belief(
                f"high_confidence_decision_{account_name[:20]}",
                result["decision"],
                confidence=result["confidence"]
            )
        
        return result
    
    def _format_variance_for_ai(self, variance: dict) -> str:
        """Format variance data for AI prompt."""
        pct = variance.get("percent_variance", 0)
        zscore = variance.get("zscore", 0)
        is_anomaly = variance.get("is_anomaly", False)
        
        return f"""- Percent Change: {pct*100:.1f}%
- Z-Score: {zscore:.2f}
- Is Anomaly: {"YES ⚠️" if is_anomaly else "No"}
- Prior Amount: ${variance.get('prior_amount', 0):,.2f}
- Current Amount: ${variance.get('current_amount', 0):,.2f}"""
    
    def _format_validation_for_ai(self, issues: list) -> str:
        """Format validation issues for AI prompt."""
        if not issues:
            return "No validation issues found ✓"
        
        return "\n".join([
            f"- {v.get('check_name', 'Unknown')}: {v.get('status', 'unknown')} - {v.get('message', '')}"
            for v in issues[:5]
        ])
    
    def _format_findings_for_ai(self, findings: list) -> str:
        """Format findings for AI prompt."""
        if not findings:
            return "No findings"
        
        return "\n".join([
            f"- {f.get('finding_type', 'Unknown')}: Severity {f.get('severity', 0):.1f}"
            for f in findings[:5]
        ])
    
    async def reflect_on_decisions(self, decisions: list) -> str:
        """
        Agentic self-reflection on recent decisions.
        
        Analyzes patterns in decisions made and suggests improvements.
        Accepts both Decision objects and dictionaries.
        """
        if not decisions:
            return "No decisions to reflect on."
        
        # Helper to get attribute from dict or object
        def get_attr(d, key, default=None):
            if isinstance(d, dict):
                return d.get(key, default)
            return getattr(d, key, default)
        
        # Aggregate stats
        total = len(decisions)
        auto_approved = sum(1 for d in decisions if get_attr(d, 'action') in ('auto_approved', DecisionAction.AUTO_APPROVED))
        escalated = sum(1 for d in decisions if get_attr(d, 'action') in ('escalated', DecisionAction.ESCALATED))
        avg_risk = sum(get_attr(d, 'risk_score', 0) or 0 for d in decisions) / total
        avg_confidence = sum(get_attr(d, 'confidence', 0) or 0 for d in decisions) / total
        
        prompt = f"""Reflect on your recent decision-making performance as an autonomous auditor agent.

DECISIONS MADE: {total}
- Auto-Approved: {auto_approved} ({auto_approved/total*100:.1f}%)
- Escalated: {escalated} ({escalated/total*100:.1f}%)
- Pending Review: {total - auto_approved - escalated}

METRICS:
- Average Risk Score: {avg_risk:.2f}
- Average Confidence: {avg_confidence:.2f}

YOUR GOALS:
1. Maximize accuracy
2. Minimize false positives
3. Ensure high-risk items are escalated

REFLECTION QUESTIONS:
1. Is my auto-approval rate appropriate?
2. Am I being too conservative or too lenient?
3. What patterns do I notice?
4. What should I do differently?

Provide specific, actionable insights.
"""
        
        reflection = await self._call_llm(prompt, temperature=0.7)
        
        # Store reflection
        self.reflection_insights.append({
            "timestamp": datetime.utcnow().isoformat(),
            "decisions_analyzed": total,
            "insight": reflection
        })
        
        # Update performance metrics
        self.performance_metrics["auto_approve_rate"] = auto_approved / total
        self.performance_metrics["avg_risk"] = avg_risk
        self.performance_metrics["avg_confidence"] = avg_confidence
        
        return reflection
