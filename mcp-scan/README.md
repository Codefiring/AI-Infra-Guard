# MCP-Scan

一个基于 AI Agent 的自动化代码扫描和漏洞检测工具，模仿 Claude Code / Gemini CLI 的工作方式。

## ✨ 特性

- **🤖 智能 Agent 系统**: 多阶段自动化扫描流程（信息收集 → 代码审计 → 漏洞整理）
- **🔍 深度代码分析**: 自动识别项目结构、技术栈和潜在安全漏洞
- **🎯 专用模型配置**: 支持为不同任务配置专用 LLM（思考、编码、快速响应等）
- **📊 安全评分系统**: 自动计算项目安全评分和风险等级
- **🛠️ 可扩展工具系统**: 轻松添加自定义工具和功能
- **📝 详细日志记录**: 使用 loguru 记录完整的执行过程
- **🐛 Debug 模式**: 集成 Laminar 追踪功能，方便调试
- **🕵️ Agent Skill 审计**: 自动识别并审计 Agent Skill 项目的一致性（SKILL.md vs 代码实现）
- **🔐 MCP TOP 25 覆盖**: 支持 Adversa AI MCP Security TOP 25 漏洞检测（**完整覆盖率：100% - 25/25**）
- **🔑 OAuth 2.0 支持**: 支持 Client Credentials 流程对受保护的 MCP Server 进行认证扫描
- **🔄 每阶段连接生命周期**: 每个扫描阶段独立建立/断开 MCP 连接，保证 Token 时效性

## 🚀 快速开始

### 1. 克隆项目

```bash
git clone <your-repo>
cd mcp-scan
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置环境变量

复制环境变量模板：

```bash
cp env.example .env
```

编辑 `.env` 文件，至少设置以下必需的环境变量：

```bash
# 必需：OpenRouter API Key
OPENROUTER_API_KEY=your-api-key-here

# 可选：自定义默认模型和 URL
DEFAULT_MODEL=deepseek/deepseek-v3.2-exp
DEFAULT_BASE_URL=https://openrouter.ai/api/v1
```

> **注意**: `.env` 文件会在程序启动时自动加载，无需手动 `source`。如果你使用系统环境变量，也会被自动识别。

### 4. 运行扫描

扫描指定项目：

```bash
python main.py --repo /path/to/your/project
```

使用自定义提示词：

```bash
python main.py --repo /path/to/your/project --prompt "重点检查 SQL 注入漏洞"
```

## 📖 使用方法

### 基本命令

```bash
python main.py --repo <项目路径> [选项]
```

### 命令行参数

| 参数 | 简写 | 说明 | 默认值 |
|------|------|------|--------|
| `--repo` | - | **必需**。要扫描的项目路径 | - |
| `--prompt` | `-p` | 自定义扫描提示词 | "" |
| `--model` | `-m` | LLM 模型名称 | `deepseek/deepseek-v3.2-exp` |
| `--api_key` | `-k` | API Key | 从 `OPENROUTER_API_KEY` 读取 |
| `--base_url` | `-u` | API 基础 URL | `https://openrouter.ai/api/v1` |
| `--debug` | - | 启用 debug 模式（包括 Laminar 跟踪） | `False` |
| `--server_url` | - | 远程 MCP server URL (启用动态分析模式) | `None` |
| `--header` | - | 自定义 HTTP header (key:value)，可多次使用 | `[]` |
| `--language` | - | 输出语言 (zh/en) | `zh` |
| `--oauth-client-id` | - | OAuth 2.0 Client ID（Client Credentials 流程） | `None` |
| `--oauth-client-secret` | - | OAuth 2.0 Client Secret | `None` |
| `--oauth-token-url` | - | OAuth 2.0 Token 端点 URL | `None` |
| `--oauth-scope` | - | OAuth 2.0 Scope（可选，空格分隔） | `None` |

### 使用示例

```bash
# 基础扫描
python main.py --repo ./myproject

# 使用特定模型
python main.py --repo ./myproject -m "anthropic/claude-3.5-sonnet"

# 使用自定义 API Key
python main.py --repo ./myproject -k "sk-or-v1-xxxxx"

# 启用 debug 模式
python main.py --repo ./myproject --debug

# 组合使用
python main.py --repo ./myproject \
  -m "google/gemini-2.5-pro" \
  -p "重点检查认证和授权相关的安全问题" \
  --debug

# 动态分析 (针对运行中的 MCP Server)
python main.py \
  --server_url "http://localhost:8000/sse" \
  --prompt "测试工具投毒漏洞"

# 动态分析 + OAuth 认证
python main.py \
  --server_url "http://localhost:8090/sse" \
  --oauth-client-id "my-client" \
  --oauth-client-secret "my-secret" \
  --oauth-token-url "https://auth.example.com/oauth/token" \
  --oauth-scope "mcp:read"
```

