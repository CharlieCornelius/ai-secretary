# AI Secretary 插件开发指南 🔌

> 插件是 AI Secretary 的功能扩展单元。自包含在 `plugins/` 目录中，通过 `manifest.yaml` 自配置、自注册，不改核心代码即可扩展功能。

---

## 目录

- [快速开始](#快速开始)
- [插件结构](#插件结构)
- [manifest.yaml](#manifestyaml)
- [工具函数](#工具函数)
- [状态检测](#状态检测)
- [插件配置](#插件配置)
- [完整示例](#完整示例)
- [内置插件](#内置插件)
- [常见问题](#常见问题)

---

## 快速开始

创建一个最小插件只需 2 个文件：

```bash
mkdir plugins/my_plugin

# 1. 插件配置
cat > plugins/my_plugin/manifest.yaml << 'EOF'
name: my_plugin
version: "1.0.0"
description: "我的第一个插件"
tools:
  - name: hello
    description: 向用户打招呼
    parameters:
      type: object
      properties:
        name:
          type: string
          description: 用户名
      required: [name]
EOF

# 2. 工具实现
cat > plugins/my_plugin/main.py << 'EOF'
async def hello(db, user_id, session_id, args):
    name = args.get("name", "陌生人")
    return f"你好，{name}！"
EOF
```

重启服务，插件自动加载。

---

## 插件结构

```
plugins/
└── {plugin_name}/          # 插件目录名
    ├── manifest.yaml       # 插件配置（必需）
    ├── main.py             # 工具实现（必需）
    └── config.yaml         # 插件私有配置（可选）
```

### 命名规范

| 项目 | 规范 |
|------|------|
| 目录名 | 小写 + 下划线，如 `weather` |
| 工具名 | 小写 + 下划线，如 `get_weather` |
| manifest 键名 | 和函数名严格一致 |

---

## manifest.yaml

插件的声明文件，控制注册信息。

### 完整字段

```yaml
name: weather                        # 插件名（显示用）
version: "1.0.0"                    # 版本
description: "天气查询插件"          # 描述
enabled: true                       # 启用开关（可选，默认 true）

tools:
  - name: get_weather               # 工具名（必须和函数名一致）
    description: "查询指定城市的天气信息"
    parameters:                     # OpenAI function calling 格式
      type: object
      properties:
        city:
          type: string
          description: "城市名，如 北京、Shanghai"
      required: ["city"]
```

### 字段说明

| 字段 | 必需 | 说明 |
|------|------|------|
| `name` | ✅ | 插件显示名称 |
| `version` | ✅ | 语义化版本 |
| `description` | ✅ | 插件功能描述 |
| `enabled` | ❌ | `false` 时跳过加载 |
| `tools` | ✅ | 工具列表 |
| `tools[].name` | ✅ | 工具名，必须和 `main.py` 中的函数名一致 |
| `tools[].description` | ✅ | LLM 决定是否调用此工具的依据 |
| `tools[].parameters` | ✅ | OpenAI function calling 格式的参数定义 |

---

## 工具函数

`main.py` 中定义的工具函数是插件的核心。

### 函数签名

```python
async def tool_name(
    db: Any,           # SQLAlchemy AsyncSession，用于数据库操作
    user_id: str,      # 当前用户 ID
    session_id: str,   # 当前会话 ID
    args: dict,        # LLM 传入的参数（由 manifest.parameters 定义）
) -> str:
    """工具实现"""
    # ...
    return "结果字符串"
```

### 参数说明

| 参数 | 类型 | 说明 |
|------|------|------|
| `db` | `AsyncSession` | 数据库会话。可用于查询/写入 SQLite |
| `user_id` | `str` | 当前用户标识 |
| `session_id` | `str` | 当前会话标识 |
| `args` | `dict` | LLM 根据 `parameters` 生成的参数 |

### 返回值

工具函数可返回 **`str`** 或 **`dict`**：

- **`str`**：纯文本结果，直接作为 tool result 送回 LLM。
- **`dict`**：结构化结果，支持富内容。格式如下：

```python
return {
    "text": "搜索结果摘要...",     # 必需：送回 LLM 的文本（与返回 str 等效）
    "content_blocks": [           # 可选：富内容块，随响应返回给前端
        {"type": "image", "data": {"file": "https://example.com/chart.png"}},
        {"type": "file", "data": {"file": "https://example.com/report.pdf", "filename": "报告.pdf"}},
    ]
}
```

| 字段 | 必需 | 说明 |
|------|------|------|
| `text` | ✅ | 送回 LLM 的文本内容 |
| `content_blocks` | ❌ | 富内容块列表，随 API 响应返回给前端展示 |

**`content_blocks` 类型**：

| type | data 字段 | 说明 |
|------|----------|------|
| `image` | `{"file": "url"}` | 图片 |
| `file` | `{"file": "url", "filename": "名"}` | 文件下载 |

---

### 附件处理

当用户发送附件时，系统会自动在 system prompt 中注入附件信息。LLM 根据 `description` 自行判断是否调用工具处理。

**三种场景**：

| 场景 | 行为 |
|------|------|
| 无附件 | 纯文本对话 |
| 有附件，有对应工具 | LLM 根据 `description` 自行调用工具 |
| 有附件，无对应工具 | LLM 告知用户无法处理 |

附件提示文字由 `config/knowledge.yaml` 的 `prompt_prefixes` 配置，可自定义：

```yaml
prompt_prefixes:
  attachment_header: "用户发送了以下附件："
  attachment_with_tools: "如果有可用工具处理附件请使用。"
  attachment_no_tools: "你无法查看或理解此类型的附件，请告知用户。"
```

**插件如何支持附件**：只需在 `description` 中说明该工具能处理什么类型的附件，LLM 会自动路由。例如：

```yaml
tools:
  - name: analyze_image
    description: "分析图片内容。当用户发送图片附件时使用此工具。"
```

### 最佳实践

1. **参数校验**：提供默认值，处理缺失参数
   ```python
   city = args.get("city", "")
   if not city:
       return "请提供城市名"
   ```

2. **超时控制**：网络请求设置合理超时
   ```python
   async with httpx2.AsyncClient(timeout=10) as client:
       ...
   ```

3. **错误处理**：捕获异常并返回友好错误信息
   ```python
   try:
       result = await fetch_data()
   except Exception as e:
       return f"请求失败：{str(e)}"
   ```

4. **日志记录**：使用 `app.common.logging.get_logger`
   ```python
   from app.common.logging import get_logger
   logger = get_logger("my_plugin")
   logger.info("执行查询", city=city)
   ```

---

## 状态检测

工具执行前可选进行状态检测，用于前置检查（如服务可用性）。

### 实现方式

在 `main.py` 中定义 `check_status` 函数：

```python
def check_status():
    """同步状态检测"""
    # 返回 None 表示正常
    # 返回字符串表示异常，直接返回给 LLM
    return None

# 或
async def check_status():
    """异步状态检测"""
    try:
        await ping_service()
        return None
    except Exception:
        return "服务暂时不可用"
```

### 执行逻辑

```
调用工具前 → 执行 check_status() → 
  返回 None    → 正常执行工具
  返回字符串  → 跳过工具，直接将字符串作为 tool result 返回给 LLM
  抛出异常    → 视为状态异常，跳过工具执行并返回错误提示（不会放行）
```

典型用途：
- 检查第三方 API 是否可用
- 检查必要配置是否已设置
- 检查网络连通性

---

## 插件配置

插件可以有私有配置文件，与核心配置隔离。配置文件统一使用 YAML 格式。

### 配置方式

```python
from pathlib import Path
import yaml

def _load_config():
    config_path = Path(__file__).parent / "config.yaml"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}

_CONFIG = _load_config()
```

### 使用配置

```python
async def get_weather(db, user_id, session_id, args):
    weather_cfg = _CONFIG.get("weather", {})
    timeout = weather_cfg.get("timeout", 10)
    url_template = weather_cfg.get(
        "url_template",
        "https://wttr.in/{city}?format=%C|%t|%h|%w|%p&lang=zh",
    )
    # ...
```

### 配置文件示例（config.yaml）

```yaml
weather:
  url_template: "https://wttr.in/{city}?format=%C|%t|%h|%w|%p&lang=zh"
  timeout: 10
```

---

## 完整示例

### weather 插件

```yaml
# manifest.yaml
name: weather
version: "1.0.0"
description: "天气查询插件：查询指定城市的天气信息"
tools:
  - name: get_weather
    description: "查询指定城市的天气信息。当用户询问天气时使用此工具。"
    parameters:
      type: object
      properties:
        city:
          type: string
          description: "城市名，如 北京、Shanghai、Tokyo"
      required: ["city"]
```

```python
# main.py
from __future__ import annotations
from pathlib import Path
from typing import Any
import httpx2
import yaml
from app.common.logging import get_logger

logger = get_logger("weather_plugin")

def _load_config():
    config_path = Path(__file__).parent / "config.yaml"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}

_CONFIG = _load_config()

async def get_weather(db, user_id, session_id, args):
    city = args.get("city", "")
    if not city:
        return "请提供城市名"
    # 实现天气查询逻辑...
    return f"{city} 天气：..."
```

---

## 内置插件

| 插件 | 工具 | 说明 |
|------|------|------|
| `weather` | `get_weather` | 天气查询（wttr.in） |
| `rag` | `search_knowledge` | 外部知识库检索 |
| `profile_query` | `query_profile` | 查询用户画像（支持按 `user_id` 或画像中的 `name` 字段查询） |

### weather 配置（config.yaml）

```yaml
weather:
  url_template: "https://wttr.in/{city}?format=%C|%t|%h|%w|%p&lang=zh"
  timeout: 10
```

---

## 常见问题

### Q: 插件不加载怎么办？

1. 检查 `manifest.yaml` 是否存在
2. 检查 `enabled` 不为 `false`
3. 检查工具名和函数名是否一致
4. 查看启动日志中的插件加载信息

### Q: 如何调试插件？

```python
from app.common.logging import get_logger
logger = get_logger("my_plugin")

async def my_tool(db, user_id, session_id, args):
    logger.info("工具被调用", args=args)
    # ...
```

日志输出为 JSON 格式，可用 `jq` 过滤。

### Q: 插件可以使用哪些依赖？

- 核心依赖：FastAPI、SQLAlchemy、httpx2 等（已在 pyproject.toml）
- 如需额外依赖：当前需安装到全局环境（后续版本支持插件独立依赖）

### Q: 工具函数必须是异步的吗？

是的，必须是 `async def`。插件加载器通过 `await executor(...)` 调用。

### Q: 一个插件可以有多个工具吗？

可以。在 `manifest.yaml` 的 `tools` 列表中注册多个，在 `main.py` 中定义同名函数。

---

## 技术细节

### 加载机制

1. 服务启动时扫描 `plugins/` 目录
2. 读取每个子目录的 `manifest.yaml`
3. 动态导入 `main.py`
4. 通过 `getattr(module, tool_name)` 获取函数
5. 注册到全局工具注册表

### 执行流程

```
用户消息 → LLM 决策 → 生成 tool_calls
                ↓
          插件系统查找工具
                ↓
          check_status()（可选）
                ↓
          执行工具函数
                ↓
          结果送回 LLM → 继续对话或返回
```

每个工具在独立的数据库事务中执行。