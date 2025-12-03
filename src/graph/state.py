from typing import List, Optional
from langgraph.graph import MessagesState
class NodeState(MessagesState):
    user_input: str
    label: str
    status: str
    goto: Optional[str]
    vulns: List[str]

    final_report: str