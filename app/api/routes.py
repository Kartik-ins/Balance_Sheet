"""
API Routes
==========
FastAPI routes for the Financial Assurance Platform.
"""
from datetime import datetime
from typing import Any, Optional
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Depends
from pydantic import BaseModel
import pandas as pd
import io

from app.agents import AgentOrchestrator
from app.models import Entity, Period, Feedback, FeedbackType, DecisionAction
from app.services import get_audit_service, get_explanation_service


router = APIRouter()

# Global orchestrator instance
_orchestrator: Optional[AgentOrchestrator] = None


def get_orchestrator() -> AgentOrchestrator:
    """Get or create orchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = AgentOrchestrator()
    return _orchestrator


# ============================================================================
# Request/Response Models
# ============================================================================

class EntityCreate(BaseModel):
    code: str
    name: str
    currency: str = "USD"


class PeriodCreate(BaseModel):
    name: str
    start_date: datetime
    end_date: datetime
    entity_id: str


class PipelineRequest(BaseModel):
    entity_code: str
    entity_name: str
    period_name: str
    period_start: datetime
    period_end: datetime
    currency: str = "USD"


class FeedbackRequest(BaseModel):
    decision_id: str
    user_id: str
    feedback_type: str  # approved, rejected, override_approved, override_rejected
    reason: Optional[str] = None
    corrected_action: Optional[str] = None


class ExplanationRequest(BaseModel):
    account_id: str
    period_id: str
    explanation_type: str = "decision"  # decision, variance, finding


# ============================================================================
# Health & Status Endpoints
# ============================================================================

@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "Financial Assurance Platform"
    }


@router.get("/status")
async def get_status(orchestrator: AgentOrchestrator = Depends(get_orchestrator)):
    """Get system status and agent states."""
    return {
        "status": "running",
        "agents": orchestrator.get_agent_states(),
        "timestamp": datetime.utcnow().isoformat()
    }


# ============================================================================
# Pipeline Endpoints
# ============================================================================

@router.post("/pipeline/run")
async def run_pipeline(
    file: UploadFile = File(...),
    entity_code: str = Form(...),
    entity_name: str = Form(...),
    period_name: str = Form(...),
    period_start: str = Form(...),
    period_end: str = Form(...),
    currency: str = Form("USD"),
    orchestrator: AgentOrchestrator = Depends(get_orchestrator)
):
    """
    Run the full assurance pipeline on an uploaded trial balance file.
    
    Accepts CSV or Excel files with columns:
    - account_code (required)
    - account_name (required)
    - debit (required)
    - credit (required)
    - account_type (optional)
    """
    # Validate file type
    if not file.filename.endswith(('.csv', '.xlsx', '.xls')):
        raise HTTPException(
            status_code=400,
            detail="File must be CSV or Excel format"
        )
    
    # Read file content
    content = await file.read()
    
    try:
        if file.filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(content))
        else:
            df = pd.read_excel(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to parse file: {str(e)}"
        )
    
    # Create entity and period
    entity = Entity(
        code=entity_code,
        name=entity_name,
        currency=currency
    )
    
    period = Period(
        name=period_name,
        start_date=datetime.fromisoformat(period_start),
        end_date=datetime.fromisoformat(period_end),
        entity_id=entity.id
    )
    
    # Run pipeline
    try:
        result = await orchestrator.run_pipeline(
            entity=entity,
            period=period,
            dataframe=df
        )
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Pipeline execution failed: {str(e)}"
        )


@router.post("/pipeline/run-json")
async def run_pipeline_json(
    request: dict,
    orchestrator: AgentOrchestrator = Depends(get_orchestrator)
):
    """
    Run pipeline with JSON data (for programmatic access).
    
    Request body should contain:
    - entity: {code, name, currency}
    - period: {name, start_date, end_date}
    - balances: [{account_code, account_name, debit, credit}, ...]
    """
    try:
        entity = Entity(**request["entity"])
        period = Period(
            **request["period"],
            entity_id=entity.id
        )
        
        # Convert balances to DataFrame
        df = pd.DataFrame(request["balances"])
        
        result = await orchestrator.run_pipeline(
            entity=entity,
            period=period,
            dataframe=df,
            prior_balances=request.get("prior_balances"),
            historical_balances=request.get("historical_balances")
        )
        return result
    except KeyError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required field: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Pipeline execution failed: {str(e)}"
        )


# ============================================================================
# Decision Endpoints
# ============================================================================

@router.get("/decisions/{run_id}")
async def get_decisions(
    run_id: str,
    orchestrator: AgentOrchestrator = Depends(get_orchestrator)
):
    """Get decisions from a pipeline run."""
    # In production, would fetch from database
    if orchestrator.current_run and orchestrator.current_run.id == run_id:
        return {
            "run_id": run_id,
            "summary": orchestrator.current_run.summary
        }
    raise HTTPException(status_code=404, detail="Run not found")


@router.get("/decisions/{run_id}/pending")
async def get_pending_decisions(run_id: str):
    """Get decisions requiring human review."""
    # Would filter for pending/escalated decisions
    return {"run_id": run_id, "pending": []}


# ============================================================================
# Feedback Endpoints
# ============================================================================

@router.post("/feedback")
async def submit_feedback(
    feedback: FeedbackRequest,
    orchestrator: AgentOrchestrator = Depends(get_orchestrator)
):
    """Submit human feedback on a decision."""
    try:
        feedback_obj = Feedback(
            decision_id=feedback.decision_id,
            user_id=feedback.user_id,
            feedback_type=FeedbackType(feedback.feedback_type),
            reason=feedback.reason,
            corrected_action=DecisionAction(feedback.corrected_action) if feedback.corrected_action else None
        )
        
        result = await orchestrator.process_feedback(feedback_obj.model_dump())
        
        return {
            "status": "accepted",
            "feedback_id": feedback_obj.id,
            "result": result
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/feedback/summary")
async def get_feedback_summary(
    orchestrator: AgentOrchestrator = Depends(get_orchestrator)
):
    """Get summary of feedback and learning metrics."""
    insights = await orchestrator.get_learning_insights()
    return insights


# ============================================================================
# Explanation Endpoints
# ============================================================================

@router.post("/explain/decision")
async def explain_decision(decision: dict):
    """Generate explanation for a decision."""
    service = get_explanation_service()
    explanation = service.generate_decision_explanation(decision)
    return explanation


@router.post("/explain/variance")
async def explain_variance(variance: dict):
    """Generate explanation for a variance analysis."""
    service = get_explanation_service()
    explanation = service.generate_variance_explanation(
        variance,
        account_name=variance.get("account_name")
    )
    return explanation


@router.post("/explain/finding")
async def explain_finding(finding: dict):
    """Generate explanation for a finding."""
    service = get_explanation_service()
    explanation = service.generate_finding_explanation(finding)
    return explanation


# ============================================================================
# Audit Endpoints
# ============================================================================

@router.get("/audit/events")
async def get_audit_events(
    entity_id: Optional[str] = None,
    period_id: Optional[str] = None,
    event_type: Optional[str] = None,
    limit: int = 100
):
    """Query audit events."""
    service = get_audit_service()
    events = service.query_events(
        entity_id=entity_id,
        period_id=period_id,
        event_type=event_type,
        limit=limit
    )
    return {"events": [e.model_dump() for e in events]}


@router.get("/audit/trail/{account_id}/{period_id}")
async def get_audit_trail(account_id: str, period_id: str):
    """Get complete audit trail for an account/period."""
    service = get_audit_service()
    trail = service.get_decision_trail(account_id, period_id)
    return {"trail": trail}


@router.get("/audit/statistics")
async def get_audit_statistics():
    """Get audit statistics."""
    service = get_audit_service()
    return service.get_statistics()


@router.post("/audit/export")
async def export_audit_log(
    entity_id: Optional[str] = None,
    period_id: Optional[str] = None
):
    """Export audit log to file."""
    service = get_audit_service()
    filepath = service.export_audit_log(
        entity_id=entity_id,
        period_id=period_id
    )
    return {"status": "exported", "filepath": filepath}


# ============================================================================
# Agent Endpoints
# ============================================================================

@router.get("/agents")
async def list_agents(orchestrator: AgentOrchestrator = Depends(get_orchestrator)):
    """List all agents and their states."""
    return orchestrator.get_agent_states()


@router.get("/agents/audit-log")
async def get_combined_audit_log(
    orchestrator: AgentOrchestrator = Depends(get_orchestrator)
):
    """Get combined audit log from all agents."""
    return {"audit_log": orchestrator.get_audit_log()}


# ============================================================================
# Learning Endpoints
# ============================================================================

@router.get("/learning/insights")
async def get_learning_insights(
    orchestrator: AgentOrchestrator = Depends(get_orchestrator)
):
    """Get learning insights and threshold suggestions."""
    return await orchestrator.get_learning_insights()


@router.get("/learning/thresholds")
async def get_suggested_thresholds(
    orchestrator: AgentOrchestrator = Depends(get_orchestrator)
):
    """Get suggested threshold adjustments from learning."""
    return orchestrator.learning_agent.get_adjusted_thresholds()
