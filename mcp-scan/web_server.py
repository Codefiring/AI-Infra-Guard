"""
mcp-scan Web Server

FastAPI backend that:
  - Serves the single-page frontend (web/index.html)
  - Manages scan tasks (create, list, detail, abort)
  - Launches mcp-scan as a subprocess; mcp-scan writes stage progress
    directly to mcp_scan.db — no log parsing needed
  - Polls DB every second and pushes stage diffs to the browser via SSE
  - Persists everything in SQLite (mcp_scan.db) via db.py
  - Stores LLM profiles (api_key included — local tool only)

Startup:
  conda run -n AI-Infra-Guard python web_server.py
  → http://localhost:7788
"""

import asyncio
import json
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator

import db

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
WEB_DIR    = SCRIPT_DIR / "web"
PORT       = 7788

# All 15 selectable stage IDs with their names (mirrors frontend ALL_STAGES)
ALL_STAGES = [
    (11, "MCP01 Prompt Injection"),
    (12, "MCP02 Command Injection"),
    (2,  "MCP03 Tool Poisoning (TPA)"),
    (13, "MCP04 Remote Code Execution (RCE)"),
    (14, "MCP05 Unauthenticated Access"),
    (16, "MCP08 Token/Credential Theft"),
    (18, "MCP10 Path Traversal"),
    (3,  "MCP11 Full Schema Poisoning (FSP)"),
    (7,  "MCP12 Tool Name Spoofing"),
    (5,  "MCP14 Rug Pull"),
    (4,  "MCP15 Advanced Tool Poisoning (ATPA)"),
    (8,  "MCP17 Tool Shadowing"),
    (9,  "MCP18 Resource Content Poisoning"),
    (21, "MCP19 Privilege Abuse"),
    (23, "MCP21 SQL Injection"),
]
STAGE_NAME_MAP = {sid: name for sid, name in ALL_STAGES}
STAGE_NAME_MAP[1]  = "Info Collection"
STAGE_NAME_MAP[27] = "Vulnerability Review"
ALL_STAGE_IDS = [sid for sid, _ in ALL_STAGES]

# In-memory only (never persisted)
processes:  dict[str, subprocess.Popen] = {}
sse_queues: dict[str, asyncio.Queue]    = {}
event_loop: asyncio.AbstractEventLoop | None = None

# ─────────────────────────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────────────────────────
app = FastAPI(title="mcp-scan Web Server", version="2.0.0")
app.mount("/web", StaticFiles(directory=WEB_DIR), name="web_static")


@app.on_event("startup")
async def startup():
    global event_loop
    event_loop = asyncio.get_event_loop()
    db.init_db()


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────────────────────────────────────
class TaskIn(BaseModel):
    llm_profile_id:      str
    url:                 str
    name:                str = ""
    stage_ids:           list[int] | None = None   # None = all 15 selectable stages
    prompt:              str = ""
    language:            str = "en"
    oauth_client_id:     str | None = None
    oauth_client_secret: str | None = None
    oauth_token_url:     str | None = None
    oauth_scope:         str | None = None

    @field_validator("url")
    @classmethod
    def validate_url(cls, v):
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v

    @field_validator("stage_ids")
    @classmethod
    def validate_stages(cls, v):
        if v is None:
            return v
        bad = [i for i in v if i < 2 or i > 26]
        if bad:
            raise ValueError(f"Stage IDs must be between 2 and 26: {bad}")
        return v


class LlmProfileIn(BaseModel):
    name:       str
    base_url:   str
    api_key:    str | None = None  # optional on update
    model:      str
    is_default: bool = False


class ConfigIn(BaseModel):
    name:             str
    url:              str
    stage_ids:        list[int] | None = None
    prompt:           str = ""
    language:         str = "zh"
    llm_profile_id:   str | None = None
    oauth_client_id:      str | None = None
    oauth_client_secret:  str | None = None
    oauth_token_url:      str | None = None
    oauth_scope:          str | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Build stage list helper
