"""后台任务运行器测试"""

import asyncio

import pytest

import app.common.background as background_module
from app.common.background import BackgroundRunner, get_background_runner, shutdown_background


@pytest.mark.asyncio
async def test_submit_runs_task():
    """submit 提交正常协程，任务被执行"""
    runner = BackgroundRunner()
    done = asyncio.Event()

    async def _task():
        done.set()

    runner.submit(_task(), name="normal")

    # 等待任务执行（带超时避免卡死）
    await asyncio.wait_for(done.wait(), timeout=1.0)
    assert done.is_set()


@pytest.mark.asyncio
async def test_submit_exception_isolated():
    """submit 抛异常的协程，异常被捕获不外溢"""
    runner = BackgroundRunner()

    async def _bad_task():
        raise RuntimeError("boom")

    # 不应抛出异常
    runner.submit(_bad_task(), name="bad")

    # 等待任务完成（让 _run 的 except 有机会执行）
    await asyncio.sleep(0.1)
    # 任务已完成并从集合移除
    assert len(runner._tasks) == 0


@pytest.mark.asyncio
async def test_tasks_isolated_from_each_other():
    """A 任务异常不影响 B 任务执行"""
    runner = BackgroundRunner()
    b_done = asyncio.Event()

    async def _task_a():
        raise ValueError("A failed")

    async def _task_b():
        b_done.set()

    runner.submit(_task_a(), name="A")
    runner.submit(_task_b(), name="B")

    await asyncio.wait_for(b_done.wait(), timeout=1.0)
    assert b_done.is_set()


def test_get_runner_singleton():
    """get_background_runner 两次返回同一实例"""
    # 重置单例
    background_module._runner = None
    try:
        r1 = get_background_runner()
        r2 = get_background_runner()
        assert r1 is r2
    finally:
        background_module._runner = None


@pytest.mark.asyncio
async def test_shutdown_waits_tasks():
    """shutdown 等待在途任务完成"""
    runner = BackgroundRunner()
    done = asyncio.Event()

    async def _task():
        await asyncio.sleep(0.05)
        done.set()

    runner.submit(_task(), name="slow")

    # shutdown 应等待任务完成
    await runner.shutdown(timeout=2.0)
    assert done.is_set()
    assert len(runner._tasks) == 0


@pytest.mark.asyncio
async def test_shutdown_background_resets_runner():
    """shutdown_background 后 _runner 置 None，下次 get 为新实例"""
    background_module._runner = None
    r1 = get_background_runner()
    await shutdown_background()
    assert background_module._runner is None
    r2 = get_background_runner()
    assert r1 is not r2
    background_module._runner = None