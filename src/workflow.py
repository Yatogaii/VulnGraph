import asyncio
from graph.state import NodeState
from graph.builder import graph

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
    if initial_state is None:
        initial_state = NodeState(
            user_input=user_input,
            messages=[],
            label="Start",
            status="initialized",
            goto=None,
            vulns=[],
            final_report="",
        )

    last_message_cnt = 0
    final_state = None
    async for s in graph.astream(
        input=initial_state
    ):
        try:
            final_state = s
            if isinstance(s, dict) and "messages" in s:
                if len(s["messages"]) <= last_message_cnt:
                    continue
                last_message_cnt = len(s["messages"])
                message = s["messages"][-1]
                if isinstance(message, tuple):
                    print(message)
                else:
                    message.pretty_print()
            else:
                print(f"Output: {s}")
        except Exception as e:
            print(f"Error processing output: {str(e)}")

