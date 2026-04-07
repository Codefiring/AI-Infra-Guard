"""
mcp-scan Web Server

FastAPI backend that:
  - Serves the single-page frontend (web/index.html)
  - Manages scan tasks (create, list, detail, abort)
  - Launches mcp-scan subprocesses and streams logs via SSE
  - Persists everything in SQLite (mcp_scan.db) via db.py
  - Stores LLM profiles (api_key included — local tool only)

Startup:
  conda run -n AI-Infra-Guard python web_server.py
  → http://localhost:7788
"""

import ast
import asyncio
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import AsyncGenerator

import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator

import db

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
LOGS_DIR   = SCRIPT_DIR / "logs"
WEB_DIR    = SCRIPT_DIR / "web"
PORT       = 7788

# All 15 selectable stage IDs with their names (mirrors frontend ALL_STAGES)
ALL_STAGES = [
    (2,  "Tool Poisoning (TPA)"),
    (3,  "Full Schema Poisoning (FSP)"),
    (4,  "Advanced Tool Poisoning (ATPA)"),
    (5,  "Rug Pull"),
    (7,  "Tool Name Spoofing"),
    (8,  "Tool Shadowing"),
    (14, "Unauthenticated Access"),
    (18, "Path Traversal"),
    (21, "Privilege Abuse"),
    (9,  "Resource Content Poisoning"),
    (11, "Prompt Injection"),
    (12, "Command Injection"),
    (13, "Remote Code Execution (RCE)"),
    (16, "Token/Credential Theft"),
    (23, "SQL Injection"),
]
STAGE_NAME_MAP = {sid: name for sid, name in ALL_STAGES}
STAGE_NAME_MAP[1]  = "Info Collection"
STAGE_NAME_MAP[27] = "Vulnerability Review"
ALL_STAGE_IDS = [sid for sid, _ in ALL_STAGES]

# In-memory only (never persisted)
processes: dict[str, subprocess.Popen] = {}
sse_queues: dict[str, asyncio.Queue]   = {}
event_loop: asyncio.AbstractEventLoop | None = None

# ─────────────────────────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────────────────────────
app = FastAPI(title="mcp-scan Web Server", version="1.0.0")


@app.on_event("startup")
async def startup():
    global event_loop
    event_loop = asyncio.get_event_loop()
    LOGS_DIR.mkdir(exist_ok=True)
    db.init_db()


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────────────────────────────────────
class TargetIn(BaseModel):
    name:      str | None = None
    url:       str
    stage_ids: list[int] | None = None  # None = all 15 selectable stages

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


class TaskIn(BaseModel):
    llm_profile_id:     str
    targets:            list[TargetIn]
    prompt:             str = ""
    language:           str = "zh"
    oauth_client_id:    str | None = None
    oauth_client_secret:str | None = None
    oauth_token_url:    str | None = None
    oauth_scope:        str | None = None

    @field_validator("targets")
    @classmethod
    def at_least_one_target(cls, v):
        if not v:
            raise ValueError("At least one target is required")
        return v


class LlmProfileIn(BaseModel):
    name:       str
    base_url:   str
    api_key:    str | None = None  # optional on update
    model:      str
    is_default: bool = False


