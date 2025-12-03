from graph.state import NodeState
from typing import Annotated
from prompts.template import get_prompt_template
from models import get_model_by_type
from logger import logger

from langchain_core.tools import tool
from langgraph.types import Command
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage


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
    prompt = get_prompt_template("coordinator")
    initial_topic = state.get("user_input", "")
    
    if initial_topic.strip() == "":
        raise ValueError("User input is empty for CoordinatorNode.")

    current_messages = [
        SystemMessage(content=prompt),
        HumanMessage(content=initial_topic, name="User"),
    ]

    tools = [handoff_to_planner]

    response = (
        get_model_by_type("agentic")
        .bind_tools(tools)
        .invoke(input=current_messages)
    )

    messages = state.get("messages", [])
    if response.content:
        messages.append(HumanMessage(content=response.content, name="CoordinatorNode"))

    goto = '_end_'
    if hasattr(response, "tool_calls") and response.tool_calls:
        for call in response.tool_calls:
            if call.__getattribute__("tool_name") == "handoff_to_planner":
                goto="PlannerNode",
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

def PlannerNode(state: NodeState):
    """A node that plans actions based on the states of other nodes."""
    pass

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
    pass