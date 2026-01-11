"""
Variance Reasoning Agent (Agentic AI)
======================================
Analyzes period-over-period changes, detects abnormal deviations,
and generates natural-language explanations using historical trends.

AGENTIC FEATURES:
- AI-powered explanation of variances
- Goal-driven anomaly detection
- Memory of historical patterns
- Inter-agent communication of anomalies
"""
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
import numpy as np
from scipy import stats

from app.agents.agentic_base import AgenticBase, AgentCapability
from app.models import (
    AgentType, Balance, Finding, FindingType, 
    MaterialityBand, VarianceAnalysis
)
from app.config import get_settings


class VarianceReasoningAgent(AgenticBase):
    """
    AGENTIC Variance Analysis Agent.
    
    Agentic Capabilities:
    - Uses LLM to explain variances in business terms
    - Remembers patterns across periods
    - Alerts decision agent about anomalies
    - Self-reflects on detection accuracy
    
    Performs:
    - Period-over-period variance calculation
    - Z-score based anomaly detection
    - Trend analysis with seasonality awareness
    - Natural language explanation generation
    - Historical pattern recognition
    """
    
    def __init__(self):
        super().__init__(
            AgentType.VARIANCE,
            capabilities=[
                AgentCapability.REASONING,
                AgentCapability.MEMORY,
                AgentCapability.COMMUNICATION,
                AgentCapability.REFLECTION
            ]
        )
        self.settings = get_settings()
        
        # Agentic goals
        self.add_goal("Detect all significant variances accurately", priority=0.9)
        self.add_goal("Minimize false positive anomalies", priority=0.7)
        self.add_goal("Provide actionable explanations for variances", priority=0.8)
        
        # Initialize beliefs
        self.update_belief("zscore_threshold", self.settings.variance_zscore_threshold, confidence=0.9)
        self.update_belief("percent_threshold", self.settings.variance_percent_threshold, confidence=0.9)
    
    def validate_input(self, context: dict[str, Any]) -> bool:
        """Validate that required inputs are present."""
        has_current = "current_balances" in context or "current_period" in context
        has_prior = "prior_balances" in context or "prior_period" in context
        return has_current and has_prior
    
    async def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        """
        Execute variance analysis.
        
        Context should contain:
        - current_balances: List of Balance objects for current period
        - prior_balances: List of Balance objects for prior period
        - historical_balances: Optional list of historical balances for trend analysis
        - accounts: Optional dict mapping account_id to Account
        - entity_id: Entity identifier
        - current_period_id: Current period identifier
        - prior_period_id: Prior period identifier
        """
        current_balances = context.get("current_balances", [])
        prior_balances = context.get("prior_balances", [])
        historical_balances = context.get("historical_balances", [])
        accounts = context.get("accounts", {})
        entity_id = context.get("entity_id")
        current_period_id = context.get("current_period_id")
        prior_period_id = context.get("prior_period_id")
        
        # Convert to dicts for easy lookup
        current_by_account = {b.account_id: b for b in current_balances}
        prior_by_account = {b.account_id: b for b in prior_balances}
        
        # Build historical data for trend analysis
        historical_by_account = self._build_historical_lookup(historical_balances)
        
        # Analyze each account
        variance_analyses = []
        findings = []
        anomalies = []
        
        all_account_ids = set(current_by_account.keys()) | set(prior_by_account.keys())
        
        for account_id in all_account_ids:
            current = current_by_account.get(account_id)
            prior = prior_by_account.get(account_id)
            historical = historical_by_account.get(account_id, [])
            account = accounts.get(account_id, {})
            
            # Perform variance analysis
            analysis = await self._analyze_variance(
                account_id=account_id,
                current_balance=current,
                prior_balance=prior,
                historical_amounts=historical,
                account=account,
                current_period_id=current_period_id,
                prior_period_id=prior_period_id
            )
            
            variance_analyses.append(analysis)
            
            # Generate findings for anomalies
            if analysis.is_anomaly:
                anomalies.append(analysis)
                finding = self._create_finding(
                    analysis, entity_id, account
                )
                findings.append(finding)
        
        # Calculate summary statistics
        total_variance = sum(
            abs(float(v.absolute_variance)) for v in variance_analyses
        )
        anomaly_count = len(anomalies)
        anomaly_rate = anomaly_count / len(variance_analyses) if variance_analyses else 0
        
        # Log audit event
        self.log_audit_event(
            event_type="variance_analysis_completed",
            payload={
                "accounts_analyzed": len(variance_analyses),
                "anomalies_detected": anomaly_count,
                "anomaly_rate": anomaly_rate,
                "total_absolute_variance": total_variance
            },
            entity_id=entity_id,
            period_id=current_period_id
        )
        
        return {
            "variance_analyses": [v.model_dump() for v in variance_analyses],
            "findings": [f.model_dump() for f in findings],
            "anomalies": [a.model_dump() for a in anomalies],
            "summary": {
                "accounts_analyzed": len(variance_analyses),
                "anomalies_detected": anomaly_count,
                "anomaly_rate": anomaly_rate,
                "total_absolute_variance": total_variance,
                "top_variances": self._get_top_variances(variance_analyses, n=10)
            }
        }
    
    def _build_historical_lookup(
        self, 
        historical_balances: list[Balance]
    ) -> dict[str, list[float]]:
        """Build lookup of historical amounts by account."""
        result: dict[str, list[float]] = {}
        
        for balance in historical_balances:
            if balance.account_id not in result:
                result[balance.account_id] = []
            result[balance.account_id].append(float(balance.net_amount))
        
        return result
    
    async def _analyze_variance(
        self,
        account_id: str,
        current_balance: Optional[Balance],
        prior_balance: Optional[Balance],
        historical_amounts: list[float],
        account: dict,
        current_period_id: str,
        prior_period_id: str
    ) -> VarianceAnalysis:
        """Analyze variance for a single account."""
        
        current_amount = current_balance.net_amount if current_balance else Decimal("0")
        prior_amount = prior_balance.net_amount if prior_balance else Decimal("0")
        
        absolute_variance = current_amount - prior_amount
        
        # Calculate percent variance
        percent_variance = None
        if prior_amount != 0:
            percent_variance = float(absolute_variance / prior_amount)
        elif current_amount != 0:
            percent_variance = 1.0 if current_amount > 0 else -1.0
        
        # Calculate z-score if we have historical data
        zscore = None
        if len(historical_amounts) >= 3:
            all_amounts = historical_amounts + [float(current_amount)]
            mean = np.mean(historical_amounts)
            std = np.std(historical_amounts)
            if std > 0:
                zscore = (float(current_amount) - mean) / std
        
        # Determine if this is an anomaly
        is_anomaly = self._is_anomaly(
            percent_variance=percent_variance,
            zscore=zscore,
            absolute_variance=absolute_variance,
            account=account
        )
        
        # Determine trend direction
        trend_direction = "stable"
        if percent_variance is not None:
            if percent_variance > 0.05:
                trend_direction = "up"
            elif percent_variance < -0.05:
                trend_direction = "down"
        
        # Generate explanation
        explanation = await self._generate_explanation(
            account_id=account_id,
            account=account,
            current_amount=current_amount,
            prior_amount=prior_amount,
            absolute_variance=absolute_variance,
            percent_variance=percent_variance,
            zscore=zscore,
            trend_direction=trend_direction,
            is_anomaly=is_anomaly,
            historical_amounts=historical_amounts
        )
        
        return VarianceAnalysis(
            account_id=account_id,
            current_period_id=current_period_id,
            prior_period_id=prior_period_id,
            current_amount=current_amount,
            prior_amount=prior_amount,
            absolute_variance=absolute_variance,
            percent_variance=percent_variance,
            zscore=zscore,
            is_anomaly=is_anomaly,
            trend_direction=trend_direction,
            explanation=explanation,
            evidence={
                "historical_data_points": len(historical_amounts),
                "thresholds_applied": {
                    "zscore_threshold": self.settings.variance_zscore_threshold,
                    "percent_threshold": self.settings.variance_percent_threshold
                }
            }
        )
    
    def _is_anomaly(
        self,
        percent_variance: Optional[float],
        zscore: Optional[float],
        absolute_variance: Decimal,
        account: dict
    ) -> bool:
        """Determine if the variance constitutes an anomaly."""
        
        # Get materiality band for threshold adjustment
        materiality = account.get("materiality_band", MaterialityBand.MEDIUM)
        if isinstance(materiality, str):
            try:
                materiality = MaterialityBand(materiality)
            except ValueError:
                materiality = MaterialityBand.MEDIUM
        
        # Adjust thresholds by materiality
        materiality_multipliers = {
            MaterialityBand.HIGH: 0.8,     # More sensitive for high materiality
            MaterialityBand.MEDIUM: 1.0,
            MaterialityBand.LOW: 1.2,
            MaterialityBand.IMMATERIAL: 1.5
        }
        multiplier = materiality_multipliers.get(materiality, 1.0)
        
        zscore_threshold = self.settings.variance_zscore_threshold * multiplier
        percent_threshold = self.settings.variance_percent_threshold * multiplier
        
        # Check z-score threshold
        if zscore is not None and abs(zscore) > zscore_threshold:
            return True
        
        # Check percent variance threshold
        if percent_variance is not None and abs(percent_variance) > percent_threshold:
            return True
        
        # Check absolute variance for immaterial accounts with large swings
        if abs(absolute_variance) > Decimal("100000"):
            return True
        
        return False
    
    async def _generate_explanation(
        self,
        account_id: str,
        account: dict,
        current_amount: Decimal,
        prior_amount: Decimal,
        absolute_variance: Decimal,
        percent_variance: Optional[float],
        zscore: Optional[float],
        trend_direction: str,
        is_anomaly: bool,
        historical_amounts: list[float]
    ) -> str:
        """Generate a natural language explanation for the variance."""
        
        account_name = account.get("name", account_id)
        account_type = account.get("account_type", "unknown")
        
        # Build explanation components
        parts = []
        
        # Direction and magnitude
        if absolute_variance > 0:
            direction = "increased"
        elif absolute_variance < 0:
            direction = "decreased"
        else:
            return f"{account_name}: No change from prior period."
        
        # Main variance description
        if percent_variance is not None:
            parts.append(
                f"{account_name} {direction} by {abs(percent_variance):.1%} "
                f"(${abs(float(absolute_variance)):,.0f})"
            )
        else:
            parts.append(
                f"{account_name} {direction} by ${abs(float(absolute_variance)):,.0f}"
            )
        
        # Prior vs current
        parts.append(
            f"from ${float(prior_amount):,.0f} to ${float(current_amount):,.0f}"
        )
        
        # Z-score context
        if zscore is not None:
            if abs(zscore) > self.settings.variance_zscore_threshold:
                parts.append(
                    f"This change is {abs(zscore):.1f} standard deviations from the historical mean, "
                    f"indicating unusual activity"
                )
            else:
                parts.append(
                    f"This change is within normal historical ranges (z-score: {zscore:.2f})"
                )
        
        # Historical trend context
        if len(historical_amounts) >= 4:
            recent_trend = self._calculate_trend(historical_amounts[-4:])
            if recent_trend > 0.05:
                parts.append("The account has shown an upward trend over recent periods")
            elif recent_trend < -0.05:
                parts.append("The account has shown a downward trend over recent periods")
        
        # Anomaly flag
        if is_anomaly:
            parts.append("⚠️ This variance requires review due to unusual magnitude")
        
        return ". ".join(parts) + "."
    
    def _calculate_trend(self, amounts: list[float]) -> float:
        """Calculate trend as average period-over-period change."""
        if len(amounts) < 2:
            return 0.0
        
        changes = []
        for i in range(1, len(amounts)):
            if amounts[i-1] != 0:
                changes.append((amounts[i] - amounts[i-1]) / abs(amounts[i-1]))
        
        return np.mean(changes) if changes else 0.0
    
    def _create_finding(
        self, 
        analysis: VarianceAnalysis, 
        entity_id: str,
        account: dict
    ) -> Finding:
        """Create a finding from a variance analysis."""
        
        finding_type = FindingType.VARIANCE_SPIKE if analysis.absolute_variance > 0 else FindingType.VARIANCE_DROP
        
        severity = min(0.9, abs(analysis.zscore or 0) / 5.0 + 0.3) if analysis.zscore else 0.5
        
        return Finding(
            finding_type=finding_type,
            account_id=analysis.account_id,
            period_id=analysis.current_period_id,
            entity_id=entity_id,
            severity=severity,
            magnitude=float(abs(analysis.absolute_variance)),
            description=analysis.explanation or f"Unusual variance detected: {analysis.percent_variance:.1%}",
            evidence={
                "current_amount": float(analysis.current_amount),
                "prior_amount": float(analysis.prior_amount),
                "absolute_variance": float(analysis.absolute_variance),
                "percent_variance": analysis.percent_variance,
                "zscore": analysis.zscore,
                "trend_direction": analysis.trend_direction
            },
            detected_by=AgentType.VARIANCE
        )
    
    def _get_top_variances(
        self, 
        analyses: list[VarianceAnalysis], 
        n: int = 10
    ) -> list[dict]:
        """Get the top N largest variances by absolute amount."""
        sorted_analyses = sorted(
            analyses,
            key=lambda x: abs(float(x.absolute_variance)),
            reverse=True
        )
        
        return [
            {
                "account_id": a.account_id,
                "absolute_variance": float(a.absolute_variance),
                "percent_variance": a.percent_variance,
                "is_anomaly": a.is_anomaly
            }
            for a in sorted_analyses[:n]
        ]

    async def _generate_ai_explanation(
        self,
        account_name: str,
        account_type: str,
        current_amount: float,
        prior_amount: float,
        percent_variance: float,
        zscore: Optional[float],
        is_anomaly: bool
    ) -> str:
        """
        Use LLM to generate a business-context explanation for the variance.
        This is the AGENTIC AI feature.
        """
        direction = "increased" if current_amount > prior_amount else "decreased"
        abs_change = abs(current_amount - prior_amount)
        
        prompt = f"""You are an AI financial analyst explaining a variance to an auditor.

ACCOUNT: {account_name}
TYPE: {account_type}
CHANGE: {direction} from ${prior_amount:,.2f} to ${current_amount:,.2f}
ABSOLUTE CHANGE: ${abs_change:,.2f}
PERCENT CHANGE: {percent_variance*100:.1f}%
Z-SCORE: {zscore:.2f if zscore else 'N/A'}
ANOMALY DETECTED: {'YES' if is_anomaly else 'No'}

Based on the account type and change, suggest 2-3 possible business reasons for this variance.
Be specific and practical. Keep your response to 2-3 sentences.
"""
        
        explanation = await self._call_llm(prompt, temperature=0.6)
        
        # Remember this pattern
        self.remember({
            "type": "variance_explanation",
            "account_type": account_type,
            "direction": direction,
            "percent_change": percent_variance,
            "is_anomaly": is_anomaly
        }, importance=0.6 if is_anomaly else 0.3)
        
        # If anomaly, alert decision agent
        if is_anomaly:
            self.send_message(
                receiver="decision",
                message_type="anomaly_alert",
                content={
                    "account": account_name,
                    "percent_variance": percent_variance,
                    "zscore": zscore,
                    "explanation": explanation[:200]
                },
                priority=0.8
            )
        
        return explanation
    
    async def analyze_variance_patterns(self, analyses: list[VarianceAnalysis]) -> dict:
        """
        Agentic pattern analysis across all variances.
        Uses AI to identify trends and systemic issues.
        """
        if not analyses:
            return {"patterns": [], "insights": "No data to analyze"}
        
        # Aggregate by direction
        increases = [a for a in analyses if a.absolute_variance > 0]
        decreases = [a for a in analyses if a.absolute_variance < 0]
        anomalies = [a for a in analyses if a.is_anomaly]
        
        # Calculate totals
        total_increase = sum(float(a.absolute_variance) for a in increases)
        total_decrease = sum(float(abs(a.absolute_variance)) for a in decreases)
        
        prompt = f"""Analyze these variance patterns for an audit review:

SUMMARY:
- Total accounts analyzed: {len(analyses)}
- Accounts with increases: {len(increases)} (total +${total_increase:,.0f})
- Accounts with decreases: {len(decreases)} (total -${total_decrease:,.0f})
- Anomalies detected: {len(anomalies)}

TOP ANOMALIES:
{self._format_top_anomalies(anomalies[:5])}

As an AI auditor, identify:
1. Any concerning patterns
2. Potential explanations for the overall trend
3. Recommendations for the audit team

Keep response concise (3-4 sentences).
"""
        
        insights = await self._call_llm(prompt, temperature=0.5)
        
        # Update beliefs
        self.update_belief("anomaly_rate", len(anomalies) / len(analyses) if analyses else 0, confidence=0.9)
        self.update_belief("net_variance_direction", "increase" if total_increase > total_decrease else "decrease", confidence=0.8)
        
        # Reflect and store
        self.remember({
            "type": "pattern_analysis",
            "anomaly_count": len(anomalies),
            "total_analyzed": len(analyses)
        }, importance=0.7)
        
        return {
            "patterns": {
                "increases": len(increases),
                "decreases": len(decreases),
                "anomalies": len(anomalies),
                "total_increase": total_increase,
                "total_decrease": total_decrease
            },
            "ai_insights": insights,
            "anomaly_rate": len(anomalies) / len(analyses) if analyses else 0
        }
    
    def _format_top_anomalies(self, anomalies: list) -> str:
        """Format top anomalies for AI prompt."""
        if not anomalies:
            return "None"
        
        lines = []
        for a in anomalies[:5]:
            pct = a.percent_variance * 100 if a.percent_variance else 0
            lines.append(f"- Account {a.account_id}: {pct:+.1f}% (z-score: {a.zscore:.2f if a.zscore else 'N/A'})")
        return "\n".join(lines)
