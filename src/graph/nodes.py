from graph.state import NodeState, preserve_state_meta_fields
from schemas.plans import parse_plan_from_llm, Plan, Step
from schemas.vulns import Vuln, ImpactedSoftware, parse_vulns_from_llm
from typing import Annotated, Any
from prompts.template import apply_prompt_template
from models import get_model_by_type
from logger import logger
from tools.search import search_topic_by_ddgs
from tools.vuln_analyzer import get_cve_details

from langgraph.prebuilt import ToolNode
from langchain_core.tools import tool
from langgraph.types import Command, interrupt, Send
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage, RemoveMessage
from langchain_core.language_models.chat_models import BaseChatModel

from settings import settings
from graph.subgraphs.asset_analysis import asset_analysis_subgraph, AssetSubState
from graph.subgraphs.vuln_detail import vuln_detail_subgraph, VulnDetailSubState
from graph.subgraphs.vuln_discovery import vuln_discovery_subgraph, VulnDiscoverySubState

# Configuration for parallel execution
STEP_CONFIG = {
    "asset_analysis": {"parallel": True},
    "vuln_detail":    {"parallel": True},
    "vuln_discovery": {"parallel": False}, # Keep discovery serial for stability
    "reporting":      {"parallel": False},
}

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

def PlanRefineNode(state: NodeState):
    """
    Refines the plan based on discovery results.
    Converts discovered CVE IDs into specific vuln_detail steps.
    """
    plan: Plan | None = state.get("plan")
    step_results = state.get("step_results", {})
    
    if not plan or not plan.steps:
        return Command(goto="WorkerTeamNode")
        
    new_steps = []
    # Find discovery steps that have results
    for step in plan.steps:
        if step.step_type == "vuln_discovery" and step.id in step_results:
            result = step_results[step.id]
            if isinstance(result, dict) and result.get("type") == "vuln_discovery":
                cve_ids = result.get("cve_ids", [])
                
                # Generate detail steps for each CVE
                for i, cve_id in enumerate(cve_ids):
                    # Check if we already have a step for this CVE to avoid duplicates
                    # Simple check: look for target match
                    if any(s.target == cve_id for s in plan.steps + new_steps):
                        continue
                        
                    new_step = Step(
                        id=f"detail-{step.id}-{i}",
                        step_type="vuln_detail",
                        title=f"Analyze {cve_id}",
                        description=f"Fetch detailed information and impact analysis for {cve_id}",
                        target=cve_id,
                        stage=step.stage + 1, # Run in next stage
                        depends_on=[step.id]
                    )
                    new_steps.append(new_step)
                    
    if new_steps:
        plan.steps.extend(new_steps)
        logger.info(f"PlanRefineNode: Added {len(new_steps)} new steps based on discovery.")
        return Command(
            update={"plan": plan},
            goto="WorkerTeamNode"
        )
    
    return Command(goto="WorkerTeamNode")

def TriageNode(state: NodeState):
    """
    Aggregates results from all steps and prepares final vulnerability list.
    """
    plan: Plan | None = state.get("plan")
    step_results = state.get("step_results", {})
    vulns: list[Vuln] = state.get("vulns", []) or []
    
    # Process results from vuln_detail steps
    for step_id, result in step_results.items():
        # Check if this result contains vulns
        if isinstance(result, dict) and "vulns" in result:
            found_vulns = result["vulns"]
            if isinstance(found_vulns, list):
                # Merge vulns, avoiding duplicates by ID
                existing_ids = {v.id for v in vulns}
                for v in found_vulns:
                    if isinstance(v, Vuln) and v.id not in existing_ids:
                        vulns.append(v)
                        existing_ids.add(v.id)
                    elif isinstance(v, dict) and v.get("id") not in existing_ids:
                        # Handle dict if not parsed to object yet
                        try:
                            vuln_obj = Vuln(**v)
                            vulns.append(vuln_obj)
                            existing_ids.add(vuln_obj.id)
                        except Exception as e:
                            logger.error(f"Error parsing vuln in TriageNode: {e}")

    return Command(
        update={"vulns": vulns},
        goto="ReporterNode"
    )

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
    plan_review_status = state.get("plan_review_status")
    if isinstance(plan, Plan):
        if plan.has_enough_context:
            goto = "ReporterNode"
            plan_review_status = None
        elif plan.finish_plan:
            # 计划完成但缺少上下文，先让用户确认
            goto = "UserFeedbackNode"
            plan_review_status = "pending"
        else:
            goto = "PlannerNode"
    
    return Command(
        update={
            "plan_iterations": plan_iterations,
            "plan": plan,
            "plan_review_status": plan_review_status,
            "plan_review_comment": None if plan_review_status == "pending" else state.get("plan_review_comment"),
        },
        goto=goto,
    )

