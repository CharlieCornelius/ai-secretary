"""Chroma 缓存刷新测试"""

import pytest


@pytest.mark.asyncio
async def test_chroma_reset_and_recreate():
    """重置缓存后重新创建 collection"""
    from app.memory.experience import (
        _get_collection,
        _reset_chroma,
        store_experience,
        search_experiences,
        clear_all_experiences,
    )

    # 清空并添加测试数据
    await clear_all_experiences()
    await store_experience("测试经验", category="test")

    # 验证正常
    results = await search_experiences("测试", n_results=3)
    assert len(results) >= 1

    # 重置全局缓存（模拟目录被删除后的状态）
    _reset_chroma()

    # 再次获取 collection，应自动重建（连接到已有持久化数据）
    collection = _get_collection()
    assert collection is not None
    # 注意：PersistentClient 的数据在磁盘上，重置内存缓存不会删除已有数据
    # 这里验证的是 _get_collection() 能正常返回有效 collection

    # 验证可以继续添加
    await store_experience("新经验", category="test")
    results = await search_experiences("新经验", n_results=3)
    assert len(results) >= 1


def test_reset_chroma_sets_globals_to_none():
    """_reset_chroma() 将全局变量设为 None"""
    import app.memory.experience as exp_module

    # 先确保 collection 已初始化
    _ = exp_module._get_collection()
    assert exp_module._client is not None
    assert exp_module._collection is not None

    # 重置后应为 None
    exp_module._reset_chroma()
    assert exp_module._client is None
    assert exp_module._collection is None
