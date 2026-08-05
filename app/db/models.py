"""SQLAlchemy 模型定义 - 5 张表"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# 列宽常量（仅本模块使用）
UUID_LENGTH = 36   # UUID 字符串长度
ENUM_LENGTH = 20   # 枚举型字段（mode/status/role/direction）长度


class Base(DeclarativeBase):
    """SQLAlchemy 声明式基类"""
    type_annotation_map = {
        dict[str, Any]: JSON,
        list[dict[str, Any]]: JSON,
    }


def _uuid() -> str:
    """生成 UUID 字符串"""
    return str(uuid.uuid4())


def _now() -> datetime:
    """获取当前本地时间"""
    return datetime.now()


# === 1. 会话 ===

class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(UUID_LENGTH), primary_key=True, default=_uuid)
    title: Mapped[Optional[str]] = mapped_column(String(256), nullable=True, comment="会话标题（可选，由客户端提供）")
    mode: Mapped[str] = mapped_column(String(ENUM_LENGTH), default="single", comment="single | group")
    status: Mapped[str] = mapped_column(String(ENUM_LENGTH), default="active", comment="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


# === 2. 消息 ===

class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(UUID_LENGTH), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(String(UUID_LENGTH), ForeignKey("sessions.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(ENUM_LENGTH), nullable=False, comment="user | assistant | tool | system")
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tool_calls: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSON, nullable=True, comment="assistant 工具调用详情（多步编排中间产物）")
    metadata_: Mapped[Optional[dict[str, Any]]] = mapped_column("metadata", JSON, nullable=True, comment="扩展元数据")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


# === 3. 用户画像 ===
# AI 对用户的记忆与认知，由 LLM 自主维护

class Profile(Base):
    __tablename__ = "profiles"

    user_id: Mapped[str] = mapped_column(String(UUID_LENGTH), primary_key=True)
    memories: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, comment="AI 对用户的记忆与认知（LLM 自主维护）")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


# === 4. 审计日志 ===
# 全量交互记录，只追加不读取，与 LLM 记忆分离

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(UUID_LENGTH), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(UUID_LENGTH), nullable=False)
    session_id: Mapped[str] = mapped_column(String(UUID_LENGTH), ForeignKey("sessions.id"), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(ENUM_LENGTH), nullable=False, comment="user | assistant | tool | system")
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    metadata_: Mapped[Optional[dict[str, Any]]] = mapped_column("metadata", JSON, nullable=True, comment="扩展信息")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True, comment="按时间删旧时需要索引")
