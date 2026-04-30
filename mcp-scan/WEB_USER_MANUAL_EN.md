# mcp-scan Detection Website User Manual (Based on `web_server.py`)

> Audience: security testers and developers running the local website via `mcp-scan/web_server.py`.  
> Default URL: `http://localhost:7788`

## 1. System Overview

`web_server.py` is a FastAPI backend that:

- Serves the frontend page (`web/index.html`).
- Provides task APIs (create, query, abort, delete record).
- Launches `main.py` as a subprocess to run scans.
- Streams stage progress and final results via SSE (Server-Sent Events).
- Persists tasks, configs, and LLM profiles in SQLite (`mcp_scan.db`).

## 2. Start and Access

Run from the project root (as indicated in source comments):

```bash
cd mcp-scan
conda run -n AI-Infra-Guard python web_server.py
```

After startup:

- Home page: `http://localhost:7788/`
- OpenAPI docs: `http://localhost:7788/docs`

## 3. Recommended Website Workflow

1. **Create an LLM profile first** (model endpoint, model name, API key).
2. **Enter target URL** (must start with `http://` or `https://`).
3. **Select test stages** (all 15 selectable stages by default).
4. (Optional) Add custom prompt and OAuth parameters.
5. **Create and start task**.
6. Monitor real-time stage progress; review risk score and findings when complete.

## 3.1 UI Screenshots (Reference)

> Note: screenshots are for quick orientation. Exact labels/buttons may vary by version.

### Scan entry page

![Scan page reference](../img/scan-zh.png)

### Plugin/capability panel (reference)

![Plugin page reference](../img/plugin-zh.gif)

### Result/output view (reference)

![Output page reference](../img/output.gif)

## 4. Core Data Model

## 4.1 Task Input (`TaskIn`)

Main fields when creating a task:

- `llm_profile_id`: required, links to an LLM profile.
- `url`: required, target URL (must be `http/https`).
- `name`: task name (optional).
- `stage_ids`: list of stage IDs (optional; empty means default all stages).
- `prompt`: extra prompt (optional).
- `language`: language, default `en`.
- OAuth fields (all optional):
  - `oauth_client_id`
  - `oauth_client_secret`
  - `oauth_token_url`
  - `oauth_scope`

> `has_oauth = true` only when `client_id + client_secret + token_url` are all provided.

## 4.2 Stage Mechanism

The system always inserts two fixed stages:

- `1`: Info Collection
- `27`: Vulnerability Review

The 15 selectable stages in between (all selected by default):

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

## 5. API Guide

Common endpoints are listed below (see `/docs` for complete schemas).

### 5.1 LLM Profile Management

- `GET /api/llm-profiles`: list profiles (`api_key` is masked in response).
- `POST /api/llm-profiles`: create profile (`api_key` required on create).
- `PUT /api/llm-profiles/{profile_id}`: update profile (`api_key` optional; unchanged if omitted).
- `DELETE /api/llm-profiles/{profile_id}`: delete profile (returns `409` if used by running task).

Example:

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

### 5.2 Saved Config Management

- `GET /api/configs`: list saved configs.
- `POST /api/configs`: save a config template.
- `DELETE /api/configs/{config_id}`: delete a saved config.

### 5.3 Scan Task Management

- `GET /api/tasks`: list tasks.
- `GET /api/tasks/{task_id}`: get task detail.
- `POST /api/tasks`: create and start task.
- `DELETE /api/tasks/{task_id}`: abort task (task marked failed with `Aborted by user`).
- `DELETE /api/tasks/{task_id}/record`: delete task record (and terminate process if needed).

Example:

```bash
curl -X POST http://localhost:7788/api/tasks \
  -H 'Content-Type: application/json' \
  -d '{
    "llm_profile_id":"abcd1234",
    "url":"http://127.0.0.1:3000",
    "name":"demo-scan",
    "stage_ids":[2,3,11,12,13],
    "prompt":"Please focus on command execution paths",
    "language":"en"
  }'
```

### 5.4 Real-Time Stream (SSE)

- `GET /api/tasks/{task_id}/stream`

Event types:

- `init`: full task snapshot on connect (supports reconnect catch-up).
- `stage`: one stage status changed.
- `result`: emitted when score and findings are available.
- `done`: task finished (success/failure/deleted).
- comment keepalive: `: keep-alive` every 15 seconds.

Use `EventSource` in frontend/scripts to build live progress updates.

## 6. Scan Execution Model

After task creation, backend builds and runs subprocess command:

```bash
conda run -n AI-Infra-Guard --no-capture-output python main.py ...
```

Key points:

- Scan subprocess stdout/stderr is redirected to `DEVNULL` (UI progress is DB-driven, not log-driven).
- Backend polls SQLite every second, diffs stage status changes, and pushes SSE events.
- If subprocess exits unexpectedly while task is still running, backend auto-marks task as failed.

## 7. FAQ

### Q1: Why does task creation fail with URL error?
`url` is strictly validated and must begin with `http://` or `https://`.

### Q2: Why can’t I delete an LLM profile?
If the profile is referenced by a running task, API returns `409`.

### Q3: Why did page updates stop after interruption?
Call `GET /api/tasks/{task_id}` again or reconnect to `/stream`; `init` returns current snapshot.

### Q4: Where is the database?
By default: `mcp_scan.db` (in the runtime context with `web_server.py`).

## 8. Security & Operations Recommendations

- This is a local tool; LLM API keys are stored in local DB. Ensure host-level access control.
- Prefer internal-network deployment only; do not expose directly to public internet.
- Back up `mcp_scan.db` periodically for audit/history retention.
- For high task volume, monitor SSE connection count and DB polling load (currently 1-second poll).

## 9. Quick Checklist

- [ ] `conda` and `AI-Infra-Guard` environment are available
- [ ] `web/index.html` exists
- [ ] Valid LLM profile has been created
- [ ] Target URL is reachable
- [ ] Port `7788` is free
- [ ] SSE `init/stage/done` events are received successfully
