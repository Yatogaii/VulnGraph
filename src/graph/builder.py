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
    VulnDetailNode,
    VulnDiscoveryNode,
    PlanRefineNode,
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

def _build_base_graph() -> StateGraph:
    graph = StateGraph(state_schema=NodeState)

    graph.add_node("CoordinatorNode", CoordinatorNode)
    graph.add_node("TriageNode", TriageNode)
    graph.add_node("PlannerNode", PlannerNode)
    graph.add_node("UserFeedbackNode", UserFeedbackNode)
    graph.add_node("WorkerTeamNode", WorkerTeamNode)
    graph.add_node("PlanRefineNode", PlanRefineNode)
    
    # Wrapper nodes for subgraphs
    graph.add_node("AssetsAnalzerNode", AssetsAnalzerNode)
    graph.add_node("VulnDetailNode", VulnDetailNode)
    graph.add_node("VulnDiscoveryNode", VulnDiscoveryNode)
    
    graph.add_node("ReporterNode", ReporterNode)

    graph.add_edge(START, "CoordinatorNode")
    graph.add_edge("ReporterNode", END)
    
    # Note: Most transitions are now handled by Command(goto=...) in the nodes.
    # We don't need explicit edges for those.
    
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