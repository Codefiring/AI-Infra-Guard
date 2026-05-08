// ═══════════════════════════════════════════════════════════════
//  ACTIONS
// ═══════════════════════════════════════════════════════════════
function newScan() {
  AppState.selectedTaskId = null;
  AppState.selectedStageId = null;
  AppState.configForm = {
    name: "", url: "", stage_ids:[...ALL_STAGE_IDS], stagesOpen:false,
    prompt:"", language:"en",
    oauth_client_id:"", oauth_client_secret:"", oauth_token_url:"", oauth_scope:"",
  };
  render();
}

async function selectTask(id) {
  AppState.selectedTaskId = id;
  AppState.selectedStageId = null;
  render();
  // Fetch full task detail (includes stages) — list API omits them for performance
  try {
    const res = await fetch(`/api/tasks/${id}`);
    if (res.ok) {
      const full = await res.json();
      full.targets?.forEach(t => t.stages?.forEach((s, i) => { s.position = i + 1; }));
      const idx = AppState.tasks.findIndex(t => t.id === id);
      if (idx >= 0) AppState.tasks[idx] = full; else AppState.tasks.unshift(full);
      render();
    }
  } catch(e) { /* backend unavailable */ }
  // Auto-connect SSE if task is running
  const task = AppState.tasks.find(t => t.id === id);
  if (task && (task.status === "running" || task.status === "pending")) connectToTask(id);
}

function togglePanel(name) {
  AppState.panelOpen[name] = !AppState.panelOpen[name];
  render();
}

function toggleStage(stageId, checked) {
  const ids = AppState.configForm.stage_ids;
  if (checked && !ids.includes(stageId)) ids.push(stageId);
  if (!checked) {
    const i = ids.indexOf(stageId);
    if (i >= 0) ids.splice(i, 1);
  }
  render();
}

function toggleAllStages(select) {
  AppState.configForm.stage_ids = select ? ALL_STAGES.map(s => s.id) : [];
  render();
}

function toggleVuln(id) {
  if (AppState.expandedVulns.has(id)) AppState.expandedVulns.delete(id);
  else AppState.expandedVulns.add(id);
  render();
}

// ── LLM Modal actions ──
function openLlmModal() {
  AppState.showLlmModal = true;
  AppState.llmFormOpen = false;
  AppState.editingProfileId = null;
  AppState.llmForm = { name:"", base_url:"https://openrouter.ai/api/v1", api_key:"", model:"", is_default:false };
  render();
}

function closeLlmModal() {
  AppState.showLlmModal = false;
  AppState.llmFormOpen = false;
  render();
}

function editLlmProfile(id) {
  const p = AppState.llmProfiles.find(p => p.id === id);
  if (!p) return;
  AppState.editingProfileId = id;
  AppState.llmFormOpen = true;
  AppState.llmForm = { name:p.name, base_url:p.base_url, api_key:"", model:p.model, is_default:p.is_default };
  renderLlmModal();
}

function cancelLlmForm() {
  AppState.llmFormOpen = false;
  AppState.editingProfileId = null;
  renderLlmModal();
}


function confirmDeleteLlm(id) {
  const p = AppState.llmProfiles.find(p => p.id === id);
  if (!p) return;
  if (!confirm(`Delete "${p.name}"?`)) return;
  deleteLlmProfile(id);
}

// ═══════════════════════════════════════════════════════════════
//  INIT
// ═══════════════════════════════════════════════════════════════
window.addEventListener("DOMContentLoaded", async () => {
  // Initialize with mock data for Phase 1 standalone testing
  initMockData();
  render();

  // Try to load real data from backend (will silently fail if not running)
  await Promise.all([loadTasks(), loadLlmProfiles(), loadSavedConfigs()]);

  // Auto-connect SSE for any running task
  const running = AppState.tasks.find(t => t.status === "running");
  if (running && AppState.selectedTaskId === running.id) connectToTask(running.id);
});
