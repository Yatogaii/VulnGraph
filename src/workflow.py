import asyncio
import os
import uuid
import copy
from datetime import datetime
from typing import Any, Callable, cast
from graph.state import NodeState
from graph.builder import get_graph
from langchain_core.runnables.config import RunnableConfig
from langgraph.types import Command

from logger import logger

from rich.console import Console
from rich.pretty import Pretty
from langchain_core.load.serializable import Serializable
from pydantic import BaseModel

console = Console()

EventSink = Callable[[Any], None]

# 报告输出目录
REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "reports")



def _save_report_to_markdown(report: str, user_input: str) -> str:
    """Save the final report to a markdown file.
    
    Args:
        report: The report content to save
        user_input: The original user input (used for filename)
        
    Returns:
        The path to the saved report file
    """
    # 确保报告目录存在
    os.makedirs(REPORTS_DIR, exist_ok=True)
    
    # 生成文件名：时间戳 + 简化的用户输入
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # 清理用户输入作为文件名的一部分（只保留前30个字符，移除特殊字符）
    safe_input = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in user_input[:30]).strip()
    safe_input = safe_input.replace(' ', '_')
    
    filename = f"report_{timestamp}_{safe_input}.md"
    filepath = os.path.join(REPORTS_DIR, filename)
    
    # 写入报告
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(report)
    
    return filepath


def get_run_state(run_id: str) -> NodeState | None:
    """Sync helper: returns cached state only. Use get_run_state_async for fresh state."""
async def get_run_state_async(run_id: str) -> NodeState | None:
    """Get the last state for a run_id via checkpointer (fallback to memory)."""
    cfg: RunnableConfig = cast(RunnableConfig, {"configurable": {"thread_id": run_id}})
    try:
        compiled_graph = await get_graph()
        snapshot = await compiled_graph.aget_state(cfg)
        if snapshot:
            values = None
            if hasattr(snapshot, "values"):
                values = snapshot.values
            elif isinstance(snapshot, dict):
                values = snapshot.get("values") or snapshot
            if values:
                return cast(NodeState, values)
    except Exception as e:
        logger.error(f"Failed to get state for {run_id} from checkpointer: {e}")
    return None


def _emit(renderable: Any, event_sink: EventSink | None) -> None:
    if event_sink is not None:
        event_sink(renderable)
        return
    console.print(renderable)


def _render_for_emit(obj: Any) -> Any:
    serialized = _serialize_for_print(obj)
    if isinstance(serialized, str):
        return serialized
    return Pretty(serialized)


