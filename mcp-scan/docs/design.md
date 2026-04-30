# MCP Scan Web UI — 前后端设计文档

## 1. 概述

### 1.1 项目背景

`mcp-scan` 是一个基于 Python 的 MCP Server 安全扫描工具，原生以命令行方式调用。本文档描述为其设计的 Web UI，目标是：

- 提供可视化配置界面，替代繁琐的命令行参数
- 实时展示 27 个扫描阶段的执行进度
- 解析扫描日志并渲染最终漏洞报告与安全评分

### 1.2 整体架构

```
┌──────────────────────────────────────────────────────────────┐
│                       用户浏览器                              │
│  HTML + Tailwind CSS + Vanilla JS + EventSource API          │
└───────────────────────────┬──────────────────────────────────┘
                            │  HTTP / SSE
                            ▼
┌──────────────────────────────────────────────────────────────┐
│              FastAPI Web Server (web_server.py)               │
│  端口 7788 · 运行于 conda 环境 AI-Infra-Guard                 │
│                                                              │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────┐  │
│  │  REST API   │  │ SSE 流式推送 │  │  任务状态管理      │  │
│  └─────────────┘  └──────────────┘  └────────────────────┘  │
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │                  LogParser (日志解析器)                  │ │
│  └─────────────────────────────────────────────────────────┘ │
└───────────────────────────┬──────────────────────────────────┘
                            │  subprocess.Popen
                            ▼
┌──────────────────────────────────────────────────────────────┐
│  conda run -n AI-Infra-Guard python main.py ...              │
│  mcp-scan 扫描进程（每个 Task 独立进程）                      │
│                                                              │
│  输出 → ./logs/mcp-scan_YYYY-MM-DD-HH-MM-SS.log             │
└──────────────────────────────────────────────────────────────┘
```

### 1.3 技术选型

| 层 | 技术 | 选型理由 |
|----|------|----------|
| 后端框架 | FastAPI + Uvicorn | 已在 conda 环境中安装 starlette/uvicorn，FastAPI 轻量添加；原生支持 async SSE |
| 前端框架 | 原生 HTML + Tailwind CSS CDN | 无需构建步骤；与现有 AI-Infra-Guard UI 风格一致 |
| Markdown 渲染 | marked.js (CDN) | 轻量级、无依赖，渲染 LLM 生成的报告 |
| 实时推送 | Server-Sent Events (SSE) | 单向日志流推送，比 WebSocket 更简单 |
| 进程管理 | `subprocess.Popen` + `threading.Thread` | 每个扫描任务独立后台进程 |

---

## 2. 目录结构

```
mcp-scan/
├── main.py                        # 原有 CLI 入口（不修改）
├── web_server.py                  # 新增：FastAPI 后端
├── requirements.txt               # 修改：添加 fastapi>=0.110.0
├── tasks.json                     # 运行时自动生成：任务持久化存储
├── web/
│   └── index.html                 # 新增：单页前端
├── logs/
│   └── mcp-scan_YYYY-MM-DD-HH-MM-SS.log   # 扫描进程输出
└── _temp_{task_id}.yaml           # 批量扫描时临时生成，扫描结束后自动删除
```

**启动命令**：
```bash
cd mcp-scan
conda run -n AI-Infra-Guard python web_server.py
# 访问 http://localhost:7788
```

---

## 3. 后端设计

