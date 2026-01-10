"""
Validation Agent
================
Performs comprehensive financial data validation including zero-balance checks,
GL hygiene, classification consistency, and structural integrity validation.
"""
from datetime import datetime
from decimal import Decimal
from typing import Any
import structlog

from app.agents.base import BaseAgent
from app.models import (
    AgentType, AccountType, Balance, Finding, FindingType,
    TrialBalance, ValidationResult, ValidationStatus
)
from app.config import get_settings


class ValidationAgent(BaseAgent):
    """
    Autonomous agent for financial data validation.
    
    Performs:
    - Zero-balance (debit/credit) validation
    - Sign convention checks
    - Account classification consistency
    - GL hygiene validation
    - Structural integrity checks
    - Completeness validation
    """
    
    # Expected sign conventions by account type
    EXPECTED_SIGNS = {
        AccountType.ASSET: "debit",      # Assets normally have debit balances
        AccountType.EXPENSE: "debit",    # Expenses normally have debit balances
        AccountType.LIABILITY: "credit", # Liabilities normally have credit balances
        AccountType.EQUITY: "credit",    # Equity normally has credit balances
        AccountType.REVENUE: "credit",   # Revenue normally has credit balances
    }
    
    def __init__(self):
        super().__init__(AgentType.VALIDATION)
        self.settings = get_settings()
    
    def validate_input(self, context: dict[str, Any]) -> bool:
        """Validate that required inputs are present."""
        return "trial_balance" in context or "balances" in context
    
    async def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        """
        Execute validation checks on trial balance data.
        
        Context should contain:
        - trial_balance: TrialBalance object or dict
        - balances: List of Balance objects (if no trial_balance)
        - accounts: Optional dict mapping account_id to Account
        - entity_id: Entity identifier
        - period_id: Period identifier
        """
        # Extract data
        if "trial_balance" in context:
            tb = context["trial_balance"]
            if isinstance(tb, dict):
                trial_balance = TrialBalance(**tb)
            else:
                trial_balance = tb
            balances = trial_balance.balances
        else:
            balances = context["balances"]
            trial_balance = None
        
        accounts = context.get("accounts", {})
        entity_id = context.get("entity_id", trial_balance.entity_id if trial_balance else None)
        period_id = context.get("period_id", trial_balance.period_id if trial_balance else None)
        
        # Run all validation checks
        validation_results = []
        findings = []
        
        # 1. Zero-balance check
        zb_result, zb_findings = await self._check_zero_balance(balances, entity_id, period_id)
        validation_results.append(zb_result)
        findings.extend(zb_findings)
        
        # 2. Sign convention check
        sign_result, sign_findings = await self._check_sign_conventions(
            balances, accounts, entity_id, period_id
        )
        validation_results.append(sign_result)
        findings.extend(sign_findings)
        
        # 3. Classification consistency
        class_result, class_findings = await self._check_classification_consistency(
            balances, accounts, entity_id, period_id
        )
        validation_results.append(class_result)
        findings.extend(class_findings)
        
        # 4. Completeness check
        complete_result, complete_findings = await self._check_completeness(
            balances, entity_id, period_id
        )
        validation_results.append(complete_result)
        findings.extend(complete_findings)
        
        # 5. Data quality check
        quality_result, quality_findings = await self._check_data_quality(
            balances, entity_id, period_id
        )
        validation_results.append(quality_result)
        findings.extend(quality_findings)
        
        # Calculate overall validation score
        passed_checks = sum(1 for r in validation_results if r.status == ValidationStatus.PASSED)
        total_checks = len(validation_results)
        overall_score = passed_checks / total_checks if total_checks > 0 else 0.0
        
        # Determine overall status
        if any(r.status == ValidationStatus.FAILED for r in validation_results):
            overall_status = ValidationStatus.FAILED
        elif any(r.status == ValidationStatus.WARNING for r in validation_results):
            overall_status = ValidationStatus.WARNING
        else:
            overall_status = ValidationStatus.PASSED
        
        # Log audit event
        self.log_audit_event(
            event_type="validation_completed",
            payload={
                "checks_run": total_checks,
                "checks_passed": passed_checks,
                "findings_count": len(findings),
                "overall_status": overall_status.value,
                "overall_score": overall_score
            },
            entity_id=entity_id,
            period_id=period_id
        )
        
        return {
            "validation_results": [r.model_dump() for r in validation_results],
            "findings": [f.model_dump() for f in findings],
            "summary": {
                "total_checks": total_checks,
                "passed_checks": passed_checks,
                "failed_checks": total_checks - passed_checks,
                "findings_count": len(findings),
                "overall_status": overall_status.value,
                "overall_score": overall_score
            }
        }
    
    async def _check_zero_balance(
        self, 
        balances: list[Balance], 
        entity_id: str, 
        period_id: str
    ) -> tuple[ValidationResult, list[Finding]]:
        """Check that total debits equal total credits."""
        findings = []
        
        total_debits = sum(b.debit_amount for b in balances)
        total_credits = sum(b.credit_amount for b in balances)
        difference = abs(total_debits - total_credits)
        
        # Allow for small rounding differences
        is_balanced = difference < Decimal("0.01")
        
        if is_balanced:
            result = ValidationResult(
                check_name="zero_balance",
                status=ValidationStatus.PASSED,
                message="Trial balance is in balance (debits = credits)",
                confidence=1.0,
                evidence={
                    "total_debits": float(total_debits),
                    "total_credits": float(total_credits),
                    "difference": float(difference)
                }
            )
        else:
            result = ValidationResult(
                check_name="zero_balance",
                status=ValidationStatus.FAILED,
                message=f"Trial balance out of balance by {difference}",
                confidence=1.0,
                evidence={
                    "total_debits": float(total_debits),
                    "total_credits": float(total_credits),
                    "difference": float(difference)
                }
            )
            
            findings.append(Finding(
                finding_type=FindingType.ZERO_BALANCE_VIOLATION,
                account_id="ALL",
                period_id=period_id,
                entity_id=entity_id,
                severity=0.9,
                magnitude=float(difference),
                description=f"Trial balance is out of balance. Debits ({total_debits}) ≠ Credits ({total_credits}). Difference: {difference}",
                evidence={
                    "total_debits": float(total_debits),
                    "total_credits": float(total_credits),
                    "difference": float(difference)
                },
                detected_by=AgentType.VALIDATION
            ))
        
        return result, findings
    
    async def _check_sign_conventions(
        self,
        balances: list[Balance],
        accounts: dict[str, Any],
        entity_id: str,
        period_id: str
    ) -> tuple[ValidationResult, list[Finding]]:
        """Check that account balances follow expected sign conventions."""
        findings = []
        violations = []
        
        for balance in balances:
            account = accounts.get(balance.account_id)
            if not account:
                continue
            
            account_type = account.account_type if hasattr(account, 'account_type') else account.get('account_type')
            if isinstance(account_type, str):
                try:
                    account_type = AccountType(account_type)
                except ValueError:
                    continue
            
            expected_sign = self.EXPECTED_SIGNS.get(account_type)
            if not expected_sign:
                continue
            
            net = balance.net_amount
            if net == 0:
                continue
            
            actual_sign = "debit" if net > 0 else "credit"
            
            if actual_sign != expected_sign and abs(net) > Decimal("100"):
                violations.append({
                    "account_id": balance.account_id,
                    "account_type": account_type.value,
                    "expected_sign": expected_sign,
                    "actual_sign": actual_sign,
                    "net_amount": float(net)
                })
                
                findings.append(Finding(
                    finding_type=FindingType.SIGN_VIOLATION,
                    account_id=balance.account_id,
                    period_id=period_id,
                    entity_id=entity_id,
                    severity=0.6,
                    magnitude=float(abs(net)),
                    description=f"Account has unexpected {actual_sign} balance. {account_type.value} accounts typically have {expected_sign} balances.",
                    evidence={
                        "expected_sign": expected_sign,
                        "actual_sign": actual_sign,
                        "net_amount": float(net)
                    },
                    detected_by=AgentType.VALIDATION
                ))
        
        if not violations:
            result = ValidationResult(
                check_name="sign_conventions",
                status=ValidationStatus.PASSED,
                message="All accounts follow expected sign conventions",
                confidence=0.95,
                evidence={"accounts_checked": len(balances)}
            )
        else:
            result = ValidationResult(
                check_name="sign_conventions",
                status=ValidationStatus.WARNING,
                message=f"{len(violations)} accounts have unexpected sign balances",
                confidence=0.9,
                affected_accounts=[v["account_id"] for v in violations],
                evidence={"violations": violations}
            )
        
        return result, findings
    
    async def _check_classification_consistency(
        self,
        balances: list[Balance],
        accounts: dict[str, Any],
        entity_id: str,
        period_id: str
    ) -> tuple[ValidationResult, list[Finding]]:
        """Check for classification inconsistencies."""
        findings = []
        issues = []
        
        # Group accounts by code prefix to detect inconsistencies
        prefix_types: dict[str, set] = {}
        
        for balance in balances:
            account = accounts.get(balance.account_id)
            if not account:
                continue
            
            code = account.code if hasattr(account, 'code') else account.get('code', '')
            account_type = account.account_type if hasattr(account, 'account_type') else account.get('account_type')
            
            if len(code) >= 2:
                prefix = code[:2]
                if prefix not in prefix_types:
                    prefix_types[prefix] = set()
                prefix_types[prefix].add(str(account_type))
        
        # Check for prefixes with multiple account types
        for prefix, types in prefix_types.items():
            if len(types) > 1:
                issues.append({
                    "prefix": prefix,
                    "types_found": list(types)
                })
        
        if not issues:
            result = ValidationResult(
                check_name="classification_consistency",
                status=ValidationStatus.PASSED,
                message="Account classifications are consistent",
                confidence=0.9,
                evidence={"prefixes_checked": len(prefix_types)}
            )
        else:
            result = ValidationResult(
                check_name="classification_consistency",
                status=ValidationStatus.WARNING,
                message=f"{len(issues)} account code prefixes have mixed classifications",
                confidence=0.8,
                evidence={"issues": issues}
            )
            
            for issue in issues:
                findings.append(Finding(
                    finding_type=FindingType.CLASSIFICATION_ERROR,
                    account_id=f"prefix_{issue['prefix']}",
                    period_id=period_id,
                    entity_id=entity_id,
                    severity=0.4,
                    description=f"Account code prefix '{issue['prefix']}' has multiple account types: {issue['types_found']}",
                    evidence=issue,
                    detected_by=AgentType.VALIDATION
                ))
        
        return result, findings
    
    async def _check_completeness(
        self,
        balances: list[Balance],
        entity_id: str,
        period_id: str
    ) -> tuple[ValidationResult, list[Finding]]:
        """Check for data completeness issues."""
        findings = []
        issues = []
        
        # Check for zero balances (might indicate missing data)
        zero_balance_count = sum(1 for b in balances if b.debit_amount == 0 and b.credit_amount == 0)
        
        # Check for missing amounts
        missing_amounts = sum(1 for b in balances if b.debit_amount == 0 and b.credit_amount == 0)
        
        total_balances = len(balances)
        completeness_ratio = (total_balances - zero_balance_count) / total_balances if total_balances > 0 else 0
        
        if completeness_ratio >= 0.95:
            result = ValidationResult(
                check_name="completeness",
                status=ValidationStatus.PASSED,
                message="Data completeness check passed",
                confidence=completeness_ratio,
                evidence={
                    "total_balances": total_balances,
                    "zero_balance_count": zero_balance_count,
                    "completeness_ratio": completeness_ratio
                }
            )
        elif completeness_ratio >= 0.8:
            result = ValidationResult(
                check_name="completeness",
                status=ValidationStatus.WARNING,
                message=f"{zero_balance_count} accounts have zero balances",
                confidence=completeness_ratio,
                evidence={
                    "total_balances": total_balances,
                    "zero_balance_count": zero_balance_count,
                    "completeness_ratio": completeness_ratio
                }
            )
        else:
            result = ValidationResult(
                check_name="completeness",
                status=ValidationStatus.FAILED,
                message=f"Low data completeness: {completeness_ratio:.1%}",
                confidence=completeness_ratio,
                evidence={
                    "total_balances": total_balances,
                    "zero_balance_count": zero_balance_count,
                    "completeness_ratio": completeness_ratio
                }
            )
        
        return result, findings
    
    async def _check_data_quality(
        self,
        balances: list[Balance],
        entity_id: str,
        period_id: str
    ) -> tuple[ValidationResult, list[Finding]]:
        """Check for data quality issues."""
        findings = []
        issues = []
        
        for balance in balances:
            # Check for unusually large amounts (potential data entry errors)
            if abs(balance.net_amount) > Decimal("1000000000"):  # 1 billion
                issues.append({
                    "account_id": balance.account_id,
                    "issue": "unusually_large_amount",
                    "amount": float(balance.net_amount)
                })
            
            # Check for unusual precision
            net_str = str(balance.net_amount)
            if "." in net_str and len(net_str.split(".")[1]) > 2:
                issues.append({
                    "account_id": balance.account_id,
                    "issue": "unusual_precision",
                    "amount": float(balance.net_amount)
                })
        
        if not issues:
            result = ValidationResult(
                check_name="data_quality",
                status=ValidationStatus.PASSED,
                message="No data quality issues detected",
                confidence=0.95,
                evidence={"balances_checked": len(balances)}
            )
        else:
            result = ValidationResult(
                check_name="data_quality",
                status=ValidationStatus.WARNING,
                message=f"{len(issues)} potential data quality issues found",
                confidence=0.85,
                evidence={"issues": issues[:10]}  # Limit to first 10
            )
        
        return result, findings
