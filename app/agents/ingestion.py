"""
Ingestion Agent
===============
Automatically collects Trial Balance data from configured sources,
validates schema and completeness, and handles ingestion failures.
"""
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional
import pandas as pd

from app.agents.base import BaseAgent
from app.models import (
    AgentType, Account, AccountType, Balance, Entity, 
    MaterialityBand, Period, TrialBalance, ValidationResult, ValidationStatus
)


class IngestionAgent(BaseAgent):
    """
    Autonomous agent for ingesting financial data.
    
    Responsibilities:
    - Parse CSV/Excel trial balance files
    - Validate schema completeness
    - Normalize data to standard format
    - Create or match accounts in chart of accounts
    - Handle currency and entity mapping
    """
    
    # Expected columns in trial balance file
    REQUIRED_COLUMNS = {"account_code", "account_name", "debit", "credit"}
    OPTIONAL_COLUMNS = {"account_type", "currency", "description", "parent_account"}
    
    def __init__(self):
        super().__init__(AgentType.INGESTION)
        self.supported_formats = [".csv", ".xlsx", ".xls"]
    
    def validate_input(self, context: dict[str, Any]) -> bool:
        """Validate that required inputs are present."""
        # Need either file_path or dataframe
        has_file = "file_path" in context and context["file_path"]
        has_df = "dataframe" in context and context["dataframe"] is not None
        has_entity = "entity" in context or "entity_id" in context
        has_period = "period" in context or "period_id" in context
        
        return (has_file or has_df) and has_entity and has_period
    
    async def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        """
        Execute the ingestion pipeline.
        
        Context should contain:
        - file_path: Path to the trial balance file, OR
        - dataframe: Pre-loaded pandas DataFrame
        - entity: Entity object or entity_id
        - period: Period object or period_id
        - account_mapping: Optional dict for account code mapping
        """
        entity = context.get("entity")
        period = context.get("period")
        account_mapping = context.get("account_mapping", {})
        
        # Load data
        if "dataframe" in context and context["dataframe"] is not None:
            df = context["dataframe"]
            source_file = "dataframe_input"
        else:
            file_path = Path(context["file_path"])
            df, source_file = await self._load_file(file_path)
        
        # Validate schema
        schema_result = self._validate_schema(df)
        if schema_result.status == ValidationStatus.FAILED:
            self.log_audit_event(
                event_type="schema_validation_failed",
                payload={"error": schema_result.message},
                entity_id=entity.id if entity else None,
                period_id=period.id if period else None
            )
            return {
                "success": False,
                "validation_result": schema_result.model_dump(),
                "error": schema_result.message
            }
        
        # Normalize column names
        df = self._normalize_columns(df)
        
        # Parse and create balances
        balances, accounts, parse_errors = await self._parse_balances(
            df, entity, period, account_mapping
        )
        
        # Create trial balance summary
        total_debits = sum(b.debit_amount for b in balances)
        total_credits = sum(b.credit_amount for b in balances)
        is_balanced = abs(total_debits - total_credits) < Decimal("0.01")
        
        trial_balance = TrialBalance(
            entity_id=entity.id if entity else context.get("entity_id"),
            period_id=period.id if period else context.get("period_id"),
            balances=balances,
            total_debits=total_debits,
            total_credits=total_credits,
            is_balanced=is_balanced,
            source_file=source_file
        )
        
        # Log success
        self.log_audit_event(
            event_type="ingestion_completed",
            payload={
                "accounts_processed": len(accounts),
                "balances_created": len(balances),
                "total_debits": str(total_debits),
                "total_credits": str(total_credits),
                "is_balanced": is_balanced,
                "parse_errors": len(parse_errors)
            },
            entity_id=trial_balance.entity_id,
            period_id=trial_balance.period_id
        )
        
        return {
            "trial_balance": trial_balance.model_dump(),
            "accounts": [a.model_dump() for a in accounts],
            "validation_result": schema_result.model_dump(),
            "parse_errors": parse_errors,
            "summary": {
                "total_accounts": len(accounts),
                "total_balances": len(balances),
                "total_debits": float(total_debits),
                "total_credits": float(total_credits),
                "is_balanced": is_balanced,
                "balance_difference": float(abs(total_debits - total_credits))
            }
        }
    
    async def _load_file(self, file_path: Path) -> tuple[pd.DataFrame, str]:
        """Load trial balance from file."""
        self.logger.info("loading_file", path=str(file_path))
        
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        suffix = file_path.suffix.lower()
        if suffix not in self.supported_formats:
            raise ValueError(f"Unsupported file format: {suffix}")
        
        if suffix == ".csv":
            df = pd.read_csv(file_path)
        else:
            df = pd.read_excel(file_path)
        
        return df, str(file_path)
    
    def _normalize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalize column names to standard format."""
        # Create mapping for common variations
        column_mapping = {
            "account": "account_code",
            "acc_code": "account_code",
            "account_no": "account_code",
            "gl_account": "account_code",
            "name": "account_name",
            "acc_name": "account_name",
            "description": "account_name",
            "dr": "debit",
            "debit_amount": "debit",
            "cr": "credit",
            "credit_amount": "credit",
            "type": "account_type",
            "acc_type": "account_type",
        }
        
        # Normalize to lowercase first
        df.columns = df.columns.str.lower().str.strip().str.replace(" ", "_")
        
        # Apply mapping
        df = df.rename(columns={
            k: v for k, v in column_mapping.items() if k in df.columns
        })
        
        return df
    
    def _validate_schema(self, df: pd.DataFrame) -> ValidationResult:
        """Validate that required columns are present."""
        df_cols = set(df.columns.str.lower().str.strip().str.replace(" ", "_"))
        
        # Check for required columns (with some flexibility)
        required_found = set()
        for req in self.REQUIRED_COLUMNS:
            if req in df_cols:
                required_found.add(req)
            # Check common alternatives
            elif req == "account_code" and any(c in df_cols for c in ["account", "acc_code", "account_no", "gl_account"]):
                required_found.add(req)
            elif req == "account_name" and any(c in df_cols for c in ["name", "acc_name", "description"]):
                required_found.add(req)
            elif req == "debit" and any(c in df_cols for c in ["dr", "debit_amount"]):
                required_found.add(req)
            elif req == "credit" and any(c in df_cols for c in ["cr", "credit_amount"]):
                required_found.add(req)
        
        missing = self.REQUIRED_COLUMNS - required_found
        
        if missing:
            return ValidationResult(
                check_name="schema_validation",
                status=ValidationStatus.FAILED,
                message=f"Missing required columns: {missing}. Found: {df_cols}",
                confidence=1.0,
                evidence={"missing_columns": list(missing), "found_columns": list(df_cols)}
            )
        
        return ValidationResult(
            check_name="schema_validation",
            status=ValidationStatus.PASSED,
            message="Schema validation passed",
            confidence=1.0,
            evidence={"found_columns": list(df_cols)}
        )
    
    async def _parse_balances(
        self,
        df: pd.DataFrame,
        entity: Optional[Entity],
        period: Optional[Period],
        account_mapping: dict[str, str]
    ) -> tuple[list[Balance], list[Account], list[dict]]:
        """Parse DataFrame rows into Balance and Account objects."""
        balances = []
        accounts = {}
        errors = []
        
        entity_id = entity.id if entity else "unknown"
        period_id = period.id if period else "unknown"
        currency = entity.currency if entity else "USD"
        
        for idx, row in df.iterrows():
            try:
                # Extract account code
                account_code = str(row.get("account_code", "")).strip()
                if not account_code:
                    errors.append({"row": idx, "error": "Missing account code"})
                    continue
                
                # Parse amounts
                debit = self._parse_amount(row.get("debit", 0))
                credit = self._parse_amount(row.get("credit", 0))
                net = debit - credit
                
                # Create or update account
                if account_code not in accounts:
                    account = Account(
                        code=account_code,
                        name=str(row.get("account_name", account_code)),
                        account_type=self._infer_account_type(
                            account_code, 
                            str(row.get("account_type", ""))
                        ),
                        materiality_band=self._calculate_materiality_band(net),
                        mapping_key=account_mapping.get(account_code)
                    )
                    accounts[account_code] = account
                
                # Create balance - use account CODE as account_id for period matching
                balance = Balance(
                    account_id=account_code,  # Use code, not UUID, for variance matching
                    period_id=period_id,
                    entity_id=entity_id,
                    debit_amount=debit,
                    credit_amount=credit,
                    net_amount=net,
                    currency=currency
                )
                balances.append(balance)
                
            except Exception as e:
                errors.append({"row": idx, "error": str(e)})
        
        return balances, list(accounts.values()), errors
    
    def _parse_amount(self, value: Any) -> Decimal:
        """Parse a value into a Decimal amount."""
        if pd.isna(value) or value == "" or value is None:
            return Decimal("0")
        
        if isinstance(value, (int, float)):
            return Decimal(str(value))
        
        # Handle string with currency symbols
        cleaned = str(value).replace(",", "").replace("$", "").replace("€", "").strip()
        if cleaned == "" or cleaned == "-":
            return Decimal("0")
        
        return Decimal(cleaned)
    
    def _infer_account_type(self, code: str, type_hint: str) -> AccountType:
        """Infer account type from code pattern or hint."""
        # Check explicit type hint first
        type_lower = type_hint.lower()
        if "asset" in type_lower:
            return AccountType.ASSET
        elif "liab" in type_lower:
            return AccountType.LIABILITY
        elif "equity" in type_lower or "capital" in type_lower:
            return AccountType.EQUITY
        elif "rev" in type_lower or "income" in type_lower:
            return AccountType.REVENUE
        elif "exp" in type_lower or "cost" in type_lower:
            return AccountType.EXPENSE
        
        # Infer from common account code patterns
        first_digit = code[0] if code else ""
        if first_digit == "1":
            return AccountType.ASSET
        elif first_digit == "2":
            return AccountType.LIABILITY
        elif first_digit == "3":
            return AccountType.EQUITY
        elif first_digit == "4":
            return AccountType.REVENUE
        elif first_digit in ("5", "6", "7", "8"):
            return AccountType.EXPENSE
        
        return AccountType.ASSET  # Default
    
    def _calculate_materiality_band(self, amount: Decimal) -> MaterialityBand:
        """Calculate materiality band based on amount."""
        abs_amount = abs(amount)
        
        if abs_amount >= Decimal("1000000"):
            return MaterialityBand.HIGH
        elif abs_amount >= Decimal("100000"):
            return MaterialityBand.MEDIUM
        elif abs_amount >= Decimal("10000"):
            return MaterialityBand.LOW
        else:
            return MaterialityBand.IMMATERIAL
