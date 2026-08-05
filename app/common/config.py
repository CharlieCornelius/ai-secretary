"""Pydantic Settings 配置模型 - YAML 加载 + 环境变量替换"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field


def _resolve_env_vars(value: Any) -> Any:
    """递归解析字符串中的 ${VAR} 和 ${VAR:-default}，并自动解析 JSON"""
    if isinstance(value, dict):
        return {k: _resolve_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_env_vars(item) for item in value]
    if not isinstance(value, str):
        return value

    pattern = re.compile(r'\$\{([^}:]+)(?::-(.*))?\}')

    def replacer(match: re.Match) -> str:
        var_name = match.group(1)
        default = match.group(2)
        env_val = os.getenv(var_name)
        if env_val is not None:
            return env_val
        if default is not None:
            return default
        return ""  # 无环境变量且无默认值 → 空字符串（校验会报错）

    result = pattern.sub(replacer, value)

    # 尝试解析 JSON（数组或对象）
    if result.strip().startswith(("[", "{")):
        try:
            import json
            return json.loads(result)
        except (json.JSONDecodeError, ValueError):
            pass

    return result


class _StrictConfig(BaseModel, extra="forbid"):
    """配置模型基类：拒绝未知字段，启动即捕获 YAML typo（如 sever:/tempreture:）"""


class ServerConfig(_StrictConfig):
    """服务器配置"""
    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = False


class LLMConfig(_StrictConfig):
    """LLM 配置"""
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    temperature: float = 1
    max_tokens: int = 4096
    sub_task_max_tokens: int = 2048
    sub_task_temperature: float = 1
    max_retries: int = 2


class DatabaseConfig(_StrictConfig):
    """数据库配置"""
    url: str = "sqlite+aiosqlite:///data/secretary.db"
    echo: bool = False
    pool_pre_ping: bool = True


class ChromaConfig(_StrictConfig):
    """向量库配置"""
    persist_directory: str = "data/chroma"
    collection_name: str = "experience"
    hnsw_space: str = "cosine"


class AuthConfig(_StrictConfig):
    """认证配置"""
    api_keys: list[str] = Field(default_factory=list)
    api_key_header: str = "X-API-Key"


class LoggingConfig(_StrictConfig):
    """日志配置"""
    level: str = "INFO"
    format: str = "json"


class CorsConfig(_StrictConfig):
    """CORS 配置"""
    allow_origins: list[str] = Field(default_factory=lambda: ["*"])
    allow_methods: list[str] = Field(default_factory=lambda: ["*"])
    allow_headers: list[str] = Field(default_factory=lambda: ["*"])
    allow_credentials: bool = False


class AppMetaConfig(_StrictConfig):
    """应用元信息（FastAPI / OpenAPI 文档）"""
    title: str = "AI Secretary"
    description: str = "AI 秘书 - 智能对话"
    version: str = "1.0.0"


class PluginsConfig(_StrictConfig):
    """插件系统配置"""
    directory: str = "plugins"


class TimeFormatConfig(_StrictConfig):
    """时间格式化配置"""
    weekdays: list[str] = Field(default_factory=lambda: [
        "星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"
    ])
    format: str = "当前时间：{date} {weekday} {time}"
    date_format: str = "%Y年%m月%d日"
    time_format: str = "%H:%M"


class PromptPrefixesConfig(_StrictConfig):
    """prompt 前缀配置"""
    tool_list_header: str = "你可以使用以下工具完成操作："
    tool_list_footer: str = "当用户有相关需求时，请主动调用对应工具。"
    tool_list_entry: str = "• {name} - {desc}"
    memory_header: str = "你对该用户的认知："
    memory_entry: str = "- {k}：{v}"
    experience_header: str = "相关经验模式："
    experience_entry: str = "- {exp}"
    external_header: str = "外部知识："
    attachment_header: str = "用户发送了以下附件："
    attachment_with_tools: str = "如果有可用工具处理附件请使用。"
    attachment_no_tools: str = "你无法查看或理解此类型的附件，请告知用户。"
    group_chat_hint: str = "当前为群聊模式，多人参与对话，每条消息前方的 [user_id] 标识发言者。提及或称呼用户时，优先使用用户的名字（如画像或上下文中已知），仅在无法获知名字时才使用 user_id。"
    group_chat_prefix: str = "[{user_id}] {content}"


class KnowledgeConfig(_StrictConfig):
    """知识注入配置"""
    time_format: TimeFormatConfig = Field(default_factory=TimeFormatConfig)
    prompt_separator: str = "\n\n---\n\n"
    experience_n_results: int = 3
    prompt_prefixes: PromptPrefixesConfig = Field(default_factory=PromptPrefixesConfig)


class ContextConfig(_StrictConfig):
    """上下文窗口配置"""
    max_context_turns: int = 20
    max_tool_iterations: int = 5
    fallback_response: str = "抱歉，我暂时无法回复，请稍后再试。"


class ProfilePrompts(_StrictConfig):
    """画像 prompt 模板"""
    extraction: str = ""
    compression: str = ""


class ProfileConfig(_StrictConfig):
    """用户画像配置"""
    max_memory_entries: int = 30
    prompts: ProfilePrompts = Field(default_factory=ProfilePrompts)
    message_truncation: int = 500


class ExperiencePrompts(_StrictConfig):
    """经验库 prompt 模板"""
    extraction: str = ""
    compression: str = ""


class ExperienceFilterConfig(_StrictConfig):
    """经验过滤规则配置"""
    invalid_keywords: list[str] = Field(default_factory=lambda: ["不存在", "无"])
    markdown_prefixes: list[str] = Field(default_factory=lambda: [
        "```", "#", "**", "---", "> ", "- "
    ])
    filter_json: bool = True
    min_length: int = 10


class ExperienceConfig(_StrictConfig):
    """经验库配置"""
    max_entries: int = 50
    prompts: ExperiencePrompts = Field(default_factory=ExperiencePrompts)
    filter: ExperienceFilterConfig = Field(default_factory=ExperienceFilterConfig)
    message_truncation: int = 500


class ApiDefaultsConfig(_StrictConfig):
    """API 默认值配置"""
    session_limit: int = 50
    experience_n_results: int = 50


class LoggingTruncationConfig(_StrictConfig):
    """日志截断配置"""
    pattern_log: int = 100
    error_content: int = 200


class AuditConfig(_StrictConfig):
    """审计日志配置"""
    max_logs: int = 1_000_000
    trim_ratio: float = 0.1


class BackgroundConfig(_StrictConfig):
    """后台任务配置"""
    shutdown_timeout: float = 5.0


class AppConfig(_StrictConfig):
    """主配置模型 - 整合所有子配置"""

    server: ServerConfig = Field(default_factory=ServerConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    chroma: ChromaConfig = Field(default_factory=ChromaConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    cors: CorsConfig = Field(default_factory=CorsConfig)
    app: AppMetaConfig = Field(default_factory=AppMetaConfig)
    plugins: PluginsConfig = Field(default_factory=PluginsConfig)

    api_defaults: ApiDefaultsConfig = Field(default_factory=ApiDefaultsConfig)
    logging_truncation: LoggingTruncationConfig = Field(default_factory=LoggingTruncationConfig)

    context: ContextConfig = Field(default_factory=ContextConfig)
    profile: ProfileConfig = Field(default_factory=ProfileConfig)
    experience: ExperienceConfig = Field(default_factory=ExperienceConfig)
    audit: AuditConfig = Field(default_factory=AuditConfig)
    background: BackgroundConfig = Field(default_factory=BackgroundConfig)
    knowledge: KnowledgeConfig = Field(default_factory=KnowledgeConfig)

    @classmethod
    def from_yaml(cls, path: Path) -> "AppConfig":
        """从 YAML 文件加载配置，支持 ${VAR} 和 ${VAR:-default} 环境变量占位符"""
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        # 解析环境变量占位符
        data = _resolve_env_vars(data)

        return cls(**data)


# 全局配置单例
_config: Optional[AppConfig] = None


def _load_module_config(config_dir: Path, name: str) -> dict[str, Any]:
    """加载单个模块配置 yaml"""
    path = config_dir / f"{name}.yaml"
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def _deep_merge(base: dict, override: dict) -> dict:
    """递归合并两个字典，override 覆盖 base"""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _load_module_configs(config_dir: Path, config: AppConfig) -> None:
    """加载模块化业务配置并合并到主配置"""
    config.profile = ProfileConfig(**_deep_merge(
        config.profile.model_dump(), _load_module_config(config_dir, "profile")
    ))
    config.experience = ExperienceConfig(**_deep_merge(
        config.experience.model_dump(), _load_module_config(config_dir, "experience")
    ))
    config.knowledge = KnowledgeConfig(**_deep_merge(
        config.knowledge.model_dump(), _load_module_config(config_dir, "knowledge")
    ))


def get_config() -> AppConfig:
    """获取全局配置"""
    global _config
    if _config is None:
        config_dir = Path(__file__).parent.parent.parent / "config"
        _config = AppConfig.from_yaml(config_dir / "app.yaml")
        _load_module_configs(config_dir, _config)
    return _config


def _resolve_data_paths(config: AppConfig, project_root: Path) -> None:
    """将 data 相对路径解析为基于项目根目录的绝对路径，确保无论从哪个目录启动都能正确创建"""
    # 解析 SQLite 数据库路径
    db_url = config.database.url
    if db_url.startswith("sqlite+aiosqlite:///") and not db_url.startswith("sqlite+aiosqlite:////"):
        # 相对路径：sqlite+aiosqlite:///data/secretary.db
        rel_path = db_url[len("sqlite+aiosqlite:///"):]
        abs_path = project_root / rel_path
        config.database.url = f"sqlite+aiosqlite:///{abs_path}"

    # 解析 ChromaDB 持久化目录
    chroma_dir = config.chroma.persist_directory
    if not Path(chroma_dir).is_absolute():
        config.chroma.persist_directory = str(project_root / chroma_dir)

    # 解析插件目录（相对路径基于项目根目录）
    plugins_dir = config.plugins.directory
    if not Path(plugins_dir).is_absolute():
        config.plugins.directory = str(project_root / plugins_dir)


def init_config(path: Optional[Path] = None) -> AppConfig:
    """初始化配置（启动时调用）"""
    global _config

    if path is None:
        path = Path(__file__).parent.parent.parent / "config" / "app.yaml"

    config_dir = path.parent
    project_root = path.parent.parent  # config/ 的上一级就是项目根目录
    _config = AppConfig.from_yaml(path)
    _load_module_configs(config_dir, _config)

    # 解析 data 相对路径为绝对路径
    _resolve_data_paths(_config, project_root)

    # 校验 LLM 必填配置
    missing = []
    if not _config.llm.api_key:
        missing.append("llm.api_key")
    if not _config.llm.base_url:
        missing.append("llm.base_url")
    if not _config.llm.model:
        missing.append("llm.model")

    if missing:
        raise ValueError(
            f"缺少 LLM 配置：{', '.join(missing)}\n"
            f"请设置环境变量或在 {path} 中配置"
        )

    return _config