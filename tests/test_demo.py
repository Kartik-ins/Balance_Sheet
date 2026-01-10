"""
Test Script for Financial Assurance Platform
=============================================
Demonstrates the agentic pipeline with sample data.
"""
import asyncio
import pandas as pd
from pathlib import Path
from datetime import datetime
from decimal import Decimal

# Add parent to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models import Entity, Period, Balance
from app.agents import AgentOrchestrator


async def run_demo():
    """Run a demonstration of the full pipeline."""
    print("=" * 60)
    print("Autonomous Financial Assurance Platform - Demo")
    print("=" * 60)
    
    # Initialize orchestrator
    orchestrator = AgentOrchestrator()
    
    # Create entity and periods
    entity = Entity(
        code="ACME-001",
        name="ACME Corporation",
        currency="USD"
    )
    
    current_period = Period(
        name="2025-Q4",
        start_date=datetime(2025, 10, 1),
        end_date=datetime(2025, 12, 31),
        entity_id=entity.id
    )
    
    prior_period = Period(
        name="2025-Q3",
        start_date=datetime(2025, 7, 1),
        end_date=datetime(2025, 9, 30),
        entity_id=entity.id
    )
    
    # Load sample data
    data_dir = Path(__file__).parent.parent / "data" / "sample"
    current_file = data_dir / "trial_balance_2025_q4.csv"
    prior_file = data_dir / "trial_balance_2025_q3.csv"
    
    print(f"\n📂 Loading data from: {data_dir}")
    
    if not current_file.exists():
        print(f"❌ Current period file not found: {current_file}")
        return
    
    # Load current period
    current_df = pd.read_csv(current_file)
    print(f"✅ Loaded current period: {len(current_df)} accounts")
    
    # Load and convert prior period balances
    prior_balances = []
    if prior_file.exists():
        prior_df = pd.read_csv(prior_file)
        print(f"✅ Loaded prior period: {len(prior_df)} accounts")
        
        for _, row in prior_df.iterrows():
            debit = Decimal(str(row.get("debit", 0)))
            credit = Decimal(str(row.get("credit", 0)))
            prior_balances.append(Balance(
                account_id=str(row["account_code"]),
                period_id=prior_period.id,
                entity_id=entity.id,
                debit_amount=debit,
                credit_amount=credit,
                net_amount=debit - credit
            ))
    
    print("\n🚀 Running Assurance Pipeline...")
    print("-" * 40)
    
    # Run the pipeline
    result = await orchestrator.run_pipeline(
        entity=entity,
        period=current_period,
        dataframe=current_df,
        prior_period=prior_period,
        prior_balances=prior_balances if prior_balances else None
    )
    
    # Display results
    print("\n📊 Pipeline Results")
    print("=" * 60)
    
    # Summary
    summary = result.get("summary", {})
    print(f"\n📈 Summary:")
    print(f"   • Accounts Processed: {summary.get('accounts_processed', 'N/A')}")
    print(f"   • Trial Balance Balanced: {'✅ Yes' if summary.get('is_balanced') else '❌ No'}")
    print(f"   • Validation Score: {summary.get('validation_score', 0):.1%}")
    print(f"   • Anomalies Detected: {summary.get('anomalies_detected', 0)}")
    
    # Decisions
    print(f"\n🎯 Decisions:")
    print(f"   • Total Decisions: {summary.get('total_decisions', 0)}")
    print(f"   • Auto-Approved: {summary.get('auto_approved', 0)}")
    print(f"   • Escalated: {summary.get('escalated', 0)}")
    print(f"   • Pending Review: {summary.get('pending_review', 0)}")
    print(f"   • Auto-Approve Rate: {summary.get('auto_approve_rate', 0):.1%}")
    print(f"   • Average Risk Score: {summary.get('average_risk_score', 0):.2f}")
    
    # Agent results summary
    print("\n🤖 Agent Execution:")
    for agent_name, agent_result in result.get("agents", {}).items():
        if isinstance(agent_result, dict):
            success = agent_result.get("success", agent_result.get("skipped", False) == False)
            status = "✅" if success else ("⏭️ Skipped" if agent_result.get("skipped") else "❌")
            print(f"   • {agent_name.capitalize()}: {status}")
    
    # Show top variance accounts
    variance_result = result.get("agents", {}).get("variance", {})
    if variance_result.get("success"):
        top_variances = variance_result.get("result", {}).get("summary", {}).get("top_variances", [])
        if top_variances:
            print("\n📉 Top Variances:")
            for i, v in enumerate(top_variances[:5], 1):
                pct = v.get("percent_variance")
                pct_str = f"{pct:.1%}" if pct else "N/A"
                anomaly = "⚠️" if v.get("is_anomaly") else ""
                print(f"   {i}. Account {v['account_id']}: ${v['absolute_variance']:,.0f} ({pct_str}) {anomaly}")
    
    # Show escalated items
    decision_result = result.get("agents", {}).get("decision", {})
    if decision_result.get("success"):
        decisions = decision_result.get("result", {}).get("decisions", [])
        escalated = [d for d in decisions if d.get("action") == "escalated"]
        if escalated:
            print("\n🚨 Escalated Items (require review):")
            for d in escalated[:5]:
                print(f"   • Account {d['account_id']}: Risk={d['risk_score']:.2f}")
                print(f"     Rationale: {d['rationale'][:100]}...")
    
    # Audit summary
    audit_log = result.get("audit_log", [])
    print(f"\n📝 Audit Log: {len(audit_log)} events recorded")
    
    print("\n" + "=" * 60)
    print("✅ Demo Complete!")
    print("=" * 60)
    
    return result


