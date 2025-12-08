from __future__ import annotations

import asyncio
import sys
import uuid
import os
from datetime import datetime
from aiohttp import web
from logger import logger

from workflow import run_agent_workflow_async, get_run_state, get_run_state_async, update_plan_feedback_state
from settings import settings

RUN_IDS_LOG = os.path.join(os.path.dirname(__file__), "run_ids.log")


async def resume_with_feedback(run_id: str, approved: bool, comment: str | None = None) -> str:
    """Apply user feedback to a pending plan and resume the workflow."""
    state = await update_plan_feedback_state(run_id, approved=approved, comment=comment)
    if state is None:
        raise ValueError(f"No cached state found for run_id {run_id}")

    await run_agent_workflow_async(
        user_input=state.get("user_input", ""),
        run_id=run_id,
        debug=settings.debug,
        max_plan_iterations=settings.max_plan_iterations,
        max_step_num=settings.max_step_num,
        enable_background_investigation=settings.enable_background_investigation,
        enable_clarification=settings.enable_clarification,
        max_clarification_rounds=settings.max_clarification_rounds,
        initial_state=state,
    )
    return run_id


async def start_agent_workflow(user_input: str, run_id: str | None = None) -> str:
    """启动异步工作流程，返回使用的 run_id。"""
    run_id = run_id or uuid.uuid4().hex
    logger.info("Starting agent workflow run_id={} input: {}", run_id, user_input)
    await run_agent_workflow_async(
        user_input=user_input,
        run_id=run_id,
        debug=settings.debug,
        max_plan_iterations=settings.max_plan_iterations,
        max_step_num=settings.max_step_num,
        enable_background_investigation=settings.enable_background_investigation,
        enable_clarification=settings.enable_clarification,
        max_clarification_rounds=settings.max_clarification_rounds,
    )
    _record_run_id(run_id, user_input)
    return run_id

async def create_stdin_reader() -> asyncio.StreamReader:
    """创建一个异步的 stdin reader，可被取消。"""
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)
    return reader


async def stdin_listener(shutdown_event: asyncio.Event) -> None:
    """持续监听 stdin 输入，处理用户命令。
    
    只有 'stop'/'exit'/'quit' 会触发关闭，其他输入正常处理。
    """
    reader = await create_stdin_reader()
    logger.info("Stdin listener started. Commands: 'stop'/'exit'/'quit' to shutdown")

    while not shutdown_event.is_set():
        try:
            line = await reader.readline()
        except asyncio.CancelledError:
            logger.info("Stdin listener cancelled")
            return

        if not line:  # EOF
            logger.info("EOF on stdin, stopping...")
            shutdown_event.set()
            return

        text = line.decode().strip()
        if not text:
            # 空行不做任何事，继续监听
            continue

        if text.lower() in ('stop', 'exit', 'quit'):
            logger.info("Received stop command via stdin: {}", text)
            shutdown_event.set()
            return

        # 处理其他用户输入（这里可以扩展业务逻辑）
        logger.info("Received stdin input: {}", text)
        try:
            await handle_stdin_command(text)
        except Exception as e:
            logger.exception("Error handling stdin command: {}", e)


def _parse_run_command(text: str) -> tuple[str | None, str]:
    """Parse stdin text for an optional run_id prefix.

    Supported patterns:
    - "run <run_id> <query>"
    - otherwise: treat entire text as query with auto-generated run_id
    """
    parts = text.split(maxsplit=2)
    if len(parts) >= 3 and parts[0].lower() == "run":
        return parts[1], parts[2]
    return None, text


def _record_run_id(run_id: str, user_input: str) -> None:
    """Append run_id to a local log for later listing."""
    try:
        os.makedirs(os.path.dirname(RUN_IDS_LOG), exist_ok=True)
        ts = datetime.utcnow().isoformat()
        with open(RUN_IDS_LOG, "a", encoding="utf-8") as f:
            f.write(f"{ts}\t{run_id}\t{user_input}\n")
    except Exception as e:
        logger.error("Failed to record run_id {}: {}", run_id, e)