def UserFeedbackNode(state: NodeState):
    """A node that handles user feedback based on their states."""
    plan: Plan | None = state.get("plan")

    if plan is None:
        logger.warning("UserFeedbackNode called without plan; sending back to planner")
        return Command(update={}, goto="PlannerNode")

    # Interrupt execution and wait for user feedback
    # The value returned by interrupt() will be the value passed to Command(resume=...)
    # When first called, this will suspend execution.
    # When resumed, feedback will contain the user's decision.
    feedback = interrupt({
        "type": "plan_approval",
        "plan": plan.model_dump() if hasattr(plan, "model_dump") else plan,
        "run_id": state.get("run_id")
    })
    
    # feedback is expected to be a dict: {"approved": bool, "comment": str}
    approved = feedback.get("approved", False)
    comment = feedback.get("comment")

    if approved:
        logger.info("Run {} plan approved by user", state.get("run_id"))
        return Command(
            update={
                "plan_review_status": "approved",
                "plan_review_comment": comment,
                "status": "plan_approved",
            },
            goto="WorkerTeamNode",
        )
    else:
        messages = state.get("messages", [])
        if comment:
            messages.append(SystemMessage(content=f"User feedback: {comment}", name="UserFeedback"))
        logger.info("Run {} plan rejected by user, re-planning", state.get("run_id"))
        return Command(
            update={
                "plan_review_status": "rejected",
                "status": "plan_rejected",
                "messages": messages,
            },
            goto="PlannerNode",
        )

def _deps_done(step: Step, plan: Plan, step_results: dict) -> bool:
    """Check if all dependencies of a step are met."""
    if not step.depends_on:
        return True
    
    # Check if all dependent steps have results in step_results
    # Note: We check step_results, not step.execution_res, because parallel nodes update step_results
    for dep_id in step.depends_on:
        if dep_id not in step_results:
            return False
    return True

def _node_for_step_type(step_type: str) -> str:
    """Map step_type to node name."""
    mapping = {
        "asset_analysis": "AssetsAnalzerNode",
        "vuln_discovery": "VulnDiscoveryNode",
        "vuln_detail": "VulnDetailNode",
        "reporting": "ReporterNode", # Usually not called by WorkerTeam, but for completeness
    }
    return mapping.get(step_type, "WorkerTeamNode")

def WorkerTeamNode(state: NodeState):
    """
    Orchestrates the execution of the plan.
    Schedules steps based on stage, dependencies, and parallel configuration.
    """
    plan: Plan | None = state.get("plan")
    step_results = state.get("step_results", {})
    
    if not plan or not plan.steps:
        logger.warning("WorkerTeamNode called without plan")
        return Command(goto="PlannerNode")

    # 0. Check if we need to refine the plan (Discovery -> Detail)
    # If we have discovery results that haven't generated detail steps yet
    # Logic: Find discovery steps with results, check if any step depends on them
    # If no step depends on a finished discovery step, it likely needs refinement
    # BUT PlanRefineNode handles the "already generated" check.
    # So we just check if there are ANY finished discovery steps.
    # Optimization: Only go to Refine if we haven't visited it for these results?
    # For now, let's rely on PlanRefineNode's idempotency.
    # We can check if there are discovery steps with results.
    has_discovery_results = any(
        s.step_type == "vuln_discovery" and s.id in step_results 
        for s in plan.steps
    )
    
    # Simple heuristic: If we just finished a discovery step, we should probably refine.
    # But how do we know we "just" finished?
    # Let's just always check PlanRefineNode if there are discovery results.
    # PlanRefineNode will return immediately if nothing to do.
    # To avoid infinite loop, PlanRefineNode must NOT return goto="PlanRefineNode".
    # And WorkerTeam must have a way to know if it should skip Refine.
    # Actually, PlanRefineNode returns goto="WorkerTeamNode".
    # So if WorkerTeam sends to Refine, Refine sends back.
    # We need to avoid ping-pong if Refine did nothing.
    # Maybe we can check if we have pending discovery steps?
    # If all discovery steps are done, and we have results, we might need refine.
    
    # Let's try a different approach:
    # If there are discovery steps that are DONE (in step_results),
    # AND we haven't generated detail steps for them (checked by PlanRefineNode),
    # then go to Refine.
    # Since PlanRefineNode is cheap (just logic), we can visit it.
    # But we need to avoid loop: Worker -> Refine -> Worker -> Refine ...
    # We can use a state flag? Or just let Refine handle it?
    # If Refine adds steps, it updates plan.
    # If Refine does nothing, it returns.
    # If we blindly go to Refine, we loop.
    
    # Better: Only go to Refine if we have *newly* finished discovery steps?
    # Hard to track "newly".
    
    # Alternative: PlanRefineNode is part of the flow.
    # But we want to run it only when needed.
    
    # Let's look at the steps.
    # If we have a discovery step that is done, and NO step depends on it, 
    # it's a strong signal that we need to refine (unless it's a leaf discovery).
    # Most discovery steps in our flow are meant to spawn details.
    
    candidates_for_refine = []
    for step in plan.steps:
        if step.step_type == "vuln_discovery" and step.id in step_results:
            # Check if any step depends on this one
            is_depended_on = any(step.id in s.depends_on for s in plan.steps)
            if not is_depended_on:
                candidates_for_refine.append(step)
                
    if candidates_for_refine:
        return Command(goto="PlanRefineNode")

    # 1. Find pending steps (not in step_results)
    pending_steps = [s for s in plan.steps if s.id not in step_results]
    
    if not pending_steps:
        # All steps done
        return Command(goto="TriageNode")
        
    # 2. Filter runnable steps (dependencies met)
    runnable = [s for s in pending_steps if _deps_done(s, plan, step_results)]
    
    if not runnable:
        # Deadlock or waiting?
        # If pending but not runnable, it means dependencies are missing.
        # If dependencies are missing but not in pending, they are done?
        # _deps_done checks step_results.
        # So if not runnable, it means dependencies are NOT in step_results.
        # If dependencies are not in step_results and not in pending... wait, they must be in pending.
        # So we are waiting for dependencies.
        # But if we are in WorkerTeamNode, it means some node just finished and returned here.
        # So there should be *something* runnable, unless the plan is invalid (cycle).
        logger.error("No runnable steps found, but plan is not complete. Possible deadlock.")
        return Command(goto="TriageNode") # Fail safe
        
    # 3. Group by stage (min stage)
    min_stage = min(s.stage for s in runnable)
    runnable_at_stage = [s for s in runnable if s.stage == min_stage]
    
    # 4. Apply parallel strategy
    jobs = []
    serial_step = None
    
    for step in runnable_at_stage:
        config = STEP_CONFIG.get(step.step_type, {"parallel": False})
        
        if config["parallel"]:
            node_name = _node_for_step_type(step.step_type)
            jobs.append(Send(node_name, {"step_id": step.id}))
        else:
            # Serial step
            if serial_step is None:
                serial_step = step
                
    # 5. Dispatch
    if jobs:
        logger.info(f"WorkerTeamNode: Dispatching {len(jobs)} parallel jobs")
        return jobs
        
    if serial_step:
        node_name = _node_for_step_type(serial_step.step_type)
        logger.info(f"WorkerTeamNode: Dispatching serial job: {serial_step.id} ({node_name})")
        return [Send(node_name, {"step_id": serial_step.id})]
        
    return Command(goto="TriageNode")