# ─────────────────────────────────────────────────────────────────────────────
def build_stage_rows(stage_ids: list[int] | None) -> list[dict]:
    """Return ordered list of stage dicts for insertion into task_stages."""
    ids = sorted(stage_ids) if stage_ids else sorted(ALL_STAGE_IDS)
    rows = [{"id": str(uuid.uuid4())[:8], "stage_id": 1, "name": "Info Collection"}]
    for sid in ids:
        rows.append({"id": str(uuid.uuid4())[:8], "stage_id": sid,
                     "name": STAGE_NAME_MAP.get(sid, f"Stage {sid}")})
    rows.append({"id": str(uuid.uuid4())[:8], "stage_id": 27, "name": "Vulnerability Review"})
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# SSE push helper (thread-safe)
# ─────────────────────────────────────────────────────────────────────────────
def push_event(task_id: str, event_type: str, data: dict):
    queue = sse_queues.get(task_id)
    if queue and event_loop:
        asyncio.run_coroutine_threadsafe(queue.put({"type": event_type, "data": data}), event_loop)


# ─────────────────────────────────────────────────────────────────────────────
# DB polling monitor (replaces log-parsing monitor_task)
# ─────────────────────────────────────────────────────────────────────────────
def poll_task_db(task_id: str, proc: subprocess.Popen):
    """Poll DB every second for stage/status changes; push SSE diffs to browser."""
    last_stages: dict[int, str] = {}   # stage_id → last known status
    result_sent = False

    try:
        while proc.poll() is None:
            task = db.task_get(task_id)
            if task and task["targets"]:
                target = task["targets"][0]
                for s in target.get("stages", []):
                    sid, new_st = s["stage_id"], s["status"]
                    if last_stages.get(sid) != new_st:
                        push_event(task_id, "stage", {
                            "stage_id": sid,
                            "name":     s["name"],
                            "status":   new_st,
                            "output":   s.get("output", "") if new_st == "completed" else "",
                        })
                        last_stages[sid] = new_st

                if not result_sent and target.get("score") is not None:
                    push_event(task_id, "result", {
                        "target_index": 0,
                        "score":        target["score"],
                        "results":      target.get("vulnerabilities", []),
                        "readme":       target.get("readme", ""),
                    })
                    result_sent = True

            time.sleep(1.0)

        # Process exited — read final DB state
        task = db.task_get(task_id)
        if task and task["status"] == "running":
            # mcp-scan crashed without calling task_set_done
            db.task_set_done(task_id, "failed", f"Process exited (code {proc.returncode})")
        # Final flush — catch stage/result events written during the last poll interval
        task = db.task_get(task_id)
        if task and task["targets"]:
            target = task["targets"][0]
            for s in target.get("stages", []):
                sid, new_st = s["stage_id"], s["status"]
                if last_stages.get(sid) != new_st:
                    push_event(task_id, "stage", {
                        "stage_id": sid,
                        "name":     s["name"],
                        "status":   new_st,
                        "output":   s.get("output", "") if new_st == "completed" else "",
                    })
                    last_stages[sid] = new_st
            if not result_sent and target.get("score") is not None:
                push_event(task_id, "result", {
                    "target_index": 0,
                    "score":        target["score"],
                    "results":      target.get("vulnerabilities", []),
                    "readme":       target.get("readme", ""),
                })
                result_sent = True
        final_status = (task or {}).get("status", "failed")
        push_event(task_id, "done", {"status": final_status})

    except Exception as exc:
        try:
            db.task_set_done(task_id, "failed", str(exc))
        except Exception:
            pass
        push_event(task_id, "done", {"status": "failed"})
    finally:
        processes.pop(task_id, None)
        q = sse_queues.get(task_id)
        if q and event_loop:
            asyncio.run_coroutine_threadsafe(q.put(None), event_loop)


# ─────────────────────────────────────────────────────────────────────────────
# SSE generator
# ─────────────────────────────────────────────────────────────────────────────
async def sse_generator(task_id: str) -> AsyncGenerator[str, None]:
    queue: asyncio.Queue = asyncio.Queue()
    sse_queues[task_id] = queue

    try:
        # Send full current state (catch-up for reconnects)
        task = db.task_get(task_id)
        if task:
            yield f"event: init\ndata: {json.dumps(task)}\n\n"

        # If task is already done, just close
        if task and task["status"] not in ("pending", "running"):
            return

        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=15.0)
                if event is None:  # sentinel
                    break
                yield f"event: {event['type']}\ndata: {json.dumps(event['data'])}\n\n"
                if event["type"] == "done":
                    break
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"
    finally:
        sse_queues.pop(task_id, None)


