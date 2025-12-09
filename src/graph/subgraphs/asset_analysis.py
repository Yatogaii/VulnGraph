from typing import TypedDict, List, Optional, Any
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_core.messages import BaseMessage, SystemMessage, ToolMessage, AIMessage, RemoveMessage
from schemas.plans import Step
from tools.asset_tools import asset_tools
from models import get_model_by_type
from logger import logger
from prompts.template import apply_prompt_template
from langgraph.graph import MessagesState


class AssetSubState(MessagesState):
    step: Step
    result: Optional[str]

def AssetAnalyzerNode(state: AssetSubState):
    """
    Subgraph node for analyzing a single asset step.
    """
    step = state["step"]
    
    # Reuse the existing prompt template logic
    # Note: apply_prompt_template expects a dict-like state with "messages"
    # We pass our AssetSubState which has "messages"
    prompt = apply_prompt_template("asset_analyzer", state)
    
    # Append specific task info
    prompt.append(SystemMessage(content=f"""
Current task:
- Title: {step.title}
- Target: {step.target}
- Description: {step.description}
"""))
    
    response = (
        get_model_by_type("agentic")
        .bind_tools(asset_tools)
        .invoke(input=prompt)
    )
    
    # If no tool calls, we are done
    if not response.tool_calls:
        content = response.content
        if isinstance(content, str):
            execution_result = content
        elif content:
            execution_result = str(content)
        else:
            execution_result = "Asset analysis completed."
            
        return {
            "messages": [response],
            "result": execution_result
        }
    
    # If tool calls, return response to trigger ToolNode
    return {"messages": [response]}

# Build the subgraph
builder = StateGraph(AssetSubState)

builder.add_node("AssetAnalyzerNode", AssetAnalyzerNode)
builder.add_node("AssetToolNode", ToolNode(asset_tools))

builder.add_edge(START, "AssetAnalyzerNode")

# Conditional edge: if tool calls -> ToolNode, else -> END
builder.add_conditional_edges(
    "AssetAnalyzerNode",
    tools_condition,
    {
        "tools": "AssetToolNode",
        "__end__": END
    }
)

builder.add_edge("AssetToolNode", "AssetAnalyzerNode")

asset_analysis_subgraph = builder.compile()
