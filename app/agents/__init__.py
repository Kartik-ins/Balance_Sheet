"""
Agents Package
==============
Autonomous AGENTIC AI agents for financial statement assurance.

Features:
- Goal-driven behavior
- LLM-powered reasoning
- Inter-agent communication
- Self-reflection and learning
- Memory and beliefs
"""
from app.agents.base import BaseAgent
from app.agents.agentic_base import AgenticBase, AgentCapability, Goal, Belief, AgentMessage, Plan
from app.agents.ingestion import IngestionAgent
from app.agents.validation import ValidationAgent
from app.agents.variance import VarianceReasoningAgent
from app.agents.decision import DecisionAgent
from app.agents.learning import LearningAgent
from app.agents.orchestrator import AgentOrchestrator
from app.agents.coordinator import CoordinatorAgent
from app.agents.supervisor import SupervisorAgent

__all__ = [
    # Base classes
    "BaseAgent",
    "AgenticBase",
    "AgentCapability",
    "Goal",
    "Belief",
    "AgentMessage",
    "Plan",
    # Specialized agents
    "IngestionAgent",
    "ValidationAgent",
    "VarianceReasoningAgent",
    "DecisionAgent",
    "LearningAgent",
    # Coordination
    "AgentOrchestrator",
    "CoordinatorAgent",
    "SupervisorAgent",
]