# ─────────────────────────────────────────────────────────────────────────────
# Log detection
# ─────────────────────────────────────────────────────────────────────────────
def detect_log_file(launch_time: float, timeout: float = 12.0) -> Path | None:
    """Poll LOGS_DIR for the mcp-scan log file created at/after launch_time."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        candidates = [
            f for f in LOGS_DIR.glob("mcp-scan_*.log")
            if f.stat().st_mtime >= launch_time - 1.5
        ]
        if candidates:
            return max(candidates, key=lambda f: f.stat().st_mtime)
        time.sleep(0.25)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Log parser
# ─────────────────────────────────────────────────────────────────────────────
RE_LOG_LINE     = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \| (\w+) \| (.*)$')
RE_STAGE_START  = re.compile(r'^=== 阶段 (\d+): (.+) ===$')
RE_FINAL_OUTPUT = re.compile(r'^Final Output: ?(.*)$')
RE_DYN_RESULTS  = re.compile(r'^Dynamic analysis results:$')


class LogParser:
    """Stateful line-by-line log parser."""

    def __init__(self):
        self.current_stage_id:       int  | None = None
        self.collecting_final_output: bool       = False
        self.final_output_lines:     list[str]  = []
        self.awaiting_results_dict:   bool       = False

    def feed(self, line: str) -> list[dict]:
        """Feed one log line; return list of events emitted."""
        line = line.rstrip("\n")
        events = []

        m = RE_LOG_LINE.match(line)
        if m:
            # Finalize any in-progress Final Output
            if self.collecting_final_output:
                output = "\n".join(self.final_output_lines).strip()
                events.append({
                    "type": "stage",
                    "data": {
                        "stage_id": self.current_stage_id,
                        "name": STAGE_NAME_MAP.get(self.current_stage_id, f"Stage {self.current_stage_id}"),
                        "status": "completed",
                        "output": output,
                    }
                })
                self.collecting_final_output = False
                self.final_output_lines = []

            _ts, level, msg = m.group(1), m.group(2), m.group(3)

            # Stage start marker
            sm = RE_STAGE_START.match(msg)
            if sm:
                stage_id = int(sm.group(1))
                stage_name = sm.group(2).strip()
                self.current_stage_id = stage_id
                self.awaiting_results_dict = False
                events.append({
                    "type": "stage",
                    "data": {
                        "stage_id": stage_id,
                        "name": stage_name,
                        "status": "running",
                        "output": "",
                    }
                })
                return events

            # Final Output start
            fom = RE_FINAL_OUTPUT.match(msg)
            if fom:
                self.collecting_final_output = True
                self.final_output_lines = []
                first_line = fom.group(1)
                if first_line:
                    self.final_output_lines.append(first_line)
                return events

            # Dynamic analysis results marker
            if RE_DYN_RESULTS.match(msg):
                self.awaiting_results_dict = True
                return events

            # Emit log line event for INFO/ERROR
            if level in ("INFO", "ERROR", "WARNING", "SUCCESS"):
                events.append({"type": "log", "data": {"line": msg, "level": level}})

        else:
            # Continuation line (no timestamp prefix)
            if self.collecting_final_output:
                self.final_output_lines.append(line)
                return events

            if self.awaiting_results_dict:
                self.awaiting_results_dict = False
                try:
                    result_dict = ast.literal_eval(line)
                    events.append({"type": "result", "data": result_dict})
                except Exception:
                    pass

        return events


# ─────────────────────────────────────────────────────────────────────────────
# Build stage list helper
# ─────────────────────────────────────────────────────────────────────────────
def build_stage_rows(stage_ids: list[int] | None) -> list[dict]:
    """Return ordered list of stage dicts for insertion into task_stages."""
    ids = sorted(stage_ids) if stage_ids else sorted(ALL_STAGE_IDS)
    rows = [{"id": str(uuid.uuid4())[:8], "stage_id": 1, "name": "Info Collection"}]
    for sid in ids:
        rows.append({"id": str(uuid.uuid4())[:8], "stage_id": sid, "name": STAGE_NAME_MAP.get(sid, f"Stage {sid}")})
    rows.append({"id": str(uuid.uuid4())[:8], "stage_id": 27, "name": "Vulnerability Review"})
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# SSE queue helper
# ─────────────────────────────────────────────────────────────────────────────
def push_event(task_id: str, event_type: str, data: dict):
    """Push an SSE event to all listeners for this task (thread-safe)."""
    queue = sse_queues.get(task_id)
    if queue and event_loop:
        asyncio.run_coroutine_threadsafe(queue.put({"type": event_type, "data": data}), event_loop)


# ─────────────────────────────────────────────────────────────────────────────
# monitor_task — background thread
# ─────────────────────────────────────────────────────────────────────────────
def monitor_task(task_id: str, proc: subprocess.Popen, targets_meta: list[dict], temp_yaml: Path | None):
    """Watch the subprocess log file, parse events, write to DB, push SSE."""
    try:
        launch_time = time.time()
        log_file = detect_log_file(launch_time)
        if not log_file:
            db.task_set_done(task_id, "failed", "Log file not detected within 12s")
            push_event(task_id, "done", {"status": "failed"})
            return

        db.task_set_running(task_id, str(log_file))

        parser = LogParser()
        current_target_idx = 0
        target = targets_meta[0]
        target_id = target["id"]
        db.target_set_running(target_id)

        # Tail the log file
        with open(log_file, "r", encoding="utf-8", errors="replace") as fh:
            while True:
                line = fh.readline()
                if not line:
                    if proc.poll() is not None:
                        break
                    time.sleep(0.1)
                    continue

                events = parser.feed(line)
                for ev in events:
                    etype = ev["type"]
                    edata = ev["data"]

                    if etype == "log":
                        push_event(task_id, "log", edata)

                    elif etype == "stage":
                        stage_id = edata["stage_id"]
                        status   = edata["status"]
                        output   = edata.get("output", "")
                        db.stage_update(target_id, stage_id, status, output)
                        push_event(task_id, "stage", {
                            "stage_id": stage_id,
                            "name":     edata["name"],
                            "status":   status,
                            "output":   output,
                        })

                    elif etype == "result":
                        # Stage 27 completed — store result for current target
                        score   = edata.get("score")
                        readme  = edata.get("readme", "")
                        vulns   = edata.get("results", [])
                        vuln_rows = [
                            {
                                "id":          str(uuid.uuid4())[:8],
                                "title":       v.get("title", ""),
                                "description": v.get("description"),
                                "risk_type":   v.get("risk_type"),
                                "level":       v.get("level"),
                                "suggestion":  v.get("suggestion"),
                            }
                            for v in (vulns or [])
                        ]
                        db.vulnerabilities_insert(target_id, vuln_rows)
                        db.stage_update(target_id, 27, "completed", edata.get("readme", ""))
                        db.target_set_done(target_id, score, readme)

                        push_event(task_id, "result", {
                            "target_index": current_target_idx,
                            "score":        score,
                            "results":      vuln_rows,
                            "readme":       readme,
                        })

                        # Advance to next target in batch
                        current_target_idx += 1
                        if current_target_idx < len(targets_meta):
                            target    = targets_meta[current_target_idx]
                            target_id = target["id"]
                            db.task_set_current_target(task_id, current_target_idx)
                            db.target_set_running(target_id)
                            push_event(task_id, "target", {
                                "target_index": current_target_idx,
                                "name":         target.get("name"),
                                "url":          target["url"],
                                "stage_ids":    target.get("stage_ids"),
                            })

        # Process exited
        returncode = proc.wait()
        final_status = "completed" if returncode == 0 else "failed"
        db.task_set_done(task_id, final_status, None if returncode == 0 else f"Exit code {returncode}")
        push_event(task_id, "done", {"status": final_status})

    except Exception as exc:
        db.task_set_done(task_id, "failed", str(exc))
        push_event(task_id, "done", {"status": "failed"})

    finally:
        processes.pop(task_id, None)
        if temp_yaml and temp_yaml.exists():
            temp_yaml.unlink(missing_ok=True)
        # Send sentinel to close SSE generator
        queue = sse_queues.get(task_id)
        if queue and event_loop:
            asyncio.run_coroutine_threadsafe(queue.put(None), event_loop)


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


@app.post("/api/tasks", status_code=201)
async def create_task(body: TaskIn):
    # Resolve LLM profile
    profile = db.llm_profile_get(body.llm_profile_id)
    if not profile:
        raise HTTPException(404, "LLM profile not found")

    task_id = str(uuid.uuid4())[:8]
    targets_data = []
    for pos, t in enumerate(body.targets):
        tid = str(uuid.uuid4())[:8]
        stages = build_stage_rows(t.stage_ids)
        targets_data.append({
            "id":       tid,
            "position": pos,
            "name":     t.name,
            "url":      t.url,
            "stage_ids": t.stage_ids,
            "stages":   stages,
        })

    has_oauth = bool(body.oauth_client_id and body.oauth_client_secret and body.oauth_token_url)
    task = db.task_create({
        "id":               task_id,
        "llm_profile_id":   body.llm_profile_id,
        "llm_profile_name": profile["name"],
        "llm_model":        profile["model"],
        "prompt":           body.prompt,
        "language":         body.language,
        "has_oauth":        has_oauth,
        "targets":          targets_data,
    })

    # Build and launch subprocess
    temp_yaml: Path | None = None
    try:
        proc, temp_yaml = _launch_subprocess(body, profile, task_id, targets_data)
    except FileNotFoundError as exc:
        db.task_set_done(task_id, "failed", f"conda not found: {exc}")
        return db.task_get(task_id)
    except Exception as exc:
        db.task_set_done(task_id, "failed", str(exc))
        return db.task_get(task_id)

    processes[task_id] = proc

    # Start monitor thread
    t = threading.Thread(
        target=monitor_task,
        args=(task_id, proc, targets_data, temp_yaml),
        daemon=True,
    )
    t.start()

    return db.task_get(task_id)


def _launch_subprocess(body: TaskIn, profile: dict, task_id: str, targets_data: list) -> tuple:
    """Build the subprocess command and launch it. Returns (proc, temp_yaml_path|None)."""
    common_args = [
        "conda", "run", "-n", "AI-Infra-Guard", "--no-capture-output",
        "python", str(SCRIPT_DIR / "main.py"),
        "-k", profile["api_key"],
        "-u", profile["base_url"],
        "-m", profile["model"],
        "--language", body.language,
    ]
    if body.prompt:
        common_args += ["-p", body.prompt]
    if body.oauth_client_id:
        common_args += ["--oauth-client-id", body.oauth_client_id]
    if body.oauth_client_secret:
        common_args += ["--oauth-client-secret", body.oauth_client_secret]
    if body.oauth_token_url:
        common_args += ["--oauth-token-url", body.oauth_token_url]
    if body.oauth_scope:
        common_args += ["--oauth-scope", body.oauth_scope]

    temp_yaml = None

    if len(body.targets) == 1:
        t = body.targets[0]
        cmd = common_args + ["--server_url", t.url]
        if t.stage_ids:
            cmd += ["--stages", ",".join(str(i) for i in sorted(t.stage_ids))]
    else:
        # Batch: write per-target YAML
        temp_yaml = SCRIPT_DIR / f"_temp_{task_id}.yaml"
        yaml_targets = []
        for t, td in zip(body.targets, targets_data):
            entry: dict = {"url": t.url}
            if t.name:
                entry["name"] = t.name
            if t.stage_ids:
                entry["stages"] = sorted(t.stage_ids)
            yaml_targets.append(entry)
        temp_yaml.write_text(yaml.dump({"targets": yaml_targets}, allow_unicode=True))
        cmd = common_args + ["-c", str(temp_yaml)]

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=str(SCRIPT_DIR),
        start_new_session=True,
    )
    return proc, temp_yaml


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
    db.task_set_done(task_id, "failed", "Aborted by user")
    push_event(task_id, "done", {"status": "failed"})


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
