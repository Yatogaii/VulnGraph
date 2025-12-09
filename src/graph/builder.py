from graph.state import NodeState
from pathlib import Path
from typing import Any
import aiosqlite
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from graph.nodes import (
    CoordinatorNode,
    TriageNode,
    PlannerNode,
    UserFeedbackNode,
    WorkerTeamNode,
    AssetsAnalzerNode,
    VulnAnalyzerNode,
    vuln_tool_node,
    asset_tool_node,
    ReporterNode
)
from schemas.plans import Plan

from langgraph.prebuilt import tools_condition
from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph

CHECKPOINTS_DIR = Path(__file__).resolve().parent.parent / "data"
CHECKPOINTS_DIR.mkdir(parents=True, exist_ok=True)
CHECKPOINTS_DB = CHECKPOINTS_DIR / "checkpoints.sqlite"
# Ensure the db file exists to avoid aiosqlite open errors
CHECKPOINTS_DB.touch(exist_ok=True)
CHECKPOINTS_URL = str(CHECKPOINTS_DB.resolve())
_saver_ctx: Any | None = None
_checkpointer: AsyncSqliteSaver | None = None
_setup_done: bool = False
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
    graph.add_node("AssetToolNode", asset_tool_node)
    graph.add_node("VulnAnalyzerNode", VulnAnalyzerNode)
    graph.add_node("VulnToolNode", vuln_tool_node)
    graph.add_node("ReporterNode", ReporterNode)

    graph.add_edge(START, "CoordinatorNode")
    graph.add_edge("ReporterNode", END)
    # graph.add_edge("PlannerNode", "UserFeedbackNode")
    # UserFeedbackNode uses Command with goto, so no static edges needed
    # graph.add_edge("UserFeedbackNode", "PlannerNode")
    # graph.add_edge("UserFeedbackNode", "WorkerTeamNode")

    graph.add_conditional_edges(
        source="WorkerTeamNode",
        path=decide_worker_team_goto,
        path_map=["PlannerNode", "VulnAnalyzerNode", "AssetsAnalzerNode"],
    )

    graph.add_conditional_edges(
        source="AssetsAnalzerNode",
        path=tools_condition,
        path_map={
            "tools": "AssetToolNode",
            "__end__": "WorkerTeamNode",
        }
    )
    graph.add_edge("AssetToolNode", "AssetsAnalzerNode")

    graph.add_conditional_edges(
        source="VulnAnalyzerNode",
        path=tools_condition,
        path_map={
            "tools": "VulnToolNode",
            "__end__": "WorkerTeamNode",
        }
    )
    graph.add_edge("VulnToolNode", "VulnAnalyzerNode")

    return graph


compiled_graph: CompiledStateGraph | None = None


async def get_graph() -> CompiledStateGraph:
    """Lazily initialize and return the compiled graph with async sqlite checkpointer.

    We keep the saver open for the process lifetime by manually entering the
    async context once and reusing it.
    """
    global compiled_graph, _checkpointer, _saver_ctx
    if compiled_graph is not None:
        return compiled_graph

    if _checkpointer is None:
        _saver_ctx = AsyncSqliteSaver.from_conn_string(CHECKPOINTS_URL)
        _checkpointer = await _saver_ctx.__aenter__()
        # Run setup once to create tables
        global _setup_done
        if _checkpointer is not None and not _setup_done:
            await _checkpointer.setup()
            _setup_done = True


    g = _build_base_graph()
    compiled_graph = g.compile(checkpointer=_checkpointer)
    return compiled_graph