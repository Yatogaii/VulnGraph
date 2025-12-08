import asyncio
import os
import uuid
import copy
from datetime import datetime
from typing import Any
from graph.state import NodeState
from graph.builder import graph

from logger import logger

from rich.console import Console
from rich.pretty import Pretty
from langchain_core.load.serializable import Serializable
from pydantic import BaseModel

console = Console()

# 报告输出目录
REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "reports")

# 简单的内存态缓存，后续可被 durable checkpointer 替换
RUN_STATE_CACHE: dict[str, NodeState] = {}


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
    """Get the last cached state for a run_id (in-memory only)."""
    return RUN_STATE_CACHE.get(run_id)


def update_plan_feedback_state(run_id: str, approved: bool, comment: str | None = None) -> NodeState | None:
    """Prepare a resumed state with user feedback applied.

    Returns the new state (not yet executed) or None if not found.
    """
    state = RUN_STATE_CACHE.get(run_id)
    if state is None:
        return None
    new_state = copy.deepcopy(state)
    new_state["plan_review_status"] = "approved" if approved else "rejected"
    if comment:
        new_state["plan_review_comment"] = comment
    return NodeState(new_state)

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
    async for s in graph.astream(
        input=initial_state,
        config={"recursion_limit": 100}
    ):
        try:
            final_state = s
            # 缓存最近的状态，便于外部审批后恢复
            if isinstance(s, dict):
                run_id = s.get("run_id", run_id)
                if run_id:
                    RUN_STATE_CACHE[run_id] = copy.deepcopy(s)
            if isinstance(s, dict) and "messages" in s:
                if len(s["messages"]) <= last_message_cnt:
                    continue
                last_message_cnt = len(s["messages"])
                message = s["messages"][-1]
                if isinstance(message, tuple):
                    console.print(Pretty(message))
                else:
                    # Prefer a structured print for message objects (langchain messages
                    # often inherit from Serializable). Fall back to pretty_print for
                    # runtime rendering when available.
                    try:
                        serial = _serialize_for_print(message)
                    except Exception:
                        # fallback to the existing method which prints nicely in
                        # interactive environments
                        message.pretty_print()
                    else:
                        console.print(Pretty(serial))
            else:
                console.print(Pretty(_serialize_for_print(s)))

            # 如果等待用户审批，立即返回，留给外部触发恢复
            if isinstance(s, dict) and s.get("plan_review_status") == "pending":
                console.print("[yellow]Waiting for user approval of plan. Use approve/reject commands or API.[/yellow]")
                logger.info(f"Run {run_id} waiting for plan approval")
                return
        except Exception as e:
            console.print(f"Error processing output: {str(e)}")
    
    # 保存最终报告到 markdown 文件
    if final_state and isinstance(final_state, dict):
        # final_state 可能是 {"ReporterNode": {...}} 的形式
        report_state = final_state.get("ReporterNode", final_state)
        final_report = report_state.get("final_report", "") if isinstance(report_state, dict) else ""
        
        if final_report:
            try:
                report_path = _save_report_to_markdown(final_report, user_input)
                console.print(f"\n[green]✓ Report saved to: {report_path}[/green]")
                logger.info(f"Report saved to: {report_path}")
            except Exception as e:
                console.print(f"[red]Failed to save report: {str(e)}[/red]")
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