### 3.1 API 接口总览

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/` | 返回 `web/index.html` |
| POST | `/api/tasks` | 创建并启动扫描任务 |
| GET | `/api/tasks` | 获取历史任务列表（按创建时间降序） |
| GET | `/api/tasks/{task_id}` | 获取单个任务详情 |
| DELETE | `/api/tasks/{task_id}` | 终止进程，将任务标记为 failed |
| GET | `/api/tasks/{task_id}/stream` | SSE 实时日志流 |

---

### 3.2 数据模型

#### 3.2.1 请求体 — 创建任务 `POST /api/tasks`

```json
{
  "targets": ["http://192.168.1.10:8080/sse", "http://192.168.1.11:9090/sse"],
  "api_key": "sk-xxxxx",
  "base_url": "https://openrouter.ai/api/v1",
  "model": "deepseek/deepseek-v3.2-exp",
  "prompt": "重点检测路径穿越漏洞。",
  "language": "zh",
  "oauth_client_id": null,
  "oauth_client_secret": null,
  "oauth_token_url": null,
  "oauth_scope": null
}
```

> **安全说明**：`api_key` 仅在进程启动时使用，不写入 `tasks.json`，仅存储最后 4 位用于历史展示。

---

#### 3.2.2 任务对象 `TaskRecord`

```json
{
  "id": "a3f7c2b1",
  "status": "running",
  "created_at": "2026-03-31T10:00:00Z",
  "targets": ["http://192.168.1.10:8080/sse"],
  "config": {
    "api_key_hint": "xxxx",
    "base_url": "https://openrouter.ai/api/v1",
    "model": "deepseek/deepseek-v3.2-exp",
    "prompt": "",
    "language": "zh",
    "has_oauth": false
  },
  "log_file": "/abs/path/mcp-scan/logs/mcp-scan_2026-03-31-10-00-01.log",
  "pid": 12345,
  "stages": [
    { "id": "1",  "name": "Info Collection",          "status": "completed", "output": "# MCP 服务信息收集报告\n..." },
    { "id": "2",  "name": "Tool Poisoning (TPA)",     "status": "running",   "output": "" },
    { "id": "3",  "name": "Full Schema Poisoning",    "status": "pending",   "output": "" },
    "..."
  ],
  "score": null,
  "results": [],
  "readme": null,
  "error": null
}
```

**字段说明**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | UUID4 前 8 位 |
| `status` | enum | `running` / `completed` / `failed` |
| `stages` | array | 27 个阶段，创建时全部初始化为 `pending` |
| `score` | int\|null | 0–100，Stage 27 完成后填充 |
| `results` | array | 漏洞列表，见下方结构 |
| `readme` | string\|null | Stage 1 Info Collection 的 Markdown 报告 |
| `pid` | int\|null | 仅内存保留，不持久化 |

**`results` 单条漏洞结构**：
```json
{
  "title": "路径穿越漏洞",
  "description": "get_filename 工具未对路径参数进行验证...",
  "risk_type": "Path Traversal",
  "level": "high",
  "suggestion": "对 filename 参数实施白名单校验..."
}
```

---

#### 3.2.3 27 个扫描阶段定义

| ID | 名称 | 类别 |
|----|------|------|
| 1 | Info Collection | 信息收集 |
| 2 | Tool Poisoning (TPA) | 恶意行为 |
| 3 | Full Schema Poisoning (FSP) | 恶意行为 |
| 4 | Advanced Tool Poisoning (ATPA) | 恶意行为 |
| 5 | Rug Pull Attack | 恶意行为 |
| 6 | MCP Configuration Poisoning | 恶意行为 |
| 7 | Tool Name Spoofing | 恶意行为 |
| 8 | Tool Shadowing | 恶意行为 |
| 9 | Resource Content Poisoning | 恶意行为 |
| 10 | MCP Preference Manipulation (MPMA) | 恶意行为 |
| 11 | Prompt Injection | 漏洞扫描 |
| 12 | Command Injection | 漏洞扫描 |
| 13 | Remote Code Execution (RCE) | 漏洞扫描 |
| 14 | Unauthenticated Access | 漏洞扫描 |
| 15 | Confused Deputy (OAuth Proxy) | 漏洞扫描 |
| 16 | Token/Credential Theft | 漏洞扫描 |
| 17 | Token Passthrough | 漏洞扫描 |
| 18 | Path Traversal | 漏洞扫描 |
| 19 | Localhost Bypass (NeighborJack) | 漏洞扫描 |
| 20 | Session Management Flaws | 漏洞扫描 |
| 21 | Privilege Abuse | 漏洞扫描 |
| 22 | Cross-Repository Data Theft | 漏洞扫描 |
| 23 | SQL Injection | 漏洞扫描 |
| 24 | Context Bleeding | 漏洞扫描 |
| 25 | Configuration File Exposure | 漏洞扫描 |
| 26 | Cross-Tenant Data Exposure | 漏洞扫描 |
| 27 | Vulnerability Review | 汇总分析 |

---

### 3.3 进程管理

#### 3.3.1 命令构建

**单目标**（1 个 URL）：
```python
cmd = [
    "conda", "run", "-n", "AI-Infra-Guard", "--no-capture-output",
    "python", str(SCRIPT_DIR / "main.py"),
    "--server_url", targets[0],
    "-k", api_key,
    "-u", base_url,
    "-m", model,
    "--language", language,
]
if prompt:
    cmd += ["-p", prompt]