# ─────────────────────────────────────────────────────────────────────────────
# API — Frontend
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/")
async def serve_index():
    index = WEB_DIR / "index.html"
    if not index.exists():
        raise HTTPException(status_code=404, detail="index.html not found")
    return FileResponse(index)


# ─────────────────────────────────────────────────────────────────────────────
# API — LLM Profiles
# ─────────────────────────────────────────────────────────────────────────────
def _mask_profile(p: dict) -> dict:
    """Return profile dict with api_key masked."""
    out = dict(p)
    if out.get("api_key"):
        out["api_key"] = out["api_key"][:4] + "••••"
    return out


@app.get("/api/llm-profiles")
async def list_llm_profiles():
    return [_mask_profile(p) for p in db.llm_profiles_list()]


@app.post("/api/llm-profiles", status_code=201)
async def create_llm_profile(body: LlmProfileIn):
    if not body.name or not body.base_url or not body.model:
        raise HTTPException(400, "name, base_url, and model are required")
    if not body.api_key:
        raise HTTPException(400, "api_key is required when creating a profile")
    data = {
        "id":         str(uuid.uuid4())[:8],
        "name":       body.name,
        "base_url":   body.base_url,
        "api_key":    body.api_key,
        "model":      body.model,
        "is_default": body.is_default,
    }
    profile = db.llm_profile_create(data)
    return _mask_profile(profile)


@app.put("/api/llm-profiles/{profile_id}")
async def update_llm_profile(profile_id: str, body: LlmProfileIn):
    existing = db.llm_profile_get(profile_id)
    if not existing:
        raise HTTPException(404, "Profile not found")
    data = {"name": body.name, "base_url": body.base_url, "model": body.model, "is_default": body.is_default}
    if body.api_key:
        data["api_key"] = body.api_key
    updated = db.llm_profile_update(profile_id, data)
    return _mask_profile(updated)


@app.delete("/api/llm-profiles/{profile_id}", status_code=204)
async def delete_llm_profile(profile_id: str):
    if db.profile_has_active_tasks(profile_id):
        raise HTTPException(409, "Profile is used by a running task")
    db.llm_profile_delete(profile_id)


# ─────────────────────────────────────────────────────────────────────────────
# API — Saved configs
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/api/configs")
async def list_configs():
    return db.configs_list()


@app.post("/api/configs", status_code=201)
async def create_config(body: ConfigIn):
    profile = db.llm_profile_get(body.llm_profile_id) if body.llm_profile_id else None
    stage_ids_json = json.dumps(body.stage_ids) if body.stage_ids is not None else None
    return db.config_create({
        "id":               str(uuid.uuid4())[:8],
        "name":             body.name,
        "created_at":       db.now_iso(),
        "url":              body.url,
        "stage_ids":        stage_ids_json,
        "prompt":           body.prompt,
        "language":         body.language,
        "llm_profile_id":   body.llm_profile_id,
        "llm_profile_name": profile["name"] if profile else None,
        "oauth_client_id":      body.oauth_client_id,
        "oauth_client_secret":  body.oauth_client_secret,
        "oauth_token_url":      body.oauth_token_url,
        "oauth_scope":          body.oauth_scope,
    })


@app.delete("/api/configs/{config_id}", status_code=204)
async def delete_config(config_id: str):
    db.config_delete(config_id)


# ─────────────────────────────────────────────────────────────────────────────
# API — Tasks
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/api/tasks")
async def list_tasks():
    return db.tasks_list()


