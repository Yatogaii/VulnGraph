from typing import TypedDict, List, Optional
from langgraph.graph.message import AnyMessage

class NodeState(TypedDict):
    id: str
    label: str
    status: str
    goto: Optional[str]
    messages: List[AnyMessage]
    vulns: List[str]