# OAuth（全部三项都提供时才添加）
if oauth_client_id:
    cmd += ["--oauth-client-id", oauth_client_id,
            "--oauth-client-secret", oauth_client_secret,
            "--oauth-token-url", oauth_token_url]
    if oauth_scope:
        cmd += ["--oauth-scope", oauth_scope]
```

**多目标**（≥2 个 URL）：写入临时 YAML 文件，使用 `-c` 批量模式：
```yaml
# _temp_{task_id}.yaml
targets:
  - name: "Target-1"
    url: "http://192.168.1.10:8080/sse"
  - name: "Target-2"
    url: "http://192.168.1.11:9090/sse"
```
```python
cmd += ["-c", str(SCRIPT_DIR / f"_temp_{task_id}.yaml")]
```

#### 3.3.2 进程启动

```python
proc = subprocess.Popen(
    cmd,
    stdout=subprocess.DEVNULL,  # 日志写入文件，不需要 pipe
    stderr=subprocess.DEVNULL,
    cwd=str(SCRIPT_DIR),
    start_new_session=True,     # 独立进程组，kill 时可整组终止
)
```

#### 3.3.3 后台监控线程

每个任务启动一个 `daemon=True` 的后台线程：

```
monitor_task(task_id, proc)
    │
    ├─ detect_log_file()       轮询 logs/ 目录，等待新日志文件出现（最多 10s）
    │   └─ 发现后更新 tasks[task_id]["log_file"]
    │
    ├─ proc.wait()             阻塞等待进程结束
    │
    ├─ 根据 returncode 更新 status
    │   ├─ 0 → "completed"
    │   └─ 其他 → "failed"
    │
    └─ 清理临时 YAML 文件 + persist_tasks()
