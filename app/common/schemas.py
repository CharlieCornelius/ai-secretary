"""共享 Pydantic 模型 - API 请求/响应"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, Literal, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


# === 通用响应 ===

class OkResponse(BaseModel, Generic[T]):
    """成功响应"""
    ok: bool = True
    data: T

# === 会话 ===

class SessionCreate(BaseModel):
    """创建会话请求"""
    title: Optional[str] = None
    mode: Literal["single", "group"] = "single"


class SessionUpdate(BaseModel):
    """更新会话请求"""
    title: Optional[str] = None


class SessionResponse(BaseModel):
    """会话响应"""
    id: str
    title: Optional[str] = None
    mode: str = "single"
    status: str = "active"
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, session) -> "SessionResponse":
        """从 SQLAlchemy Session 模型构造响应，消除重复字段映射"""
        return cls(
            id=session.id,
            title=session.title,
            mode=session.mode,
            status=session.status,
            created_at=session.created_at,
            updated_at=session.updated_at,
        )


# === 对话 ===

class ContentBlock(BaseModel):
    """富内容块 - 统一模型，输入附件与输出富内容共用"""
    type: str                        # 路由标签，给前端看的："image", "emoji", "file", "audio"...
    data: dict[str, Any]             # 开放数据，插件/适配器自由定义


class InteractRequest(BaseModel):
    """对话交互请求"""
    message: str = Field(max_length=32000)
    attachments: list[ContentBlock] = Field(default_factory=list, max_length=20)
    user_id: str = Field(max_length=128)


class InteractData(BaseModel):
    """对话交互响应数据"""
    type: str = "response"
    response: str
    events: list[dict[str, Any]] = Field(default_factory=list)
    content_blocks: Optional[list[ContentBlock]] = None


# === 用户画像 ===

class ProfileUpdate(BaseModel):
    """更新用户画像请求（供外部手动编辑）"""
    memories: Optional[dict[str, Any]] = None


class ProfileResponse(BaseModel):
    """用户画像响应"""
    user_id: str
    memories: dict[str, Any] = Field(default_factory=dict)
    updated_at: Optional[datetime] = None


# === 消息 ===

class MessageResponse(BaseModel):
    """消息响应"""
    id: str
    session_id: str
    role: str
    content: str
    tool_calls: Optional[list[dict[str, Any]]] = None
    metadata: Optional[dict[str, Any]] = None
    created_at: datetime


# === 插件 ===

class PluginResponse(BaseModel):
    """插件信息响应"""
    name: str
    version: str
    description: Optional[str] = None
    tools: list[str] = Field(default_factory=list)



