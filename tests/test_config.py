"""配置加载测试"""

import os

import pytest


def test_app_config_loaded(monkeypatch):
    """app.yaml 配置正确加载（通过环境变量）"""
    from app.common.config import init_config

    # 重置全局配置
    import app.common.config as config_module
    config_module._config = None

    # mock 环境变量
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-123")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://test")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")

    try:
        cfg = init_config()
        assert cfg.server.host == "0.0.0.0"
        assert cfg.server.port == 8000
        # 相对路径被解析为基于项目根目录的绝对路径
        assert "secretary.db" in cfg.database.url
        assert cfg.database.url.startswith("sqlite+aiosqlite:///")
        from pathlib import Path
        project_root = Path(__file__).parent.parent
        assert str(project_root) in cfg.database.url
        assert cfg.llm.model == "test-model"
        assert cfg.llm.api_key == "test-key-123"
        assert cfg.llm.base_url == "http://test"
        assert cfg.llm.temperature == 1
        assert cfg.llm.max_tokens == 4096
        assert cfg.llm.sub_task_max_tokens == 2048
        assert cfg.llm.sub_task_temperature == 1
        assert cfg.context.max_context_turns == 20
        assert cfg.context.max_tool_iterations == 5
        assert cfg.audit.max_logs == 1_000_000
        assert cfg.logging.level == "INFO"
        assert cfg.chroma.hnsw_space == "cosine"
    finally:
        config_module._config = None


def test_missing_llm_config(monkeypatch):
    """LLM 必填配置缺失时报错"""
    from app.common.config import init_config

    # 重置全局配置
    import app.common.config as config_module
    config_module._config = None

    # 清除可能的环境变量
    for key in ["OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL"]:
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(ValueError, match="缺少 LLM 配置"):
        init_config()

    config_module._config = None


def test_api_defaults_loaded():
    """api_defaults 配置正确加载"""
    from app.common.config import get_config

    defaults = get_config().api_defaults
    assert defaults.session_limit == 50
    assert defaults.experience_n_results == 50


def test_logging_truncation_loaded():
    """logging_truncation 配置正确加载"""
    from app.common.config import get_config

    trunc = get_config().logging_truncation
    assert trunc.pattern_log == 100
    assert trunc.error_content == 200


def test_background_config_loaded():
    """background 配置正确加载"""
    from app.common.config import get_config

    cfg = get_config().background
    assert cfg.shutdown_timeout == 5.0


def test_knowledge_config_loaded():
    """knowledge.yaml 配置正确加载"""
    from app.common.config import get_config

    cfg = get_config().knowledge
    assert cfg.time_format.weekdays[0] == "星期一"
    assert cfg.prompt_prefixes.tool_list_header == "你可以使用以下工具完成操作："
    assert cfg.prompt_prefixes.memory_header == "你对该用户的认知："
    assert cfg.prompt_separator == "\n\n---\n\n"


def test_attachment_prompt_prefixes_loaded():
    """附件提示配置正确加载"""
    from app.common.config import get_config

    prefixes = get_config().knowledge.prompt_prefixes
    assert prefixes.attachment_header == "用户发送了以下附件："
    assert prefixes.attachment_with_tools == "如果有可用工具处理附件请使用。"
    assert prefixes.attachment_no_tools == "你无法查看或理解此类型的附件，请告知用户。"


def test_experience_config_loaded():
    """experience.yaml 配置正确加载"""
    from app.common.config import get_config

    cfg = get_config().experience
    assert cfg.max_entries == 50
    assert cfg.message_truncation == 500
    assert cfg.filter.min_length == 10
    assert "不存在" in cfg.filter.invalid_keywords
    assert "```" in cfg.filter.markdown_prefixes
    assert cfg.filter.filter_json is True


def test_profile_config_loaded():
    """profile.yaml 配置正确加载"""
    from app.common.config import get_config

    cfg = get_config().profile
    assert cfg.max_memory_entries == 30
    assert cfg.message_truncation == 500


def test_unknown_config_key_rejected():
    """配置 YAML typo（未知字段）应在加载时报错，而非静默回退默认值"""
    from pydantic import ValidationError
    from app.common.config import LLMConfig

    with pytest.raises(ValidationError):
        LLMConfig(api_key="k", base_url="u", model="m", tempreture=0.5)  # typo: tempreture