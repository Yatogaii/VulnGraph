from typing import TypedDict, List, Optional, Any
import json
from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_core.messages import BaseMessage, SystemMessage, ToolMessage, AIMessage
from schemas.plans import Step, extract_json_from_text
from tools.vuln_tools import vuln_tools
from models import get_model_by_type
from prompts.template import apply_prompt_template

class VulnDiscoverySubState(MessagesState):
    step: Step
    result: Optional[dict] # {"cve_ids": List[str], "summary": str}

def VulnDiscoveryNode(state: VulnDiscoverySubState):
    """
    Subgraph node for discovering vulnerabilities (CVEs).
    """
    step = state["step"]
    
    # Use the vuln_discovery prompt template
    # We need to pass 'discovery_target' to the template context
    # apply_prompt_template uses **context to render the template
    context = {
        "discovery_target": step.target,
        "messages": state["messages"] # Pass messages for history
    }
    
    # Manually call _get_prompt_template logic or just pass context to apply_prompt_template
    # apply_prompt_template signature: (prompt_name: str, state: NodeState, **context)
    # It expects state["messages"]. Our SubState has "messages".
    prompt = apply_prompt_template("vuln_discovery", state, discovery_target=step.target)
    
    prompt.append(SystemMessage(content=f"""
Current Discovery Task:
- Title: {step.title}
- Target: {step.target}
- Description: {step.description}
"""))
    
    response = (
        get_model_by_type("agentic")
        .bind_tools(vuln_tools)
        .invoke(input=prompt)
    )
    
    # If no tool calls, we are done
    if not response.tool_calls:
        content = response.content
        cve_ids = []
        summary = ""
        
        if isinstance(content, str):
            json_str = extract_json_from_text(content)
            if json_str:
                try:
                    data = json.loads(json_str)
                    if isinstance(data, dict):
                        cve_ids = data.get("cve_ids", [])
                        summary = data.get("summary", "")
                except json.JSONDecodeError:
                    summary = content # Fallback
            else:
                summary = content
        
        return {
            "messages": [response],
            "result": {
                "type": "vuln_discovery",
                "cve_ids": cve_ids,
                "summary": summary
            }
        }
    
    # If tool calls, return response to trigger ToolNode
    return {"messages": [response]}

# Build the subgraph
builder = StateGraph(VulnDiscoverySubState)

builder.add_node("VulnDiscoveryNode", VulnDiscoveryNode)
builder.add_node("VulnToolNode", ToolNode(vuln_tools))

builder.add_edge(START, "VulnDiscoveryNode")

# Conditional edge: if tool calls -> ToolNode, else -> END
builder.add_conditional_edges(
    "VulnDiscoveryNode",
    tools_condition,
    {
        "tools": "VulnToolNode",
        "__end__": END
    }
)

builder.add_edge("VulnToolNode", "VulnDiscoveryNode")

vuln_discovery_subgraph = builder.compile()
