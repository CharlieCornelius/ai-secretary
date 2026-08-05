"""LLM 工厂测试"""

import pytest


def test_get_llm_returns_instance():
    """get_llm() 返回 ChatOpenAI 实例"""
    from app.common.llm import get_llm

    llm = get_llm()
    assert llm is not None
    assert hasattr(llm, "model")
    assert hasattr(llm, "temperature")


def test_get_sub_task_llm_returns_instance():
    """get_sub_task_llm() 返回 ChatOpenAI 实例"""
    from app.common.llm import get_sub_task_llm

    llm = get_sub_task_llm()
    assert llm is not None
    assert hasattr(llm, "model")


def test_llm_and_sub_task_different_max_tokens():
    """主 LLM 和子任务 LLM 使用不同配置"""
    from app.common.llm import get_llm, get_sub_task_llm
    from app.common.config import get_config

    cfg = get_config()
    main_llm = get_llm()
    sub_llm = get_sub_task_llm()

    assert main_llm.max_tokens == cfg.llm.max_tokens
    assert sub_llm.max_tokens == cfg.llm.sub_task_max_tokens


def test_llm_and_sub_task_same_model():
    """主 LLM 和子任务 LLM 使用相同模型"""
    from app.common.llm import get_llm, get_sub_task_llm

    main_llm = get_llm()
    sub_llm = get_sub_task_llm()

    assert main_llm.model == sub_llm.model