async def test_individual_agents():
    """Test each agent individually."""
    print("\n🧪 Testing Individual Agents...")
    
    from app.agents import (
        IngestionAgent, ValidationAgent, 
        VarianceReasoningAgent, DecisionAgent, LearningAgent
    )
    from app.models import Entity, Period
    
    # Create test data
    entity = Entity(code="TEST", name="Test Entity", currency="USD")
    period = Period(
        name="2025-Q4",
        start_date=datetime(2025, 10, 1),
        end_date=datetime(2025, 12, 31),
        entity_id=entity.id
    )
    
    # Test data
    test_df = pd.DataFrame([
        {"account_code": "1010", "account_name": "Cash", "debit": 100000, "credit": 0, "account_type": "asset"},
        {"account_code": "2010", "account_name": "Payables", "debit": 0, "credit": 50000, "account_type": "liability"},
        {"account_code": "3010", "account_name": "Equity", "debit": 0, "credit": 50000, "account_type": "equity"},
    ])
    
    print("\n1️⃣ Testing Ingestion Agent...")
    ingestion = IngestionAgent()
    ing_result = await ingestion.run({
        "dataframe": test_df,
        "entity": entity,
        "period": period
    })
    print(f"   Success: {ing_result.get('success')}")
    print(f"   Accounts: {ing_result.get('result', {}).get('summary', {}).get('total_accounts', 0)}")
    
    if ing_result.get("success"):
        trial_balance = ing_result["result"]["trial_balance"]
        accounts = {a["id"]: a for a in ing_result["result"]["accounts"]}
        
        print("\n2️⃣ Testing Validation Agent...")
        validation = ValidationAgent()
        val_result = await validation.run({
            "trial_balance": trial_balance,
            "accounts": accounts,
            "entity_id": entity.id,
            "period_id": period.id
        })
        print(f"   Success: {val_result.get('success')}")
        print(f"   Score: {val_result.get('result', {}).get('summary', {}).get('overall_score', 0):.1%}")
    
    print("\n3️⃣ Testing Learning Agent...")
    learning = LearningAgent()
    learn_result = await learning.run({
        "analyze": True
    })
    print(f"   Success: {learn_result.get('success')}")
    print(f"   Metrics: {learn_result.get('result', {}).get('metrics', {})}")
    
    print("\n✅ Individual agent tests complete!")


if __name__ == "__main__":
    print("Starting Financial Assurance Platform Demo...")
    
    # Run main demo
    asyncio.run(run_demo())
    
    # Optionally run individual tests
    # asyncio.run(test_individual_agents())
