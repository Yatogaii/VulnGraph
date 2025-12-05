from graph.state import NodeState
from graph.nodes import (
    CoordinatorNode,
    TriageNode,
    PlannerNode,
    UserFeedbackNode,
    WorkerTeamNode,
    AssetsAnalzerNode,
    VulnAnalyzerNode,
    vuln_tool_node,
    ReporterNode
)
from schemas.plans import Plan

from langgraph.prebuilt import tools_condition
from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph

def decide_worker_team_goto(state: NodeState) -> str:
    """Decide which node the WorkerTeamNode should go to next based on state."""
    plan: Plan|None = state.get("plan", None)
    if plan is None:
        raise ValueError("No plan found in state for WorkerTeamNode decision.")
    if not plan.steps:
        return "ReporterNode"

    # Find first unfinished step
    incomplete_step = None
    for step in plan.steps:
        if not step.execution_res:
            incomplete_step = step
            break

    if incomplete_step is None:
        return "PlannerNode"
    if incomplete_step.step_type == "asset_analysis":
        return "AssetsAnalzerNode"
    elif incomplete_step.step_type == "vuln_analysis":
        return "VulnAnalyzerNode"
    else:
        return "PlannerNode"
    
def _build_base_graph() -> StateGraph:
    graph = StateGraph(state_schema=NodeState)

    graph.add_node("CoordinatorNode", CoordinatorNode)
    # Skil tirage node for now
    # graph.add_node("TriageNode", TriageNode)
    graph.add_node("PlannerNode", PlannerNode)
    graph.add_node("UserFeedbackNode", UserFeedbackNode)
    graph.add_node("WorkerTeamNode", WorkerTeamNode)
    graph.add_node("AssetsAnalzerNode", AssetsAnalzerNode)
    graph.add_node("VulnAnalyzerNode", VulnAnalyzerNode)
    graph.add_node("VulnToolNode", vuln_tool_node)
    graph.add_node("ReporterNode", ReporterNode)

    graph.add_edge(START, "CoordinatorNode")
    graph.add_edge("ReporterNode", END)

    graph.add_conditional_edges(
        source="WorkerTeamNode",
        path=decide_worker_team_goto,
        path_map=["PlannerNode", "VulnAnalyzerNode", "AssetsAnalzerNode"],
    )

    graph.add_conditional_edges(
        source="VulnAnalyzerNode",
        path=tools_condition,
        path_map={
            "tools": "VulnToolNode",
            "__end__": "WorkerTeamNode",
        }
    )

    return graph

def build_graph() -> CompiledStateGraph:
    graph = _build_base_graph()

    return graph.compile()

graph = build_graph()