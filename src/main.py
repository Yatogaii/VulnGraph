from __future__ import annotations

import asyncio
import sys
from aiohttp import web
from loguru import logger

from src.workflow import run_agent_workflow_async
from src.settings import settings

def start_agent_workflow(user_input: str) -> None:
    """启动异步工作流程。"""
    asyncio.run(run_agent_workflow_async(
        user_input=user_input,
        debug=settings.debug,
        max_plan_iterations=settings.max_plan_iterations,
        max_step_num=settings.max_step_num,
        enable_background_investigation=settings.enable_background_investigation,
        enable_clarification=settings.enable_clarification,
        max_clarification_rounds=settings.max_clarification_rounds,
    ))

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
        await handle_stdin_command(text)


async def handle_stdin_command(text: str) -> None:
    """处理用户通过 stdin 输入的命令。
    
    扩展点：在这里添加你的业务逻辑。
    """
    # 示例：简单的命令处理
    if text.lower() == 'status':
        logger.info("Status: Server is running")
    elif text.lower() == 'help':
        logger.info("Available commands: status, help, stop/exit/quit")
    else:
        start_agent_workflow(text)

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
    
    # Main api endpoint for scanner.
    async def query_handler(request: web.Request) -> web.Response:
        data = await request.json()
        start_agent_workflow(data.get('query', ''))
        return web.json_response({'received': data})
        

    app = web.Application()
    app.router.add_get('/', index_handler)
    app.router.add_route('*', '/stop', stop_handler)
    app.router.add_post('/echo', echo_handler)
    app.router.add_post('/query', query_handler)

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