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
from app.services import get_audit_service, get_explanation_service

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
        st.markdown(f"""
        | Status | Count | Percentage |
        |--------|-------|------------|
        | ✅ Auto-Approved | {auto_approved} | {auto_approved/total*100:.1f}% |
        | 🔴 Escalated | {escalated} | {escalated/total*100:.1f}% |
        | 🟡 Pending Review | {pending} | {pending/total*100:.1f}% |
        | **Total** | **{total}** | **100%** |
        """)
    
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
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        if st.button("✅ Approve", key=f"approve_{decision_id}"):
                            submit_feedback(decision_id, "approved")
                            st.session_state.feedback_submitted[feedback_key] = "Approved"
                            st.rerun()
                    
                    with col2:
                        if st.button("❌ Reject", key=f"reject_{decision_id}"):
                            submit_feedback(decision_id, "rejected")
                            st.session_state.feedback_submitted[feedback_key] = "Rejected"
                            st.rerun()
                    
                    reason = st.text_input("Reason (optional)", key=f"reason_{decision_id}")


def submit_feedback(decision_id: str, feedback_type: str, reason: str = None):
    """Submit feedback for a decision."""
    try:
        feedback = {
            "decision_id": decision_id,
            "user_id": "streamlit_user",
            "feedback_type": feedback_type,
            "reason": reason
        }
        
        run_async(
            st.session_state.orchestrator.process_feedback(feedback)
        )
        
        st.success("Feedback submitted!")
    except Exception as e:
        st.error(f"Failed to submit feedback: {e}")


def render_audit_tab():
    """Render the audit log tab."""
    result = st.session_state.pipeline_result
    if not result:
        st.info("Run the pipeline first to see audit logs.")
        return
    
    audit_log = result.get("audit_log", [])
    
    st.subheader("📝 Audit Trail")
    st.write(f"Total events: {len(audit_log)}")
    
    if not audit_log:
        st.info("No audit events recorded.")
        return
    
    # Convert to DataFrame
    df_data = []
    for event in audit_log:
        df_data.append({
            "Timestamp": event.get("timestamp", ""),
            "Event Type": event.get("event_type", ""),
            "Agent": event.get("agent_type", ""),
            "Entity": event.get("entity_id", "")[:8] + "..." if event.get("entity_id") else "",
            "Account": event.get("account_id", ""),
        })
    
    df = pd.DataFrame(df_data)
    
    # Filter
    event_types = df["Event Type"].unique().tolist()
    selected_types = st.multiselect("Filter by Event Type", event_types, default=event_types)
    
    filtered_df = df[df["Event Type"].isin(selected_types)]
    
    st.dataframe(filtered_df, use_container_width=True, height=400)
    
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
    """Render the learning insights tab."""
    st.subheader("🧠 Learning Insights")
    
    if not st.session_state.pipeline_result:
        st.info("Run the pipeline and submit feedback to see learning insights.")
        return
    
    # Get learning insights
    try:
        insights = run_async(
            st.session_state.orchestrator.get_learning_insights()
        )
        
        if insights.get("success"):
            result = insights.get("result", {})
            metrics = result.get("metrics", {})
            suggestions = result.get("suggestions", [])
            
            # Metrics
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Total Feedback", metrics.get("total_feedback", 0))
            with col2:
                st.metric("Override Rate", f"{metrics.get('override_rate', 0):.1%}")
            with col3:
                st.metric("Agreement Rate", f"{metrics.get('agreement_rate', 0):.1%}")
            with col4:
                accuracy = metrics.get("accuracy_estimate")
                st.metric("Accuracy Estimate", f"{accuracy:.1%}" if accuracy else "N/A")
            
            st.divider()
            
            # Suggestions
            st.subheader("💡 Improvement Suggestions")
            
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
                st.success("No adjustments needed at this time.")
            
            # Threshold status
            st.subheader("⚙️ Current Thresholds")
            thresholds = metrics.get("suggested_thresholds", {})
            
            if thresholds:
                for param, value in thresholds.items():
                    st.write(f"- **{param}**: {value:.2f}")
            else:
                st.write("Using default thresholds.")
                
    except Exception as e:
        st.error(f"Failed to get learning insights: {e}")


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
        "📋 Data"
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


if __name__ == "__main__":
    main()