async def run_agent_workflow_async(
    user_input: str,
    run_id: str | None = None,
    debug: bool = False,
    max_plan_iterations: int = 1,
    max_step_num: int = 3,
    enable_background_investigation: bool = True,
    enable_clarification: bool | None = None,
    max_clarification_rounds: int | None = None,
    initial_state: NodeState | None = None,
    resume_value: dict | None = None,
    event_sink: EventSink | None = None,
) -> None:
    # allow caller-provided run_id; fall back to state-provided or fresh uuid
    if initial_state is not None:
        run_id = run_id or initial_state.get("run_id")
    run_id = run_id or uuid.uuid4().hex
    logger.info(f"Starting agent workflow run_id={run_id} input: {user_input}")

    if initial_state is None:
        initial_state = NodeState({
            "user_input": user_input,
            "run_id": run_id,
            "messages": [],
            "label": "Start",
            "status": "initialized",
            "goto": None,
            "vulns": [],
            "plan": None,
            "plan_iterations": 0,
            "plan_review_status": None,
            "plan_review_comment": None,
            "final_report": "",
        })
    else:
        # ensure run_id is present on resumed state
        initial_state["run_id"] = run_id

    last_message_cnt = 0
    final_state = None
    compiled_graph = await get_graph()
    cfg: RunnableConfig = cast(RunnableConfig, {
        "recursion_limit": 100,
        "configurable": {"thread_id": run_id},
    })

    workflow_input = Command(resume=resume_value) if resume_value is not None else initial_state

    try:
        async for s in compiled_graph.astream(
            input=workflow_input,
            config=cfg,
        ):
            try:
                final_state = s
                # 缓存最近的状态，便于外部审批后恢复
                if isinstance(s, dict) and "messages" in s:
                    if len(s["messages"]) <= last_message_cnt:
                        continue
                    last_message_cnt = len(s["messages"])
                    message = s["messages"][-1]
                    if isinstance(message, tuple):
                        _emit(Pretty(message), event_sink)
                    else:
                        # Prefer a structured print for message objects (langchain messages
                        # often inherit from Serializable). For CLI, keep pretty_print.
                        if event_sink is None and hasattr(message, "pretty_print"):
                            try:
                                message.pretty_print()
                                continue
                            except Exception:
                                pass
                        try:
                            _emit(_render_for_emit(message), event_sink)
                        except Exception:
                            _emit(repr(message), event_sink)
                else:
                    _emit(_render_for_emit(s), event_sink)

                # 如果等待用户审批，立即返回，留给外部触发恢复
                # Check for interrupt signal
                if isinstance(s, dict) and "__interrupt__" in s:
                     _emit("[yellow]Workflow interrupted. Waiting for user input.[/yellow]", event_sink)
                     logger.info(f"Run {run_id} interrupted")
                     return

            except Exception as e:
                _emit(f"Error processing output: {str(e)}", event_sink)
    except Exception as e:
        logger.exception(f"Workflow execution failed for run_id={run_id}: {e}")
        _emit(f"[red]Workflow execution failed: {e}[/red]", event_sink)
        raise
    
    # 保存最终报告到 markdown 文件
    if final_state and isinstance(final_state, dict):
        # final_state 可能是 {"ReporterNode": {...}} 的形式
        report_state = final_state.get("ReporterNode", final_state)
        final_report = report_state.get("final_report", "") if isinstance(report_state, dict) else ""
        
        # Try to get user_input from state if not provided (e.g. resume)
        if not user_input and isinstance(report_state, dict):
            user_input = report_state.get("user_input", "")

        if final_report:
            try:
                report_path = _save_report_to_markdown(final_report, user_input)
                _emit(f"\n[green]✓ Report saved to: {report_path}[/green]", event_sink)
                logger.info(f"Report saved to: {report_path}")
            except Exception as e:
                _emit(f"[red]Failed to save report: {str(e)}[/red]", event_sink)
                logger.error(f"Failed to save report: {str(e)}")


def _serialize_for_print(obj: Any) -> Any:
    """Convert various objects into JSON-serializable/Python-native objects
    suitable for pretty-printing with `rich`.

    This function handles:
    - Objects exposing `to_json()` (LangChain Serializable objects)
    - Pydantic BaseModel instances (`model_dump()`)
    - Mappings, lists, tuples recursively
    - Fallback to `str(obj)` for unknown objects
    """
    # Avoid circular imports for Serializable check; we import at module top
    # so just test for the methods.
    if obj is None:
        return None
    # LangChain Serializable objects
    if hasattr(obj, "to_json") and callable(getattr(obj, "to_json")):
        try:
            return obj.to_json()
        except Exception:
            # Some LangChain objects may intentionally not provide JSON serializable
            # metadata - fall back to __repr__ so user can still inspect.
            return repr(obj)
    # Pydantic models
    if isinstance(obj, BaseModel):
        try:
            return obj.model_dump()
        except Exception:
            return repr(obj)
    # dict-like
    if isinstance(obj, dict):
        return {k: _serialize_for_print(v) for k, v in obj.items()}
    # list/tuple
    if isinstance(obj, (list, tuple)):
        return [_serialize_for_print(v) for v in obj]
    # simple scalars
    if isinstance(obj, (str, int, float, bool)):
        return obj
    # fallback
    try:
        return str(obj)
    except Exception:
        return repr(obj)
