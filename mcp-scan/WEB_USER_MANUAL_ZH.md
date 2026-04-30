# mcp-scan 检测网站使用手册（基于 `web_server.py`）

> 适用对象：使用 `mcp-scan/web_server.py` 启动本地检测网站的安全测试人员与开发人员。  
> 默认访问地址：`http://localhost:7788`

## 1. 系统概览

`web_server.py` 是一个基于 FastAPI 的后端服务，主要职责包括：

- 提供前端页面（`web/index.html`）。
- 提供任务管理 API（创建、查询、终止、删除记录）。
- 以子进程方式调用 `main.py` 发起扫描。
- 通过 SSE（Server-Sent Events）实时推送阶段进度和最终结果。
- 使用 SQLite（`mcp_scan.db`）持久化任务、配置和 LLM 配置。

## 2. 启动与访问

在项目根目录执行（按源码注释中的方式）：

```bash
cd mcp-scan
conda run -n AI-Infra-Guard python web_server.py
```

启动成功后访问：

- 首页：`http://localhost:7788/`
- OpenAPI 文档：`http://localhost:7788/docs`

## 3. 页面使用流程（推荐）

1. **先配置 LLM Profile**（模型地址、模型名、API Key）。
2. **填写扫描目标 URL**（必须以 `http://` 或 `https://` 开头）。
3. **选择检测阶段**（默认全选 15 个可选阶段）。
4. （可选）填写 Prompt 与 OAuth 参数。
5. **创建并启动任务**。
6. 通过实时进度流查看各阶段状态；结束后查看风险评分与漏洞结果。

## 3.1 网页截图（界面参考）

> 说明：以下截图用于帮助快速识别关键页面区域，具体字段与按钮名称请以你当前版本页面为准。

### 主页/扫描入口

![扫描页面示意图](../img/scan-zh.png)

### 插件与能力面板（示意）

![插件页面示意图](../img/plugin-zh.gif)

### 结果查看与输出（示意）

![结果输出示意图](../img/output.gif)

## 4. 核心数据对象说明

## 4.1 任务输入（TaskIn）

创建任务时主要字段：

- `llm_profile_id`：必填，绑定 LLM 配置。
- `url`：必填，目标地址（必须是 `http/https`）。
- `name`：任务名（可选）。
- `stage_ids`：阶段 ID 列表（可选；为空表示默认全部阶段）。
- `prompt`：额外提示词（可选）。
- `language`：语言，默认 `en`。
- OAuth 四项（均可选）：
  - `oauth_client_id`
  - `oauth_client_secret`
  - `oauth_token_url`
  - `oauth_scope`

> 只有在同时提供 `client_id + client_secret + token_url` 时，任务才会被标记为 `has_oauth = true`。

## 4.2 阶段机制

系统固定在任务前后插入两个阶段：

- `1`：Info Collection
- `27`：Vulnerability Review

中间可选阶段共 15 项（默认全选）：

- 2 Tool Poisoning (TPA)
- 3 Full Schema Poisoning (FSP)
- 4 Advanced Tool Poisoning (ATPA)
- 5 Rug Pull
- 7 Tool Name Spoofing
- 8 Tool Shadowing
- 9 Resource Content Poisoning
- 11 Prompt Injection
- 12 Command Injection
- 13 Remote Code Execution (RCE)
- 14 Unauthenticated Access
- 16 Token/Credential Theft
- 18 Path Traversal
- 21 Privilege Abuse
- 23 SQL Injection

## 5. API 使用手册

以下为常用接口（完整字段可通过 `/docs` 查看）。

### 5.1 LLM 配置管理

- `GET /api/llm-profiles`：列表（返回时 `api_key` 会打码）。
- `POST /api/llm-profiles`：创建（`api_key` 创建时必填）。
- `PUT /api/llm-profiles/{profile_id}`：更新（`api_key` 可选，不传则保持不变）。
- `DELETE /api/llm-profiles/{profile_id}`：删除（若被运行中任务引用会返回 409）。

创建示例：

```bash
curl -X POST http://localhost:7788/api/llm-profiles \
  -H 'Content-Type: application/json' \
  -d '{
    "name":"local-openai",
    "base_url":"https://api.openai.com/v1",
    "api_key":"sk-***",
    "model":"gpt-4o-mini",
    "is_default":true
  }'
```

### 5.2 保存配置管理

- `GET /api/configs`：获取保存的配置。
- `POST /api/configs`：保存配置模板。
- `DELETE /api/configs/{config_id}`：删除配置模板。

### 5.3 扫描任务管理

- `GET /api/tasks`：任务列表。
- `GET /api/tasks/{task_id}`：任务详情。
- `POST /api/tasks`：创建并启动任务。
- `DELETE /api/tasks/{task_id}`：中止任务（会将任务标记失败并写入“Aborted by user”）。
- `DELETE /api/tasks/{task_id}/record`：删除任务记录（必要时也会先杀进程）。

创建任务示例：

```bash
curl -X POST http://localhost:7788/api/tasks \
  -H 'Content-Type: application/json' \
  -d '{
    "llm_profile_id":"abcd1234",
    "url":"http://127.0.0.1:3000",
    "name":"demo-scan",
    "stage_ids":[2,3,11,12,13],
    "prompt":"请重点关注命令执行链路",
    "language":"zh"
  }'
```

### 5.4 实时进度流（SSE）

- `GET /api/tasks/{task_id}/stream`

事件类型：

- `init`：连接建立时发送当前任务快照（支持断线重连后补状态）。
- `stage`：单阶段状态变化。
- `result`：出现总评分与漏洞结果时发送。
- `done`：任务结束（成功/失败/删除）。
- 注释心跳：每 15 秒 `: keep-alive`。

前端或脚本可用 `EventSource` 订阅该接口实现实时进度条。

## 6. 扫描执行原理

创建任务后，后端会组装命令并启动子进程：

```bash
conda run -n AI-Infra-Guard --no-capture-output python main.py ...
```

关键点：

- 扫描进程标准输出/错误被重定向到 `DEVNULL`（网页进度不依赖日志）。
- 实时状态通过轮询 SQLite 数据库并对比阶段变化后推送 SSE。
- 如果子进程异常退出且任务仍是 running，会自动补写 failed 状态。

## 7. 常见问题（FAQ）

### Q1：为什么创建任务报 URL 错误？
`url` 字段有严格校验，必须以 `http://` 或 `https://` 开头。

### Q2：为什么删除 LLM Profile 失败？
若该 Profile 被运行中的任务引用，接口会返回 `409`。

### Q3：任务中断后页面一直无更新？
可重新请求任务详情 `GET /api/tasks/{task_id}` 或重连 `/stream`，`init` 事件会返回当前快照。

### Q4：在哪看数据库？
默认使用 `mcp_scan.db`（与 `web_server.py` 同目录的运行上下文）。

## 8. 安全与运维建议

- 当前为本地工具定位，LLM API Key 存在本地数据库中，请确保宿主机权限隔离。
- 建议仅内网使用，不要直接暴露在公网。
- 建议给 `mcp_scan.db` 做周期备份，便于审计任务历史。
- 当任务量较大时，可关注 SSE 连接数与数据库轮询频率（当前 1 秒轮询一次）。

## 9. 快速检查清单

- [ ] `conda` 与 `AI-Infra-Guard` 环境可用
- [ ] `web/index.html` 存在
- [ ] 已创建可用的 LLM Profile
- [ ] 目标 URL 可访问
- [ ] 端口 `7788` 未被占用
- [ ] 能成功收到 SSE 的 `init/stage/done` 事件
