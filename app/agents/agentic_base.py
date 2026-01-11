"""
Agentic AI Base Class
=====================
Provides true agentic capabilities: goals, beliefs, planning,
reflection, memory, and inter-agent communication.
"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Optional, Callable
from enum import Enum
import structlog
import uuid
import asyncio
from collections import deque

from app.models import AgentType, AgentState, AuditEvent
from app.config import get_settings


class AgentCapability(str, Enum):
    """Capabilities an agent can have."""
    REASONING = "reasoning"
    PLANNING = "planning"
    LEARNING = "learning"
    MEMORY = "memory"
    COMMUNICATION = "communication"
    REFLECTION = "reflection"
    TOOL_USE = "tool_use"


class Goal:
    """Represents an agent's goal."""
    def __init__(
        self,
        description: str,
        priority: float = 0.5,
        success_criteria: Optional[Callable[[], bool]] = None,
        deadline: Optional[datetime] = None
    ):
        self.id = str(uuid.uuid4())
        self.description = description
        self.priority = priority  # 0.0 to 1.0
        self.success_criteria = success_criteria
        self.deadline = deadline
        self.status = "active"  # active, achieved, failed, abandoned
        self.progress = 0.0
        self.created_at = datetime.utcnow()
        
    def is_achieved(self) -> bool:
        if self.success_criteria:
            return self.success_criteria()
        return self.progress >= 1.0
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "description": self.description,
            "priority": self.priority,
            "status": self.status,
            "progress": self.progress,
            "created_at": self.created_at.isoformat()
        }


class Belief:
    """Represents an agent's belief about the world."""
    def __init__(self, key: str, value: Any, confidence: float = 0.5, source: str = "observation"):
        self.key = key
        self.value = value
        self.confidence = confidence  # 0.0 to 1.0
        self.source = source
        self.timestamp = datetime.utcnow()
        
    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "value": self.value,
            "confidence": self.confidence,
            "source": self.source,
            "timestamp": self.timestamp.isoformat()
        }


class AgentMessage:
    """Message for inter-agent communication."""
    def __init__(
        self,
        sender: str,
        receiver: str,
        message_type: str,
        content: dict[str, Any],
        priority: float = 0.5,
        requires_response: bool = False
    ):
        self.id = str(uuid.uuid4())
        self.sender = sender
        self.receiver = receiver
        self.message_type = message_type
        self.content = content
        self.priority = priority
        self.requires_response = requires_response
        self.timestamp = datetime.utcnow()
        self.response: Optional[dict] = None
        self.processed = False
        
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "sender": self.sender,
            "receiver": self.receiver,
            "type": self.message_type,
            "content": self.content,
            "priority": self.priority,
            "timestamp": self.timestamp.isoformat(),
            "processed": self.processed
        }


class Plan:
    """Represents an agent's plan to achieve a goal."""
    def __init__(self, goal: Goal, steps: list[dict]):
        self.id = str(uuid.uuid4())
        self.goal = goal
        self.steps = steps  # [{"action": str, "params": dict, "status": str}]
        self.current_step = 0
        self.status = "pending"  # pending, executing, completed, failed
        self.created_at = datetime.utcnow()
        
    def get_next_step(self) -> Optional[dict]:
        if self.current_step < len(self.steps):
            return self.steps[self.current_step]
        return None
    
    def advance(self, success: bool = True):
        if self.current_step < len(self.steps):
            self.steps[self.current_step]["status"] = "completed" if success else "failed"
            self.current_step += 1
            
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "goal": self.goal.description,
            "steps": self.steps,
            "current_step": self.current_step,
            "status": self.status
        }


