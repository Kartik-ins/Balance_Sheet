"""
Database Initialization Script
==============================
Run this to set up the database and seed with sample data.

Usage:
    python -m scripts.init_db
    python -m scripts.init_db --seed
    python -m scripts.init_db --reset
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
from datetime import datetime, timedelta
import random
from decimal import Decimal

from app.services.db import init_db, drop_db, get_db
from app.models.database import (
    EntityModel, PeriodModel, BalanceModel, 
    DecisionModel, AuditLogModel, PeriodStatus
)


def create_sample_entity(db) -> EntityModel:
    """Create sample entity."""
    entity = EntityModel(
        code="ACME-001",
        name="ACME Corporation",
        currency="USD",
        is_active=True
    )
    db.add(entity)
    db.flush()
    print(f"✅ Created entity: {entity.code}")
    return entity


def create_sample_periods(db, entity: EntityModel) -> list[PeriodModel]:
    """Create sample periods for last 4 quarters."""
    periods = []
    
    # Create Q1-Q4 2025
    quarters = [
        ("2025-Q1", datetime(2025, 1, 1), datetime(2025, 3, 31)),
        ("2025-Q2", datetime(2025, 4, 1), datetime(2025, 6, 30)),
        ("2025-Q3", datetime(2025, 7, 1), datetime(2025, 9, 30)),
        ("2025-Q4", datetime(2025, 10, 1), datetime(2025, 12, 31)),
    ]
    
    for name, start, end in quarters:
        period = PeriodModel(
            entity_id=entity.id,
            name=name,
            start_date=start,
            end_date=end,
            status=PeriodStatus.COMPLETED.value
        )
        db.add(period)
        periods.append(period)
    
    db.flush()
    print(f"✅ Created {len(periods)} periods")
    return periods


def create_sample_balances(db, period: PeriodModel, prior_period: PeriodModel = None) -> list[BalanceModel]:
    """Create sample trial balance with realistic accounts."""
    
    # Chart of accounts with typical balances
    chart_of_accounts = [
        # Assets
        ("1010", "Cash and Cash Equivalents", "asset", 5_250_000),
        ("1020", "Accounts Receivable", "asset", 3_200_000),
        ("1025", "Allowance for Doubtful Accounts", "asset", -150_000),
        ("1030", "Inventory - Raw Materials", "asset", 1_800_000),
        ("1031", "Inventory - Work in Progress", "asset", 650_000),
        ("1032", "Inventory - Finished Goods", "asset", 1_350_000),
        ("1040", "Prepaid Expenses", "asset", 450_000),
        ("1050", "Short-term Investments", "asset", 1_500_000),
        ("1060", "Notes Receivable - Current", "asset", 250_000),
        ("1100", "Land", "asset", 2_500_000),
        ("1110", "Buildings", "asset", 8_500_000),
        ("1111", "Accumulated Depreciation - Buildings", "asset", -1_200_000),
        ("1120", "Machinery and Equipment", "asset", 4_500_000),
        ("1121", "Accumulated Depreciation - Equipment", "asset", -1_800_000),
        ("1130", "Vehicles", "asset", 850_000),
        ("1131", "Accumulated Depreciation - Vehicles", "asset", -350_000),
        ("1140", "Furniture and Fixtures", "asset", 450_000),
        ("1141", "Accumulated Depreciation - Furniture", "asset", -180_000),
        ("1150", "Leasehold Improvements", "asset", 750_000),
        ("1200", "Intangible Assets - Patents", "asset", 1_200_000),
        ("1210", "Intangible Assets - Trademarks", "asset", 800_000),
        ("1220", "Goodwill", "asset", 3_500_000),
        ("1230", "Accumulated Amortization", "asset", -450_000),
        ("1300", "Long-term Investments", "asset", 2_800_000),
        ("1400", "Deferred Tax Assets", "asset", 380_000),
        
        # Liabilities
        ("2010", "Accounts Payable", "liability", 1_850_000),
        ("2020", "Accrued Liabilities", "liability", 920_000),
        ("2025", "Accrued Payroll", "liability", 680_000),
        ("2030", "Short-term Debt", "liability", 500_000),
        ("2040", "Current Portion of Long-term Debt", "liability", 750_000),
        ("2050", "Income Tax Payable", "liability", 420_000),
        ("2060", "Unearned Revenue", "liability", 380_000),
        ("2070", "Customer Deposits", "liability", 150_000),
        ("2080", "Dividends Payable", "liability", 200_000),
        ("2100", "Long-term Debt", "liability", 8_500_000),
        ("2110", "Bonds Payable", "liability", 5_000_000),
        ("2120", "Mortgage Payable", "liability", 3_200_000),
        ("2200", "Deferred Tax Liabilities", "liability", 890_000),
        ("2300", "Pension Liability", "liability", 1_450_000),
        ("2400", "Lease Liabilities", "liability", 1_100_000),
        
        # Equity
        ("3010", "Common Stock", "equity", 5_000_000),
        ("3020", "Preferred Stock", "equity", 1_000_000),
        ("3030", "Additional Paid-in Capital", "equity", 4_500_000),
        ("3040", "Retained Earnings", "equity", 8_750_000),
        ("3050", "Treasury Stock", "equity", -500_000),
        ("3060", "Accumulated Other Comprehensive Income", "equity", 180_000),
        
        # Revenue
        ("4010", "Product Sales Revenue", "revenue", 28_500_000),
        ("4020", "Service Revenue", "revenue", 8_200_000),
        ("4030", "Subscription Revenue", "revenue", 3_500_000),
        ("4040", "Licensing Revenue", "revenue", 1_200_000),
        ("4100", "Sales Returns and Allowances", "revenue", -850_000),
        ("4110", "Sales Discounts", "revenue", -420_000),
        ("4200", "Interest Income", "revenue", 125_000),
        ("4210", "Dividend Income", "revenue", 85_000),
        ("4300", "Gain on Sale of Assets", "revenue", 150_000),
        ("4400", "Other Revenue", "revenue", 280_000),
        
        # Expenses
        ("5010", "Cost of Goods Sold - Materials", "expense", 12_500_000),
        ("5020", "Cost of Goods Sold - Labor", "expense", 4_800_000),
        ("5030", "Cost of Goods Sold - Overhead", "expense", 2_200_000),
        ("6010", "Salaries and Wages Expense", "expense", 6_500_000),
        ("6020", "Employee Benefits Expense", "expense", 1_300_000),
        ("6030", "Payroll Tax Expense", "expense", 520_000),
        ("6100", "Rent Expense", "expense", 960_000),
        ("6110", "Utilities Expense", "expense", 280_000),
        ("6120", "Insurance Expense", "expense", 450_000),
        ("6130", "Repairs and Maintenance", "expense", 380_000),
        ("6200", "Depreciation Expense", "expense", 1_850_000),
        ("6210", "Amortization Expense", "expense", 320_000),
        ("6300", "Advertising Expense", "expense", 1_200_000),
        ("6310", "Marketing Expense", "expense", 850_000),
        ("6400", "Professional Fees", "expense", 420_000),
        ("6410", "Legal Fees", "expense", 280_000),
        ("6420", "Accounting Fees", "expense", 180_000),
        ("6500", "Office Supplies", "expense", 95_000),
        ("6510", "Postage and Shipping", "expense", 125_000),
        ("6520", "Telephone and Internet", "expense", 68_000),
        ("6600", "Travel Expense", "expense", 320_000),
        ("6610", "Meals and Entertainment", "expense", 85_000),
        ("6700", "Bad Debt Expense", "expense", 180_000),
        ("6800", "Interest Expense", "expense", 850_000),
        ("6900", "Income Tax Expense", "expense", 1_250_000),
        ("6950", "Other Operating Expenses", "expense", 420_000),
    ]
    
    balances = []
    
    for code, name, acc_type, base_amount in chart_of_accounts:
        # Add some variance (±5% to ±25%)
        variance_pct = random.uniform(-0.15, 0.20)
        amount = base_amount * (1 + variance_pct)
        
        # Determine debit/credit based on account type and sign
        if acc_type in ["asset", "expense"]:
            debit = max(0, amount)
            credit = max(0, -amount)
        else:  # liability, equity, revenue
            debit = max(0, -amount)
            credit = max(0, amount)
        
        net = debit - credit
        
        # Calculate variance from prior if available
        prior_balance = None
        variance_amount = None
        variance_percent = None
        zscore = None
        is_anomaly = False
        
        if prior_period:
            # Simulate prior period balance
            prior_variance = random.uniform(-0.10, 0.10)
            prior_balance = base_amount * (1 + prior_variance)
            variance_amount = net - prior_balance
            if abs(prior_balance) > 0:
                variance_percent = variance_amount / abs(prior_balance)
            
            # Random z-score, some anomalies
            zscore = random.gauss(0, 1)
            if random.random() < 0.05:  # 5% anomaly rate
                zscore = random.choice([-3.5, 3.2, -4.1, 2.8])
                is_anomaly = True
        
        balance = BalanceModel(
            period_id=period.id,
            account_code=code,
            account_name=name,
            account_type=acc_type,
            debit=round(debit, 2),
            credit=round(credit, 2),
            net_balance=round(net, 2),
            currency="USD",
            prior_balance=round(prior_balance, 2) if prior_balance else None,
            variance_amount=round(variance_amount, 2) if variance_amount else None,
            variance_percent=round(variance_percent, 4) if variance_percent else None,
            zscore=round(zscore, 3) if zscore else None,
            is_anomaly=is_anomaly
        )
        db.add(balance)
        balances.append(balance)
    
    db.flush()
    
    # Update period stats
    period.total_accounts = len(balances)
    
    print(f"✅ Created {len(balances)} balance entries for {period.name}")
    return balances


def create_sample_decisions(db, period: PeriodModel, balances: list[BalanceModel]) -> list[DecisionModel]:
    """Create sample decisions for balances."""
    from app.models.database import FeedbackModel
    
    decisions = []
    
    # Sample 30% of accounts for decisions
    sample_balances = random.sample(balances, min(25, len(balances)))
    
    for balance in sample_balances:
        # Determine action based on variance/risk
        risk_score = random.uniform(0.1, 0.95)
        
        if risk_score < 0.3:
            action = "auto_approved"
        elif risk_score < 0.6:
            action = "auto_approved"
        elif risk_score < 0.8:
            action = "escalate_review"
        else:
            action = "escalate_senior"
        
        decision = DecisionModel(
            period_id=period.id,
            account_code=balance.account_code,
            action=action,
            risk_score=round(risk_score, 3),
            confidence_score=round(random.uniform(0.65, 0.98), 3),
            validation_risk=round(random.uniform(0.0, 0.5), 3),
            variance_risk=round(random.uniform(0.0, 0.7), 3),
            materiality_risk=round(random.uniform(0.1, 0.6), 3),
            data_quality_risk=round(random.uniform(0.0, 0.3), 3),
            rationale=f"Risk assessment for {balance.account_name}. " + 
                     ("Low risk - automated approval." if risk_score < 0.4 else
                      "Moderate risk - standard review." if risk_score < 0.7 else
                      "High risk - senior review required."),
            created_at=datetime.utcnow() - timedelta(days=random.randint(1, 30))
        )
        db.add(decision)
        decisions.append(decision)
    
    db.flush()
    print(f"✅ Created {len(decisions)} decisions for {period.name}")
    return decisions


def create_sample_feedback(db, decisions: list[DecisionModel]) -> int:
    """Create sample feedback with some overrides."""
    from app.models.database import FeedbackModel
    
    feedback_count = 0
    
    # Add feedback for ~40% of decisions
    sample_decisions = random.sample(decisions, min(15, len(decisions) // 2 + 1))
    
    feedback_types = [
        ("approved", 0.6),      # 60% approved as-is
        ("override_approved", 0.15),  # 15% overridden to approve
        ("override_rejected", 0.10),  # 10% overridden to reject
        ("comment", 0.15),      # 15% just comments
    ]
    
    override_reasons = [
        "Historical pattern supports this variance",
        "Known seasonal fluctuation - approved",
        "Confirmed with business unit manager",
        "Documentation verified - no issues",
        "One-time transaction properly documented",
        "Variance explained by new contract",
        "Prior year comparison shows consistent trend",
        "Risk threshold too conservative for this account",
        "False positive - normal business operation",
        "Threshold adjustment needed for this account type",
    ]
    
    approval_reasons = [
        "Verified supporting documentation",
        "Reconciliation confirmed accurate",
        "No material issues found",
        "Approved per review procedures",
    ]
    
    for decision in sample_decisions:
        # Weighted random selection
        r = random.random()
        cumulative = 0
        selected_type = "approved"
        for ftype, weight in feedback_types:
            cumulative += weight
            if r < cumulative:
                selected_type = ftype
                break
        
        was_override = selected_type in ("override_approved", "override_rejected")
        
        if was_override:
            reason = random.choice(override_reasons)
        elif selected_type == "comment":
            reason = "Additional review notes: " + random.choice(approval_reasons)
        else:
            reason = random.choice(approval_reasons)
        
        feedback = FeedbackModel(
            decision_id=decision.id,
            user_id=random.choice(["john.auditor", "jane.reviewer", "mike.senior", "sarah.manager"]),
            feedback_type=selected_type,
            reason=reason,
            was_override=was_override,
            original_action=decision.action if was_override else None,
            created_at=datetime.utcnow() - timedelta(days=random.randint(0, 25))
        )
        db.add(feedback)
        feedback_count += 1
    
    db.flush()
    return feedback_count


def create_detailed_audit_logs(db, entity: EntityModel, periods: list[PeriodModel], 
                               decisions: list[DecisionModel]) -> int:
    """Create comprehensive audit trail."""
    
    log_count = 0
    
    # Pipeline-level events for each period
    for period in periods:
        base_date = datetime.utcnow() - timedelta(days=random.randint(5, 35))
        
        # Pipeline lifecycle events
        events = [
            ("pipeline_started", "orchestrator", {"status": "initiated", "entity": entity.code, "period": period.name}),
            ("data_loaded", "ingestion", {"file": f"trial_balance_{period.name}.csv", "records": 82}),
            ("data_validated", "ingestion", {"valid_records": 82, "errors": 0}),
            ("accounts_parsed", "ingestion", {"account_count": 82, "balance_check": "passed"}),
            ("ingestion_completed", "ingestion", {"duration_ms": random.randint(150, 450)}),
            ("validation_started", "validation", {"checks": ["completeness", "accuracy", "consistency"]}),
            ("check_completed", "validation", {"check": "completeness", "passed": True, "score": round(random.uniform(0.92, 1.0), 3)}),
            ("check_completed", "validation", {"check": "accuracy", "passed": True, "score": round(random.uniform(0.88, 0.99), 3)}),
            ("check_completed", "validation", {"check": "consistency", "passed": True, "score": round(random.uniform(0.90, 1.0), 3)}),
            ("validation_completed", "validation", {"total_score": round(random.uniform(0.91, 0.98), 3), "findings": random.randint(0, 5)}),
            ("variance_analysis_started", "variance", {"accounts": 82, "prior_period": "available"}),
            ("outliers_detected", "variance", {"count": random.randint(2, 8), "method": "z-score"}),
            ("variance_completed", "variance", {"analyzed": 82, "flagged": random.randint(3, 12), "duration_ms": random.randint(200, 600)}),
            ("decision_started", "decision", {"accounts_to_process": 82}),
            ("batch_processed", "decision", {"batch": 1, "auto_approved": random.randint(60, 75)}),
            ("escalations_identified", "decision", {"review": random.randint(5, 15), "senior": random.randint(1, 5)}),
            ("decision_completed", "decision", {"total_decisions": 82, "auto_rate": round(random.uniform(0.72, 0.88), 3)}),
            ("learning_updated", "learning", {"feedback_processed": random.randint(0, 8), "thresholds_adjusted": 0}),
            ("pipeline_completed", "orchestrator", {"status": "success", "duration_seconds": random.randint(2, 8)}),
        ]
        
        for i, (event_type, agent, details) in enumerate(events):
            log = AuditLogModel(
                event_type=event_type,
                agent_name=agent,
                entity_id=entity.id,
                period_id=period.id,
                action=event_type,
                details=details,
                created_at=base_date + timedelta(seconds=i * random.randint(1, 5))
            )
            db.add(log)
            log_count += 1
    
    # Decision-specific events
    for decision in random.sample(decisions, min(20, len(decisions))):
        log = AuditLogModel(
            event_type="decision_made",
            agent_name="decision",
            entity_id=entity.id,
            period_id=decision.period_id,
            account_code=decision.account_code,
            action=decision.action,
            details={
                "risk_score": decision.risk_score,
                "confidence": decision.confidence_score,
                "rationale": decision.rationale[:100] + "..." if len(decision.rationale or "") > 100 else decision.rationale
            },
            created_at=decision.created_at
        )
        db.add(log)
        log_count += 1
    
    # Feedback events
    feedback_events = [
        ("feedback_submitted", "Reviewer submitted decision feedback"),
        ("override_processed", "Human override applied to decision"),
        ("threshold_review", "Threshold adjustment under review"),
    ]
    
    for _ in range(15):
        event_type, desc = random.choice(feedback_events)
        log = AuditLogModel(
            event_type=event_type,
            agent_name="learning",
            entity_id=entity.id,
            period_id=random.choice(periods).id,
            action=desc,
            details={"processed_by": random.choice(["john.auditor", "jane.reviewer", "mike.senior"])},
            user_id=random.choice(["john.auditor", "jane.reviewer", "mike.senior"]),
            created_at=datetime.utcnow() - timedelta(days=random.randint(0, 20))
        )
        db.add(log)
        log_count += 1
    
    db.flush()
    return log_count


def seed_database():
    """Seed database with comprehensive sample data."""
    print("\n🌱 Seeding database with sample data...")
    
    with get_db() as db:
        # Create entity
        entity = create_sample_entity(db)
        
        # Create periods
        periods = create_sample_periods(db, entity)
        
        # Create balances and decisions for each period
        all_decisions = []
        for i, period in enumerate(periods):
            prior_period = periods[i-1] if i > 0 else None
            balances = create_sample_balances(db, period, prior_period)
            decisions = create_sample_decisions(db, period, balances)
            all_decisions.extend(decisions)
        
        # Create feedback (with overrides for learning)
        feedback_count = create_sample_feedback(db, all_decisions)
        print(f"✅ Created {feedback_count} feedback entries (with overrides)")
        
        # Create detailed audit logs
        log_count = create_detailed_audit_logs(db, entity, periods, all_decisions)
        print(f"✅ Created {log_count} audit log entries")
    
    print("\n✅ Database seeded successfully!")


def main():
    parser = argparse.ArgumentParser(description="Initialize database")
    parser.add_argument("--reset", action="store_true", help="Drop and recreate all tables")
    parser.add_argument("--seed", action="store_true", help="Seed with sample data")
    args = parser.parse_args()
    
    print("🗄️  Financial Assurance Platform - Database Setup")
    print("=" * 50)
    
    if args.reset:
        print("\n⚠️  Dropping all tables...")
        drop_db()
    
    print("\n📦 Creating database tables...")
    init_db()
    print("✅ Tables created successfully!")
    
    if args.seed:
        seed_database()
    
    print("\n✅ Database initialization complete!")
    print(f"   Database: data/assurance.db")


if __name__ == "__main__":
    main()