## ⚙️ 配置说明

### 环境变量配置

所有配置都可以通过环境变量设置。创建 `.env` 文件或在系统中设置环境变量：

#### 主要 LLM 配置

```bash
# OpenRouter API Key（必需）
OPENROUTER_API_KEY=your-api-key-here

# 默认模型
DEFAULT_MODEL=deepseek/deepseek-v3.2-exp

# API 基础 URL
DEFAULT_BASE_URL=https://openrouter.ai/api/v1
```

#### 专用 LLM 配置

为不同任务配置专用模型，每个模型可以有独立的 API Key 和 Base URL：

```bash
# Thinking 模型（用于深度推理）
THINKING_MODEL=google/gemini-2.5-pro
THINKING_BASE_URL=https://openrouter.ai/api/v1
THINKING_API_KEY=  # 可选，不设置则使用主 API Key

# Coding 模型（用于代码生成和分析）
CODING_MODEL=anthropic/claude-sonnet-4.5
CODING_BASE_URL=https://openrouter.ai/api/v1
CODING_API_KEY=  # 可选，不设置则使用主 API Key
```

#### Debug 和日志配置

```bash
# Laminar API Key（用于 debug 模式的追踪）
LAMINAR_API_KEY=your-laminar-api-key

# 日志级别
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR
```

### 配置优先级

配置的优先级从高到低：

1. 命令行参数（如 `-m`, `-k`, `-u`）
2. 环境变量
3. 代码中的默认值

## 📁 项目结构

```
mcp-scan/
├── agent/                  # Agent 核心实现
│   ├── agent.py           # 主 Agent（多阶段扫描流程）
│   └── base_agent.py      # 基础 Agent 类
├── tools/                  # 工具模块
│   ├── registry.py        # 工具注册系统
│   ├── thinking/          # 思考工具
│   ├── finish/            # 完成工具
│   ├── file/              # 文件操作工具
│   └── execute/           # 代码执行工具
├── utils/                  # 工具函数
│   ├── config.py          # 配置管理
│   ├── llm.py             # LLM 基础封装
│   ├── llm_manager.py     # LLM 管理器（多模型支持）
│   ├── loging.py          # 日志配置
│   ├── mcp_oauth.py       # OAuth 2.0 Client Credentials 支持
│   ├── mcp_tools.py       # MCP 客户端封装
│   ├── parse.py           # XML 解析
│   ├── project_analyzer.py # 项目分析工具
│   ├── extract_vuln.py    # 漏洞提取工具
│   ├── tool_context.py    # 工具上下文
│   └── aig_logger.py      # 结构化日志记录
├── prompt/                 # 提示词模板
│   ├── system_prompt.md   # 系统提示词
│   ├── agents/            # 各阶段 Agent 提示词
│       ├── project_summary.md # 信息收集（含 Skill 识别）
│       ├── code_audit.md      # 代码审计（含 Skill 一致性审计）
│       └── vuln_review.md     # 漏洞整理
├── main.py                 # 主入口
├── requirements.txt        # 依赖列表
├── env.example            # 环境变量模板
└── README.md              # 本文档
```

## 🔧 工作原理

### 扫描流程

MCP-Scan 采用多阶段自动化流程：

```
1. 信息收集 (Information Collection)
   ├── 分析项目结构
   ├── 识别技术栈
   └── 识别项目类型 (普通项目 / Agent Skill)

2. 代码审计 (Code Audit)
   ├── 深度代码分析
   ├── 识别安全问题
   └── 若为 Agent Skill，执行一致性审计 (Intent Alignment Check)

3. 漏洞整理 (Vulnerability Review)
   ├── 整理发现的漏洞
   ├── 评估风险等级
   └── 生成详细报告
```

### Agent Skill 审计
如果项目根目录下存在 `SKILL.md`，工具会自动触发 **Agent Skill 一致性审计**：
- **功能意图一致性**：对比 `SKILL.md` 的描述与 `scripts/` 下的代码实现。
- **隐形行为检测**：检查代码中是否存在未在描述中提及的隐藏功能。
- **输出格式验证**：验证代码输出是否符合描述的预期格式。

### MCP Security TOP 25 漏洞检测

