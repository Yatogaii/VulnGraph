from graph.state import NodeState, preserve_state_meta_fields
from schemas.plans import parse_plan_from_llm, Plan
from schemas.vulns import Vuln, ImpactedSoftware, parse_vulns_from_llm
from typing import Annotated
from prompts.template import apply_prompt_template
from models import get_model_by_type
from logger import logger
from tools.search import search_topic_by_ddgs
from tools.vuln_analyzer import get_cve_details

from langgraph.prebuilt import ToolNode
from langchain_core.tools import tool
from langgraph.types import Command
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage, RemoveMessage
from langchain_core.language_models.chat_models import BaseChatModel

from settings import settings


@tool
def handoff_to_planner(
    research_topic: Annotated[str, "The topic of the research task to be handed off."],
    locale: Annotated[str, "The user's detected language locale (e.g., en-US, zh-CN)."],
):
    """Handoff to planner agent to do plan."""
    # This tool is not returning anything: we're just using it
    # as a way for LLM to signal that it needs to hand off to planner agent
    return

def CoordinatorNode(state: NodeState):
    """A node that coordinates other nodes based on their states."""
    prompt = apply_prompt_template("coordinator", state)
    initial_topic = state.get("user_input", "")

    prompt += [SystemMessage(content=f"User input: {initial_topic}")]
    
    if initial_topic.strip() == "":
        raise ValueError("User input is empty for CoordinatorNode.")

    tools = [handoff_to_planner]

    response = (
        get_model_by_type("agentic")
        .bind_tools(tools)
        .invoke(input=prompt)
    )

    messages = state.get("messages", [])
    if response.content:
        messages.append(HumanMessage(content=response.content, name="CoordinatorNode"))

    goto = '_end_'
    if hasattr(response, "tool_calls") and response.tool_calls:
        for call in response.tool_calls:
            try:
                if call["name"] == "handoff_to_planner":
                    goto = "PlannerNode"
            except Exception as e:
                logger.error(f"Error processing tool call: {e}")
    else:
        # No tool calls detected - fallback to planner instead of ending
        logger.warning(
            "LLM didn't call any tools. This may indicate tool calling issues with the model. "
            "Falling back to planner to ensure research proceeds."
        )
        # Log full response for debugging
        logger.debug(f"Coordinator response content: {response.content}")
        logger.debug(f"Coordinator response object: {response}")
        # Fallback to planner to ensure workflow continues
        goto = "PlannerNode"

    return Command(
        update={
            "messages": messages,
        },
        goto=goto,
    )

def TriageNode(state: NodeState):
    """A node that triages vulnerabilities based on their states."""
    pass

def PlannerNode(state: NodeState):
    """A node that plans actions based on the states of other nodes."""
    plan_iterations = state["plan_iterations"] if state.get("plan_iterations", 0) else 0
    
    logger.info(f"PlannerNode: Current plan iteration {plan_iterations}, max allowed {settings.max_plan_iterations}")

    if plan_iterations >= settings.max_plan_iterations:
        return Command(
            update=preserve_state_meta_fields(state),
            goto="ReporterNode",
        )

    assert len(state["messages"])>0, "No messages found in state for PlannerNode."

    msgs = state["messages"]
    msgs += [SystemMessage(content=f"Current plan iteration: {plan_iterations + 1}, max allowed: {settings.max_plan_iterations}", name="PlannerNode")]
    if plan_iterations > 0:
        msgs += [SystemMessage(content=f"Previous plan: {state['plan']}", name="PlannerNode")]

    plan_iterations += 1    
    state["plan_iterations"] = plan_iterations
    
    prompt = apply_prompt_template("planner", state)

    response = (
        get_model_by_type("agentic")
        .invoke(input=prompt)
    )

    plan = None
    if isinstance(response.content, str):
        plan = parse_plan_from_llm(response.content)
    

    # Check for tool calls to end planning
    goto = "PlannerNode"
    if isinstance(plan, Plan):
        if plan.has_enough_context:
            goto = "ReporterNode"
        elif plan.finish_plan:
            goto = "WorkerTeamNode"
        else:
            goto = "PlannerNode"
    
    return Command(
        update={
            "plan_iterations": plan_iterations,
            "plan": plan,
        },
        goto=goto,
    )

def UserFeedbackNode(state: NodeState):
    """A node that handles user feedback based on their states."""
    pass