@app.get("/api/tasks/{task_id}")
async def get_task(task_id: str):
    task = db.task_get(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return task


@app.get("/api/tasks/{task_id}/log")
async def get_task_log(task_id: str, tail: int = 300):
    task = db.task_get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    stored = task.get("log_file")
    if stored:
        log_path = Path(stored) if Path(stored).is_absolute() else SCRIPT_DIR / stored
    else:
        log_path = SCRIPT_DIR / "logs" / f"{task_id}.log"
    if not log_path.exists():
        return {"lines": [], "has_log": False}
    try:
        with open(log_path, "r", errors="replace") as f:
            lines = f.readlines()
        return {"lines": [l.rstrip("\n") for l in lines[-tail:]], "has_log": True}
    except Exception:
        return {"lines": [], "has_log": False}


@app.post("/api/tasks", status_code=201)
async def create_task(body: TaskIn):
    # Resolve LLM profile
    profile = db.llm_profile_get(body.llm_profile_id)
    if not profile:
        raise HTTPException(404, "LLM profile not found")

    task_id   = str(uuid.uuid4())[:8]
    target_id = str(uuid.uuid4())[:8]
    stage_rows = build_stage_rows(body.stage_ids)

    has_oauth = bool(body.oauth_client_id and body.oauth_client_secret and body.oauth_token_url)
    db.task_create({
        "id":               task_id,
        "name":             body.name,
        "llm_profile_id":   body.llm_profile_id,
        "llm_profile_name": profile["name"],
        "llm_model":        profile["model"],
        "prompt":           body.prompt,
        "language":         body.language,
        "has_oauth":        has_oauth,
        "targets": [{
            "id":       target_id,
            "position": 0,
            "name":     None,
            "url":      body.url,
            "stage_ids": body.stage_ids,
            "stages":   stage_rows,
        }],
    })

    try:
        proc = _launch_subprocess(body, profile, task_id, target_id)
    except FileNotFoundError as exc:
        db.task_set_done(task_id, "failed", f"conda not found: {exc}")
        return db.task_get(task_id)
    except Exception as exc:
        db.task_set_done(task_id, "failed", str(exc))
        return db.task_get(task_id)

    processes[task_id] = proc
    threading.Thread(target=poll_task_db, args=(task_id, proc), daemon=True).start()
    return db.task_get(task_id)


def _launch_subprocess(body: TaskIn, profile: dict, task_id: str, target_id: str) -> subprocess.Popen:
    """Build the subprocess command and launch it."""
    cmd = [
        "python", str(SCRIPT_DIR / "main.py"),
        "--server_url", body.url,
        "-k", profile["api_key"],
        "-u", profile["base_url"],
        "-m", profile["model"],
        "--language", body.language,
        "--task-id",   task_id,
        "--target-id", target_id,
    ]
    if body.prompt:
        cmd += ["-p", body.prompt]
    if body.stage_ids:
        cmd += ["--stages", ",".join(str(i) for i in sorted(body.stage_ids))]
    if body.oauth_client_id:
        cmd += ["--oauth-client-id",     body.oauth_client_id]
    if body.oauth_client_secret:
        cmd += ["--oauth-client-secret", body.oauth_client_secret]
    if body.oauth_token_url:
        cmd += ["--oauth-token-url",     body.oauth_token_url]
    if body.oauth_scope:
        cmd += ["--oauth-scope",         body.oauth_scope]

    return subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=str(SCRIPT_DIR),
        start_new_session=True,
    )


@app.delete("/api/tasks/{task_id}", status_code=204)
async def abort_task(task_id: str):
    proc = processes.get(task_id)
    if proc:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            proc.wait(timeout=5)
        except Exception:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                pass
        processes.pop(task_id, None)
    db.stages_mark_aborted(task_id)
    db.task_set_done(task_id, "failed", "Aborted by user")
    push_event(task_id, "done", {"status": "failed"})


@app.delete("/api/tasks/{task_id}/record", status_code=204)
async def delete_task(task_id: str):
    proc = processes.pop(task_id, None)
    if proc:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            proc.wait(timeout=5)
        except Exception:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                pass
    push_event(task_id, "done", {"status": "deleted"})
    db.task_delete(task_id)


@app.get("/api/tasks/{task_id}/stream")
async def stream_task(task_id: str):
    task = db.task_get(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return StreamingResponse(
        sse_generator(task_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    print(f"Starting mcp-scan Web Server on http://localhost:{PORT}")
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
