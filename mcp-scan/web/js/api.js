// ── Scan start ──
async function startScan() {
  const form = AppState.configForm;

  // Validate
  if (!form.url || !form.url.startsWith("http")) { alert("Please enter a valid URL (must start with http:// or https://)"); return; }
  if (form.stage_ids.length === 0) { alert("Please select at least one scan stage"); return; }
  if (!AppState.selectedLlmProfileId) { alert("Please configure an LLM service first"); return; }

  const body = {
    name: form.name || "",
    llm_profile_id: AppState.selectedLlmProfileId,
    url: form.url,
    stage_ids: form.stage_ids,
    prompt: form.prompt,
    language: form.language,
    oauth_client_id:     form.oauth_client_id     || null,
    oauth_client_secret: form.oauth_client_secret || null,
    oauth_token_url:     form.oauth_token_url     || null,
    oauth_scope:         form.oauth_scope         || null,
  };

  try {
    const res = await fetch("/api/tasks", { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body) });
    if (!res.ok) { const e = await res.json(); alert("Failed to create task: " + (e.detail || res.status)); return; }
    const task = await res.json();
    AppState.tasks.unshift(task);
    AppState.selectedTaskId = task.id;
    AppState.selectedStageId = null;
    render();
    connectToTask(task.id);
  } catch(e) {
    alert("Cannot connect to backend. Make sure web_server.py is running on http://localhost:7788");
  }
}

// ── SSE ──
function connectToTask(taskId) {
  if (AppState.eventSource) { AppState.eventSource.close(); AppState.eventSource = null; }
  let retries = 0;
  function connect() {
    const es = new EventSource(`/api/tasks/${taskId}/stream`);
    AppState.eventSource = es;

    es.addEventListener("init", e => {
      const task = JSON.parse(e.data);
      // Assign sequential display positions to stages loaded from DB
      task.targets?.forEach(t => t.stages?.forEach((s, i) => { s.position = i + 1; }));
      const idx = AppState.tasks.findIndex(t => t.id === taskId);
      if (idx >= 0) AppState.tasks[idx] = task; else AppState.tasks.unshift(task);
      render();
    });
    es.addEventListener("stage", e => {
      const ev = JSON.parse(e.data);
      const task = AppState.tasks.find(t => t.id === taskId);
      if (!task) return;
      const target = task.targets[0];
      if (!target) return;
      const stage = target.stages.find(s => s.stage_id === ev.stage_id);
      if (stage) { stage.status = ev.status; if (ev.output) stage.output = ev.output; }
      if (ev.status === "running" && AppState.selectedTaskId === taskId && AppState.selectedStageId === null) {
        AppState.selectedStageId = null;
      }
      render();
      document.getElementById(`stage-${ev.stage_id}`)?.scrollIntoView({ behavior:"smooth", block:"nearest" });
    });
    es.addEventListener("result", e => {
      const ev = JSON.parse(e.data);
      const task = AppState.tasks.find(t => t.id === taskId);
      if (!task) return;
      const target = task.targets[ev.target_index];
      if (target) Object.assign(target, { score:ev.score, vulnerabilities:ev.results, readme:ev.readme, status:"completed" });
      render();
    });
    es.addEventListener("done", e => {
      const ev = JSON.parse(e.data);
      const task = AppState.tasks.find(t => t.id === taskId);
      if (task) task.status = ev.status;
      es.close(); AppState.eventSource = null;
      render();
    });
    es.onerror = () => {
      es.close();
      if (retries < 3) { retries++; setTimeout(connect, 3000); }
    };
  }
  connect();
}

async function abortTask(id) {
  if (!confirm("Abort this scan task?")) return;
  if (AppState.eventSource) { AppState.eventSource.close(); AppState.eventSource = null; }
  // Immediately patch local state for instant visual feedback
  const task = AppState.tasks.find(t => t.id === id);
  if (task) {
    task.status = "failed";
    task.targets?.forEach(target => {
      target.stages?.forEach(s => {
        if (s.status === "running" || s.status === "pending") s.status = "error";
      });
    });
    render();
  }
  try {
    await fetch(`/api/tasks/${id}`, { method:"DELETE" });
    await loadTasks();
  } catch(e) {
    render();
  }
}

