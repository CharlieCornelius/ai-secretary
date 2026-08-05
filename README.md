# AI Secretary 🤖

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2+-purple.svg)](https://langchain-ai.github.io/langgraph/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

> 基于 LangGraph 的智能对话引擎，支持三层记忆系统、插件扩展和向量经验库。

AI Secretary 是一个轻量级 AI 秘书后端服务，采用单容器架构（SQLite + Chroma），零外部依赖，适合个人部署和小型团队使用。

---

## ✨ 它能做什么

- **智能对话**：LLM 自主决策调用工具，多步编排完成复杂任务，支持群聊/单人模式
- **三层记忆**：AI 经验（跨用户共享）+ 用户画像（用户级隔离）+ 对话上下文（全量持久化）
- **插件扩展**：自包含插件，通过 `manifest.yaml` 自配置，不改核心代码
- **单容器部署**：SQLite + Chroma，无需外部数据库

---

## 🚀 快速开始

```bash
# 1. 安装
pip install -e .

# 2. 配置
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY

# 3. 启动
python start_server.py
```

访问 `http://localhost:8000/docs` 查看交互式 API 文档。

### Docker

```bash
# 编辑 docker-compose.yml 中的 environment（OPENAI_API_KEY 等）
docker-compose up -d
```

> `.env` 仅用于本地 `python start_server.py`（启动脚本通过 python-dotenv 加载）；Docker 部署的环境变量在 `docker-compose.yml` 的 `environment` 段配置。

---

## 🏗️ 架构

### 对话流程

```
用户消息 → knowledge_inject → llm_call → tool_execute? → post_process
                                              ↓ yes          ↓
                                         回到 llm_call   返回响应
```

1. **knowledge_inject**：组装 system prompt（角色 + 时间 + 画像 + 经验 + 上下文）
2. **llm_call**：调用 LLM，解析 tool_calls
3. **tool_execute**：每个工具独立事务执行，结果加入 conversation_history
4. **循环**：最多 5 次迭代，防止无限循环
5. **post_process**：持久化消息、写审计日志、异步更新长期记忆

### 状态定义

```python
{
    "user_id": "",
    "session_id": "",
    "session_mode": "single",      # 会话模式：single / group
    "user_message": "",
    "system_prompt": "",           # 知识注入结果
    "context_messages": [],        # 历史对话
    "conversation_history": [],    # 本轮编排（assistant/tool 中间产物）
    "llm_response": "",
    "tool_calls": [],              # 待执行工具
    "tool_results": [],            # 当前轮执行结果
    "all_tool_calls": [],          # 跨轮次累积（审计用）
    "all_tool_results": [],
    "final_response": "",
    "events": [],                  # 执行事件列表
    "attachments": [],             # 用户输入附件
    "content_blocks": [],          # AI 输出富内容
    "iteration_count": 0,          # 循环计数（上限 5）
    "error": null,                 # 错误信息（仅日志，不返回客户端）
}
```

---

## 🧠 记忆系统

| 层级 | 存储 | 范围 | 维护方式 |
|------|------|------|----------|
| AI 经验 | Chroma 向量库 | 跨用户共享 | LLM 自动提取抽象模式 |
| 用户画像 | SQLite | 用户级隔离 | LLM 分析对话更新 |
| 对话上下文 | SQLite | 会话级隔离 | 全量持久化，自动 trim |

---

## 🔌 插件

插件自包含在 `plugins/` 目录，通过 `manifest.yaml` 自配置、自注册。

```yaml
name: my_plugin
version: "1.0.0"
tools:
  - name: hello
```

```python
async def hello(db, user_id, session_id, args):
    return f"你好，{args.get('name', '陌生人')}！"
```

→ 详见 [PLUGINS.md](PLUGINS.md)

---

## 📡 API

所有 API 返回统一格式：

```json
{"ok": true, "data": { ... }}
{"ok": false, "error": {"code": "...", "message": "..."}}
```

核心端点：

| 端点 | 说明 |
|------|------|
| `POST /api/v1/sessions` | 创建会话 |
| `POST /api/v1/sessions/{id}/interact` | 对话交互（返回事件追踪列表） |
| `GET /api/v1/sessions/{id}/messages` | 获取消息历史 |
| `GET /api/v1/experiences` | 经验库管理 |
| `GET /api/v1/profile/{user_id}` | 用户画像 |
| `DELETE /api/v1/profile/{user_id}` | 删除用户画像 |
| `GET /api/v1/plugins` | 插件列表 |

→ 详见 [API.md](API.md)

---

## ⚙️ 配置

### 环境变量（`.env`）

```bash
OPENAI_API_KEY=sk-xxx          # 必填
OPENAI_BASE_URL=https://...    # 必填
OPENAI_MODEL=gpt-4o            # 必填
AUTH_API_KEYS=[]               # 可选，[]=无需认证
```

### YAML 配置（`config/`）

| 文件 | 说明 |
|------|------|
| `app.yaml` | 主配置，支持 `${VAR:-default}` 占位符；含 server/database/llm/auth/cors/plugins 等段；未知字段启动报错 |
| `persona.yaml` | 角色设定 |
| `profile.yaml` | 画像模板 |
| `experience.yaml` | 经验库规则 |
| `knowledge.yaml` | 时间格式、prompt 前缀 |

---

## 📁 项目结构

```
ai-secretary/
├── app/                          # 应用代码
│   ├── api/                      # FastAPI 路由
│   │   ├── router.py             # 路由聚合
│   │   └── routes/               # 各模块路由
│   │       ├── chat.py           # 对话交互
│   │       ├── sessions.py       # 会话 CRUD
│   │       ├── experiences.py    # 经验库
│   │       ├── profile.py        # 用户画像
│   │       └── plugins.py        # 插件列表
│   ├── common/                   # 公共模块
│   │   ├── auth.py               # API Key 认证
│   │   ├── background.py         # 后台任务运行器
│   │   ├── config.py             # 配置管理（YAML + 环境变量，严格模式拒绝未知字段）
│   │   ├── database.py           # SQLite 异步连接
│   │   ├── errors.py             # 统一错误定义
│   │   ├── logging.py            # structlog 日志
│   │   ├── schemas.py            # Pydantic 模型
│   │   └── llm.py                # LLM 工厂
│   ├── db/                       # 数据库
│   │   ├── models.py             # SQLAlchemy 模型
│   │   └── migrations.py         # 迁移
│   ├── engine/                   # LangGraph 对话引擎
│   │   ├── graph.py              # 工作流定义
│   │   ├── state.py              # 状态定义
│   │   └── nodes/                # 节点实现
│   │       ├── knowledge_injector.py  # 知识注入
│   │       ├── llm_caller.py     # LLM 调用
│   │       ├── tool_executor.py  # 工具执行
│   │       └── post_processor.py # 后处理
│   ├── memory/                   # 三层记忆
│   │   ├── context.py            # 对话上下文（SQLite）
│   │   ├── experience.py         # 经验库（Chroma）
│   │   ├── knowledge.py          # 知识注入组装
│   │   ├── profile.py            # 用户画像（SQLite）
│   │   └── profile_updater.py    # 画像维护
│   ├── plugins/                  # 插件系统
│   │   └── loader.py             # 插件加载器
│   └── main.py                   # FastAPI 应用入口
├── config/                       # 配置文件
│   ├── app.yaml                  # 主配置
│   ├── persona.yaml              # 角色设定
│   ├── profile.yaml              # 画像配置
│   ├── experience.yaml           # 经验库配置
│   └── knowledge.yaml            # 知识注入配置
├── plugins/                      # 外部插件目录
│   ├── weather/                  # 天气查询插件
│   │   ├── manifest.yaml
│   │   ├── main.py
│   │   └── config.yaml
│   ├── rag/                      # RAG 检索插件
│   │   ├── manifest.yaml
│   │   ├── main.py
│   │   └── config.yaml
│   └── profile_query/            # 画像查询插件
│       ├── manifest.yaml
│       └── main.py
├── tests/                        # 测试（126 个）
├── .env.example                  # 环境变量模板
├── .gitignore
├── .dockerignore                 # Docker 构建忽略
├── docker-compose.yml            # Docker Compose
├── Dockerfile                    # 多阶段构建
├── pyproject.toml                # 依赖和项目配置
├── start_server.py               # 启动脚本
├── API.md                        # API 文档
├── PLUGINS.md                    # 插件开发指南
└── README.md                     # 本文档
```

---

## 🧰 技术栈

FastAPI · LangGraph · LangChain · OpenAI API · Chroma · SQLite · SQLAlchemy 2.0 · Pydantic 2 · structlog

---

## 📚 文档

| 文档 | 内容 |
|------|------|
| [API.md](API.md) | 完整 API 参考，含请求/响应示例 |
| [PLUGINS.md](PLUGINS.md) | 插件开发指南，含 manifest 规范和最佳实践 |
| README.md | 项目概览（本文档） |

---

## 📄 License

MIT