# 使用 asyncio 实现多路输入监听（中文说明）

说明：本文档以 `src/main.py` 中的示例代码为基础，讲解如何用 `asyncio` + `aiohttp` 实现：同时监听 HTTP 请求和标准输入（stdin），并在其中任意一方触发时优雅关闭程序。

---

## 概要

目标：在一个异步进程中同时监听"HTTP 请求（aiohttp）"与"用户标准输入（stdin）"，当任意一端需要退出时（例如按下 Enter、输入 `stop`，或收到 `/stop` 请求），触发统一的退出信号并优雅清理资源。

实现要点：
- 使用 `aiohttp` 启动一个异步 HTTP 服务。
- 使用 `asyncio.wait` 配合 `FIRST_COMPLETED` 实现任务竞争：第一个完成的任务触发关闭，自动取消其余任务。
- 使用 `asyncio.StreamReader` 异步读取 stdin（可被取消），替代传统的 `asyncio.to_thread(input)` 方案。
- 使用 `asyncio.Future` 在 HTTP handler 中传递关闭信号。

---

## 关键概念与实现说明

### 1. 任务竞争模式（Race Pattern）

核心思想是让多个协程"竞赛"，谁先完成就用谁的结果，并取消其他未完成的任务：

```python
async def first_completed(*coros):
    """运行多个协程，返回第一个完成的结果，取消其余。"""
    tasks = [asyncio.create_task(coro) for coro in coros]
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    
    # 取消未完成的任务
    for task in pending:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    
    return done.pop().result()
```

### 2. 异步 stdin 读取（可取消）

传统方式使用 `asyncio.to_thread(input, '')` 将阻塞调用放到线程池，但问题是线程中的 `input()` 无法被取消，导致程序退出时可能卡住。

改进方案使用 `asyncio.StreamReader` 直接异步读取 stdin：

```python
async def create_stdin_reader() -> asyncio.StreamReader:
    """创建一个异步的 stdin reader，可被取消。"""
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)
    return reader

async def stdin_listener() -> str:
    reader = await create_stdin_reader()
    while True:
        line = await reader.readline()  # 可被 cancel！
        if not line:  # EOF
            return "stdin_eof"
        text = line.decode().strip()
        if not text or text.lower() in ('stop', 'exit', 'quit'):
            return "stdin_command"
```

优点：
- `await reader.readline()` 是真正的异步操作，可被 `task.cancel()` 取消
- 无需线程池，资源开销更小
- 退出更加优雅，不会卡住

### 3. HTTP 服务器与 Future 通信

使用 `asyncio.Future` 作为 handler 与主任务之间的通信桥梁：

```python
async def run_server(host: str = '127.0.0.1', port: int = 8080) -> str:
    shutdown_future: asyncio.Future[str] = asyncio.get_running_loop().create_future()

    async def stop_handler(request: web.Request) -> web.Response:
        if not shutdown_future.done():
            shutdown_future.set_result("http_stop")
        return web.json_response({'status': 'stopping'})

    # ... 设置路由和启动服务器 ...

    try:
        result = await shutdown_future  # 等待 /stop 请求
        return result
    except asyncio.CancelledError:
        raise
    finally:
        await runner.cleanup()  # 确保清理
```

### 4. 主函数：组合一切

```python
async def main_async(host: str = '127.0.0.1', port: int = 8080) -> None:
    try:
        reason = await first_completed(
            run_server(host, port),
            stdin_listener()
        )
        logger.info("Shutdown triggered by: %s", reason)
    except KeyboardInterrupt:
        logger.info("Interrupted by user (Ctrl+C)")
```

---

## 新旧方案对比

| 特性 | 旧方案 | 新方案 |
|------|--------|--------|
| stdin 读取 | `asyncio.to_thread(input)` | `asyncio.StreamReader` |
| 可取消性 | ❌ 线程中的 input() 无法取消 | ✅ 原生异步，可被 cancel |
| 协调机制 | `asyncio.Event` 手动管理 | 任务竞争 + Future |
| 清理方式 | `gather` 后处理 | `try/finally` 确保清理 |
| 代码风格 | 命令式 | 更 Pythonic |

---

## 运行说明（使用 `uv`）

我们建议使用 `uv` 来管理项目运行，而不强制创建额外 venv：

```bash
# 添加运行时依赖到项目（只需在第一次设置时执行）
uv add aiohttp

# 启动服务（uv 管理环境／依赖）
uv run python -m src.main
```

你也可以在另一个终端触发 `stop`：
```bash
curl -X POST http://127.0.0.1:8080/stop
``` 

或者在 `uv run` 的终端中直接按 Enter 或输入 `stop`。

---

## 测试（建议步骤）

1. 在项目根目录运行 `uv run python -m src.main`。
2. 打开新终端并使用 `curl` 检查状态：
   - `curl http://127.0.0.1:8080/` → 返回 `{'status': 'running'}`。
3. 触发关机：
   - `curl -X POST http://127.0.0.1:8080/stop` → 服务器收到请求并进行优雅关闭
   - 或者在运行脚本的控制台中按 Enter（空行）或输入 `stop`。
4. 验证优雅关闭：日志应显示 `Shutdown triggered by: http_stop` 或 `stdin_command` 等。

---

## 注意事项与扩展建议

- **平台兼容性**：`loop.connect_read_pipe()` 在 Linux/macOS 上工作良好，但在 Windows 上可能需要额外处理。如需跨平台支持，考虑使用 `anyio` 库。
- **Python 版本**：本代码需要 Python 3.9+（使用了类型注解语法）。若使用 Python 3.11+，可改用 `asyncio.TaskGroup` 进一步简化。
- **扩展场景**：
  - 需要监听更多输入源？添加更多协程到 `first_completed()` 调用中
  - 需要 WebSocket？在 `run_server` 中扩展 aiohttp 路由
  - 需要超时自动关闭？添加 `asyncio.sleep(timeout)` 作为竞争任务之一

---

如果你希望我把该文档合并到 README 中的运行指南，或补充进一步关于测试与 CI 的内容，请告诉我你希望的样式。