def list_run_ids(limit: int = 50) -> list[dict[str, str]]:
    """Return the latest run_ids with timestamps and queries (most recent last)."""
    if not os.path.exists(RUN_IDS_LOG):
        return []
    try:
        with open(RUN_IDS_LOG, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        logger.error("Failed to read run_id log: {}", e)
        return []

    lines = lines[-limit:]
    entries = []
    for line in lines:
        parts = line.rstrip("\n").split("\t", 2)
        if len(parts) == 3:
            ts, rid, query = parts
            entries.append({"timestamp": ts, "run_id": rid, "query": query})
    return entries


async def handle_stdin_command(text: str) -> None:
    """处理用户通过 stdin 输入的命令，支持 run_id。"""
    lower = text.lower()
    if lower == 'status':
        logger.info("Status: Server is running")
        return
    if lower == 'help':
        logger.info("Available commands: status, help, stop/exit/quit, run <run_id> <query>, plan <run_id>, approve <run_id> [comment], reject <run_id> <comment>")
        return
    if lower in ('list', 'list runs', 'list run_id', 'list run_ids'):
        runs = list_run_ids()
        if not runs:
            logger.info("No runs recorded yet")
            return
        logger.info("Last {} runs (oldest->newest):", len(runs))
        for r in runs:
            logger.info("{} | {} | {}", r["timestamp"], r["run_id"], r["query"])
        return

    if lower.startswith('plan '):
        parts = text.split(maxsplit=1)
        run_id = parts[1] if len(parts) > 1 else None
        if not run_id:
            logger.info("Usage: plan <run_id>")
            return
        state = await get_run_state_async(run_id)
        if not state:
            logger.info("No state found for run_id={}", run_id)
            return
        plan = state.get("plan")
        status = state.get("plan_review_status")
        logger.info("Plan status for {}: {}", run_id, status)
        logger.info("Plan content: {}", plan)
        return

    if lower.startswith('approve '):
        parts = text.split(maxsplit=2)
        if len(parts) < 2:
            logger.info("Usage: approve <run_id> [comment]")
            return
        run_id = parts[1]
        comment = parts[2] if len(parts) == 3 else None
        try:
            await resume_with_feedback(run_id, approved=True, comment=comment)
            logger.info("Run {} approved and resumed", run_id)
        except Exception as e:
            logger.error("Failed to approve {}: {}", run_id, e)
        return

    if lower.startswith('reject '):
        parts = text.split(maxsplit=2)
        if len(parts) < 3:
            logger.info("Usage: reject <run_id> <comment>")
            return
        run_id = parts[1]
        comment = parts[2]
        try:
            await resume_with_feedback(run_id, approved=False, comment=comment)
            logger.info("Run {} rejected and sent back to planner", run_id)
        except Exception as e:
            logger.error("Failed to reject {}: {}", run_id, e)
        return

    run_id, query = _parse_run_command(text)
    used_run_id = await start_agent_workflow(query, run_id=run_id)
    logger.info("Workflow started with run_id={}", used_run_id)

async def run_server(
    shutdown_event: asyncio.Event,
    host: str = '127.0.0.1', 
    port: int = 8080
) -> None:
    """启动 HTTP 服务器，持续运行直到 shutdown_event 被设置。"""

    async def index_handler(request: web.Request) -> web.Response:
        return web.json_response({'status': 'running'})

    async def stop_handler(request: web.Request) -> web.Response:
        logger.info("Received HTTP stop request, shutting down...")
        shutdown_event.set()
        return web.json_response({'status': 'stopping'})
    
    async def echo_handler(request: web.Request) -> web.Response:
        """示例：处理 POST 请求"""
        data = await request.json()
        logger.info("Received data: {}", data)
        return web.json_response({'received': data})

    async def runs_handler(request: web.Request) -> web.Response:
        runs = list_run_ids()
        return web.json_response({'runs': runs})

    async def plan_handler(request: web.Request) -> web.Response:
        run_id = request.match_info.get('run_id')
        if run_id is None:
            return web.json_response({'error': 'run_id is required'}, status=400)
        state = await get_run_state_async(run_id)
        if not state:
            return web.json_response({'error': 'run_id not found'}, status=404)
        plan = state.get('plan')
        if plan is not None and hasattr(plan, "model_dump"):
            plan = plan.model_dump()
        status = state.get('plan_review_status')
        return web.json_response({'run_id': run_id, 'plan_review_status': status, 'plan': plan})

    async def plan_feedback_handler(request: web.Request) -> web.Response:
        run_id = request.match_info.get('run_id')
        if run_id is None:
            return web.json_response({'error': 'run_id is required'}, status=400)
        data = await request.json()
        approved = bool(data.get('approved', False))
        comment = data.get('comment')
        try:
            await resume_with_feedback(run_id, approved=approved, comment=comment)
        except Exception as e:
            logger.error("Feedback failed for {}: {}", run_id, e)
            return web.json_response({'error': str(e)}, status=400)
        return web.json_response({'run_id': run_id, 'approved': approved})
    
    # Main api endpoint for scanner.
    async def query_handler(request: web.Request) -> web.Response:
        data = await request.json()
        run_id = data.get('run_id')
        used_run_id = await start_agent_workflow(data.get('query', ''), run_id=run_id)
        return web.json_response({'received': data, 'run_id': used_run_id})
        

    app = web.Application()
    app.router.add_get('/', index_handler)
    app.router.add_route('*', '/stop', stop_handler)
    app.router.add_post('/echo', echo_handler)
    app.router.add_post('/query', query_handler)
    app.router.add_get('/runs', runs_handler)
    app.router.add_get('/runs/{run_id}/plan', plan_handler)
    app.router.add_post('/runs/{run_id}/plan/feedback', plan_feedback_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    
    try:
        await site.start()
        logger.info("Server started at http://{}:{}", host, port)
        logger.info("Endpoints: GET /, POST /echo, */stop")
        
        # 持续等待直到收到关闭信号
        await shutdown_event.wait()
        
    finally:
        logger.info("Cleaning up HTTP server...")
        await runner.cleanup()


async def main_async(host: str = '127.0.0.1', port: int = 8080) -> None:
    """主异步入口：同时运行 HTTP 服务器和 stdin 监听器。
    
    两者共享同一个 shutdown_event，任一来源触发关闭都会停止整个程序。
    """
    shutdown_event = asyncio.Event()
    
    # 创建任务
    server_task = asyncio.create_task(
        run_server(shutdown_event, host, port),
        name="http_server"
    )
    stdin_task = asyncio.create_task(
        stdin_listener(shutdown_event),
        name="stdin_listener"
    )
    
    try:
        # 等待关闭信号
        await shutdown_event.wait()
        logger.info("Shutdown signal received, stopping all tasks...")
        
    except asyncio.CancelledError:
        logger.info("Main task cancelled")
        shutdown_event.set()
    
    finally:
        # 取消所有任务并等待它们完成
        for task in [server_task, stdin_task]:
            if not task.done():
                task.cancel()
        
        # 等待任务完成（包括清理）
        await asyncio.gather(server_task, stdin_task, return_exceptions=True)
        logger.info("All tasks stopped. Goodbye!")


def main() -> None:
    """同步入口点"""
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info("Run interrupted by user (Ctrl+C)")


if __name__ == '__main__':
    main()