from typing import TypedDict, List, Optional, Any
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_core.messages import BaseMessage, SystemMessage, ToolMessage, AIMessage
from schemas.plans import Step
from schemas.vulns import Vuln, parse_vulns_from_llm
from tools.vuln_tools import vuln_tools
from models import get_model_by_type
from prompts.template import apply_prompt_template

class VulnDetailSubState(TypedDict):
    messages: List[BaseMessage]
    step: Step
    result: Optional[dict] # {"execution_res": str, "vulns": List[Vuln]}

def VulnDetailAnalyzerNode(state: VulnDetailSubState):
    """
    Subgraph node for analyzing a single vulnerability detail step.
    """
    step = state["step"]
    
    # Reuse the existing prompt template logic
    prompt = apply_prompt_template("vuln_analyzer", state)
    
    # Append specific task info
    # If the target is a CVE ID, we can explicitly mention it
    prompt.append(SystemMessage(content=f"""
Current task:
- Title: {step.title}
- Target: {step.target}
- Description: {step.description}

Please focus on gathering detailed information for this specific target.
"""))
    
    response = (
        get_model_by_type("agentic")
        .bind_tools(vuln_tools)
        .invoke(input=prompt)
    )
    
    # If no tool calls, we are done
    if not response.tool_calls:
        content = response.content
        execution_res = ""
        vulns = []
        
        if isinstance(content, str):
            execution_res = content
            # Try to parse structured vulns from the response
            parsed_vulns = parse_vulns_from_llm(content, raise_on_error=False)
            if parsed_vulns:
                vulns = parsed_vulns
        elif content:
            execution_res = str(content)
        else:
            execution_res = "Vulnerability detail analysis completed."
            
        return {
            "messages": [response],
            "result": {
                "execution_res": execution_res,
                "vulns": vulns
            }
        }
    
    # If tool calls, return response to trigger ToolNode
    return {"messages": [response]}

# Build the subgraph
builder = StateGraph(VulnDetailSubState)

builder.add_node("VulnDetailAnalyzerNode", VulnDetailAnalyzerNode)
builder.add_node("VulnToolNode", ToolNode(vuln_tools))

builder.add_edge(START, "VulnDetailAnalyzerNode")

# Conditional edge: if tool calls -> ToolNode, else -> END
builder.add_conditional_edges(
    "VulnDetailAnalyzerNode",
    tools_condition,
    {
        "tools": "VulnToolNode",
        "__end__": END
    }
)

builder.add_edge("VulnToolNode", "VulnDetailAnalyzerNode")

vuln_detail_subgraph = builder.compile()
