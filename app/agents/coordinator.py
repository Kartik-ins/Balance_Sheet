"""
Coordinator Agent
=================
High-level agent that manages goals, creates plans, and
delegates tasks to specialized agents.
"""
from datetime import datetime
from typing import Any, Optional
import asyncio

from app.agents.agentic_base import AgenticBase, AgentCapability, Goal, Plan
from app.models import AgentType


class CoordinatorAgent(AgenticBase):
    """
    The Coordinator Agent is the 'brain' that:
    - Receives high-level objectives
    - Breaks them down into sub-goals
    - Delegates to specialized agents
    - Monitors progress
    - Handles failures and re-planning
    """
    
    def __init__(self):
        super().__init__(
            agent_type=AgentType.ORCHESTRATOR,
            capabilities=[
                AgentCapability.REASONING,
                AgentCapability.PLANNING,
                AgentCapability.COMMUNICATION,
                AgentCapability.REFLECTION,
                AgentCapability.MEMORY
            ]
        )
        
        # Track delegated tasks
        self.delegated_tasks: dict[str, dict] = {}
        self.agent_registry: dict[str, AgenticBase] = {}
        
        # Default goals
        self.add_goal(
            "Maximize auto-approval rate while maintaining accuracy",
            priority=0.8
        )
        self.add_goal(
            "Minimize false negatives (missed risks)",
            priority=0.9
        )
        self.add_goal(
            "Complete assurance pipeline efficiently",
            priority=0.7
        )
    
    def register_agent(self, agent: AgenticBase):
        """Register a specialized agent for delegation."""
        self.agent_registry[agent.agent_type.value] = agent
        self.log_action("agent_registered", {
            "agent_type": agent.agent_type.value,
            "agent_name": agent.agent_name
        })
    
    def validate_input(self, context: dict[str, Any]) -> bool:
        return "objective" in context or "task" in context
    
    async def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        """
        Execute the coordination task.
        
        1. Understand the objective
        2. Create a plan
        3. Delegate to agents
        4. Monitor and adapt
        5. Aggregate results
        """
        objective = context.get("objective", context.get("task", "Process trial balance"))
        
        # Create a goal for this objective
        goal = self.add_goal(objective, priority=0.9)
        
        # Reason about how to achieve the goal
        reasoning = await self.reason({
            "objective": objective,
            "available_agents": list(self.agent_registry.keys()),
            "context": {k: str(v)[:100] for k, v in context.items()}
        })
        
        # Create a plan
        plan = await self.create_plan(goal)
        plan.status = "executing"
        
        # Execute the plan
        results = {}
        all_messages = []
        
        for i, step in enumerate(plan.steps):
            step_action = step.get("action", "")
            step_params = step.get("params", {})
            
            self.log_action("executing_step", {
                "step": i + 1,
                "action": step_action,
                "total_steps": len(plan.steps)
            })
            
            # Determine which agent should handle this
            target_agent = self._get_agent_for_action(step_action)
            
            if target_agent:
                # Delegate to the agent
                task_id = f"task_{i}_{step_action}"
                
                # Send task message
                msg = self.send_message(
                    receiver=target_agent.agent_name,
                    message_type="task_assignment",
                    content={
                        "action": step_action,
                        "params": {**step_params, **context},
                        "deadline": None
                    },
                    priority=0.8,
                    requires_response=True
                )
                
                all_messages.append(msg.to_dict())
                
                # Execute the agent
                try:
                    agent_result = await target_agent.run({**step_params, **context})
                    results[step_action] = agent_result
                    
                    # Check if successful
                    if agent_result.get("success"):
                        plan.advance(success=True)
                        self.update_goal_progress(goal.id, (i + 1) / len(plan.steps))
                        
                        # Update context with results for next step
                        if "result" in agent_result:
                            context.update(agent_result["result"])
                    else:
                        plan.advance(success=False)
                        # Could trigger re-planning here
                        
                except Exception as e:
                    plan.advance(success=False)
                    results[step_action] = {"error": str(e)}
            else:
                # No agent for this action, skip
                plan.advance(success=True)
        
        # Mark plan as completed
        plan.status = "completed"
        goal.status = "achieved"
        
        # Reflect on the execution
        reflection = await self.reflect()
        
        return {
            "objective": objective,
            "plan": plan.to_dict(),
            "agent_results": results,
            "messages": all_messages,
            "reflection": reflection,
            "reasoning": reasoning,
            "summary": {
                "steps_completed": plan.current_step,
                "total_steps": len(plan.steps),
                "success": plan.status == "completed"
            }
        }
    
    def _get_agent_for_action(self, action: str) -> Optional[AgenticBase]:
        """Map an action to the appropriate agent."""
        action_lower = action.lower()
        
        mappings = {
            "ingest": "ingestion",
            "parse": "ingestion",
            "load": "ingestion",
            "validate": "validation",
            "check": "validation",
            "verify": "validation",
            "variance": "variance",
            "analyze": "variance",
            "compare": "variance",
            "decide": "decision",
            "approve": "decision",
            "escalate": "decision",
            "learn": "learning",
            "feedback": "learning",
            "improve": "learning"
        }
        
        for keyword, agent_type in mappings.items():
            if keyword in action_lower:
                return self.agent_registry.get(agent_type)
        
        return None
    
    async def handle_failure(self, failed_step: dict, error: str) -> Plan:
        """Handle a step failure by re-planning."""
        prompt = f"""A step in my plan failed. I need to re-plan.

FAILED STEP: {failed_step}
ERROR: {error}

CURRENT GOAL: {self.current_plan.goal.description if self.current_plan else 'Unknown'}
REMAINING STEPS: {self.current_plan.steps[self.current_plan.current_step:] if self.current_plan else []}

How should I adapt? Should I:
1. Retry the step?
2. Skip and continue?
3. Create an alternative approach?

Provide a new plan as JSON array.
"""
        
        response = await self._call_llm(prompt)
        
        # For now, mark as needing human intervention
        self.broadcast_message(
            message_type="alert",
            content={
                "type": "step_failure",
                "step": failed_step,
                "error": error,
                "suggestion": response
            },
            priority=0.9
        )
        
        return self.current_plan
    
    async def monitor_agents(self) -> dict:
        """Monitor all registered agents' states."""
        agent_states = {}
        
        for agent_type, agent in self.agent_registry.items():
            state = agent.get_state()
            agent_states[agent_type] = {
                "name": state["agent_name"],
                "pending_messages": state["pending_messages"],
                "recent_actions": len(state["recent_actions"]),
                "active_goals": len([g for g in agent.goals if g.status == "active"]),
                "beliefs_count": len(state["beliefs"])
            }
        
        return agent_states
