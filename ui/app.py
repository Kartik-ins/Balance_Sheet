"""
Streamlit UI for Autonomous Financial Assurance Platform
=========================================================
A fully functional web interface for trial balance validation and assurance.
"""
import streamlit as st
import pandas as pd
import asyncio
from datetime import datetime
from decimal import Decimal
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path
import sys
import json

# Add app to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.agents import AgentOrchestrator
from app.models import Entity, Period, Balance, Feedback, FeedbackType, DecisionAction
from app.services import get_audit_service, get_explanation_service, init_db, get_db
from app.models.database import (
    EntityModel, PeriodModel, BalanceModel, DecisionModel, 
    AuditLogModel, FeedbackModel, PeriodStatus
)

# Initialize database on startup
init_db()

# Page config
st.set_page_config(
    page_title="Financial Assurance Platform",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        color: #1E3A5F;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        font-size: 1.1rem;
        color: #6B7280;
        margin-bottom: 2rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem;
        border-radius: 10px;
        color: white;
    }
    .status-approved {
        background-color: #10B981;
        color: white;
        padding: 0.25rem 0.75rem;
        border-radius: 9999px;
        font-size: 0.875rem;
    }
    .status-escalated {
        background-color: #EF4444;
        color: white;
        padding: 0.25rem 0.75rem;
        border-radius: 9999px;
        font-size: 0.875rem;
    }
    .status-pending {
        background-color: #F59E0B;
        color: white;
        padding: 0.25rem 0.75rem;
        border-radius: 9999px;
        font-size: 0.875rem;
    }
    .finding-card {
        border-left: 4px solid #EF4444;
        padding: 1rem;
        background-color: #FEF2F2;
        margin-bottom: 0.5rem;
        border-radius: 0 8px 8px 0;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        padding-left: 20px;
        padding-right: 20px;
    }
</style>
""", unsafe_allow_html=True)


# Initialize session state
def init_session_state():
    if 'orchestrator' not in st.session_state:
        st.session_state.orchestrator = AgentOrchestrator()
    if 'pipeline_result' not in st.session_state:
        st.session_state.pipeline_result = None
    if 'uploaded_file' not in st.session_state:
        st.session_state.uploaded_file = None
    if 'prior_file' not in st.session_state:
        st.session_state.prior_file = None
    if 'feedback_submitted' not in st.session_state:
        st.session_state.feedback_submitted = {}
    if 'run_history' not in st.session_state:
        st.session_state.run_history = []


init_session_state()


def run_async(coro):
    """Run async function in sync context."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def render_header():
    """Render the main header."""
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown('<p class="main-header">📊 Financial Assurance Platform</p>', unsafe_allow_html=True)
        st.markdown('<p class="sub-header">Autonomous AI-driven trial balance validation and assurance</p>', unsafe_allow_html=True)
    with col2:
        st.markdown(f"**Date:** {datetime.now().strftime('%Y-%m-%d')}")
        if st.session_state.pipeline_result:
            st.success("✅ Pipeline Complete")


def render_sidebar():
    """Render the sidebar with upload and configuration."""
    with st.sidebar:
        st.header("⚙️ Configuration")
        
        # Entity Information
        st.subheader("📋 Entity Details")
        entity_code = st.text_input("Entity Code", value="ACME-001")
        entity_name = st.text_input("Entity Name", value="ACME Corporation")
        currency = st.selectbox("Currency", ["USD", "EUR", "GBP", "INR", "JPY"], index=0)
        
        # Period Information
        st.subheader("📅 Period Details")
        period_name = st.text_input("Period Name", value="2025-Q4")
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("Start Date", value=datetime(2025, 10, 1))
        with col2:
            end_date = st.date_input("End Date", value=datetime(2025, 12, 31))
        
        # File Upload
        st.subheader("📁 Upload Files")
        
        current_file = st.file_uploader(
            "Current Period Trial Balance",
            type=['csv', 'xlsx', 'xls'],
            help="Upload CSV or Excel file with columns: account_code, account_name, debit, credit"
        )
        
        prior_file = st.file_uploader(
            "Prior Period (Optional)",
            type=['csv', 'xlsx', 'xls'],
            help="For variance analysis"
        )
        
        # Sample data option
        use_sample = st.checkbox("Use sample data", value=False)
        
        st.divider()
        
        # Thresholds
        st.subheader("🎚️ Thresholds")
        with st.expander("Adjust Thresholds"):
            auto_approve_threshold = st.slider(
                "Auto-Approve Confidence",
                min_value=0.5, max_value=1.0, value=0.85, step=0.05
            )
            escalation_threshold = st.slider(
                "Escalation Risk",
                min_value=0.3, max_value=1.0, value=0.7, step=0.05
            )
            variance_threshold = st.slider(
                "Variance % Threshold",
                min_value=0.05, max_value=0.5, value=0.25, step=0.05
            )
        
        st.divider()
        
        # Run Pipeline Button
        run_disabled = not (current_file or use_sample)
        
        if st.button("🚀 Run Assurance Pipeline", type="primary", disabled=run_disabled, use_container_width=True):
            with st.spinner("Running autonomous agents..."):
                result = run_pipeline(
                    current_file=current_file,
                    prior_file=prior_file,
                    entity_code=entity_code,
                    entity_name=entity_name,
                    currency=currency,
                    period_name=period_name,
                    start_date=start_date,
                    end_date=end_date,
                    use_sample=use_sample
                )
                if result:
                    st.session_state.pipeline_result = result
                    st.session_state.run_history.append({
                        "timestamp": datetime.now().isoformat(),
                        "entity": entity_code,
                        "period": period_name,
                        "summary": result.get("summary", {})
                    })
                    st.rerun()
        
        if st.button("🔄 Reset", use_container_width=True):
            st.session_state.pipeline_result = None
            st.session_state.feedback_submitted = {}
            st.rerun()
        
        return {
            "entity_code": entity_code,
            "entity_name": entity_name,
            "currency": currency,
            "period_name": period_name
        }


