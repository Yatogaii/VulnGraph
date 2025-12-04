from graph.state import NodeState, preserve_state_meta_fields
from graph.plans import parse_plan_from_llm
from typing import Annotated
from prompts.template import apply_prompt_template
from models import get_model_by_type
from logger import logger

from langchain_core.tools import tool
from langgraph.types import Command
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from settings import settings


@tool
def handoff_to_planner(
    research_topic: Annotated[str, "The topic of the research task to be handed off."],
    locale: Annotated[str, "The user's detected language locale (e.g., en-US, zh-CN)."],
):
    """Handoff to planner agent to do plan."""
    # This tool is not returning anything: we're just using it
    # as a way for LLM to signal that it needs to hand off to planner agent
    return

def CoordinatorNode(state: NodeState):
    """A node that coordinates other nodes based on their states."""
    prompt = apply_prompt_template("coordinator", state)
    initial_topic = state.get("user_input", "")

    prompt += [SystemMessage(content=f"User input: {initial_topic}")]
    
    if initial_topic.strip() == "":
        raise ValueError("User input is empty for CoordinatorNode.")

    tools = [handoff_to_planner]

    response = (
        get_model_by_type("agentic")
        .bind_tools(tools)
        .invoke(input=prompt)
    )

    messages = state.get("messages", [])
    if response.content:
        messages.append(HumanMessage(content=response.content, name="CoordinatorNode"))

    goto = '_end_'
    if hasattr(response, "tool_calls") and response.tool_calls:
        for call in response.tool_calls:
            try:
                if call["name"] == "handoff_to_planner":
                    goto = "PlannerNode"
            except Exception as e:
                logger.error(f"Error processing tool call: {e}")
    else:
        # No tool calls detected - fallback to planner instead of ending
        logger.warning(
            "LLM didn't call any tools. This may indicate tool calling issues with the model. "
            "Falling back to planner to ensure research proceeds."
        )
        # Log full response for debugging
        logger.debug(f"Coordinator response content: {response.content}")
        logger.debug(f"Coordinator response object: {response}")
        # Fallback to planner to ensure workflow continues
        goto = "PlannerNode"

    return Command(
        update={
            "messages": messages,
        },
        goto=goto,
    )

def TriageNode(state: NodeState):
    """A node that triages vulnerabilities based on their states."""
    pass

@tool
def end_planning():
    """Signal the end of planning phase."""
    return

def PlannerNode(state: NodeState):
    """A node that plans actions based on the states of other nodes."""
    plan_iterations = state["plan_iterations"] if state.get("plan_iterations", 0) else 0
    
    logger.info(f"PlannerNode: Current plan iteration {plan_iterations}, max allowed {settings.max_plan_iterations}")

    if plan_iterations >= settings.max_plan_iterations:
        return Command(
            update=preserve_state_meta_fields(state),
            goto="ReporterNode",
        )

    assert len(state["messages"])>0, "No messages found in state for PlannerNode."

    msgs = state["messages"]
    msgs += [SystemMessage(content=f"Current plan iteration: {plan_iterations + 1}, max allowed: {settings.max_plan_iterations}", name="PlannerNode")]

    plan_iterations += 1    
    state["plan_iterations"] = plan_iterations
    
    prompt = apply_prompt_template("planner", state)

    response = (
        get_model_by_type("agentic")
        .bind_tools([end_planning])
        .invoke(input=prompt)
    )

    plan = None
    if isinstance(response.content, str):
        plan = parse_plan_from_llm(response.content)
    
    msgs += [AIMessage(content=response.content, name="PlannerNode")]

    # Check for tool calls to end planning
    goto = "PlannerNode"
    if plan:
        goto = "ReporterNode"
    
    return Command(
        update={
            "messages": msgs,
        },
        goto=goto,
    )

def UserFeedbackNode(state: NodeState):
    """A node that handles user feedback based on their states."""
    pass

def WorkerTeamNode(state: NodeState):
    """A node that represents a team of workers handling tasks based on their states."""
    pass

def AssetsAnalzerNode(state: NodeState):
    """A node that analyzes assets based on their states."""
    pass

def VulnAnalyzerNode(state: NodeState):
    """A node that analyzes vulnerabilities based on their states."""
    pass

def ReporterNode(state: NodeState):
    """A node that generates reports based on the states of other nodes."""

    return {"final_report": state["messages"]}