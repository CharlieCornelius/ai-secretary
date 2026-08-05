# AI Secretary API 使用文档

本文档详细说明如何使用 AI Secretary 的 REST API。

**基础 URL**：`http://localhost:8000`

**认证方式**（如配置）：
```bash
curl -H "X-API-Key: your-api-key" http://localhost:8000/api/v1/sessions
```

> 认证头名称由 `config/app.yaml` 的 `auth.api_key_header` 配置（默认 `X-API-Key`）。`auth.api_keys` 为空时无需认证。

**请求追踪**：每个响应都带 `X-Request-Id` 头，服务端日志按该 ID 关联同一请求的全部日志，便于排障。

---

## 目录

- [通用规范](#通用规范)
- [健康检查](#健康检查)
- [会话管理](#会话管理)
- [对话交互](#对话交互)
- [经验库](#经验库)
- [用户画像](#用户画像)
- [插件](#插件)

---

## 通用规范

### 响应格式

所有响应均为 JSON，统一结构：

```json
// 成功
{
  "ok": true,
  "data": { ... }
}

// 错误
{
  "ok": false,
  "error": {
    "code": "错误码",
    "message": "错误描述"
  }
}
```

### 错误码

| 错误码 | HTTP 状态码 | 说明 |
|--------|------------|------|
| `AUTH_ERROR` | 401 | 认证失败 |
| `NOT_FOUND` | 404 | 资源不存在 |
| `SESSION_ERROR` | 400 | 会话相关错误 |
| `VALIDATION_ERROR` | 422 | 请求参数校验失败 |
| `INTERNAL_ERROR` | 500 | 服务器内部错误 |

---

## 健康检查

### GET /health

检查服务是否正常运行。

**请求**：
```bash
curl http://localhost:8000/health
```

**响应**：
```json
{
  "status": "ok",
  "service": "ai-secretary"
}
```

---

## 会话管理

### POST /api/v1/sessions

创建新会话。

**请求**：
```bash
curl -X POST http://localhost:8000/api/v1/sessions \
  -H "Content-Type: application/json" \
  -d '{"title": "我的会话"}'
```

**参数**：

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `title` | string | 否 | 会话标题 |
| `mode` | string | 否 | 会话模式：`single`（默认，单人）或 `group`（群聊） |

**响应**：
```json
{
  "ok": true,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "title": "我的会话",
    "mode": "single",
    "status": "active",
    "created_at": "2024-01-15T08:30:00",
    "updated_at": "2024-01-15T08:30:00"
  }
}
```

---

### GET /api/v1/sessions

列出所有活跃会话（按更新时间倒序）。

**请求**：
```bash
curl http://localhost:8000/api/v1/sessions
```

**响应**：
```json
{
  "ok": true,
  "data": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "title": "我的会话",
      "mode": "single",
      "status": "active",
      "created_at": "2024-01-15T08:30:00",
      "updated_at": "2024-01-15T08:35:00"
    }
  ]
}
```

---

### GET /api/v1/sessions/{id}

获取会话详情。

**请求**：
```bash
curl http://localhost:8000/api/v1/sessions/550e8400-e29b-41d4-a716-446655440000
```

**响应**：
```json
{
  "ok": true,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "title": "我的会话",
    "mode": "single",
    "status": "active",
    "created_at": "2024-01-15T08:30:00",
    "updated_at": "2024-01-15T08:35:00"
  }
}
```

---

### PATCH /api/v1/sessions/{id}

修改会话标题。

**请求**：
```bash
curl -X PATCH http://localhost:8000/api/v1/sessions/550e8400-e29b-41d4-a716-446655440000 \
  -H "Content-Type: application/json" \
  -d '{"title": "新标题"}'
```

**参数**：

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `title` | string | 否 | 新标题 |

**响应**：
```json
{
  "ok": true,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "title": "新标题",
    "status": "active",
    "created_at": "2024-01-15T08:30:00",
    "updated_at": "2024-01-15T08:40:00"
  }
}
```

---

### DELETE /api/v1/sessions/{id}

删除会话（级联删除消息和审计日志）。

**请求**：
```bash
curl -X DELETE http://localhost:8000/api/v1/sessions/550e8400-e29b-41d4-a716-446655440000
```

**响应**：
```json
{
  "ok": true,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "deleted": true
  }
}
```

---

### GET /api/v1/sessions/{id}/messages

获取会话消息列表。

**请求**：
```bash
curl "http://localhost:8000/api/v1/sessions/550e8400-e29b-41d4-a716-446655440000/messages?limit=20"
```

**参数**：

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `limit` | integer | 否 | 返回数量，默认 50 |

**响应**：
```json
{
  "ok": true,
  "data": [
    {
      "id": "msg-001",
      "session_id": "550e8400-e29b-41d4-a716-446655440000",
      "role": "user",
      "content": "北京天气怎么样？",
      "tool_calls": null,
      "metadata": null,
      "created_at": "2024-01-15T08:30:00"
    },
    {
      "id": "msg-002",
      "session_id": "550e8400-e29b-41d4-a716-446655440000",
      "role": "assistant",
      "content": "",
      "tool_calls": [{"id": "call_abc", "name": "get_weather", "args": {"city": "北京"}}],
      "metadata": null,
      "created_at": "2024-01-15T08:30:02"
    },
    {
      "id": "msg-003",
      "session_id": "550e8400-e29b-41d4-a716-446655440000",
      "role": "tool",
      "content": "北京 晴 25℃",
      "tool_calls": null,
      "metadata": {"tool_call_id": "call_abc"},
      "created_at": "2024-01-15T08:30:03"
    },
    {
      "id": "msg-004",
      "session_id": "550e8400-e29b-41d4-a716-446655440000",
      "role": "assistant",
      "content": "北京今天晴，25℃。",
      "tool_calls": null,
      "metadata": null,
      "created_at": "2024-01-15T08:30:05"
    }
  ]
}
```

> 多步工具编排的完整轨迹（assistant 工具调用 → tool 结果 → 最终回复）会持久化到消息表，使后续轮次能重建工具上下文。

**字段说明**：

| 字段 | 说明 |
|------|------|
| `role` | `user` / `assistant` / `tool` |
| `tool_calls` | assistant 消息中的工具调用请求（`[{id, name, args}]`），仅工具调用轮次的 assistant 有值 |
| `metadata` | 消息元数据。群聊模式（`mode: group`）下 user 消息含 `{"user_id": "..."}`；tool 消息含 `{"tool_call_id": "..."}`；含富内容的最终回复含 `{"content_blocks": [...]}` |

---

## 对话交互

### POST /api/v1/sessions/{id}/interact

发送消息并获取 AI 回复。

**请求**：
```bash
curl -X POST http://localhost:8000/api/v1/sessions/550e8400-e29b-41d4-a716-446655440000/interact \
  -H "Content-Type: application/json" \
  -d '{
    "message": "北京今天天气怎么样？",
    "user_id": "user-123",
    "attachments": []
  }'
```

**参数**：

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `message` | string | 是 | 用户消息（最长 32000 字符） |
| `user_id` | string | 是 | 用户标识（最长 128 字符） |
| `attachments` | array | 否 | 附件列表，每项为 `{"type": str, "data": dict}`，最多 20 项 |

**`attachments` 格式**：

```json
[
  {"type": "image", "data": {"file": "https://example.com/photo.jpg"}},
  {"type": "file", "data": {"file": "https://example.com/doc.pdf", "filename": "报告.pdf"}}
]
```

**响应（无工具调用）**：
```json
{
  "ok": true,
  "data": {
    "type": "response",
    "response": "北京今天天气晴朗，气温 15-25°C，适合外出。",
    "events": [
      {
        "event": "thinking",
        "data": {"status": "knowledge_injected"}
      },
      {
        "event": "llm_response",
        "data": {"has_tool_calls": false, "tool_count": 0}
      },
      {
        "event": "complete",
        "data": {"response": "北京今天天气晴朗，气温 15-25°C，适合外出。"}
      }
    ]
  }
}
```

> `content_blocks` 字段仅当工具返回富内容时才出现（缺省时省略）。

**响应（有工具调用，含富内容）**：
```json
{
  "ok": true,
  "data": {
    "type": "response",
    "response": "北京今天晴，15°C，北风3级。",
    "content_blocks": [
      {"type": "image", "data": {"file": "https://example.com/weather_chart.png"}}
    ],
    "events": [
      {
        "event": "thinking",
        "data": {"status": "knowledge_injected"}
      },
      {
        "event": "llm_response",
        "data": {"has_tool_calls": true, "tool_count": 1}
      },
      {
        "event": "tool_executed",
        "data": {"tool": "get_weather", "success": true}
      },
      {
        "event": "llm_response",
        "data": {"has_tool_calls": false, "tool_count": 0}
      },
      {
        "event": "complete",
        "data": {"response": "北京今天晴，15°C，北风3级。"}
      }
    ]
  }
}
```

**事件类型**：

| 事件 | 说明 |
|------|------|
| `thinking` | 知识注入完成 |
| `llm_response` | LLM 响应，含 tool_calls 信息（每轮编排各一次） |
| `tool_executed` | 工具执行成功，`data: {tool, success: true}` |
| `tool_error` | 工具执行失败，`data: {tool, error}`（error 为通用文案，完整错误仅记日志） |
| `error` | LLM 调用失败，`data: {error}`（通用文案，不泄露内部细节） |
| `complete` | 对话完成，返回最终回复 |

---

## 经验库

### GET /api/v1/experiences

列出所有经验。

**请求**：
```bash
curl "http://localhost:8000/api/v1/experiences?n_results=10"
```

**参数**：

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `n_results` | integer | 否 | 返回数量，默认 50 |

**响应**：
```json
{
  "ok": true,
  "data": [
    "用户喜欢科幻电影，偏好推荐类查询",
    "用户习惯在晚上查询信息"
  ]
}
```

---

### POST /api/v1/experiences

手动添加经验。

**请求**：
```bash
curl -X POST http://localhost:8000/api/v1/experiences \
  -H "Content-Type: application/json" \
  -d '{
    "pattern": "用户喜欢简洁回复",
    "category": "manual"
  }'
```

**参数**：

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `pattern` | string | 是 | 经验内容 |
| `category` | string | 否 | 分类，默认 `manual` |

**响应**：
```json
{
  "ok": true,
  "data": {
    "added": true,
    "pattern": "用户喜欢简洁回复"
  }
}
```

---

### DELETE /api/v1/experiences

清空所有经验。

**请求**：
```bash
curl -X DELETE http://localhost:8000/api/v1/experiences
```

**响应**：
```json
{
  "ok": true,
  "data": {
    "cleared": true
  }
}
```

---

## 用户画像

### GET /api/v1/profile/{user_id}

获取用户画像。

**请求**：
```bash
curl "http://localhost:8000/api/v1/profile/user-123"
```

**参数**：

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `user_id` | string | 是 | 用户标识（路径参数） |

**响应**：
```json
{
  "ok": true,
  "data": {
    "user_id": "user-123",
    "memories": {
      "name": "张三",
      "role": "开发者",
      "偏好": "简洁回复"
    },
    "updated_at": "2024-01-15T08:30:00"
  }
}
```

> `memories` 为扁平的 `key → value` 字符串映射，由 LLM 自动从对话中提取并维护。

---

### PATCH /api/v1/profile/{user_id}

更新用户画像。

**请求**：
```bash
curl -X PATCH "http://localhost:8000/api/v1/profile/user-123" \
  -H "Content-Type: application/json" \
  -d '{
    "memories": {
      "偏好": "简洁回复"
    }
  }'
```

**参数**：

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `user_id` | string | 是 | 用户标识（路径参数） |
| `memories` | object | 否 | 要更新的记忆项（整体替换） |

**响应**：
```json
{
  "ok": true,
  "data": {
    "user_id": "user-123",
    "memories": {
      "name": "张三",
      "偏好": "简洁回复"
    },
    "updated_at": "2024-01-15T08:45:00"
  }
}
```

---

### DELETE /api/v1/profile/{user_id}

删除用户画像（不可恢复）。

**请求**：
```bash
curl -X DELETE "http://localhost:8000/api/v1/profile/user-123"
```

**响应**：
```json
{
  "ok": true,
  "data": {
    "user_id": "user-123",
    "deleted": true
  }
}
```

> 画像按 `user_id` 隔离，删除不影响其他用户或会话消息。

---

## 插件

### GET /api/v1/plugins

列出已加载的插件。

**请求**：
```bash
curl http://localhost:8000/api/v1/plugins
```

**响应**：
```json
{
  "ok": true,
  "data": [
    {
      "name": "weather",
      "version": "1.0.0",
      "description": "天气查询插件",
      "tools": ["get_weather"]
    },
    {
      "name": "rag",
      "version": "1.0.0",
      "description": "外部 RAG 检索插件",
      "tools": ["search_knowledge"]
    }
  ]
}
```

---

## 完整对话示例

```bash
# 1. 创建会话
SESSION=$(curl -s -X POST http://localhost:8000/api/v1/sessions \
  -H "Content-Type: application/json" \
  -d '{"title": "测试会话"}' | jq -r '.data.id')

echo "会话ID: $SESSION"

# 2. 发送消息
curl -X POST "http://localhost:8000/api/v1/sessions/$SESSION/interact" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "搜索 Python 教程",
    "user_id": "user-123"
  }'

# 3. 查看历史消息
curl "http://localhost:8000/api/v1/sessions/$SESSION/messages"

# 4. 删除会话
curl -X DELETE "http://localhost:8000/api/v1/sessions/$SESSION"