class AgenticBase(ABC):
    """
    Base class for truly agentic AI agents.
    
    Agentic capabilities:
    - Goal-directed behavior
    - Belief maintenance (world model)
    - Planning and re-planning
    - Self-reflection and improvement
    - Inter-agent communication
    - Memory (short-term and long-term)
    - Autonomous decision making
    - Tool use
    """
    
    # Class-level message bus for inter-agent communication
    _message_bus: dict[str, deque] = {}
    _all_agents: dict[str, "AgenticBase"] = {}
    
    def __init__(self, agent_type: AgentType, capabilities: list[AgentCapability] = None):
        self.agent_type = agent_type
        self.agent_id = str(uuid.uuid4())
        self.agent_name = f"{agent_type.value}_{self.agent_id[:8]}"
        self.capabilities = capabilities or [
            AgentCapability.REASONING,
            AgentCapability.COMMUNICATION
        ]
        
        self.logger = structlog.get_logger().bind(
            agent_type=agent_type.value,
            agent_id=self.agent_id
        )
        self.settings = get_settings()
        
        # Agentic state
        self.goals: list[Goal] = []
        self.beliefs: dict[str, Belief] = {}
        self.plans: list[Plan] = []
        self.current_plan: Optional[Plan] = None
        
        # Memory systems
        self.short_term_memory: deque = deque(maxlen=100)  # Recent events
        self.working_memory: dict[str, Any] = {}  # Current task context
        self.episodic_memory: list[dict] = []  # Past experiences
        
        # Communication
        self._inbox: deque = deque(maxlen=50)
        self._outbox: deque = deque(maxlen=50)
        
        # Reflection and learning
        self.action_history: list[dict] = []
        self.reflection_insights: list[str] = []
        self.performance_metrics: dict[str, float] = {
            "success_rate": 0.0,
            "avg_confidence": 0.5,
            "goal_achievement_rate": 0.0
        }
        
        # Audit
        self._audit_log: list[AuditEvent] = []
        
        # Register agent
        AgenticBase._all_agents[self.agent_name] = self
        AgenticBase._message_bus[self.agent_name] = self._inbox
        
        # LLM client
        self._llm_client = None
        
    def _get_llm_client(self):
        """Lazy-load OpenRouter LLM client."""
        if self._llm_client is None and self.settings.openrouter_api_key:
            try:
                from openai import OpenAI
                self._llm_client = OpenAI(
                    api_key=self.settings.openrouter_api_key,
                    base_url=self.settings.openrouter_base_url,
                    default_headers={
                        "HTTP-Referer": "https://github.com/Kartik-ins/Balance_Sheet",
                        "X-Title": "Financial Assurance Platform"
                    }
                )
            except Exception as e:
                self.logger.warning("llm_client_init_failed", error=str(e))
        return self._llm_client
    
    async def _call_llm(self, prompt: str, system_prompt: str = None, temperature: float = 0.7) -> str:
        """Call the LLM for reasoning, planning, or reflection."""
        client = self._get_llm_client()
        if not client:
            return "[LLM not available - using fallback reasoning]"
        
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            
            response = client.chat.completions.create(
                model=self.settings.openrouter_model,
                messages=messages,
                temperature=temperature,
                max_tokens=1000
            )
            return response.choices[0].message.content
        except Exception as e:
            self.logger.error("llm_call_failed", error=str(e))
            return f"[LLM error: {str(e)}]"
    
    # ==================== GOAL MANAGEMENT ====================
    
    def add_goal(self, description: str, priority: float = 0.5, 
                 success_criteria: Callable = None) -> Goal:
        """Add a new goal for the agent to pursue."""
        goal = Goal(description, priority, success_criteria)
        self.goals.append(goal)
        self.goals.sort(key=lambda g: g.priority, reverse=True)
        
        self.log_action("goal_added", {"goal": goal.description, "priority": priority})
        return goal
    
    def get_active_goals(self) -> list[Goal]:
        """Get all active (not achieved/failed) goals."""
        return [g for g in self.goals if g.status == "active"]
    
    def update_goal_progress(self, goal_id: str, progress: float):
        """Update progress on a goal."""
        for goal in self.goals:
            if goal.id == goal_id:
                goal.progress = min(1.0, progress)
                if goal.is_achieved():
                    goal.status = "achieved"
                    self.log_action("goal_achieved", {"goal": goal.description})
                break
    
    # ==================== BELIEF MANAGEMENT ====================
    
    def update_belief(self, key: str, value: Any, confidence: float = 0.5, source: str = "observation"):
        """Update the agent's beliefs about the world."""
        old_belief = self.beliefs.get(key)
        self.beliefs[key] = Belief(key, value, confidence, source)
        
        if old_belief and old_belief.value != value:
            self.log_action("belief_updated", {
                "key": key,
                "old_value": old_belief.value,
                "new_value": value,
                "confidence": confidence
            })
    
    def get_belief(self, key: str, default: Any = None) -> Any:
        """Get a belief value."""
        belief = self.beliefs.get(key)
        return belief.value if belief else default
    
    def get_belief_confidence(self, key: str) -> float:
        """Get confidence in a belief."""
        belief = self.beliefs.get(key)
        return belief.confidence if belief else 0.0
    
    # ==================== PLANNING ====================
    
    async def create_plan(self, goal: Goal) -> Plan:
        """Use LLM to create a plan for achieving a goal."""
        
        # Get current context
        context = {
            "beliefs": {k: v.to_dict() for k, v in self.beliefs.items()},
            "available_actions": self.get_available_actions(),
            "constraints": self.get_constraints()
        }
        
        prompt = f"""You are an autonomous AI agent planning how to achieve a goal.

GOAL: {goal.description}

CURRENT BELIEFS:
{self._format_beliefs()}

AVAILABLE ACTIONS:
{self.get_available_actions()}

Create a step-by-step plan to achieve this goal. For each step, specify:
1. The action to take
2. Any parameters needed
3. Expected outcome

Format as JSON array:
[
    {{"action": "action_name", "params": {{}}, "expected_outcome": "..."}},
    ...
]

Keep the plan concise (3-7 steps max).
"""
        
        response = await self._call_llm(prompt, system_prompt="You are a planning agent. Return only valid JSON.")
        
        try:
            import json
            # Extract JSON from response
            json_start = response.find('[')
            json_end = response.rfind(']') + 1
            if json_start >= 0 and json_end > json_start:
                steps = json.loads(response[json_start:json_end])
            else:
                steps = [{"action": "execute_default", "params": {}, "expected_outcome": "Complete goal"}]
        except:
            steps = [{"action": "execute_default", "params": {}, "expected_outcome": "Complete goal"}]
        
        # Add status to each step
        for step in steps:
            step["status"] = "pending"
        
        plan = Plan(goal, steps)
        self.plans.append(plan)
        self.current_plan = plan
        
        self.log_action("plan_created", {"goal": goal.description, "steps": len(steps)})
        return plan
    
    def get_available_actions(self) -> list[str]:
        """Return list of actions this agent can perform."""
        return ["analyze", "validate", "decide", "communicate", "reflect", "learn"]
    
    def get_constraints(self) -> list[str]:
        """Return constraints the agent must respect."""
        return [
            "Must maintain audit trail",
            "Must provide evidence for decisions",
            "Cannot approve high-risk items without human review"
        ]
    
    # ==================== INTER-AGENT COMMUNICATION ====================
    
    def send_message(self, receiver: str, message_type: str, content: dict, 
                     priority: float = 0.5, requires_response: bool = False) -> AgentMessage:
        """Send a message to another agent."""
        msg = AgentMessage(
            sender=self.agent_name,
            receiver=receiver,
            message_type=message_type,
            content=content,
            priority=priority,
            requires_response=requires_response
        )
        
        # Add to target's inbox if they exist
        if receiver in AgenticBase._message_bus:
            AgenticBase._message_bus[receiver].append(msg)
        
        self._outbox.append(msg)
        self.log_action("message_sent", {
            "to": receiver,
            "type": message_type,
            "priority": priority
        })
        
        return msg
    
    def broadcast_message(self, message_type: str, content: dict, priority: float = 0.5):
        """Broadcast a message to all agents."""
        for agent_name in AgenticBase._all_agents.keys():
            if agent_name != self.agent_name:
                self.send_message(agent_name, message_type, content, priority)
    
    def receive_messages(self) -> list[AgentMessage]:
        """Get all pending messages."""
        messages = list(self._inbox)
        self._inbox.clear()
        return sorted(messages, key=lambda m: m.priority, reverse=True)
    
    async def process_messages(self):
        """Process incoming messages and respond if needed."""
        messages = self.receive_messages()
        
        for msg in messages:
            msg.processed = True
            
            # Handle different message types
            if msg.message_type == "request_belief":
                key = msg.content.get("belief_key")
                response = {"belief": self.beliefs.get(key, {}).to_dict() if key in self.beliefs else None}
                if msg.requires_response:
                    self.send_message(msg.sender, "belief_response", response)
                    
            elif msg.message_type == "update_belief":
                self.update_belief(
                    msg.content["key"],
                    msg.content["value"],
                    msg.content.get("confidence", 0.5),
                    source=f"agent:{msg.sender}"
                )
                
            elif msg.message_type == "alert":
                # Store in working memory for consideration
                self.working_memory[f"alert_{msg.id}"] = msg.content
                
            self.log_action("message_processed", {
                "from": msg.sender,
                "type": msg.message_type
            })
    
    # ==================== MEMORY ====================
    
    def remember(self, event: dict, importance: float = 0.5):
        """Add an event to memory."""
        memory_entry = {
            "event": event,
            "importance": importance,
            "timestamp": datetime.utcnow().isoformat(),
            "agent": self.agent_name
        }
        
        self.short_term_memory.append(memory_entry)
        
        # Important events go to episodic memory
        if importance >= 0.7:
            self.episodic_memory.append(memory_entry)
    
    def recall(self, query: str, limit: int = 5) -> list[dict]:
        """Recall relevant memories based on query."""
        # Simple keyword matching for now
        query_words = set(query.lower().split())
        
        scored_memories = []
        for memory in list(self.short_term_memory) + self.episodic_memory:
            event_str = str(memory["event"]).lower()
            matches = sum(1 for word in query_words if word in event_str)
            if matches > 0:
                score = matches * memory["importance"]
                scored_memories.append((score, memory))
        
        scored_memories.sort(key=lambda x: x[0], reverse=True)
        return [m[1] for m in scored_memories[:limit]]
    
    # ==================== REFLECTION ====================
    
    async def reflect(self) -> str:
        """Reflect on recent actions and performance."""
        if AgentCapability.REFLECTION not in self.capabilities:
            return "Reflection capability not enabled"
        
        recent_actions = self.action_history[-20:] if self.action_history else []
        
        prompt = f"""You are an autonomous AI agent reflecting on your recent performance.

AGENT TYPE: {self.agent_type.value}

RECENT ACTIONS:
{self._format_actions(recent_actions)}

CURRENT GOALS:
{self._format_goals()}

PERFORMANCE METRICS:
{self.performance_metrics}

Reflect on:
1. What went well?
2. What could be improved?
3. What patterns do you notice?
4. What should you do differently next time?

Be specific and actionable in your insights.
"""
        
        reflection = await self._call_llm(prompt, temperature=0.8)
        self.reflection_insights.append(reflection)
        
        self.log_action("reflection_completed", {"insight_length": len(reflection)})
        return reflection
    
    # ==================== AUTONOMOUS REASONING ====================
    
    async def reason(self, situation: dict) -> dict:
        """Use LLM to reason about a situation and decide on action."""
        if AgentCapability.REASONING not in self.capabilities:
            return {"action": "default", "reasoning": "Reasoning not enabled"}
        
        prompt = f"""You are an autonomous AI agent that must reason about a situation and decide what to do.

SITUATION:
{situation}

YOUR BELIEFS:
{self._format_beliefs()}

YOUR GOALS:
{self._format_goals()}

RELEVANT MEMORIES:
{self.recall(str(situation), limit=3)}

Based on this information:
1. Analyze the situation
2. Consider your goals
3. Decide on the best action
4. Explain your reasoning

Format your response as:
ACTION: [your chosen action]
CONFIDENCE: [0.0 to 1.0]
REASONING: [your explanation]
"""
        
        response = await self._call_llm(prompt, temperature=0.5)
        
        # Parse response
        result = {
            "action": "default",
            "confidence": 0.5,
            "reasoning": response
        }
        
        lines = response.split('\n')
        for line in lines:
            if line.startswith("ACTION:"):
                result["action"] = line.replace("ACTION:", "").strip()
            elif line.startswith("CONFIDENCE:"):
                try:
                    result["confidence"] = float(line.replace("CONFIDENCE:", "").strip())
                except:
                    pass
            elif line.startswith("REASONING:"):
                result["reasoning"] = line.replace("REASONING:", "").strip()
        
        self.log_action("reasoning_completed", result)
        return result
    
    # ==================== LOGGING & AUDIT ====================
    
    def log_action(self, action_type: str, details: dict):
        """Log an action for history and audit."""
        action = {
            "type": action_type,
            "details": details,
            "timestamp": datetime.utcnow().isoformat(),
            "agent": self.agent_name
        }
        self.action_history.append(action)
        
        # Also add to short-term memory
        self.remember(action, importance=0.3)
    
    def log_audit_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        entity_id: Optional[str] = None,
        period_id: Optional[str] = None,
        account_id: Optional[str] = None,
    ) -> AuditEvent:
        """Log an immutable audit event."""
        event = AuditEvent(
            event_type=event_type,
            agent_type=self.agent_type,
            entity_id=entity_id,
            period_id=period_id,
            account_id=account_id,
            payload=payload,
            version_refs={"agent_version": "2.0.0-agentic"},
            timestamp=datetime.utcnow()
        )
        self._audit_log.append(event)
        return event
    
    def get_audit_log(self) -> list[AuditEvent]:
        return self._audit_log.copy()
    
    # ==================== HELPER METHODS ====================
    
    def _format_beliefs(self) -> str:
        if not self.beliefs:
            return "No beliefs yet."
        return "\n".join([
            f"- {k}: {v.value} (confidence: {v.confidence:.2f})"
            for k, v in self.beliefs.items()
        ])
    
    def _format_goals(self) -> str:
        active = self.get_active_goals()
        if not active:
            return "No active goals."
        return "\n".join([
            f"- {g.description} (priority: {g.priority:.2f}, progress: {g.progress:.0%})"
            for g in active
        ])
    
    def _format_actions(self, actions: list) -> str:
        if not actions:
            return "No recent actions."
        return "\n".join([
            f"- [{a['timestamp']}] {a['type']}: {a.get('details', {})}"
            for a in actions[-10:]
        ])
    
    # ==================== ABSTRACT METHODS ====================
    
    @abstractmethod
    async def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        """Execute the agent's primary task."""
        pass
    
    @abstractmethod
    def validate_input(self, context: dict[str, Any]) -> bool:
        """Validate input context."""
        pass
    
    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """Run the agent with full agentic lifecycle."""
        run_id = str(uuid.uuid4())
        
        # Process any pending messages first
        await self.process_messages()
        
        self.log_action("run_started", {"run_id": run_id})
        
        try:
            # Validate input
            if not self.validate_input(context):
                raise ValueError(f"Invalid input for {self.agent_type.value} agent")
            
            # Execute main task
            result = await self.execute(context)
            
            # Update beliefs based on result
            self.update_belief("last_run_success", True, confidence=1.0)
            self.update_belief("last_result_summary", str(result.get("summary", ""))[:200], confidence=0.9)
            
            # Update goal progress
            for goal in self.get_active_goals():
                if goal.is_achieved():
                    goal.status = "achieved"
            
            # Remember this execution
            self.remember({
                "type": "execution",
                "result": "success",
                "summary": result.get("summary", {})
            }, importance=0.6)
            
            self.log_action("run_completed", {"run_id": run_id, "success": True})
            
            return {
                "success": True,
                "run_id": run_id,
                "agent_type": self.agent_type.value,
                "agent_name": self.agent_name,
                "result": result,
                "beliefs": {k: v.to_dict() for k, v in self.beliefs.items()},
                "goals": [g.to_dict() for g in self.goals],
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            self.update_belief("last_run_success", False, confidence=1.0)
            self.update_belief("last_error", str(e), confidence=1.0)
            
            self.remember({
                "type": "execution",
                "result": "failure",
                "error": str(e)
            }, importance=0.9)
            
            self.log_action("run_failed", {"run_id": run_id, "error": str(e)})
            
            return {
                "success": False,
                "run_id": run_id,
                "agent_type": self.agent_type.value,
                "agent_name": self.agent_name,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
    
    def get_state(self) -> dict:
        """Get complete agent state for debugging/UI."""
        return {
            "agent_name": self.agent_name,
            "agent_type": self.agent_type.value,
            "capabilities": [c.value for c in self.capabilities],
            "goals": [g.to_dict() for g in self.goals],
            "beliefs": {k: v.to_dict() for k, v in self.beliefs.items()},
            "current_plan": self.current_plan.to_dict() if self.current_plan else None,
            "performance_metrics": self.performance_metrics,
            "recent_actions": self.action_history[-10:],
            "pending_messages": len(self._inbox),
            "reflection_count": len(self.reflection_insights)
        }