基于 [Adversa AI MCP Security TOP 25](https://adversa.ai/mcp-security-top-25-mcp-vulnerabilities/) 标准，**完整覆盖所有 25 个漏洞 (100%)**：

**Critical 级别 (5/5 = 100%)**
1. ✅ Prompt Injection - 提示词注入
2. ✅ Command Injection - 命令注入
3. ✅ Tool Poisoning (TPA) - 工具投毒
4. ✅ Remote Code Execution (RCE) - 远程代码执行
5. ✅ Unauthenticated Access - 未授权访问

**High 级别 (10/10 = 100%)**
6. ✅ Confused Deputy (OAuth Proxy) - OAuth 代理混淆
7. ✅ MCP Configuration Poisoning - MCP 配置投毒
8. ✅ Token/Credential Theft - 令牌/凭证窃取
9. ✅ Token Passthrough - 令牌透传
10. ✅ Path Traversal - 路径遍历
11. ✅ Full Schema Poisoning (FSP) - 完整模式投毒
12. ✅ Tool Name Spoofing - 工具名称欺骗
13. ✅ Localhost Bypass (NeighborJack) - 本地主机绕过
14. ✅ Rug Pull Attack - 地毯式拉取攻击
15. ✅ Advanced Tool Poisoning (ATPA) - 高级工具投毒

**Medium 级别 (10/10 = 100%)**
16. ✅ Session Management Flaws - 会话管理缺陷
17. ✅ Tool Shadowing - 工具遮蔽
18. ✅ Resource Content Poisoning - 资源内容投毒
19. ✅ Privilege Abuse/Overbroad Permissions - 权限滥用/过度授权
20. ✅ Cross-Repository Data Theft - 跨仓库数据窃取
21. ✅ SQL Injection - SQL 注入
22. ✅ Context Bleeding - 上下文泄漏
23. ✅ Configuration File Exposure - 配置文件暴露
24. ✅ MCP Preference Manipulation Attack (MPMA) - MCP 偏好操纵攻击
25. ✅ Cross-Tenant Data Exposure - 跨租户数据暴露

**分类统计**：
- 恶意行为类 (malicious_behaviour_testing.md): 9 个漏洞
- 传统漏洞类 (vulnerability_testing.md): 16 个漏洞

详细信息请参考：[MCP_TOP25_Integration_Summary.md](./MCP_TOP25_Integration_Summary.md)

## 🔑 OAuth 2.0 认证

对于需要 OAuth 认证的 MCP Server，mcp-scan 支持 **Client Credentials** 流程自动获取和刷新 Bearer Token。

### 工作原理

每个扫描阶段的连接生命周期为：

```
OAuth 获取 Token → 连接 MCP Server（携带 Bearer Token）→ 执行扫描 → 断开连接
```

Token 会被缓存并在过期前自动刷新（默认预留 30 秒缓冲），整个扫描过程无需人工干预。

### 使用示例

```bash
python main.py \
  --server_url "http://localhost:8090/sse" \
  --oauth-client-id "my-client" \
  --oauth-client-secret "my-secret" \
  --oauth-token-url "https://auth.example.com/oauth/token" \
  --oauth-scope "mcp:read"
```

### 本地测试

项目提供了一个 Flask mock OAuth Server，方便本地调试：

```bash
# 启动 mock OAuth Server（监听 http://127.0.0.1:8000）
python ../OAuth/OAuth-server.py
```

内置测试凭证：

| Client ID | Client Secret | Scope |
|-----------|--------------|-------|
| `test-client` | `test-secret` | `mcp:read` |
| `your-client-id` | `your-client-secret` | `mcp:read mcp:write` |

Mock Server 端点：

| 端点 | 说明 |
|------|------|
| `POST /oauth/token` | 颁发 Bearer Token |
| `POST /oauth/introspect` | 验证 Token 有效性 |
| `GET /protected-resource` | 测试 Bearer Token 保护资源 |

### 为 MCP Server 添加 OAuth 验证

参考 `testcase/case1/main1.py`，只需添加 `OAuthBearerMiddleware` 即可为任意 Starlette MCP Server 启用 Bearer Token 验证：

```python
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import httpx

OAUTH_INTROSPECT_URL = "http://127.0.0.1:8000/oauth/introspect"

class OAuthBearerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return JSONResponse({"error": "missing_bearer_token"}, status_code=401)
        token = auth.removeprefix("Bearer ").strip()
        async with httpx.AsyncClient() as client:
            resp = await client.post(OAUTH_INTROSPECT_URL, data={"token": token},
                                     headers={"Content-Type": "application/x-www-form-urlencoded"})
        if not resp.json().get("active"):
            return JSONResponse({"error": "invalid_or_expired_token"}, status_code=401)
        return await call_next(request)

app.add_middleware(OAuthBearerMiddleware)
```

## 🤝 开发指南

### 运行测试

```bash
# 测试 LLM 连接
python utils/llm.py

# 测试 LLM Manager
python utils/llm_manager.py
```

### 日志查看

日志文件位于项目根目录，文件名格式为 `agent_YYYYMMDD_HHMMSS.log`。

## 📄 License

MIT License

## 🙏 致谢

本项目灵感来源于 Claude Code 和 Gemini CLI。

---

**注意**: 本工具仅用于合法的安全测试和代码审计。请勿用于未授权的系统测试。