async function deleteTask(id) {
  if (!confirm("Delete this task and all its data? This cannot be undone.")) return;
  if (AppState.eventSource && AppState.selectedTaskId === id) {
    AppState.eventSource.close();
    AppState.eventSource = null;
  }
  AppState.tasks = AppState.tasks.filter(t => t.id !== id);
  if (AppState.selectedTaskId === id) AppState.selectedTaskId = null;
  render();
  try {
    await fetch(`/api/tasks/${id}/record`, { method: "DELETE" });
  } catch(e) {
    await loadTasks();
  }
}

// ── Load data ──
async function loadTasks() {
  try {
    const res = await fetch("/api/tasks");
    if (!res.ok) return;
    AppState.tasks = await res.json();
    render();
  } catch(e) { /* backend not available in Phase 1 */ }
}

async function loadSavedConfigs() {
  try {
    const r = await fetch("/api/configs");
    AppState.savedConfigs = r.ok ? await r.json() : [];
  } catch(e) { AppState.savedConfigs = []; }
}

async function saveConfig() {
  const name = prompt("Config name:", AppState.configForm.url || "New Config");
  if (!name) return;
  const form = AppState.configForm;
  await fetch("/api/configs", {
    method: "POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify({
      name,
      url: form.url,
      stage_ids: form.stage_ids.length < ALL_STAGE_IDS.length ? form.stage_ids : null,
      prompt: form.prompt,
      language: form.language,
      llm_profile_id: AppState.selectedLlmProfileId || null,
      oauth_client_id: form.oauth_client_id || null,
      oauth_client_secret: form.oauth_client_secret || null,
      oauth_token_url: form.oauth_token_url || null,
      oauth_scope: form.oauth_scope || null,
    })
  });
  await loadSavedConfigs();
  render();
}

function applyConfig(cfg) {
  const stageIds = cfg.stage_ids ? JSON.parse(cfg.stage_ids) : [...ALL_STAGE_IDS];
  AppState.configForm = {
    url: cfg.url || "",
    stage_ids: stageIds,
    stagesOpen: false,
    prompt: cfg.prompt || "",
    language: cfg.language || "zh",
    oauth_client_id: cfg.oauth_client_id || "",
    oauth_client_secret: cfg.oauth_client_secret || "",
    oauth_token_url: cfg.oauth_token_url || "",
    oauth_scope: cfg.oauth_scope || "",
  };
  if (cfg.llm_profile_id) {
    const match = AppState.llmProfiles.find(p => p.id === cfg.llm_profile_id);
    if (match) AppState.selectedLlmProfileId = match.id;
  }
  AppState.selectedTaskId = null;
  render();
}

async function deleteSavedConfig(id) {
  await fetch(`/api/configs/${id}`, { method: "DELETE" });
  await loadSavedConfigs();
  render();
}

async function loadLlmProfiles() {
  try {
    const res = await fetch("/api/llm-profiles");
    if (!res.ok) return;
    const profiles = await res.json();
    AppState.llmProfiles = profiles;
    // Keep current selection only if it exists in the real backend profile list;
    // otherwise fall back to default (or first). This prevents the mock "llm-1"
    // ID from persisting and causing a "profile not found" 404 on scan start.
    const currentValid = profiles.find(p => p.id === AppState.selectedLlmProfileId);
    if (!currentValid) {
      const def = profiles.find(p => p.is_default);
      AppState.selectedLlmProfileId = def?.id || profiles[0]?.id || null;
    }
    render();
  } catch(e) { /* backend not available */ }
}

