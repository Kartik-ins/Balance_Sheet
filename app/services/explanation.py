"""
Explanation Service
===================
Generates natural language explanations backed by evidence.
Uses LLM for text generation with strict grounding in facts.
"""
from datetime import datetime
from typing import Any, Optional
import json
import structlog

from app.models import Decision, Finding, VarianceAnalysis, EvidencePack
from app.config import get_settings


class ExplanationService:
    """
    Service for generating evidence-grounded explanations.
    
    Features:
    - Structured evidence retrieval
    - LLM-based explanation generation
    - Grounding validation
    - Multi-format output
    """
    
    def __init__(self):
        self.logger = structlog.get_logger().bind(service="explanation")
        self.settings = get_settings()
        self._openrouter_client = None
    
    def _get_openrouter_client(self):
        """Lazy-load OpenRouter client (uses OpenAI SDK with custom base URL)."""
        if self._openrouter_client is None and self.settings.openrouter_api_key:
            try:
                from openai import OpenAI
                self._openrouter_client = OpenAI(
                    api_key=self.settings.openrouter_api_key,
                    base_url=self.settings.openrouter_base_url,
                    default_headers={
                        "HTTP-Referer": "https://github.com/Kartik-ins/Balance_Sheet",
                        "X-Title": "Financial Assurance Platform"
                    }
                )
            except ImportError:
                self.logger.warning("openai_sdk_not_installed")
        return self._openrouter_client
    
    def generate_decision_explanation(
        self,
        decision: dict | Decision,
        include_evidence: bool = True
    ) -> dict:
        """
        Generate explanation for a decision.
        
        Returns structured explanation with:
        - Summary (1-2 sentences)
        - Key factors
        - Evidence references
        - Recommendation
        """
        if isinstance(decision, Decision):
            decision_dict = decision.model_dump()
        else:
            decision_dict = decision
        
        evidence = decision_dict.get("evidence_pack", {})
        
        # Build explanation from evidence
        explanation = self._build_decision_explanation(decision_dict, evidence)
        
        # Optionally enhance with LLM via OpenRouter
        if self._get_openrouter_client():
            explanation = self._enhance_with_llm(explanation, "decision")
        
        return explanation
    
    def generate_variance_explanation(
        self,
        variance: dict | VarianceAnalysis,
        account_name: Optional[str] = None
    ) -> dict:
        """Generate explanation for a variance analysis."""
        if isinstance(variance, VarianceAnalysis):
            variance_dict = variance.model_dump()
        else:
            variance_dict = variance
        
        explanation = self._build_variance_explanation(variance_dict, account_name)
        
        if self._get_openrouter_client():
            explanation = self._enhance_with_llm(explanation, "variance")
        
        return explanation
    
    def generate_finding_explanation(
        self,
        finding: dict | Finding
    ) -> dict:
        """Generate explanation for a finding."""
        if isinstance(finding, Finding):
            finding_dict = finding.model_dump()
        else:
            finding_dict = finding
        
        explanation = self._build_finding_explanation(finding_dict)
        
        return explanation
    
    def _build_decision_explanation(
        self,
        decision: dict,
        evidence: dict
    ) -> dict:
        """Build structured decision explanation from evidence."""
        action = decision.get("action", "unknown")
        risk_score = decision.get("risk_score", 0)
        confidence = decision.get("confidence", 0)
        rationale = decision.get("rationale", "")
        
        # Extract key factors from risk components
        variance_info = evidence.get("variance", {})
        validation_results = evidence.get("validation_results", [])
        findings = evidence.get("findings", [])
        
        key_factors = []
        
        # Add variance factor if relevant
        if variance_info:
            pct = variance_info.get("percent_variance")
            if pct is not None:
                direction = "increased" if pct > 0 else "decreased"
                key_factors.append(
                    f"Balance {direction} by {abs(pct):.1%} from prior period"
                )
            if variance_info.get("is_anomaly"):
                key_factors.append("Variance flagged as anomalous")
        
        # Add validation factors
        failed_validations = [v for v in validation_results if v.get("status") == "failed"]
        if failed_validations:
            for v in failed_validations[:2]:
                key_factors.append(f"Failed: {v.get('check', 'validation check')}")
        
        # Add finding factors
        for finding in findings[:2]:
            key_factors.append(finding.get("description", "Issue detected"))
        
        # Build recommendation
        if action == "auto_approved":
            recommendation = "No action required. Item has been automatically approved."
        elif action == "escalated":
            recommendation = "Review required. Please examine the flagged items and provide feedback."
        else:
            recommendation = "Pending review. Please verify and approve or reject."
        
        return {
            "summary": rationale or f"Decision: {action} with risk score {risk_score:.2f}",
            "action": action,
            "risk_score": risk_score,
            "confidence": confidence,
            "key_factors": key_factors,
            "recommendation": recommendation,
            "evidence_summary": {
                "has_variance_data": bool(variance_info),
                "validation_checks": len(validation_results),
                "findings_count": len(findings)
            }
        }
    
    def _build_variance_explanation(
        self,
        variance: dict,
        account_name: Optional[str] = None
    ) -> dict:
        """Build variance explanation from data."""
        current = variance.get("current_amount", 0)
        prior = variance.get("prior_amount", 0)
        absolute = variance.get("absolute_variance", 0)
        percent = variance.get("percent_variance")
        zscore = variance.get("zscore")
        is_anomaly = variance.get("is_anomaly", False)
        trend = variance.get("trend_direction", "stable")
        
        # Build narrative
        name = account_name or "This account"
        
        if absolute > 0:
            direction = "increased"
        elif absolute < 0:
            direction = "decreased"
        else:
            direction = "remained unchanged"
        
        parts = [f"{name} {direction}"]
        
        if percent is not None:
            parts.append(f"by {abs(percent):.1%}")
        
        parts.append(f"(${abs(float(absolute)):,.0f})")
        
        if zscore is not None:
            if abs(zscore) > 2:
                parts.append(f"This is {abs(zscore):.1f} standard deviations from historical average.")
            else:
                parts.append("This is within normal historical range.")
        
        narrative = " ".join(parts)
        
        # Risk assessment
        if is_anomaly:
            risk_level = "high"
            action = "Review recommended"
        elif percent and abs(percent) > 0.15:
            risk_level = "medium"
            action = "Monitor"
        else:
            risk_level = "low"
            action = "No action needed"
        
        return {
            "narrative": narrative,
            "current_amount": float(current) if current else 0,
            "prior_amount": float(prior) if prior else 0,
            "change_amount": float(absolute) if absolute else 0,
            "change_percent": percent,
            "zscore": zscore,
            "trend": trend,
            "is_anomaly": is_anomaly,
            "risk_level": risk_level,
            "recommended_action": action
        }
    
    def _build_finding_explanation(self, finding: dict) -> dict:
        """Build finding explanation."""
        finding_type = finding.get("finding_type", "unknown")
        severity = finding.get("severity", 0.5)
        description = finding.get("description", "")
        evidence = finding.get("evidence", {})
        
        # Severity level
        if severity >= 0.8:
            severity_label = "Critical"
        elif severity >= 0.6:
            severity_label = "High"
        elif severity >= 0.4:
            severity_label = "Medium"
        else:
            severity_label = "Low"
        
        # Type-specific guidance
        guidance = {
            "zero_balance_violation": "Verify that all journal entries are complete and properly recorded.",
            "variance_spike": "Investigate the cause of the significant increase.",
            "variance_drop": "Investigate the cause of the significant decrease.",
            "mapping_inconsistency": "Review account mapping configuration.",
            "sign_violation": "Verify the account balance sign is correct for the account type.",
            "classification_error": "Review account classification in chart of accounts.",
        }
        
        return {
            "type": finding_type,
            "severity": severity,
            "severity_label": severity_label,
            "description": description,
            "guidance": guidance.get(finding_type, "Review the finding and take appropriate action."),
            "evidence": evidence
        }
    
    def _enhance_with_llm(self, explanation: dict, context_type: str) -> dict:
        """Enhance explanation using LLM via OpenRouter."""
        client = self._get_openrouter_client()
        if not client:
            return explanation
        
        try:
            # Build prompt with strict grounding
            system_prompt = """You are a financial assurance assistant. 
Generate clear, professional explanations based ONLY on the provided evidence.
Do not make claims that aren't supported by the data.
Keep explanations concise and actionable."""
            
            user_prompt = f"""Based on this {context_type} analysis, provide a brief professional explanation:

Data:
{json.dumps(explanation, indent=2, default=str)}

Provide a 2-3 sentence summary that a finance professional would understand."""
            
            response = client.chat.completions.create(
                model=self.settings.openrouter_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=200,
                temperature=0.3
            )
            
            enhanced_summary = response.choices[0].message.content
            explanation["enhanced_summary"] = enhanced_summary
            
        except Exception as e:
            self.logger.warning("llm_enhancement_failed", error=str(e))
        
        return explanation


# Global instance
_explanation_service: Optional[ExplanationService] = None


def get_explanation_service() -> ExplanationService:
    """Get global explanation service instance."""
    global _explanation_service
    if _explanation_service is None:
        _explanation_service = ExplanationService()
    return _explanation_service
