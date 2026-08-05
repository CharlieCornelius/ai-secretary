"""数据库模型测试"""

import pytest

from datetime import datetime


class TestHelperFunctions:
    """辅助函数"""

    def test_now_returns_local_time(self):
        """_now() 返回本地时间（非 UTC）"""
        from app.db.models import _now

        now = _now()
        assert isinstance(now, datetime)
        # 与本地 datetime.now() 的小时一致
        local_now = datetime.now()
        assert now.hour == local_now.hour

    def test_now_returns_datetime_instance(self):
        """_now() 返回 datetime 实例"""
        from app.db.models import _now

        now = _now()
        assert isinstance(now, datetime)
        assert now.tzinfo is None  # naive datetime

    def test_uuid_returns_string(self):
        """_uuid() 返回 UUID 字符串"""
        from app.db.models import _uuid

        uid = _uuid()
        assert isinstance(uid, str)
        assert len(uid) == 36  # UUID 标准格式
        assert uid.count("-") == 4

    def test_uuid_unique(self):
        """_uuid() 每次生成唯一值"""
        from app.db.models import _uuid

        ids = {_uuid() for _ in range(100)}
        assert len(ids) == 100


class TestTableModels:
    """表结构定义"""

    def test_session_table_name(self):
        from app.db.models import Session

        assert Session.__tablename__ == "sessions"

    def test_message_table_name(self):
        from app.db.models import Message

        assert Message.__tablename__ == "messages"

    def test_profile_table_name(self):
        from app.db.models import Profile

        assert Profile.__tablename__ == "profiles"

    def test_audit_log_table_name(self):
        from app.db.models import AuditLog

        assert AuditLog.__tablename__ == "audit_logs"

    def test_session_default_values(self):
        """Session 默认值"""
        from app.db.models import Session

        # 检查列定义存在
        col_names = {c.name for c in Session.__table__.columns}
        assert "id" in col_names
        assert "title" in col_names
        assert "mode" in col_names
        assert "status" in col_names
        assert "created_at" in col_names
        assert "updated_at" in col_names

    def test_message_has_session_id_fk(self):
        """Message 有 session_id 外键"""
        from app.db.models import Message

        col_names = {c.name for c in Message.__table__.columns}
        assert "session_id" in col_names
        assert "role" in col_names
        assert "content" in col_names

    def test_profile_user_id_is_primary_key(self):
        """Profile 的 user_id 是主键"""
        from app.db.models import Profile

        pk_cols = [c.name for c in Profile.__table__.primary_key.columns]
        assert pk_cols == ["user_id"]