async function saveLlmProfile() {
  const f = AppState.llmForm;
  if (!f.name || !f.base_url || !f.model) { alert("Name, API URL, and Model are required"); return; }
  if (!AppState.editingProfileId && !f.api_key) { alert("API Key is required"); return; }

  const body = { name:f.name, base_url:f.base_url, model:f.model, is_default:f.is_default };
  if (f.api_key) body.api_key = f.api_key;

  try {
    let res;
    if (AppState.editingProfileId) {
      res = await fetch(`/api/llm-profiles/${AppState.editingProfileId}`, { method:"PUT", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body) });
    } else {
      if (!f.api_key) { alert("API Key is required"); return; }
      body.api_key = f.api_key;
      res = await fetch("/api/llm-profiles", { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body) });
    }
    if (!res.ok) { const e = await res.json(); alert("Save failed: " + (e.detail || res.status)); return; }
    await loadLlmProfiles();
    closeLlmModal();
  } catch(e) {
    // Mock: add locally for Phase 1 testing
    const id = "llm-" + Date.now();
    const newP = { id, ...body, created_at: new Date().toISOString() };
    if (f.is_default) AppState.llmProfiles.forEach(p => p.is_default = false);
    AppState.llmProfiles.push(newP);
    if (!AppState.selectedLlmProfileId || f.is_default) AppState.selectedLlmProfileId = id;
    closeLlmModal();
  }
}

function confirmDeleteLlm(id) {
  const p = AppState.llmProfiles.find(p => p.id === id);
  if (!p) return;
  if (!confirm(`Delete "${p.name}"?`)) return;
  deleteLlmProfile(id);
}

async function deleteLlmProfile(id) {
  try {
    await fetch(`/api/llm-profiles/${id}`, { method:"DELETE" });
    await loadLlmProfiles();
  } catch(e) {
    AppState.llmProfiles = AppState.llmProfiles.filter(p => p.id !== id);
    if (AppState.selectedLlmProfileId === id) AppState.selectedLlmProfileId = AppState.llmProfiles[0]?.id || null;
    renderLlmModal();
    render();
  }
}

// ── Export / Import ──
function exportConfig() {
  const form = AppState.configForm;
  const profile = AppState.llmProfiles.find(p => p.id === AppState.selectedLlmProfileId);
  const data = {
    version: 2,
    llm_profile_name: profile?.name || null,
    url: form.url,
    stage_ids: form.stage_ids.length < ALL_STAGE_IDS.length ? form.stage_ids : null,
    prompt: form.prompt,
    language: form.language,
    oauth_client_id: form.oauth_client_id || null,
    oauth_client_secret: form.oauth_client_secret || null,
    oauth_token_url: form.oauth_token_url || null,
    oauth_scope: form.oauth_scope || null,
  };
  const blob = new Blob([JSON.stringify(data, null, 2)], { type:"application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  const today = new Date().toISOString().slice(0,10);
  a.href = url; a.download = `mcp-scan-config-${today}.json`; a.click();
  URL.revokeObjectURL(url);
}

function importConfig() { document.getElementById("import-input").click(); }

function handleImportFile(event) {
  const file = event.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = e => {
    try {
      const data = JSON.parse(e.target.result);
      let url = "", stage_ids = [...ALL_STAGE_IDS];
      if (data.version === 2) {
        // New single-URL format
        url = data.url || "";
        stage_ids = data.stage_ids || [...ALL_STAGE_IDS];
      } else if (data.version === 1 && Array.isArray(data.targets) && data.targets.length > 0) {
        // Backward compat: take first target
        url = data.targets[0].url || "";
        stage_ids = data.targets[0].stage_ids || [...ALL_STAGE_IDS];
      } else {
        alert("Invalid configuration file format"); return;
      }
      AppState.configForm = {
        url,
        stage_ids,
        stagesOpen: false,
        prompt: data.prompt || "",
        language: data.language || "zh",
        oauth_client_id: data.oauth_client_id || "",
        oauth_client_secret: data.oauth_client_secret || "",
        oauth_token_url: data.oauth_token_url || "",
        oauth_scope: data.oauth_scope || "",
      };
      // Match LLM profile by name
      if (data.llm_profile_name) {
        const match = AppState.llmProfiles.find(p => p.name.toLowerCase() === data.llm_profile_name.toLowerCase());
        if (match) {
          AppState.selectedLlmProfileId = match.id;
        } else {
          setTimeout(() => alert(`LLM service "${data.llm_profile_name}" not found — please select one manually`), 100);
        }
      }
      AppState.selectedTaskId = null;
      AppState.panelOpen.targets = true;
      render();
    } catch(err) { alert("Failed to parse configuration file: " + err.message); }
  };
  reader.readAsText(file);
  event.target.value = "";
}

