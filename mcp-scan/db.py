"""
mcp-scan SQLite database layer.

Tables:
  llm_profiles   — saved LLM service configurations
  tasks          — top-level scan jobs
  task_targets   — per-URL targets within a task
  task_stages    — per-stage progress for each target
  vulnerabilities — findings from completed target scans

Run standalone to verify:
  conda run -n AI-Infra-Guard python db.py
"""

import json
import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
DB_FILE = SCRIPT_DIR / "mcp_scan.db"

# ─────────────────────────────────────────────────────────────────────────────
# Schema DDL
# ─────────────────────────────────────────────────────────────────────────────
SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS llm_profiles (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    base_url    TEXT NOT NULL,
    api_key     TEXT NOT NULL,
    model       TEXT NOT NULL,
    is_default  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id                  TEXT PRIMARY KEY,
    status              TEXT NOT NULL DEFAULT 'pending',
    created_at          TEXT NOT NULL,
    completed_at        TEXT,
    llm_profile_id      TEXT,
    llm_profile_name    TEXT NOT NULL,
    llm_model           TEXT NOT NULL,
    prompt              TEXT NOT NULL DEFAULT '',
    language            TEXT NOT NULL DEFAULT 'zh',
    has_oauth           INTEGER NOT NULL DEFAULT 0,
    current_target_idx  INTEGER NOT NULL DEFAULT 0,
    log_file            TEXT,
    error               TEXT,
    FOREIGN KEY (llm_profile_id) REFERENCES llm_profiles(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS task_targets (
    id          TEXT PRIMARY KEY,
    task_id     TEXT NOT NULL,
    position    INTEGER NOT NULL,
    name        TEXT,
    url         TEXT NOT NULL,
    stage_ids   TEXT,
    status      TEXT NOT NULL DEFAULT 'pending',
    score       INTEGER,
    readme      TEXT,
    started_at  TEXT,
    ended_at    TEXT,
    error       TEXT,
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS task_stages (
    id              TEXT PRIMARY KEY,
    task_target_id  TEXT NOT NULL,
    stage_id        INTEGER NOT NULL,
    name            TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    output          TEXT NOT NULL DEFAULT '',
    updated_at      TEXT,
    FOREIGN KEY (task_target_id) REFERENCES task_targets(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS vulnerabilities (
    id              TEXT PRIMARY KEY,
    task_target_id  TEXT NOT NULL,
    title           TEXT NOT NULL,
    description     TEXT,
    risk_type       TEXT,
    level           TEXT,
    suggestion      TEXT,
    FOREIGN KEY (task_target_id) REFERENCES task_targets(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tasks_created  ON tasks(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tasks_status   ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_targets_task   ON task_targets(task_id, position);
CREATE INDEX IF NOT EXISTS idx_stages_target  ON task_stages(task_target_id, stage_id);
CREATE INDEX IF NOT EXISTS idx_vulns_target   ON vulnerabilities(task_target_id);

CREATE TABLE IF NOT EXISTS saved_configs (
    id               TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    url              TEXT NOT NULL,
    stage_ids        TEXT,
    prompt           TEXT NOT NULL DEFAULT '',
    language         TEXT NOT NULL DEFAULT 'zh',
    llm_profile_id   TEXT,
    llm_profile_name TEXT,
    oauth_client_id      TEXT,
    oauth_client_secret  TEXT,
    oauth_token_url      TEXT,
    oauth_scope          TEXT
);
CREATE INDEX IF NOT EXISTS idx_configs_created ON saved_configs(created_at DESC);
"""


# ─────────────────────────────────────────────────────────────────────────────
# Connection helper
# ─────────────────────────────────────────────────────────────────────────────
@contextmanager
def get_db():
    """Open a connection, yield it, commit on success or rollback on error."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─────────────────────────────────────────────────────────────────────────────
# Startup
# ─────────────────────────────────────────────────────────────────────────────
def init_db():
    """Create schema and mark interrupted tasks as failed."""
    with get_db() as conn:
        conn.executescript(SCHEMA_SQL)
        conn.execute(
            "UPDATE tasks SET status='failed', error='Server restarted unexpectedly' "
            "WHERE status IN ('pending', 'running')"
        )


# ─────────────────────────────────────────────────────────────────────────────
# LLM Profiles
# ─────────────────────────────────────────────────────────────────────────────
def llm_profiles_list() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, name, base_url, model, is_default, created_at "
            "FROM llm_profiles ORDER BY is_default DESC, created_at ASC"
        ).fetchall()
    return [dict(r) for r in rows]


def llm_profile_get(profile_id: str) -> dict | None:
    """Full profile including api_key (server-side only)."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM llm_profiles WHERE id=?", (profile_id,)
        ).fetchone()
    return dict(row) if row else None


def llm_profile_create(data: dict) -> dict:
    with get_db() as conn:
        if data.get("is_default"):
            conn.execute("UPDATE llm_profiles SET is_default=0")
        conn.execute(
            "INSERT INTO llm_profiles (id, name, base_url, api_key, model, is_default, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (data["id"], data["name"], data["base_url"], data["api_key"],
             data["model"], 1 if data.get("is_default") else 0, now_iso())
        )
    return llm_profile_get(data["id"])


def llm_profile_update(profile_id: str, data: dict) -> dict | None:
    with get_db() as conn:
        if data.get("is_default"):
            conn.execute("UPDATE llm_profiles SET is_default=0 WHERE id!=?", (profile_id,))
        fields, vals = [], []
        for col in ("name", "base_url", "api_key", "model", "is_default"):
            if col in data:
                fields.append(f"{col}=?")
                vals.append(1 if col == "is_default" and data[col] else data[col])
        if not fields:
            return llm_profile_get(profile_id)
        vals.append(profile_id)
        conn.execute(f"UPDATE llm_profiles SET {', '.join(fields)} WHERE id=?", vals)
    return llm_profile_get(profile_id)


def llm_profile_delete(profile_id: str):
    with get_db() as conn:
        conn.execute("DELETE FROM llm_profiles WHERE id=?", (profile_id,))


# ─────────────────────────────────────────────────────────────────────────────
# Tasks — list (lightweight, no stages/vulns)
# ─────────────────────────────────────────────────────────────────────────────
def tasks_list(limit: int = 200) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT t.id, t.status, t.created_at, t.completed_at,
                   t.llm_profile_name, t.llm_model, t.prompt, t.language,
                   t.has_oauth, t.current_target_idx, t.error,
                   COUNT(tt.id) AS target_count
            FROM tasks t
            LEFT JOIN task_targets tt ON tt.task_id = t.id
            GROUP BY t.id
            ORDER BY t.created_at DESC
            LIMIT ?
            """,
            (limit,)
        ).fetchall()
        # Attach lightweight target list (url + name + status + score)
        result = []
        for row in rows:
            task = dict(row)
            targets = conn.execute(
                "SELECT id, position, name, url, stage_ids, status, score "
                "FROM task_targets WHERE task_id=? ORDER BY position",
                (task["id"],)
            ).fetchall()
            task["targets"] = [_target_row_to_dict(t) for t in targets]
            task["has_oauth"] = bool(task["has_oauth"])
            result.append(task)
    return result


def _target_row_to_dict(row) -> dict:
    d = dict(row)
    if isinstance(d.get("stage_ids"), str):
        try:
            d["stage_ids"] = json.loads(d["stage_ids"])
        except Exception:
            d["stage_ids"] = None
    return d


# ─────────────────────────────────────────────────────────────────────────────
# Tasks — full detail (includes stages + vulnerabilities)
# ─────────────────────────────────────────────────────────────────────────────
def task_get(task_id: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not row:
            return None
        task = dict(row)
        task["has_oauth"] = bool(task["has_oauth"])

        targets_rows = conn.execute(
            "SELECT * FROM task_targets WHERE task_id=? ORDER BY position",
            (task_id,)
        ).fetchall()

        targets = []
        for tr in targets_rows:
            target = _target_row_to_dict(tr)
            stages = conn.execute(
                "SELECT stage_id, name, status, output, updated_at "
                "FROM task_stages WHERE task_target_id=? ORDER BY stage_id",
                (target["id"],)
            ).fetchall()
            target["stages"] = [dict(s) for s in stages]

            vulns = conn.execute(
                "SELECT id, title, description, risk_type, level, suggestion "
                "FROM vulnerabilities WHERE task_target_id=?",
                (target["id"],)
            ).fetchall()
            target["vulnerabilities"] = [dict(v) for v in vulns]
            targets.append(target)

        task["targets"] = targets
    return task


# ─────────────────────────────────────────────────────────────────────────────
# Tasks — create
# ─────────────────────────────────────────────────────────────────────────────
def task_create(data: dict) -> dict:
    """
    data keys:
      id, llm_profile_id, llm_profile_name, llm_model,
      prompt, language, has_oauth,
      targets: list of { id, name, url, stage_ids, stages: [{stage_id, name}] }
    """
    with get_db() as conn:
        conn.execute(
            "INSERT INTO tasks (id, status, created_at, llm_profile_id, "
            "  llm_profile_name, llm_model, prompt, language, has_oauth) "
            "VALUES (?, 'pending', ?, ?, ?, ?, ?, ?, ?)",
            (data["id"], now_iso(), data["llm_profile_id"], data["llm_profile_name"],
             data["llm_model"], data.get("prompt", ""), data.get("language", "zh"),
             1 if data.get("has_oauth") else 0)
        )
        for target in data["targets"]:
            stage_ids_json = json.dumps(target["stage_ids"]) if target.get("stage_ids") is not None else None
            conn.execute(
                "INSERT INTO task_targets (id, task_id, position, name, url, stage_ids, status) "
                "VALUES (?, ?, ?, ?, ?, ?, 'pending')",
                (target["id"], data["id"], target["position"],
                 target.get("name"), target["url"], stage_ids_json)
            )
            for stage in target.get("stages", []):
                conn.execute(
                    "INSERT INTO task_stages (id, task_target_id, stage_id, name, status, output) "
                    "VALUES (?, ?, ?, ?, 'pending', '')",
                    (stage["id"], target["id"], stage["stage_id"], stage["name"])
                )
    return task_get(data["id"])


# ─────────────────────────────────────────────────────────────────────────────
# Tasks — status updates (called from monitor_task thread)
# ─────────────────────────────────────────────────────────────────────────────
def task_set_running(task_id: str, log_file: str):
    with get_db() as conn:
        conn.execute(
            "UPDATE tasks SET status='running', log_file=? WHERE id=?",
            (log_file, task_id)
        )


def task_set_done(task_id: str, status: str, error: str | None = None):
    with get_db() as conn:
        conn.execute(
            "UPDATE tasks SET status=?, completed_at=?, error=? WHERE id=?",
            (status, now_iso(), error, task_id)
        )


def task_set_current_target(task_id: str, idx: int):
    with get_db() as conn:
        conn.execute(
            "UPDATE tasks SET current_target_idx=? WHERE id=?",
            (idx, task_id)
        )


def target_set_running(target_id: str):
    with get_db() as conn:
        conn.execute(
            "UPDATE task_targets SET status='running', started_at=? WHERE id=?",
            (now_iso(), target_id)
        )


def target_set_done(target_id: str, score: int | None, readme: str | None):
    with get_db() as conn:
        conn.execute(
            "UPDATE task_targets SET status='completed', score=?, readme=?, ended_at=? WHERE id=?",
            (score, readme, now_iso(), target_id)
        )


def target_set_failed(target_id: str, error: str):
    with get_db() as conn:
        conn.execute(
            "UPDATE task_targets SET status='failed', ended_at=?, error=? WHERE id=?",
            (now_iso(), error, target_id)
        )


def stage_update(task_target_id: str, stage_id: int, status: str, output: str = ""):
    with get_db() as conn:
        conn.execute(
            "UPDATE task_stages SET status=?, output=?, updated_at=? "
            "WHERE task_target_id=? AND stage_id=?",
            (status, output, now_iso(), task_target_id, stage_id)
        )


def stages_mark_aborted(task_id: str):
    """Mark all pending/running stages as 'error' when a task is aborted."""
    with get_db() as conn:
        conn.execute(
            "UPDATE task_stages SET status='error', updated_at=? "
            "WHERE task_target_id IN (SELECT id FROM task_targets WHERE task_id=?) "
            "AND status IN ('pending', 'running')",
            (now_iso(), task_id)
        )


def task_delete(task_id: str):
    """Permanently delete a task and all its associated data (CASCADE)."""
    with get_db() as conn:
        conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))


def vulnerabilities_insert(target_id: str, vulns: list[dict]):
    with get_db() as conn:
        for v in vulns:
            conn.execute(
                "INSERT OR IGNORE INTO vulnerabilities "
                "(id, task_target_id, title, description, risk_type, level, suggestion) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (v["id"], target_id, v.get("title", ""),
                 v.get("description"), v.get("risk_type"), v.get("level"), v.get("suggestion"))
            )


# ─────────────────────────────────────────────────────────────────────────────
# Tasks — target ID lookup (for monitor_task)
# ─────────────────────────────────────────────────────────────────────────────
def task_targets_get(task_id: str) -> list[dict]:
    """Return lightweight list of targets (id, position, url, name, stage_ids)."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, position, name, url, stage_ids "
            "FROM task_targets WHERE task_id=? ORDER BY position",
            (task_id,)
        ).fetchall()
    return [_target_row_to_dict(r) for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# Tasks — has active running tasks using a given LLM profile
# ─────────────────────────────────────────────────────────────────────────────
def profile_has_active_tasks(profile_id: str) -> bool:
    with get_db() as conn:
        row = conn.execute(
            "SELECT 1 FROM tasks WHERE llm_profile_id=? AND status='running' LIMIT 1",
            (profile_id,)
        ).fetchone()
    return row is not None


# ─────────────────────────────────────────────────────────────────────────────
# Saved configs
# ─────────────────────────────────────────────────────────────────────────────
def configs_list() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM saved_configs ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def config_create(data: dict) -> dict:
    with get_db() as conn:
        conn.execute(
            "INSERT INTO saved_configs (id,name,created_at,url,stage_ids,prompt,language,"
            "llm_profile_id,llm_profile_name,oauth_client_id,oauth_client_secret,"
            "oauth_token_url,oauth_scope) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (data["id"], data["name"], data["created_at"], data["url"],
             data.get("stage_ids"), data.get("prompt", ""), data.get("language", "zh"),
             data.get("llm_profile_id"), data.get("llm_profile_name"),
             data.get("oauth_client_id"), data.get("oauth_client_secret"),
             data.get("oauth_token_url"), data.get("oauth_scope"))
        )
        row = conn.execute(
            "SELECT * FROM saved_configs WHERE id=?", (data["id"],)
        ).fetchone()
    return dict(row)


def config_delete(config_id: str):
    with get_db() as conn:
        conn.execute("DELETE FROM saved_configs WHERE id=?", (config_id,))


# ─────────────────────────────────────────────────────────────────────────────
# Self-test (run standalone: python db.py)
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uuid

    test_db = SCRIPT_DIR / "_test_mcp_scan.db"
    test_db.unlink(missing_ok=True)  # clean slate
    DB_FILE = test_db  # override for test

    print(f"Creating test DB at {test_db}")
    init_db()

    # Create LLM profile
    pid = str(uuid.uuid4())[:8]
    llm_profile_create({
        "id": pid, "name": "Test LLM", "base_url": "https://api.test.com/v1",
        "api_key": "sk-test-xxx", "model": "test-model", "is_default": True,
    })
    profiles = llm_profiles_list()
    assert len(profiles) == 1, f"Expected 1 profile, got {len(profiles)}"
    assert profiles[0]["name"] == "Test LLM"
    print(f"  ✓ LLM profile created: {profiles[0]['id']}")

    # Create task with 2 targets
    task_id = str(uuid.uuid4())[:8]
    t1_id = str(uuid.uuid4())[:8]
    t2_id = str(uuid.uuid4())[:8]
    s1_id = str(uuid.uuid4())[:8]
    s2_id = str(uuid.uuid4())[:8]
    s3_id = str(uuid.uuid4())[:8]

    task_create({
        "id": task_id,
        "llm_profile_id": pid,
        "llm_profile_name": "Test LLM",
        "llm_model": "test-model",
        "prompt": "test prompt",
        "language": "zh",
        "has_oauth": False,
        "targets": [
            {
                "id": t1_id, "position": 0, "name": "T1",
                "url": "http://localhost:8080/sse",
                "stage_ids": [2, 5, 11],
                "stages": [
                    {"id": s1_id, "stage_id": 1,  "name": "Info Collection"},
                    {"id": s2_id, "stage_id": 2,  "name": "Tool Poisoning"},
                    {"id": s3_id, "stage_id": 27, "name": "Vulnerability Review"},
                ],
            },
            {
                "id": t2_id, "position": 1, "name": "T2",
                "url": "http://localhost:9090/sse",
                "stage_ids": None,
                "stages": [],
            },
        ],
    })
    task = task_get(task_id)
    assert task is not None
    assert len(task["targets"]) == 2
    assert len(task["targets"][0]["stages"]) == 3
    print(f"  ✓ Task created: {task_id} with {len(task['targets'])} targets")

    # Update stage
    task_set_running(task_id, "/tmp/mcp-scan-test.log")
    target_set_running(t1_id)
    stage_update(t1_id, 1, "completed", "## Info\n\nServer info here.")
    stage_update(t1_id, 2, "running")

    task2 = task_get(task_id)
    s1 = next(s for s in task2["targets"][0]["stages"] if s["stage_id"] == 1)
    assert s1["status"] == "completed"
    assert "Info" in s1["output"]
    print(f"  ✓ Stage update verified")

    # Insert vulnerabilities
    v_id = str(uuid.uuid4())[:8]
    vulnerabilities_insert(t1_id, [{
        "id": v_id, "title": "Path Traversal", "description": "desc",
        "risk_type": "MCP18", "level": "High", "suggestion": "Fix it"
    }])
    stage_update(t1_id, 27, "completed", "## Review complete")
    target_set_done(t1_id, score=42, readme="## Report\n\nAll done.")

    task3 = task_get(task_id)
    t1 = task3["targets"][0]
    assert t1["score"] == 42
    assert len(t1["vulnerabilities"]) == 1
    assert t1["vulnerabilities"][0]["title"] == "Path Traversal"
    print(f"  ✓ Vulnerabilities inserted and verified")

    # Test list
    listed = tasks_list()
    assert any(t["id"] == task_id for t in listed)
    print(f"  ✓ Task list works: {len(listed)} task(s)")

    # Test profile has active tasks (task is 'running' at this point)
    assert profile_has_active_tasks(pid), "Should have active task"
    task_set_done(task_id, "completed")
    assert not profile_has_active_tasks(pid), "Should have no active task after done"
    print(f"  ✓ profile_has_active_tasks works")

    # LLM profile update
    llm_profile_update(pid, {"name": "Updated LLM", "api_key": "new-key"})
    updated = llm_profile_get(pid)
    assert updated["name"] == "Updated LLM"
    assert updated["api_key"] == "new-key"
    print(f"  ✓ LLM profile update works")

    # Cleanup
    test_db.unlink(missing_ok=True)
    print(f"\n✅ All DB tests passed. Test DB cleaned up.")