def run_pipeline(current_file, prior_file, entity_code, entity_name, currency, 
                 period_name, start_date, end_date, use_sample=False):
    """Run the assurance pipeline."""
    try:
        # Create entity and period
        entity = Entity(code=entity_code, name=entity_name, currency=currency)
        period = Period(
            name=period_name,
            start_date=datetime.combine(start_date, datetime.min.time()),
            end_date=datetime.combine(end_date, datetime.min.time()),
            entity_id=entity.id
        )
        
        # Load current period data
        if use_sample:
            sample_path = Path(__file__).parent.parent / "data" / "sample" / "trial_balance_2025_q4.csv"
            if sample_path.exists():
                current_df = pd.read_csv(sample_path)
            else:
                st.error("Sample data not found!")
                return None
        else:
            if current_file.name.endswith('.csv'):
                current_df = pd.read_csv(current_file)
            else:
                current_df = pd.read_excel(current_file)
        
        # Load prior period data if provided
        prior_balances = None
        prior_period = None
        
        if use_sample:
            prior_path = Path(__file__).parent.parent / "data" / "sample" / "trial_balance_2025_q3.csv"
            if prior_path.exists():
                prior_df = pd.read_csv(prior_path)
                prior_period = Period(
                    name="2025-Q3",
                    start_date=datetime(2025, 7, 1),
                    end_date=datetime(2025, 9, 30),
                    entity_id=entity.id
                )
                prior_balances = convert_df_to_balances(prior_df, prior_period.id, entity.id)
        elif prior_file:
            if prior_file.name.endswith('.csv'):
                prior_df = pd.read_csv(prior_file)
            else:
                prior_df = pd.read_excel(prior_file)
            prior_period = Period(
                name=f"{period_name}-Prior",
                start_date=datetime.combine(start_date, datetime.min.time()),
                end_date=datetime.combine(end_date, datetime.min.time()),
                entity_id=entity.id
            )
            prior_balances = convert_df_to_balances(prior_df, prior_period.id, entity.id)
        
        # Run pipeline
        result = run_async(
            st.session_state.orchestrator.run_pipeline(
                entity=entity,
                period=period,
                dataframe=current_df,
                prior_period=prior_period,
                prior_balances=prior_balances
            )
        )
        
        return result
        
    except Exception as e:
        st.error(f"Pipeline failed: {str(e)}")
        import traceback
        st.code(traceback.format_exc())
        return None


def convert_df_to_balances(df, period_id, entity_id):
    """Convert DataFrame to Balance objects."""
    balances = []
    
    # Normalize column names
    df.columns = df.columns.str.lower().str.strip().str.replace(" ", "_")
    
    for _, row in df.iterrows():
        account_code = str(row.get("account_code", row.get("account", "")))
        debit = Decimal(str(row.get("debit", row.get("dr", 0)) or 0))
        credit = Decimal(str(row.get("credit", row.get("cr", 0)) or 0))
        
        balances.append(Balance(
            account_id=account_code,
            period_id=period_id,
            entity_id=entity_id,
            debit_amount=debit,
            credit_amount=credit,
            net_amount=debit - credit
        ))
    
    return balances


def render_overview_tab():
    """Render the overview/summary tab."""
    result = st.session_state.pipeline_result
    if not result:
        st.info("👆 Upload a trial balance file and run the pipeline to see results.")
        return
    
    summary = result.get("summary", {})
    
    # Key Metrics Row
    st.subheader("📈 Key Metrics")
    
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric(
            label="Total Accounts",
            value=summary.get("accounts_processed", 0)
        )
    
    with col2:
        is_balanced = summary.get("is_balanced", False)
        st.metric(
            label="Trial Balance",
            value="✅ Balanced" if is_balanced else "❌ Unbalanced"
        )
    
    with col3:
        val_score = summary.get("validation_score", 0)
        st.metric(
            label="Validation Score",
            value=f"{val_score:.0%}"
        )
    
    with col4:
        auto_rate = summary.get("auto_approve_rate", 0)
        st.metric(
            label="Auto-Approve Rate",
            value=f"{auto_rate:.0%}"
        )
    
    with col5:
        avg_risk = summary.get("average_risk_score", 0)
        st.metric(
            label="Avg Risk Score",
            value=f"{avg_risk:.2f}"
        )
    
    st.divider()
    
    # Decision Breakdown
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("🎯 Decision Breakdown")
        
        auto_approved = summary.get("auto_approved", 0)
        escalated = summary.get("escalated", 0)
        pending = summary.get("pending_review", 0)
        total = auto_approved + escalated + pending
        
        if total > 0:
            fig = go.Figure(data=[go.Pie(
                labels=['Auto-Approved', 'Escalated', 'Pending Review'],
                values=[auto_approved, escalated, pending],
                hole=0.4,
                marker_colors=['#10B981', '#EF4444', '#F59E0B']
            )])
            fig.update_layout(
                showlegend=True,
                height=300,
                margin=dict(t=20, b=20, l=20, r=20)
            )
            st.plotly_chart(fig, use_container_width=True)
        
        # Stats table
        if total > 0:
            st.markdown(f"""
            | Status | Count | Percentage |
            |--------|-------|------------|
            | ✅ Auto-Approved | {auto_approved} | {auto_approved/total*100:.1f}% |
            | 🔴 Escalated | {escalated} | {escalated/total*100:.1f}% |
            | 🟡 Pending Review | {pending} | {pending/total*100:.1f}% |
            | **Total** | **{total}** | **100%** |
            """)
        else:
            st.info("No decisions made yet.")
    
    with col2:
        st.subheader("🤖 Agent Execution")
        
        agents = result.get("agents", {})
        
        for agent_name, agent_result in agents.items():
            if isinstance(agent_result, dict):
                success = agent_result.get("success", False)
                skipped = agent_result.get("skipped", False)
                
                if skipped:
                    icon = "⏭️"
                    status = "Skipped"
                    color = "gray"
                elif success:
                    icon = "✅"
                    status = "Completed"
                    color = "green"
                else:
                    icon = "❌"
                    status = "Failed"
                    color = "red"
                
                st.markdown(f"{icon} **{agent_name.title()}**: :{color}[{status}]")
        
        st.divider()
        
        # Anomalies summary
        st.subheader("⚠️ Anomalies Detected")
        anomalies = summary.get("anomalies_detected", 0)
        findings = summary.get("validation_findings", 0)
        
        st.metric("Variance Anomalies", anomalies)
        st.metric("Validation Findings", findings)