```

#### 3.3.4 日志文件检测

`utils/loging.py` 在进程启动（import 时）创建日志文件，文件名为 `mcp-scan_{YYYY-MM-DD-HH-MM-SS}.log`，无法在启动前预知（时间戳由子进程决定）。检测策略：

```python
def detect_log_file(launch_time: float, timeout: float = 10.0) -> Path | None:
    """轮询 logs/ 目录，找到 mtime >= launch_time - 1s 的最新日志文件"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        candidates = [
            f for f in LOGS_DIR.glob("mcp-scan_*.log")
            if f.stat().st_mtime >= launch_time - 1.0
        ]
        if candidates:
            return max(candidates, key=lambda f: f.stat().st_mtime)
        time.sleep(0.2)
    return None
```

#### 3.3.5 进程终止

```python
import os, signal

def kill_process(proc: subprocess.Popen):
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)  # 整组 SIGTERM
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)  # 强制 SIGKILL
    except ProcessLookupError:
        pass  # 进程已退出
```

---

### 3.4 日志解析器 (LogParser)

#### 3.4.1 日志格式

```
2026-03-31 10:15:32 | INFO  | === 阶段 2: Tool Poisoning (TPA) ===
2026-03-31 10:15:32 | DEBUG | Stage 2: performing OAuth authentication
2026-03-31 10:16:47 | INFO  | Final Output: # Tool Poisoning 分析报告
                              （续行，无时间戳前缀）
                              ## 发现
                              未检测到工具投毒行为。
2026-03-31 10:16:47 | INFO  | === 阶段 3: Full Schema Poisoning (FSP) ===
...
2026-03-31 11:05:00 | INFO  | Dynamic analysis results:
{'readme': '...', 'score': 35, 'results': [...]}
```

#### 3.4.2 正则表达式

```python
RE_LOG_LINE     = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \| (DEBUG|INFO|WARNING|ERROR|SUCCESS) \| (.*)$')
RE_STAGE_START  = re.compile(r'^=== 阶段 (\d+): (.+) ===$')
RE_FINAL_OUTPUT = re.compile(r'^Final Output: (.*)$')
RE_DYN_RESULTS  = re.compile(r'^Dynamic analysis results:$')
```

#### 3.4.3 解析状态机

```
                 ┌──────────────────────────────────────────┐
                 │              LogParser 状态              │
                 │                                          │
                 │  current_stage_id: str | None            │
                 │  collecting_final_output: bool           │
                 │  final_output_lines: list[str]           │
                 │  awaiting_results_dict: bool             │
                 └──────────────────────────────────────────┘

每行输入 → feed(line) → 返回 list[SSEEvent]

feed(line) 处理流程：
┌─────────────────────────────────────────────────────────────┐
│ 匹配 RE_LOG_LINE？                                          │
│                                                             │
│  是 → 提取 timestamp, level, message                       │
│       │                                                     │
│       ├─ collecting_final_output=True？                     │
│       │   → 调用 _finalize_final_output()                   │
│       │     （保存 output，发送 stage:completed 事件）       │
│       │                                                     │
│       ├─ awaiting_results_dict=True？                       │
│       │   → 调用 _parse_results_dict(message)               │
│       │     （发送 result 事件，重置标志）                   │
│       │                                                     │
│       ├─ 匹配 RE_STAGE_START？                              │
│       │   → 更新 current_stage_id，发送 stage:running 事件  │
│       │                                                     │
│       ├─ 匹配 RE_FINAL_OUTPUT？                             │
│       │   → 设 collecting_final_output=True                 │
│       │     final_output_lines = [首行内容]                  │
│       │                                                     │
│       ├─ 匹配 RE_DYN_RESULTS？                              │
│       │   → 设 awaiting_results_dict=True                   │
│       │                                                     │
│       └─ level in (INFO, ERROR)？                           │
│           → 发送 log 事件                                   │
│                                                             │
│  否（续行，无时间戳）                                        │
│       └─ collecting_final_output=True？                     │
│           → final_output_lines.append(line)                 │
└─────────────────────────────────────────────────────────────┘
```

#### 3.4.4 最终结果解析

`Dynamic analysis results:` 之后的续行是 Python dict 字面量：

```python
def _parse_results_dict(self, line: str, events: list):
    import ast
    try:
        result = ast.literal_eval(line)
        task = tasks[self.task_id]
        task["score"]   = result.get("score")
        task["results"] = result.get("results", [])
        task["readme"]  = result.get("readme", "")
        events.append({"type": "result", "data": {
            "score": task["score"],
            "results": task["results"],
            "readme": task["readme"],
        }})
    except (ValueError, SyntaxError):
        pass  # 解析失败时静默忽略，不影响流程
    finally:
        self.awaiting_results_dict = False
```

---

### 3.5 SSE 实时推送

#### 3.5.1 事件格式

```
event: {type}\ndata: {JSON}\n\n
```

#### 3.5.2 事件类型定义

| 事件名 | 触发时机 | data 结构 |
|--------|----------|-----------|
| `log` | 每条 INFO/ERROR 日志行 | `{"line": "...", "level": "INFO"}` |
| `stage` | 阶段状态变更 | `{"stage_id": "3", "name": "...", "status": "running"}` |
| `result` | Stage 27 完成，解析到最终结果 | `{"score": 35, "results": [...], "readme": "..."}` |
| `done` | 进程退出 | `{"status": "completed"\|"failed"}` |
| Keep-alive | 15 秒无新数据 | `: keep-alive\n\n`（注释行，不触发事件） |

#### 3.5.3 SSE 生成器核心逻辑

```python
async def stream_task_logs(task_id: str):
    # 1. 等待日志文件出现（最多 15s）
    deadline = asyncio.get_event_loop().time() + 15
    while not tasks[task_id].get("log_file"):
        if asyncio.get_event_loop().time() > deadline:
            yield sse_event("error", {"msg": "日志文件未找到，进程可能启动失败"})
            return
        await asyncio.sleep(0.5)

    # 2. 打开日志文件，逐行读取，实时推送
    parser = LogParser(task_id)
    last_yield_time = asyncio.get_event_loop().time()

    with open(tasks[task_id]["log_file"], "r", encoding="utf-8") as f:
        while True:
            line = f.readline()
            if line:
                for event in parser.feed(line.rstrip("\n")):
                    yield sse_event(event["type"], event["data"])
                last_yield_time = asyncio.get_event_loop().time()
            else:
                if tasks[task_id]["status"] != "running":
                    # 进程已结束，drain 剩余状态
                    for event in parser.flush():
                        yield sse_event(event["type"], event["data"])
                    yield sse_event("done", {"status": tasks[task_id]["status"]})
                    return
                # 发送 keep-alive
                if asyncio.get_event_loop().time() - last_yield_time > 15:
                    yield ": keep-alive\n\n"
                    last_yield_time = asyncio.get_event_loop().time()
                await asyncio.sleep(0.3)
```

---

### 3.6 任务持久化

- **内存**：`tasks: dict[str, dict]` 为主要存储，所有读写通过 `threading.Lock` 保护。
- **磁盘**：`tasks.json` 在每次状态变更后写入，`pid` 字段不持久化。
- **重启恢复**：服务启动时加载 `tasks.json`，将 `status=running` 的任务改为 `failed`（进程已不存在）。

---

## 4. 前端设计

### 4.1 整体布局

```
┌─────────────────────────────────────────────────────────────────┐
│  Header: "MCP Security Scanner"  |  A.I.G logo                 │
├───────────────────┬─────────────────────────────────────────────┤
│  左侧栏 (25%)     │  右侧主区域 (75%)                           │
│                   │                                             │
│  [ + 新建扫描 ]   │  ┌── Config 模式 ──────────────────────┐   │
│  ─────────────    │  │  ▼ 扫描目标                         │   │
│  ● 运行中任务     │  │  ▼ OAuth 认证                       │   │
│    10:00 #a3f7   │  │  ▼ 自定义 Prompt                    │   │
│    127.0.0.1:80  │  │  ▼ LLM 配置                         │   │
│  ─────────────    │  │  [ 开始扫描 ]                        │   │
│  ✓ 已完成任务     │  └─────────────────────────────────────┘   │
│    09:30 #b2e1   │                                             │
│  ─────────────    │  ┌── Scan 模式 ──────┬──────────────────┐  │
│  ✕ 失败任务       │  │  阶段进度 (40%)   │  结果面板 (60%)  │  │
│    09:00 #c4d8   │  │  ────────         │  ─────────────    │  │
│                   │  │  ✓ Stage 1       │  Score: 35        │  │
│                   │  │  ⟳ Stage 2       │  ◯ (圆形仪表)    │  │
│                   │  │  ○ Stage 3       │  ─────────────    │  │
│                   │  │  ...             │  漏洞列表         │  │
│                   │  └──────────────────┴──────────────────┘  │
└───────────────────┴─────────────────────────────────────────────┘
```

### 4.2 视觉规范

| 设计 Token | 值 | 用途 |
|-----------|-----|------|
| 主背景 | `#18181b` (zinc-900) | body、侧边栏 |
| 卡片背景 | `#27272a` (zinc-800) | 配置面板、阶段卡片 |
| 边框 | `#3f3f46` (zinc-700) | 分隔线、输入框边框 |
| 主色调 | `#3B82F6` (blue-500) | 按钮、运行状态、选中状态 |
| 主文字 | `#f4f4f5` (zinc-100) | 正文 |
| 次要文字 | `#a1a1aa` (zinc-400) | 说明文字、占位符 |
| 成功 | `#4ade80` (green-400) | 完成状态、高分 |
| 警告 | `#facc15` (yellow-400) | 中等分数 |
| 错误 | `#f87171` (red-400) | 失败状态、低分 |

---

### 4.3 Config 模式

**触发条件**：未选择任务，或点击"+ 新建扫描"按钮。

四个 `<details>` 折叠面板：

#### Panel 1：扫描目标（默认展开）

```
▼ 扫描目标
┌─────────────────────────────────────────────────┐
│  http://192.168.1.10:8080/sse                  │
│  http://192.168.1.11:9090/sse                  │
│                                                 │
└─────────────────────────────────────────────────┘
  每行一个 MCP Server URL，支持多目标批量扫描
```

输入验证：URL 必须以 `http://` 或 `https://` 开头。

#### Panel 2：OAuth 认证（默认折叠）

```
▶ OAuth 认证（可选）
  Client ID      [____________]
  Client Secret  [************]
  Token URL      [____________]
  Scope          [____________]（选填）
```

#### Panel 3：自定义 Prompt（默认折叠）

```
▶ 自定义 Prompt（可选）
┌─────────────────────────────────────────────────┐
│  重点关注路径穿越和未授权访问漏洞。              │
└─────────────────────────────────────────────────┘
```

#### Panel 4：LLM 配置（默认展开）

```
▼ LLM 配置
  API Base URL  [https://openrouter.ai/api/v1    ]
  API Key       [**********************************]
  Model         [deepseek/deepseek-v3.2-exp       ]
  Language      [中文 ▼]
```

**开始扫描按钮**：

```
┌─────────────────────────────────────────────────┐
│                  开始扫描                        │
└─────────────────────────────────────────────────┘
  blue-500 背景，禁用态为 zinc-600
```

---

### 4.4 Scan 模式

**触发条件**：点击"开始扫描"或从历史列表选中一个任务。

#### 4.4.1 阶段进度面板（左，40% 宽）

顶部任务信息栏：
```
● 运行中  127.0.0.1:8080    [中止扫描]
```

27 个阶段卡片列表（可滚动）：

```
┌──────────────────────────────────────────┐
│ ✓  1  Info Collection                   │  ← 完成：green checkmark
├──────────────────────────────────────────┤
│ ⟳  2  Tool Poisoning (TPA)              │  ← 进行中：blue spinner 动画
│    （当前选中，高亮边框）                  │
├──────────────────────────────────────────┤
│ ○  3  Full Schema Poisoning (FSP)       │  ← 待执行：gray dot
├──────────────────────────────────────────┤
│    ...                                   │
└──────────────────────────────────────────┘
```

- 点击任意已完成阶段 → 在右侧面板展示该阶段的 `output`（Markdown 渲染）
- 当前运行中的阶段自动滚动进入视图（`scrollIntoView({behavior:'smooth'})`）

#### 4.4.2 结果面板（右，60% 宽）

**状态一：扫描进行中，未选中阶段**

```
  等待扫描完成...
  [进度条动画]
  已完成 5 / 27 个阶段
```

**状态二：选中某个已完成阶段**

渲染该阶段的 `output` 字段为 Markdown：

```
# Tool Poisoning (TPA) 分析报告

## 检测结果
未发现工具投毒行为。

## 分析过程
...
```

**状态三：Stage 27 完成后（最终报告）**

```
┌───────────────────────────────────────────────┐
│           安全评分                            │
│                                               │
│              35                               │
│         ╭──────╮                             │
│         │  35  │  ← SVG 圆形进度条            │
│         ╰──────╯    红色（0-39）              │
│      风险等级：高                              │
└───────────────────────────────────────────────┘

┌───────────────────────────────────────────────┐
│  漏洞列表                                     │
│  ┌──────────────┬──────────────┬───────────┐  │
│  │ 名称         │ 类型         │ 严重程度  │  │
│  ├──────────────┼──────────────┼───────────┤  │
│  │ 路径穿越漏洞  │ Path Traversal│ ■ 高危   │  │
│  │ [展开▼]      │              │           │  │
│  │   描述：...  │              │           │  │
│  │   建议：...  │              │           │  │
│  ├──────────────┼──────────────┼───────────┤  │
│  │ 未授权访问   │ Unauth Access │ ■ 中危   │  │
│  └──────────────┴──────────────┴───────────┘  │
└───────────────────────────────────────────────┘

┌───────────────────────────────────────────────┐
│  完整报告                                     │
│  [Markdown 渲染的 readme 内容]                │
└───────────────────────────────────────────────┘
```

**安全评分颜色规则**：
- 0–39：红色（red-400），文案"高风险"
- 40–69：黄色（yellow-400），文案"中等风险"
- 70–100：绿色（green-400），文案"低风险"

**SVG 圆形仪表实现**：
```html
<svg viewBox="0 0 36 36" class="w-32 h-32">
  <!-- 背景圆 -->
  <circle cx="18" cy="18" r="15.9" fill="none" stroke="#3f3f46" stroke-width="2.5"/>
  <!-- 得分弧（stroke-dasharray = score, 100-score） -->
  <circle cx="18" cy="18" r="15.9" fill="none"
          stroke="{scoreColor}" stroke-width="2.5"
          stroke-dasharray="{score} {100 - score}"
          stroke-linecap="round"
          transform="rotate(-90 18 18)"/>
  <!-- 中心文字 -->
  <text x="18" y="20.5" text-anchor="middle" font-size="8" fill="{scoreColor}">{score}</text>
</svg>
```

---

### 4.5 前端状态管理

```javascript
const AppState = {
  tasks: [],                 // TaskRecord[]，来自 GET /api/tasks
  selectedTaskId: null,      // string | null，当前查看的任务
  activeEventSource: null,   // EventSource | null，当前 SSE 连接
  selectedStageId: null,     // string | null，当前查看的阶段输出
  configForm: {
    targets: "",             // 多行文本，每行一个 URL
    api_key: "",
    base_url: "https://openrouter.ai/api/v1",
    model: "deepseek/deepseek-v3.2-exp",
    prompt: "",
    language: "zh",
    oauth_client_id: "",
    oauth_client_secret: "",
    oauth_token_url: "",
    oauth_scope: "",
  }
};
```

**状态更新策略**：所有修改通过 `setState(patch)` 函数统一进行，之后调用 `render()` 全量重绘相关组件。

---

### 4.6 SSE 客户端

```javascript
function connectToTask(taskId) {
  if (AppState.activeEventSource) {
    AppState.activeEventSource.close();
  }

  let retries = 0;
  const MAX_RETRIES = 3;

  function connect() {
    const source = new EventSource(`/api/tasks/${taskId}/stream`);
    AppState.activeEventSource = source;

    source.addEventListener("stage", e => {
      const ev = JSON.parse(e.data);
      const task = AppState.tasks.find(t => t.id === taskId);
      if (!task) return;
      const stage = task.stages.find(s => s.id === ev.stage_id);
      if (stage) {
        stage.status = ev.status;
        if (ev.status === "running") {
          AppState.selectedStageId = ev.stage_id;  // 自动切换到当前运行阶段
        }
      }
      render();
      // 自动滚动
      document.getElementById(`stage-${ev.stage_id}`)
        ?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });

    source.addEventListener("result", e => {
      const ev = JSON.parse(e.data);
      const task = AppState.tasks.find(t => t.id === taskId);
      if (task) {
        task.score   = ev.score;
        task.results = ev.results;
        task.readme  = ev.readme;
      }
      render();
    });

    source.addEventListener("done", e => {
      const ev = JSON.parse(e.data);
      const task = AppState.tasks.find(t => t.id === taskId);
      if (task) task.status = ev.status;
      source.close();
      AppState.activeEventSource = null;
      render();
    });

    source.onerror = () => {
      source.close();
      if (retries < MAX_RETRIES) {
        retries++;
        setTimeout(connect, 3000);
      }
    };
  }

  connect();
}
```

---

### 4.7 关键函数一览

| 函数 | 说明 |
|------|------|
| `loadTasks()` | 页面加载时拉取任务列表，自动连接进行中的任务 SSE |
| `startScan()` | 验证表单 → POST /api/tasks → 选中新任务 → 连接 SSE |
| `abortTask(id)` | DELETE /api/tasks/{id} → 刷新任务状态 |
| `connectToTask(id)` | 建立 SSE 连接，监听所有事件类型 |
| `render()` | 全量重绘：侧边栏任务列表 + 主面板（Config 或 Scan 模式） |
| `renderScore(score)` | 生成 SVG 圆形仪表 HTML 字符串 |
| `renderVulnTable(results)` | 生成可展开的漏洞列表表格 |
| `renderMarkdown(text)` | `marked.parse(text)`，降级为 `<pre>` |
| `formatTime(isoStr)` | ISO 时间格式化为 `MM-DD HH:mm` |

---

## 5. 数据流全景

```
用户操作: 点击"开始扫描"
        │
        ▼
[浏览器] POST /api/tasks {targets, api_key, model, ...}
        │
        ▼
[后端] 创建 TaskRecord（27 stages: pending）
       → subprocess.Popen(conda run python main.py ...)
       → threading.Thread(monitor_task)
       → 返回 201 {task object}
        │
        ▼
[浏览器] 选中新任务 → EventSource('/api/tasks/{id}/stream')
        │
        ▼
[后端 SSE 生成器]
  ├─ 等待日志文件出现（monitor_task 检测到后更新 log_file）
  ├─ 打开日志文件，逐行 readline()
  │
  │  [mcp-scan 进程] 执行 27 个阶段，写入日志
  │   每个阶段：连接 → 认证 → LLM 分析 → 输出报告
  │
  ├─ LogParser.feed(line) → SSE events
  │   ├─ stage:running   → [浏览器] 阶段卡片显示 spinner
  │   ├─ log:INFO        → （日志缓冲，可选展示）
  │   ├─ stage:completed → [浏览器] 阶段卡片显示 checkmark
  │   └─ result          → [浏览器] 显示评分 + 漏洞表 + 报告
  │
  └─ done:{status}       → [浏览器] 关闭 SSE，更新任务状态
```

---

## 6. 错误处理

### 6.1 后端

| 场景 | 处理方式 |
|------|----------|
| conda 未找到 / 进程启动失败 | 捕获 `FileNotFoundError`，task.status="failed"，写入 error 消息 |
| 日志文件 10s 内未出现 | task.status="failed"，SSE 推送 error 事件 |
| `ast.literal_eval` 解析失败 | 静默忽略，task.score/results 保持 null，不影响 status |
| SSE 客户端断开 | 捕获 `asyncio.CancelledError`，生成器正常退出 |
| `tasks.json` 写入失败 | 记录 warning，内存状态不受影响 |

### 6.2 前端

| 场景 | 处理方式 |
|------|----------|
| POST /api/tasks 失败 | 顶部展示红色错误横幅，保留表单内容 |
| SSE 连接中断 | 3 秒后自动重连，最多 3 次 |
| marked.js CDN 加载失败 | `typeof marked === 'undefined'` 检测，降级为 `<pre>` 纯文本 |
| 任务结束但 results 为空 | 显示"未发现漏洞"，score 默认展示 100 |
| URL 格式错误 | 提交前内联校验，按钮 disabled + 红色提示文字 |

---

## 7. 安全考量

- **API Key 不持久化**：仅在内存中传递给子进程，`tasks.json` 仅存储后 4 位提示。
- **本地部署**：服务默认绑定 `0.0.0.0:7788`，建议生产环境改为 `127.0.0.1:7788`。
- **临时文件清理**：`_temp_{task_id}.yaml` 在进程结束后由 monitor 线程 finally 块删除。
- **进程隔离**：`start_new_session=True` 防止 Web Server 退出时信号传播到扫描子进程。

---

## 8. 依赖变更

`mcp-scan/requirements.txt` 添加一行：

```
fastapi>=0.110.0
```

现有依赖中已包含兼容版本：
- `starlette==0.50.0`（FastAPI 0.110 要求 ≥ 0.36.0 ✓）
- `uvicorn==0.38.0`（用于启动服务 ✓）
- `pydantic==2.12.4`（FastAPI 请求体验证 ✓）
