import asyncio
from typing import Any
from graph.state import NodeState
from graph.builder import graph

from logger import logger

from rich.console import Console
from rich.pretty import Pretty
from langchain_core.load.serializable import Serializable
from pydantic import BaseModel

console = Console()

async def run_agent_workflow_async(
    user_input: str,
    debug: bool = False,
    max_plan_iterations: int = 1,
    max_step_num: int = 3,
    enable_background_investigation: bool = True,
    enable_clarification: bool | None = None,
    max_clarification_rounds: int | None = None,
    initial_state: NodeState | None = None,
) -> None:
    logger.info(f"Starting agent workflow with input: {user_input}")

    if initial_state is None:
        initial_state = NodeState({
            "user_input": user_input,
            "messages": [],
            "label": "Start",
            "status": "initialized",
            "goto": None,
            "vulns": [],
            "plan": None,
            "plan_iterations": 0,
            "final_report": "",
        })

    last_message_cnt = 0
    final_state = None
    async for s in graph.astream(
        input=initial_state,
        config={"recursion_limit": 100}
    ):
        try:
            final_state = s
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
        except Exception as e:
            console.print(f"Error processing output: {str(e)}")


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