def render_validations_tab():
    """Render the validations tab."""
    result = st.session_state.pipeline_result
    if not result:
        st.info("Run the pipeline first to see validation results.")
        return
    
    validation_agent = result.get("agents", {}).get("validation", {})
    if not validation_agent.get("success"):
        st.warning("Validation agent did not complete successfully.")
        return
    
    validation_results = validation_agent.get("result", {}).get("validation_results", [])
    findings = validation_agent.get("result", {}).get("findings", [])
    
    st.subheader("✅ Validation Checks")
    
    # Validation results table
    if validation_results:
        for vr in validation_results:
            status = vr.get("status", "unknown")
            check_name = vr.get("check_name", "Unknown Check")
            message = vr.get("message", "")
            confidence = vr.get("confidence", 0)
            
            if status == "passed":
                icon = "✅"
                color = "green"
            elif status == "warning":
                icon = "⚠️"
                color = "orange"
            else:
                icon = "❌"
                color = "red"
            
            with st.expander(f"{icon} {check_name.replace('_', ' ').title()} - :{color}[{status.upper()}]"):
                st.write(f"**Message:** {message}")
                st.write(f"**Confidence:** {confidence:.0%}")
                
                evidence = vr.get("evidence", {})
                if evidence:
                    st.json(evidence)
    
    st.divider()
    
    # Findings
    st.subheader("🔍 Findings")
    
    if findings:
        for finding in findings:
            severity = finding.get("severity", 0.5)
            finding_type = finding.get("finding_type", "unknown")
            description = finding.get("description", "")
            
            if severity >= 0.7:
                color = "#EF4444"
                severity_label = "High"
            elif severity >= 0.4:
                color = "#F59E0B"
                severity_label = "Medium"
            else:
                color = "#3B82F6"
                severity_label = "Low"
            
            st.markdown(f"""
            <div style="border-left: 4px solid {color}; padding: 1rem; background-color: #F9FAFB; margin-bottom: 0.5rem; border-radius: 0 8px 8px 0;">
                <strong>{finding_type.replace('_', ' ').title()}</strong> 
                <span style="background-color: {color}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; margin-left: 8px;">{severity_label}</span>
                <br><span style="color: #6B7280;">{description}</span>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.success("No significant findings detected!")


def render_variance_tab():
    """Render the variance analysis tab."""
    result = st.session_state.pipeline_result
    if not result:
        st.info("Run the pipeline first to see variance analysis.")
        return
    
    variance_agent = result.get("agents", {}).get("variance", {})
    
    if variance_agent.get("skipped"):
        st.warning("Variance analysis was skipped (no prior period data provided).")
        return
    
    if not variance_agent.get("success"):
        st.warning("Variance agent did not complete successfully.")
        return
    
    variance_analyses = variance_agent.get("result", {}).get("variance_analyses", [])
    
    st.subheader("📊 Period-over-Period Variance Analysis")
    
    if not variance_analyses:
        st.info("No variance data available.")
        return
    
    # Convert to DataFrame for display
    df_data = []
    for va in variance_analyses:
        df_data.append({
            "Account": va.get("account_id"),
            "Current": float(va.get("current_amount", 0)),
            "Prior": float(va.get("prior_amount", 0)),
            "Variance $": float(va.get("absolute_variance", 0)),
            "Variance %": va.get("percent_variance"),
            "Z-Score": va.get("zscore"),
            "Anomaly": "⚠️ Yes" if va.get("is_anomaly") else "No",
            "Trend": va.get("trend_direction", "stable")
        })
    
    df = pd.DataFrame(df_data)
    
    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        show_anomalies_only = st.checkbox("Show anomalies only")
    with col2:
        min_variance = st.number_input("Min Variance $", value=0, step=1000)
    with col3:
        sort_by = st.selectbox("Sort by", ["Variance $", "Variance %", "Z-Score"], index=0)
    
    # Filter
    filtered_df = df.copy()
    if show_anomalies_only:
        filtered_df = filtered_df[filtered_df["Anomaly"] == "⚠️ Yes"]
    filtered_df = filtered_df[abs(filtered_df["Variance $"]) >= min_variance]
    filtered_df = filtered_df.sort_values(by=sort_by, key=abs, ascending=False)
    
    # Display table
    st.dataframe(
        filtered_df,
        use_container_width=True,
        height=400,
        column_config={
            "Current": st.column_config.NumberColumn(format="$%,.0f"),
            "Prior": st.column_config.NumberColumn(format="$%,.0f"),
            "Variance $": st.column_config.NumberColumn(format="$%,.0f"),
            "Variance %": st.column_config.NumberColumn(format="%.1%%"),
            "Z-Score": st.column_config.NumberColumn(format="%.2f"),
        }
    )
    
    # Variance chart
    st.subheader("📈 Top Variances")
    
    top_variances = filtered_df.nlargest(10, "Variance $", keep="first")
    
    fig = px.bar(
        top_variances,
        x="Account",
        y="Variance $",
        color="Anomaly",
        color_discrete_map={"⚠️ Yes": "#EF4444", "No": "#3B82F6"},
        title="Top 10 Largest Variances"
    )
    fig.update_layout(height=400)
    st.plotly_chart(fig, use_container_width=True)


def render_decisions_tab():
    """Render the decisions and review tab."""
    result = st.session_state.pipeline_result
    if not result:
        st.info("Run the pipeline first to see decisions.")
        return
    
    decision_agent = result.get("agents", {}).get("decision", {})
    if not decision_agent.get("success"):
        st.warning("Decision agent did not complete successfully.")
        return
    
    decisions = decision_agent.get("result", {}).get("decisions", [])
    
    st.subheader("🎯 Review Decisions")
    
    # Filter options
    col1, col2 = st.columns(2)
    with col1:
        status_filter = st.multiselect(
            "Filter by Status",
            ["auto_approved", "escalated", "pending_review"],
            default=["escalated", "pending_review"]
        )
    with col2:
        risk_filter = st.slider("Minimum Risk Score", 0.0, 1.0, 0.0)
    
    # Filter decisions
    filtered_decisions = [
        d for d in decisions
        if d.get("action") in status_filter and d.get("risk_score", 0) >= risk_filter
    ]
    
    st.write(f"Showing {len(filtered_decisions)} of {len(decisions)} decisions")
    
    if not filtered_decisions:
        st.success("No items requiring review with current filters!")
        return
    
    # Display decisions
    for i, decision in enumerate(filtered_decisions):
        account_id = decision.get("account_id", "Unknown")
        action = decision.get("action", "unknown")
        risk_score = decision.get("risk_score", 0)
        confidence = decision.get("confidence", 0)
        rationale = decision.get("rationale", "")
        decision_id = decision.get("id", str(i))
        
        # Status badge
        if action == "auto_approved":
            status_color = "#10B981"
            status_icon = "✅"
        elif action == "escalated":
            status_color = "#EF4444"
            status_icon = "🔴"
        else:
            status_color = "#F59E0B"
            status_icon = "🟡"
        
        with st.expander(f"{status_icon} Account {account_id} - Risk: {risk_score:.2f}"):
            col1, col2, col3 = st.columns([1, 1, 1])
            
            with col1:
                st.metric("Risk Score", f"{risk_score:.2f}")
            with col2:
                st.metric("Confidence", f"{confidence:.0%}")
            with col3:
                st.markdown(f"""
                <span style="background-color: {status_color}; color: white; padding: 4px 12px; border-radius: 4px;">
                    {action.replace('_', ' ').title()}
                </span>
                """, unsafe_allow_html=True)
            
            st.write("**Rationale:**")
            st.info(rationale)
            
            # Evidence
            evidence = decision.get("evidence_pack", {})
            if evidence:
                with st.expander("📋 View Evidence"):
                    st.json(evidence)
            
            # Feedback form (only for escalated/pending)
            if action in ["escalated", "pending_review"]:
                st.divider()
                st.write("**Provide Feedback:**")
                
                feedback_key = f"feedback_{decision_id}"
                
                if feedback_key in st.session_state.feedback_submitted:
                    st.success(f"✅ Feedback submitted: {st.session_state.feedback_submitted[feedback_key]}")
                else:
                    reason = st.text_area("Reason for your decision", key=f"reason_{decision_id}", 
                                         placeholder="e.g., Historical pattern supports this variance - seasonal Q4 increase is normal")
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        if st.button("✅ Approve", key=f"approve_{decision_id}", type="primary"):
                            if reason.strip():
                                submit_feedback(decision_id, "override_approved", reason, decision, i)
                                st.session_state.feedback_submitted[feedback_key] = "Approved"
                                st.rerun()
                            else:
                                st.warning("Please provide a reason for approval")
                    
                    with col2:
                        if st.button("❌ Reject", key=f"reject_{decision_id}"):
                            if reason.strip():
                                submit_feedback(decision_id, "override_rejected", reason, decision, i)
                                st.session_state.feedback_submitted[feedback_key] = "Rejected"
                                st.rerun()
                            else:
                                st.warning("Please provide a reason for rejection")


def submit_feedback(decision_id: str, feedback_type: str, reason: str, decision: dict, decision_idx: int):
    """Submit feedback for a decision and update status."""
    try:
        # Determine if this is an override
        original_action = decision.get("action", "")
        is_override = feedback_type in ["override_approved", "override_rejected"]
        
        feedback = {
            "decision_id": decision_id,
            "user_id": "streamlit_user",
            "feedback_type": feedback_type,
            "reason": reason,
            "was_override": is_override,
            "original_action": original_action
        }
        
        # Process through orchestrator
        run_async(
            st.session_state.orchestrator.process_feedback(feedback)
        )
        
        # Also save directly to database
        try:
            with get_db() as db:
                import uuid
                
                # Save feedback
                fb = FeedbackModel(
                    id=str(uuid.uuid4()),
                    decision_id=decision_id,
                    user_id="streamlit_user",
                    feedback_type=feedback_type,
                    reason=reason,
                    was_override=is_override,
                    original_action=original_action,
                    created_at=datetime.utcnow()
                )
                db.add(fb)
                
                # Update decision status in session state
                if st.session_state.pipeline_result:
                    decisions = st.session_state.pipeline_result.get("agents", {}).get("decision", {}).get("result", {}).get("decisions", [])
                    if decision_idx < len(decisions):
                        if feedback_type == "override_approved":
                            decisions[decision_idx]["action"] = "auto_approved"
                            decisions[decision_idx]["reviewed"] = True
                        elif feedback_type == "override_rejected":
                            decisions[decision_idx]["action"] = "rejected"
                            decisions[decision_idx]["reviewed"] = True
                
                db.commit()
                st.toast(f"✅ Feedback saved to database: {feedback_type}")
        except Exception as db_error:
            st.warning(f"Feedback recorded in session but DB save failed: {db_error}")
            import traceback
            st.error(f"Details: {traceback.format_exc()}")
        
        st.success(f"Feedback submitted: {feedback_type}")
    except Exception as e:
        st.error(f"Failed to submit feedback: {e}")


def render_audit_tab():
    """Render the audit log tab with both session and database events."""
    st.subheader("📝 Audit Trail")
    
    # Combine session audit log with database records
    all_events = []
    
    # Get current session events
    result = st.session_state.pipeline_result
    if result:
        session_events = result.get("audit_log", [])
        for event in session_events:
            all_events.append({
                "source": "session",
                "timestamp": event.get("timestamp", ""),
                "event_type": event.get("event_type", ""),
                "agent": event.get("agent_type", ""),
                "entity_id": event.get("entity_id", ""),
                "period_id": event.get("period_id", ""),
                "account_id": event.get("account_id", ""),
                "payload": event.get("payload", {})
            })
    
    # Get database events
    try:
        with get_db() as db:
            db_logs = db.query(AuditLogModel).order_by(
                AuditLogModel.created_at.desc()
            ).limit(200).all()
            
            for log in db_logs:
                all_events.append({
                    "source": "database",
                    "timestamp": log.created_at.isoformat() if log.created_at else "",
                    "event_type": log.event_type,
                    "agent": log.agent_name or "",
                    "entity_id": log.entity_id or "",
                    "period_id": log.period_id or "",
                    "account_id": log.account_code or "",
                    "payload": log.details or {}
                })
    except Exception as e:
        st.warning(f"Could not load database audit logs: {e}")
    
    # Stats
    col1, col2, col3 = st.columns(3)
    session_count = len([e for e in all_events if e["source"] == "session"])
    db_count = len([e for e in all_events if e["source"] == "database"])
    
    with col1:
        st.metric("Session Events", session_count)
    with col2:
        st.metric("Historical Events", db_count)
    with col3:
        st.metric("Total Events", len(all_events))
    
    if not all_events:
        st.info("No audit events recorded. Run the pipeline or initialize the database with sample data.")
        return
    
    # Convert to DataFrame
    df_data = []
    for event in all_events:
        entity_display = event.get("entity_id", "")
        if entity_display and len(entity_display) > 8:
            entity_display = entity_display[:8] + "..."
            
        df_data.append({
            "Timestamp": event.get("timestamp", ""),
            "Event Type": event.get("event_type", ""),
            "Agent": event.get("agent", ""),
            "Entity": entity_display,
            "Account": event.get("account_id", "") or "-",
            "Source": "🔵 Live" if event.get("source") == "session" else "💾 DB",
        })
    
    df = pd.DataFrame(df_data)
    
    # Filters
    col1, col2 = st.columns(2)
    with col1:
        event_types = sorted(df["Event Type"].unique().tolist())
        selected_types = st.multiselect("Filter by Event Type", event_types, default=event_types[:10] if len(event_types) > 10 else event_types)
    with col2:
        agents = sorted(df["Agent"].unique().tolist())
        selected_agents = st.multiselect("Filter by Agent", agents, default=agents)
    
    filtered_df = df[
        (df["Event Type"].isin(selected_types)) & 
        (df["Agent"].isin(selected_agents))
    ]
    
    st.dataframe(filtered_df, use_container_width=True, height=400)
    
    # Event details expander
    with st.expander("🔍 View Event Details"):
        if len(all_events) > 0:
            selected_idx = st.number_input("Event Index", min_value=0, max_value=len(all_events)-1, value=0)
            event = all_events[selected_idx]
            st.json(event)
    
    # Export option
    if st.button("📥 Export Audit Log"):
        csv = filtered_df.to_csv(index=False)
        st.download_button(
            label="Download CSV",
            data=csv,
            file_name=f"audit_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )


def render_learning_tab():
    """Render the learning insights tab with database-backed metrics."""
    st.subheader("🧠 Learning Insights")
    
    # Refresh button
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("🔄 Refresh Data", key="refresh_learning"):
            st.rerun()
    
    # Load feedback and decision data from database
    feedback_data = []
    decision_data = []
    
    try:
        with get_db() as db:
            # Get all feedback
            feedback_records = db.query(FeedbackModel).order_by(
                FeedbackModel.created_at.desc()
            ).limit(500).all()
            
            # Debug info
            total_fb_count = db.query(FeedbackModel).count()
            total_dec_count = db.query(DecisionModel).count()
            
            st.caption(f"📊 Database: {total_fb_count} feedback records, {total_dec_count} decisions")
            
            for fb in feedback_records:
                feedback_data.append({
                    "id": fb.id,
                    "decision_id": fb.decision_id,
                    "user_id": fb.user_id,
                    "feedback_type": fb.feedback_type,
                    "reason": fb.reason,
                    "was_override": fb.was_override,
                    "original_action": fb.original_action,
                    "created_at": fb.created_at
                })
            
            # Get all decisions
            decision_records = db.query(DecisionModel).order_by(
                DecisionModel.created_at.desc()
            ).limit(500).all()
            
            for dec in decision_records:
                decision_data.append({
                    "id": dec.id,
                    "account_code": dec.account_code,
                    "action": dec.action,
                    "risk_score": dec.risk_score,
                    "confidence_score": dec.confidence_score,
                    "rationale": dec.rationale,
                    "created_at": dec.created_at
                })
    except Exception as e:
        st.warning(f"Could not load data from database: {e}")
    
    # Calculate metrics from database data
    total_feedback = len(feedback_data)
    total_decisions = len(decision_data)
    
    overrides = [f for f in feedback_data if f.get("was_override")]
    override_count = len(overrides)
    override_rate = override_count / total_feedback if total_feedback > 0 else 0
    
    agreements = [f for f in feedback_data if f.get("feedback_type") in ("approved", "comment") and not f.get("was_override")]
    agreement_rate = len(agreements) / total_feedback if total_feedback > 0 else 0
    
    # Accuracy estimate based on agreement rate
    accuracy = 1 - override_rate if total_feedback >= 10 else None
    
    # Display metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Feedback", total_feedback)
    with col2:
        st.metric("Override Rate", f"{override_rate:.1%}")
    with col3:
        st.metric("Agreement Rate", f"{agreement_rate:.1%}")
    with col4:
        st.metric("Accuracy Estimate", f"{accuracy:.1%}" if accuracy else "N/A")
    
    st.divider()
    
    # Feedback breakdown
    st.subheader("📊 Feedback Breakdown")
    
    if feedback_data:
        col1, col2 = st.columns(2)
        
        with col1:
            # Feedback type distribution
            feedback_types = {}
            for f in feedback_data:
                ft = f.get("feedback_type", "unknown")
                feedback_types[ft] = feedback_types.get(ft, 0) + 1
            
            type_df = pd.DataFrame([
                {"Type": k, "Count": v} for k, v in feedback_types.items()
            ])
            
            if not type_df.empty:
                fig = px.pie(type_df, values='Count', names='Type', 
                           title='Feedback by Type',
                           color_discrete_sequence=px.colors.qualitative.Set2)
                st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            # Reviewer activity
            reviewers = {}
            for f in feedback_data:
                user = f.get("user_id", "unknown")
                reviewers[user] = reviewers.get(user, 0) + 1
            
            reviewer_df = pd.DataFrame([
                {"Reviewer": k, "Reviews": v} for k, v in reviewers.items()
            ])
            
            if not reviewer_df.empty:
                fig = px.bar(reviewer_df, x='Reviewer', y='Reviews',
                           title='Reviews by User',
                           color='Reviews',
                           color_continuous_scale='Blues')
                st.plotly_chart(fig, use_container_width=True)
        
        # Recent feedback table
        st.subheader("📋 Recent Feedback")
        recent_fb = feedback_data[:20]
        
        fb_df = pd.DataFrame([{
            "Date": f.get("created_at").strftime("%Y-%m-%d %H:%M") if f.get("created_at") else "",
            "User": f.get("user_id", ""),
            "Type": f.get("feedback_type", ""),
            "Override": "✓" if f.get("was_override") else "",
            "Reason": (f.get("reason", "") or "")[:50] + "..." if len(f.get("reason", "") or "") > 50 else (f.get("reason", "") or "")
        } for f in recent_fb])
        
        st.dataframe(fb_df, use_container_width=True, height=300)
        
    else:
        st.info("📊 No feedback data available yet. Submit feedback on decisions to see learning insights.")
    
    st.divider()
    
    # Improvement Suggestions
    st.subheader("💡 Improvement Suggestions")
    
    suggestions = []
    
    if total_feedback < 10:
        suggestions.append({
            "type": "insufficient_data",
            "message": f"Need at least 10 feedback items to generate suggestions (currently {total_feedback})"
        })
    else:
        if override_rate > 0.20:
            suggestions.append({
                "type": "threshold_adjustment",
                "parameter": "risk_threshold",
                "current_value": 0.7,
                "suggested_value": 0.6,
                "reason": f"High override rate ({override_rate:.1%}) suggests thresholds may be too strict",
                "confidence": 0.75
            })
        
        # Find accounts with repeated overrides
        override_accounts = {}
        for fb in overrides:
            # Would need to join with decisions to get account
            pass
    
    if suggestions:
        for suggestion in suggestions:
            stype = suggestion.get("type", "")
            
            if stype == "insufficient_data":
                st.info(f"📊 {suggestion.get('message', 'Need more data')}")
            elif stype == "threshold_adjustment":
                param = suggestion.get("parameter", "")
                current = suggestion.get("current_value", 0)
                suggested = suggestion.get("suggested_value", 0)
                reason = suggestion.get("reason", "")
                confidence = suggestion.get("confidence", 0)
                
                st.warning(f"""
                **Suggested Adjustment:** `{param}`
                - Current: {current:.2f} → Suggested: {suggested:.2f}
                - Reason: {reason}
                - Confidence: {confidence:.0%}
                """)
    else:
        st.success("✅ No adjustments needed at this time.")
    
    # Current thresholds
    st.subheader("⚙️ Current Thresholds")
    
    thresholds = {
        "variance_threshold_percent": 0.10,
        "materiality_threshold_usd": 100000,
        "risk_escalation_threshold": 0.70,
        "auto_approve_confidence": 0.85,
        "zscore_outlier_threshold": 2.5
    }
    
    thresh_df = pd.DataFrame([
        {"Parameter": k, "Value": f"{v:.2f}" if isinstance(v, float) and v < 100 else f"${v:,.0f}" if v > 100 else str(v)} 
        for k, v in thresholds.items()
    ])
    
    st.dataframe(thresh_df, use_container_width=True, hide_index=True)
    
    # Database debug section
    with st.expander("🔧 Database Debug"):
        try:
            with get_db() as db:
                st.write("**Table Record Counts:**")
                counts = {
                    "Entities": db.query(EntityModel).count(),
                    "Periods": db.query(PeriodModel).count(),
                    "Balances": db.query(BalanceModel).count(),
                    "Decisions": db.query(DecisionModel).count(),
                    "Audit Logs": db.query(AuditLogModel).count(),
                    "Feedback": db.query(FeedbackModel).count(),
                }
                
                count_df = pd.DataFrame([{"Table": k, "Count": v} for k, v in counts.items()])
                st.dataframe(count_df, hide_index=True)
                
                # Recent feedback
                st.write("**Recent Feedback Records:**")
                recent_fb = db.query(FeedbackModel).order_by(FeedbackModel.created_at.desc()).limit(5).all()
                if recent_fb:
                    for fb in recent_fb:
                        st.json({
                            "id": fb.id[:8] + "...",
                            "feedback_type": fb.feedback_type,
                            "reason": (fb.reason or "")[:50],
                            "was_override": fb.was_override,
                            "created_at": str(fb.created_at)
                        })
                else:
                    st.info("No feedback records in database")
                    
                if st.button("🗑️ Reset Database", type="secondary"):
                    from app.services.db import drop_db, init_db
                    drop_db()
                    init_db()
                    st.success("Database reset!")
                    st.rerun()
                    
        except Exception as e:
            st.error(f"Debug error: {e}")


def render_data_tab():
    """Render the raw data tab."""
    result = st.session_state.pipeline_result
    if not result:
        st.info("Run the pipeline first to see data.")
        return
    
    st.subheader("📋 Trial Balance Data")
    
    # Get ingestion result
    ingestion = result.get("agents", {}).get("ingestion", {})
    if not ingestion.get("success"):
        st.warning("Ingestion data not available.")
        return
    
    trial_balance = ingestion.get("result", {}).get("trial_balance", {})
    balances = trial_balance.get("balances", [])
    
    if not balances:
        st.info("No balance data.")
        return
    
    # Convert to DataFrame
    df_data = []
    for b in balances:
        df_data.append({
            "Account": b.get("account_id", ""),
            "Debit": float(b.get("debit_amount", 0)),
            "Credit": float(b.get("credit_amount", 0)),
            "Net": float(b.get("net_amount", 0)),
            "Currency": b.get("currency", "USD")
        })
    
    df = pd.DataFrame(df_data)
    
    # Summary
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Debits", f"${df['Debit'].sum():,.0f}")
    with col2:
        st.metric("Total Credits", f"${df['Credit'].sum():,.0f}")
    with col3:
        diff = df['Debit'].sum() - df['Credit'].sum()
        st.metric("Difference", f"${diff:,.0f}")
    
    st.divider()
    
    # Data table
    st.dataframe(
        df,
        use_container_width=True,
        height=500,
        column_config={
            "Debit": st.column_config.NumberColumn(format="$%,.2f"),
            "Credit": st.column_config.NumberColumn(format="$%,.2f"),
            "Net": st.column_config.NumberColumn(format="$%,.2f"),
        }
    )
    
    # Download option
    csv = df.to_csv(index=False)
    st.download_button(
        label="📥 Download as CSV",
        data=csv,
        file_name="trial_balance_processed.csv",
        mime="text/csv"
    )


def render_history_tab():
    """Render the database history tab with persisted data."""
    st.subheader("🗄️ Database History")
    
    # Check if we need to seed the database BEFORE opening the main session
    try:
        needs_seed = False
        with get_db() as db:
            entity_count = db.query(EntityModel).count()
            needs_seed = entity_count == 0
        
        if needs_seed:
            st.info("No entities in database yet. Run an analysis to create records.")
            
            if st.button("📦 Initialize with Sample Data"):
                st.info("Seeding database with comprehensive sample data...")
                try:
                    # Import and run the full seeding function (outside any db context)
                    from scripts.init_db import seed_database
                    seed_database()
                    st.success("✅ Database seeded with sample entity, periods, balances, decisions, feedback, and audit logs!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to seed database: {e}")
                    import traceback
                    st.code(traceback.format_exc())
            return
        
        # Now open the main session for reading data
        with get_db() as db:
            # Get all entities
            entities = db.query(EntityModel).all()
            
            # Entity selector
            entity_options = {f"{e.code} - {e.name}": e.id for e in entities}
            selected_entity = st.selectbox("Select Entity", list(entity_options.keys()))
            entity_id = entity_options[selected_entity]
            
            # Get periods for this entity
            periods = db.query(PeriodModel).filter(
                PeriodModel.entity_id == entity_id
            ).order_by(PeriodModel.end_date.desc()).all()
            
            if not periods:
                st.warning("No periods found for this entity.")
                return
            
            st.divider()
            
            # Period statistics
            st.subheader("📅 Period History")
            
            period_data = []
            for p in periods:
                period_data.append({
                    "Period": p.name,
                    "Status": p.status,
                    "Accounts": p.total_accounts,
                    "Auto-Approved": p.auto_approved,
                    "Escalated": p.escalated,
                    "Pending": p.pending_review,
                    "Avg Risk": f"{p.avg_risk_score:.2f}" if p.avg_risk_score else "N/A",
                    "Created": p.created_at.strftime("%Y-%m-%d %H:%M") if p.created_at else "N/A"
                })
            
            df = pd.DataFrame(period_data)
            st.dataframe(df, use_container_width=True)
            
            # Select period for details
            period_options = {p.name: p.id for p in periods}
            selected_period = st.selectbox("Select Period for Details", list(period_options.keys()))
            period_id = period_options[selected_period]
            
            st.divider()
            
            # Balances for selected period
            balances = db.query(BalanceModel).filter(
                BalanceModel.period_id == period_id
            ).all()
            
            if balances:
                st.subheader(f"💰 Balances for {selected_period}")
                
                balance_data = []
                for b in balances:
                    balance_data.append({
                        "Account": b.account_code,
                        "Name": b.account_name[:40] + "..." if len(b.account_name) > 40 else b.account_name,
                        "Type": b.account_type,
                        "Debit": b.debit,
                        "Credit": b.credit,
                        "Net": b.net_balance,
                        "Variance %": f"{b.variance_percent:.1%}" if b.variance_percent else "N/A",
                        "Anomaly": "⚠️" if b.is_anomaly else ""
                    })
                
                balance_df = pd.DataFrame(balance_data)
                st.dataframe(
                    balance_df,
                    use_container_width=True,
                    height=400,
                    column_config={
                        "Debit": st.column_config.NumberColumn(format="$%,.0f"),
                        "Credit": st.column_config.NumberColumn(format="$%,.0f"),
                        "Net": st.column_config.NumberColumn(format="$%,.0f"),
                    }
                )
            
            # Decisions for selected period
            decisions = db.query(DecisionModel).filter(
                DecisionModel.period_id == period_id
            ).all()
            
            if decisions:
                st.subheader(f"🎯 Decisions for {selected_period}")
                
                decision_data = []
                for d in decisions:
                    decision_data.append({
                        "Account": d.account_code,
                        "Action": d.action,
                        "Risk Score": d.risk_score,
                        "Confidence": d.confidence_score,
                        "Reviewed By": d.reviewed_by or "-",
                        "Created": d.created_at.strftime("%Y-%m-%d %H:%M") if d.created_at else "N/A"
                    })
                
                decision_df = pd.DataFrame(decision_data)
                st.dataframe(decision_df, use_container_width=True)
            
            # Audit logs
            st.divider()
            st.subheader("📜 Recent Audit Logs")
            
            logs = db.query(AuditLogModel).filter(
                AuditLogModel.period_id == period_id
            ).order_by(AuditLogModel.created_at.desc()).limit(50).all()
            
            if logs:
                log_data = []
                for log in logs:
                    log_data.append({
                        "Time": log.created_at.strftime("%H:%M:%S") if log.created_at else "",
                        "Event": log.event_type,
                        "Agent": log.agent_name or "-",
                        "Account": log.account_code or "-",
                        "Action": log.action or "-"
                    })
                
                log_df = pd.DataFrame(log_data)
                st.dataframe(log_df, use_container_width=True, height=300)
            else:
                st.info("No audit logs for this period.")
                
    except Exception as e:
        st.error(f"Database error: {str(e)}")
        st.info("Make sure the database is initialized. Run: `python -m scripts.init_db --seed`")


def main():
    """Main application."""
    render_header()
    config = render_sidebar()
    
    # Main content tabs
    tabs = st.tabs([
        "📊 Overview",
        "✅ Validations",
        "📈 Variance",
        "🎯 Decisions",
        "📝 Audit Log",
        "🧠 Learning",
        "📋 Data",
        "🗄️ History"
    ])
    
    with tabs[0]:
        render_overview_tab()
    
    with tabs[1]:
        render_validations_tab()
    
    with tabs[2]:
        render_variance_tab()
    
    with tabs[3]:
        render_decisions_tab()
    
    with tabs[4]:
        render_audit_tab()
    
    with tabs[5]:
        render_learning_tab()
    
    with tabs[6]:
        render_data_tab()
    
    with tabs[7]:
        render_history_tab()


if __name__ == "__main__":
    main()
