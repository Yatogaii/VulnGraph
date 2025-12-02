from graph.state import NodeState
from typing import Annotated

from langchain_core.tools import tool
from langgraph.types import Command


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
    return Command(
        goto="PlannerNode",
    )
    pass

def TriageNode(state: NodeState):
    """A node that triages vulnerabilities based on their states."""
    pass

def PlannerNode(state: NodeState):
    """A node that plans actions based on the states of other nodes."""
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