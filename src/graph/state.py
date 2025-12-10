from typing import List, Optional, Any, Dict
from typing_extensions import Annotated
import operator
from langgraph.graph import MessagesState
from schemas.plans import Plan
from schemas.vulns import Vuln

class NodeState(MessagesState):
    user_input: str
    run_id: Optional[str]
    label: str
    status: str
    goto: Optional[str]
    vulns: Optional[List[Vuln]]

    plan_iterations: int
    plan: Optional[Plan]
    
    # Parallel execution results: key=step_id, value=result
    step_results: Annotated[Dict[str, Any], operator.or_]

    plan_review_status: Optional[str]
    plan_review_comment: Optional[str]

    execution_start_time: Optional[float]
    final_report: str
    
def preserve_state_meta_fields(state: NodeState) -> dict[str, Any]:
    """Return a dict with the NodeState meta fields preserved in 'key': value format.

    This helper returns a minimal mapping of relevant state metadata so it can be
    persisted, logged, or copied without including the full messages payload.
    """
    # Use mapping-style access (state["field"]) to ensure compatibility with
    # typed MessageState objects which may act like mappings internally.
    return {
        "user_input": state["user_input"],
        "run_id": state.get("run_id"),
        "label": state["label"],
        "status": state["status"],
        "goto": state["goto"],
        "vulns": state["vulns"],
        "plan_iterations": state["plan_iterations"],
        "plan_review_status": state.get("plan_review_status"),
        "plan_review_comment": state.get("plan_review_comment"),
        "execution_start_time": state.get("execution_start_time"),
        "final_report": state["final_report"],
    }