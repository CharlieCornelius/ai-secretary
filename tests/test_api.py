"""API 端点完整测试"""

import pytest


class TestSessions:
    """会话管理 API"""

    def test_create_session(self, client, auth_headers):
        response = client.post("/api/v1/sessions", json={"title": "Test"}, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "id" in data["data"]
        assert data["data"]["title"] == "Test"

    def test_list_sessions(self, client, auth_headers):
        client.post("/api/v1/sessions", json={"title": "S1"}, headers=auth_headers)
        response = client.get("/api/v1/sessions", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert isinstance(data["data"], list)
        assert len(data["data"]) >= 1

    def test_get_session(self, client, auth_headers):
        r = client.post("/api/v1/sessions", json={"title": "S2"}, headers=auth_headers)
        sid = r.json()["data"]["id"]
        r = client.get(f"/api/v1/sessions/{sid}", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["data"]["id"] == sid

    def test_update_session(self, client, auth_headers):
        r = client.post("/api/v1/sessions", json={"title": "Old"}, headers=auth_headers)
        sid = r.json()["data"]["id"]
        r = client.patch(f"/api/v1/sessions/{sid}", json={"title": "New"}, headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["data"]["title"] == "New"

    def test_delete_session(self, client, auth_headers):
        r = client.post("/api/v1/sessions", json={"title": "Del"}, headers=auth_headers)
        sid = r.json()["data"]["id"]
        r = client.delete(f"/api/v1/sessions/{sid}", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["data"]["deleted"] is True
        r = client.get(f"/api/v1/sessions/{sid}", headers=auth_headers)
        assert r.status_code == 404

    def test_session_not_found(self, client, auth_headers):
        r = client.get("/api/v1/sessions/non-existent", headers=auth_headers)
        assert r.status_code == 404
        assert r.json()["ok"] is False

    def test_get_session_messages(self, client, auth_headers):
        r = client.post("/api/v1/sessions", json={"title": "Msg"}, headers=auth_headers)
        sid = r.json()["data"]["id"]
        r = client.get(f"/api/v1/sessions/{sid}/messages", headers=auth_headers)
        assert r.status_code == 200
        assert isinstance(r.json()["data"], list)


class TestChat:
    """对话交互 API"""

    def test_interact_basic(self, client, auth_headers, test_user_id):
        r = client.post("/api/v1/sessions", json={"title": "Chat"}, headers=auth_headers)
        sid = r.json()["data"]["id"]
        r = client.post(
            f"/api/v1/sessions/{sid}/interact",
            json={"message": "hello", "user_id": test_user_id},
            headers=auth_headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["data"]["type"] == "response"
        assert "response" in data["data"]

    def test_interact_with_attachments(self, client, auth_headers, test_user_id):
        """带附件的对话交互"""
        r = client.post("/api/v1/sessions", json={"title": "Attach"}, headers=auth_headers)
        sid = r.json()["data"]["id"]
        r = client.post(
            f"/api/v1/sessions/{sid}/interact",
            json={
                "message": "看这张图片",
                "user_id": test_user_id,
                "attachments": [
                    {"type": "image", "data": {"file": "https://example.com/photo.jpg"}},
                ],
            },
            headers=auth_headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        # 无工具处理附件时 content_blocks 不会出现
        # 有工具返回富内容时才会出现

    def test_interact_without_attachments(self, client, auth_headers, test_user_id):
        """省略 attachments 的纯对话交互，响应和旧版一致（无 content_blocks）"""
        r = client.post("/api/v1/sessions", json={"title": "NoAttach"}, headers=auth_headers)
        sid = r.json()["data"]["id"]
        r = client.post(
            f"/api/v1/sessions/{sid}/interact",
            json={"message": "hello", "user_id": test_user_id},
            headers=auth_headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        # 纯对话时响应不应包含 content_blocks 字段，和旧版一致
        assert "content_blocks" not in data["data"]

    def test_interact_session_not_found(self, client, auth_headers, test_user_id):
        r = client.post(
            "/api/v1/sessions/non-existent/interact",
            json={"message": "hello", "user_id": test_user_id},
            headers=auth_headers,
        )
        assert r.status_code == 400
        assert r.json()["ok"] is False

class TestExperiences:
    """经验库 API"""

    def test_add_and_list(self, client, auth_headers):
        r = client.post("/api/v1/experiences", json={"pattern": "test", "category": "test"}, headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["data"]["added"] is True

        r = client.get("/api/v1/experiences", headers=auth_headers)
        assert r.status_code == 200
        assert len(r.json()["data"]) >= 1

    def test_clear_experiences(self, client, auth_headers):
        client.post("/api/v1/experiences", json={"pattern": "x", "category": "test"}, headers=auth_headers)
        r = client.delete("/api/v1/experiences", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["data"]["cleared"] is True

        r = client.get("/api/v1/experiences", headers=auth_headers)
        assert len(r.json()["data"]) == 0


class TestProfile:
    """用户画像 API"""

    def test_get_profile(self, client, auth_headers, test_user_id):
        r = client.get(f"/api/v1/profile/{test_user_id}", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["data"]["user_id"] == test_user_id

    def test_update_profile(self, client, auth_headers, test_user_id):
        r = client.patch(
            f"/api/v1/profile/{test_user_id}",
            json={"memories": {"theme": "dark"}},
            headers=auth_headers,
        )
        assert r.status_code == 200
        assert r.json()["data"]["memories"]["theme"] == "dark"

    def test_delete_profile(self, client, auth_headers, test_user_id):
        """删除画像后 GET 返回空画像"""
        # 先确保画像存在
        client.patch(
            f"/api/v1/profile/{test_user_id}",
            json={"memories": {"theme": "dark"}},
            headers=auth_headers,
        )
        r = client.delete(f"/api/v1/profile/{test_user_id}", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["data"]["deleted"] is True
        # 再次删除（已不存在）返回 deleted=False
        r = client.delete(f"/api/v1/profile/{test_user_id}", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["data"]["deleted"] is False
        # GET 重新创建空画像
        r = client.get(f"/api/v1/profile/{test_user_id}", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["data"]["memories"] == {}


class TestPlugins:
    """插件 API"""

    def test_plugins_list(self, client, auth_headers):
        r = client.get("/api/v1/plugins", headers=auth_headers)
        assert r.status_code == 200
        plugins = r.json()["data"]
        assert isinstance(plugins, list)


class TestRequestId:
    """request-id 中间件"""

    def test_response_has_request_id(self, client):
        """响应头自动带 X-Request-Id"""
        r = client.get("/health")
        assert r.status_code == 200
        assert r.headers.get("X-Request-Id")

    def test_request_id_echoed(self, client):
        """客户端传入的 X-Request-Id 被透传回响应头"""
        rid = "my-request-id-123"
        r = client.get("/health", headers={"X-Request-Id": rid})
        assert r.headers.get("X-Request-Id") == rid


class TestSessionMode:
    """会话模式（single/group）"""

    def test_create_session_with_group_mode(self, client, auth_headers):
        """创建群聊模式会话"""
        r = client.post("/api/v1/sessions", json={"title": "GroupChat", "mode": "group"}, headers=auth_headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["mode"] == "group"

    def test_create_session_default_mode(self, client, auth_headers):
        """不指定 mode 时默认为 single"""
        r = client.post("/api/v1/sessions", json={"title": "Default"}, headers=auth_headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["mode"] == "single"

    def test_create_session_with_single_mode(self, client, auth_headers):
        """显式指定 single 模式"""
        r = client.post("/api/v1/sessions", json={"title": "Single", "mode": "single"}, headers=auth_headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["mode"] == "single"

    def test_get_session_returns_mode(self, client, auth_headers):
        """获取会话时返回 mode 字段"""
        r = client.post("/api/v1/sessions", json={"title": "M", "mode": "group"}, headers=auth_headers)
        sid = r.json()["data"]["id"]
        r = client.get(f"/api/v1/sessions/{sid}", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["data"]["mode"] == "group"

    def test_group_chat_stores_user_id(self, client, auth_headers, test_user_id):
        """群聊模式 interact 时消息 metadata 存 user_id，content 存原始消息"""
        r = client.post("/api/v1/sessions", json={"title": "GC", "mode": "group"}, headers=auth_headers)
        sid = r.json()["data"]["id"]
        r = client.post(
            f"/api/v1/sessions/{sid}/interact",
            json={"message": "hello", "user_id": test_user_id},
            headers=auth_headers,
        )
        assert r.status_code == 200
        # 查看消息列表，确认 metadata 包含 user_id
        r = client.get(f"/api/v1/sessions/{sid}/messages", headers=auth_headers)
        msgs = r.json()["data"]
        user_msgs = [m for m in msgs if m["role"] == "user"]
        assert len(user_msgs) >= 1
        assert user_msgs[0]["metadata"].get("user_id") == test_user_id
        # 群聊 content 存原始消息（前缀由 context.py 读历史时拼给 LLM）
        assert user_msgs[0]["content"] == "hello"

    def test_group_chat_context_no_double_prefix(self, client, auth_headers, test_user_id):
        """群聊多轮对话：DB 中 content 无前缀（前缀由 context.py 拼给 LLM）"""
        r = client.post("/api/v1/sessions", json={"title": "GC2", "mode": "group"}, headers=auth_headers)
        sid = r.json()["data"]["id"]
        # 发送两条消息（产生多轮历史）
        client.post(f"/api/v1/sessions/{sid}/interact",
                    json={"message": "第一条", "user_id": test_user_id}, headers=auth_headers)
        client.post(f"/api/v1/sessions/{sid}/interact",
                    json={"message": "第二条", "user_id": test_user_id}, headers=auth_headers)
        # 查看历史消息，确认 user 消息 content 无前缀
        r = client.get(f"/api/v1/sessions/{sid}/messages", headers=auth_headers)
        msgs = r.json()["data"]
        user_msgs = [m for m in msgs if m["role"] == "user"]
        for m in user_msgs:
            assert m["content"] == "第一条" or m["content"] == "第二条"

    def test_single_chat_no_user_id_in_metadata(self, client, auth_headers, test_user_id):
        """单人模式 interact 时消息 metadata 不存 user_id，content 无前缀"""
        r = client.post("/api/v1/sessions", json={"title": "SC", "mode": "single"}, headers=auth_headers)
        sid = r.json()["data"]["id"]
        r = client.post(
            f"/api/v1/sessions/{sid}/interact",
            json={"message": "hello", "user_id": test_user_id},
            headers=auth_headers,
        )
        assert r.status_code == 200
        # 查看消息列表，确认 metadata 不包含 user_id
        r = client.get(f"/api/v1/sessions/{sid}/messages", headers=auth_headers)
        msgs = r.json()["data"]
        user_msgs = [m for m in msgs if m["role"] == "user"]
        assert len(user_msgs) >= 1
        # 单人模式下 metadata 为 None 或不含 user_id
        meta = user_msgs[0].get("metadata") or {}
        assert meta.get("user_id") is None
        # 单人模式 content 无 [user_id] 前缀
        assert user_msgs[0]["content"] == "hello"

    def test_create_session_invalid_mode(self, client, auth_headers):
        """创建会话时 mode 传非法值返回 422"""
        r = client.post("/api/v1/sessions", json={"title": "Bad", "mode": "invalid_mode"}, headers=auth_headers)
        assert r.status_code == 422