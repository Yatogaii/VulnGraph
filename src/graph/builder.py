from graph.state import NodeState
from graph.nodes import (
    CoordinatorNode,
    TriageNode,
    PlannerNode,
    UserFeedbackNode,
    WorkerTeamNode,
    AssetsAnalzerNode,
    VulnAnalyzerNode,
    ReporterNode
)

from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph

def whether_to_continue_analyses(state: NodeState):
    pass
    

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
    graph.add_node("ReporterNode", ReporterNode)

    graph.add_edge(START, "CoordinatorNode")
    graph.add_edge("ReporterNode", END)

    graph.add_conditional_edges(
        source="WorkerTeamNode",
        path=whether_to_continue_analyses,
        path_map=["PlannerNode", "VulnAnalyzerNode", "AssetsAnalzerNode"],
    )

    return graph

def build_graph() -> CompiledStateGraph:
    graph = _build_base_graph()

    return graph.compile()

graph = build_graph()