def AssetsAnalzerNode(state: NodeState):
    """
    Wrapper node for Asset Analysis SubGraph.
    Invokes the subgraph for a specific step and updates step_results.
    """
    step_id = state.get("step_id")
    plan = state.get("plan")
    
    if not step_id or not plan:
        logger.error("AssetsAnalzerNode called without step_id or plan")
        return Command(goto="WorkerTeamNode")
        
    # Find the step
    step = next((s for s in plan.steps if s.id == step_id), None)
    if not step:
        logger.error(f"Step {step_id} not found in plan")
        return Command(goto="WorkerTeamNode")
        
    # Invoke subgraph
    sub_state: AssetSubState = {
        "messages": [], # Isolated messages
        "step": step,
        "result": None
    }
    
    result = asset_analysis_subgraph.invoke(sub_state)
    execution_result = result.get("result")
    
    return Command(
        update={
            "step_results": {step_id: execution_result}
        },
        goto="WorkerTeamNode"
    )

def VulnDiscoveryNode(state: NodeState):
    """
    Wrapper node for Vuln Discovery SubGraph.
    """
    step_id = state.get("step_id")
    plan = state.get("plan")
    
    if not step_id or not plan:
        logger.error("VulnDiscoveryNode called without step_id or plan")
        return Command(goto="WorkerTeamNode")
        
    step = next((s for s in plan.steps if s.id == step_id), None)
    if not step:
        logger.error(f"Step {step_id} not found in plan")
        return Command(goto="WorkerTeamNode")
        
    sub_state: VulnDiscoverySubState = {
        "messages": [],
        "step": step,
        "result": None
    }
    
    result = vuln_discovery_subgraph.invoke(sub_state)
    discovery_result = result.get("result")
    
    return Command(
        update={
            "step_results": {step_id: discovery_result}
        },
        goto="WorkerTeamNode"
    )

def VulnDetailNode(state: NodeState):
    """
    Wrapper node for Vuln Detail SubGraph.
    """
    step_id = state.get("step_id")
    plan = state.get("plan")
    
    if not step_id or not plan:
        logger.error("VulnDetailNode called without step_id or plan")
        return Command(goto="WorkerTeamNode")
        
    step = next((s for s in plan.steps if s.id == step_id), None)
    if not step:
        logger.error(f"Step {step_id} not found in plan")
        return Command(goto="WorkerTeamNode")
        
    sub_state: VulnDetailSubState = {
        "messages": [],
        "step": step,
        "result": None
    }
    
    result = vuln_detail_subgraph.invoke(sub_state)
    detail_result = result.get("result")
    
    return Command(
        update={
            "step_results": {step_id: detail_result}
        },
        goto="WorkerTeamNode"
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