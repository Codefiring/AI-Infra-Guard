// ═══════════════════════════════════════════════════════════════
//  SIDEBAR
// ═══════════════════════════════════════════════════════════════
function renderSidebar() {
  document.getElementById("sidebar").style.width = AppState.layout.sidebarWidth + "px";
  const filtered = AppState.tasks.filter(t => {
    const q = AppState.taskSearchQuery.toLowerCase();
    if (!q) return true;
    if (t.id.toLowerCase().startsWith(q)) return true;
    return t.targets.some(tt => tt.url.toLowerCase().includes(q) || (tt.name||"").toLowerCase().includes(q));
  });

  const taskItems = filtered.map(t => {
    const sel = t.id === AppState.selectedTaskId;
    const dotClass = t.status === "running" ? "dot-running" : t.status === "completed" ? "dot-completed" : "dot-failed";
    const displayName = taskDisplayName(t);
    return `<div class="task-item ${sel?"selected":""}" onclick="selectTask('${t.id}')">
      <div style="display:flex;align-items:center;gap:8px;">
        <div class="dot ${dotClass}"></div>
        <span style="font-size:12px;font-weight:500;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${displayName}</span>
        <button class="btn-icon" style="flex-shrink:0;opacity:0.45;font-size:11px;padding:2px 5px;"
          onclick="event.stopPropagation();deleteTask('${t.id}')" title="Delete task">✕</button>
      </div>
    </div>`;
  }).join("");

  document.getElementById("sidebar").innerHTML = `
    <button class="btn-primary" style="margin-bottom:10px;font-size:13px;padding:9px;" onclick="newScan()">+ New Scan</button>
    <div style="margin-bottom:10px;">
      <input type="text" placeholder="Search tasks..." value="${AppState.taskSearchQuery}"
        oninput="AppState.taskSearchQuery=this.value;renderSidebar()"
        style="font-size:12px;padding:7px 10px;">
    </div>
    <div style="flex:1;overflow-y:auto;">
      ${filtered.length === 0
        ? `<div style="text-align:center;color:var(--text-muted);font-size:12px;margin-top:20px;">No tasks found</div>`
        : taskItems}
    </div>`;
}

// ═══════════════════════════════════════════════════════════════
//  MAIN PANEL ROUTING
// ═══════════════════════════════════════════════════════════════
function renderMainPanel() {
  const task = AppState.tasks.find(t => t.id === AppState.selectedTaskId);
  if (!task || AppState.selectedTaskId === null) {
    document.getElementById("main-panel").innerHTML = renderConfigMode();
  } else {
    document.getElementById("main-panel").innerHTML = renderScanMode(task);
  }
}

function render() {
  renderSidebar();
  renderMainPanel();
  renderLlmModal();
  updateLogViewer();
}

