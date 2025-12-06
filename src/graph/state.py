from typing import List, Optional, Any
from langgraph.graph import MessagesState
from schemas.plans import Plan
from schemas.vulns import Vuln

class NodeState(MessagesState):
    user_input: str
    label: str
    status: str
    goto: Optional[str]
    vulns: Optional[List[Vuln]]

    plan_iterations: int
    plan: Optional[Plan]

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
        "label": state["label"],
        "status": state["status"],
        "goto": state["goto"],
        "vulns": state["vulns"],
        "plan_iterations": state["plan_iterations"],
        "final_report": state["final_report"],
    }