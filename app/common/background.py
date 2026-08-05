"""后台任务运行器 - 封装 fire-and-forget 任务的集合与生命周期，异常隔离

设计要点：
- 任务隔离：每个后台任务独立执行，异常被完整捕获，不外溢影响其他任务或主流程
- 错误分级：业务层自治（自行 try/except 消化小错误）；只有业务层未接住的意外异常
  才上浮到此处，记 error + 完整 traceback（大错误弹出）
- 优雅关闭：shutdown 等待在途任务完成（带超时），超时则取消，避免 close_db 后报错
"""

from __future__ import annotations

import asyncio
from typing import Coroutine

from app.common.config import get_config
from app.common.logging import get_logger

logger = get_logger("background")


class BackgroundRunner:
    """后台任务运行器 - 管理任务集合与生命周期"""

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task] = set()

    def submit(self, coro: Coroutine, name: str = "") -> asyncio.Task:
        """提交后台任务（fire-and-forget）

        Args:
            coro: 协程
            name: 任务名（用于日志标识）

        Returns:
            创建的 Task（一般无需持有，由 runner 内部管理引用防 GC）
        """
        task = asyncio.create_task(self._run(coro, name), name=name or None)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def _run(self, coro: Coroutine, name: str) -> None:
        """执行单个任务，捕获并记录未处理异常"""
        try:
            await coro
        except Exception:
            # 业务层已有的小错误（网络/超时等）在业务函数内自治消化（warning）；
            # 能漏到这里的是业务层未料到的意外异常 → 记 error + 完整 traceback
            logger.error("后台任务未处理异常", name=name, exc_info=True)

    async def shutdown(self, timeout: float) -> None:
        """关闭：等待在途任务完成，超时则取消

        Args:
            timeout: 等待超时秒数（来自配置 background.shutdown_timeout）
        """
        if not self._tasks:
            return

        logger.info("等待后台任务完成", count=len(self._tasks), timeout=timeout)
        try:
            await asyncio.wait_for(
                asyncio.gather(*self._tasks, return_exceptions=True),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("后台任务关闭超时，取消剩余任务", pending=len(self._tasks))
            for task in self._tasks:
                task.cancel()
        finally:
            self._tasks.clear()


# 全局单例
_runner: BackgroundRunner | None = None


def get_background_runner() -> BackgroundRunner:
    """获取全局 BackgroundRunner 单例"""
    global _runner
    if _runner is None:
        _runner = BackgroundRunner()
    return _runner


async def shutdown_background() -> None:
    """关闭后台任务运行器（从配置读取超时）"""
    global _runner
    if _runner is None:
        return
    timeout = get_config().background.shutdown_timeout
    await _runner.shutdown(timeout)
    _runner = None