"""
FastAPI Application
===================
Main entry point for the Financial Assurance Platform API.
"""
import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import router
from app.config import get_settings

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

settings = get_settings()

# Create FastAPI app
app = FastAPI(
    title="Autonomous Financial Assurance Platform",
    description="""
    An AI-driven platform for automated financial statement validation and assurance.
    
    ## Features
    
    - **Autonomous Agents**: Five specialized agents (Ingestion, Validation, Variance, Decision, Learning)
    - **Trial Balance Processing**: Upload and validate trial balance data
    - **Anomaly Detection**: Statistical and rule-based anomaly detection
    - **Auto-Approval**: Automatic approval of low-risk items
    - **Human-on-the-Loop**: Escalation of high-risk items for human review
    - **Continuous Learning**: System improves from human feedback
    - **Full Auditability**: Complete audit trail for all decisions
    
    ## Workflow
    
    1. Upload trial balance data via `/pipeline/run`
    2. System automatically processes through all agents
    3. Review escalated items and provide feedback
    4. System learns and improves over time
    """,
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router, prefix="/api/v1")


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": "Autonomous Financial Assurance Platform",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/api/v1/health"
    }


def run_server():
    """Run the server (for CLI entry point)."""
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug
    )


if __name__ == "__main__":
    run_server()