def WorkerTeamNode(state: NodeState):
    """A node that represents a team of workers handling tasks based on their states."""
    pass

def AssetsAnalzerNode(state: NodeState):
    """A node that analyzes assets based on their states."""
    pass

@tool
def search_ddgs_tool(query: str):
    """Search for a topic using DuckDuckGo."""
    return search_topic_by_ddgs(query)

@tool
def search_cve_tool(cve_id: str):
    """Search for a CVE by ID using NVD."""
    return get_cve_details(cve_id)

vuln_tools = [search_ddgs_tool, search_cve_tool]

vuln_tool_node = ToolNode(vuln_tools)

def VulnAnalyzerNode(state: NodeState):
    """A node that analyzes vulnerabilities based on their states."""
    prompt = apply_prompt_template("vuln_analyzer", state)
    
    tools = [search_ddgs_tool, search_cve_tool]
    
    response = (
        get_model_by_type("agentic")
        .bind_tools(tools)
        .invoke(input=prompt)
    )

    # not an tool call
    vulns = []
    plan: Plan | None = state.get("plan")
    if len(response.tool_calls) == 0 and response.content and isinstance(response.content, str):
        parsed_vulns = parse_vulns_from_llm(response.content, raise_on_error=False)
        if parsed_vulns:
            vulns.extend(parsed_vulns)
    
        # 更新第一个未完成的 step 的 execution_res
        if plan and plan.steps:
            for step in plan.steps:
                if step.execution_res is None:
                    step.execution_res = response.content if response.content else "No response content"
                    break

    if not response.tool_calls:
        # 我们寻找 State 里那些 "过期的" ToolCall 和 ToolMessage
        messages_to_delete = []
        for m in state["messages"]:
            if isinstance(m, (ToolMessage, AIMessage)):
                # 只有当这是历史消息（不是本次刚生成的）才删除
                # 逻辑可以根据需求定制，比如：删除除了 HumanMessage 以外的所有旧消息
                if m.id != None and m.id != response.id: 
                     messages_to_delete.append(RemoveMessage(id=m.id))
        return Command(
            update={
                "messages": [response] + messages_to_delete,
                "vulns": vulns,
                "plan": plan,  # 返回更新后的 plan
            },
        )
    
    return Command(
        update={
            "messages": [response],
            "vulns": vulns,
            "plan": plan,  # 返回更新后的 plan
        },
    )

def ReporterNode(state: NodeState):
    """A node that generates reports based on the states of other nodes."""
    
    # 构建报告上下文
    user_input = state.get("user_input", "")
    plan: Plan | None = state.get("plan")
    vulns: list[Vuln] = state.get("vulns", []) or []
    
    # 准备漏洞摘要信息
    vuln_summary = []
    for v in vulns:
        vuln_info = {
            "id": v.id,
            "description": v.description,
            "published": v.published,
            "v2score": v.v2score,
            "v31score": v.v31score,
            "additional_info": v.additional_info,
            "impacts": [
                {"name": imp.name, "before_version": imp.before_version, "after_version": imp.after_version}
                for imp in (v.impacts or [])
            ]
        }
        vuln_summary.append(vuln_info)
    
    # 准备 plan 执行结果摘要
    plan_summary = []
    if plan and plan.steps:
        for step in plan.steps:
            plan_summary.append({
                "step_type": step.step_type,
                "title": step.title,
                "target": step.target,
                "execution_res": step.execution_res[:500] if step.execution_res else None  # 截断避免过长
            })
    
    # 构建 prompt 上下文
    context_message = f"""
## Analysis Context

### User's Original Request
{user_input}

### Executed Plan Summary
```json
{plan_summary}
```

### Discovered Vulnerabilities
```json
{vuln_summary}
```

Please generate a comprehensive security report based on the above findings.
"""
    
    prompt = apply_prompt_template("reporter", state)
    prompt.append(SystemMessage(content=context_message))
    
    response = (
        get_model_by_type("normal")
        .invoke(input=prompt)
    )
    
    final_report = ""
    if response.content and isinstance(response.content, str):
        final_report = response.content
    
    logger.info(f"ReporterNode: Generated report with {len(final_report)} characters")
    
    return Command(
        update={
            "final_report": final_report,
            "messages": [AIMessage(content=final_report, name="ReporterNode")],
        },
    )