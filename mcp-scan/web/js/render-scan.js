// ═══════════════════════════════════════════════════════════════
//  SCAN MODE
// ═══════════════════════════════════════════════════════════════
function renderScanMode(task) {
  const target = task.targets[0];
  if (!target) return `<div style="color:var(--text-muted);text-align:center;padding:40px;">No scan target</div>`;
  const isRunning = task.status === "running" || task.status === "pending"
    || AppState.eventSource !== null;
  const stages = target.stages || [];
  const completed = stages.filter(s => s.status === "completed").length;
  const total = stages.length;
  const pct = total > 0 ? Math.round((completed / total) * 100) : 0;

  return `
  <div style="display:flex;flex-direction:column;height:100%;">
    <div style="display:flex;flex:1;min-height:0;">

      <!-- Left: Stage progress -->
      <div id="scan-left" style="width:${AppState.layout.scanLeftPct}%;flex-shrink:0;display:flex;flex-direction:column;gap:12px;">
        <!-- Header card -->
        <div class="card" style="padding:14px 16px;">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;">
            <div style="display:flex;align-items:center;gap:10px;">
              <div class="dot ${isRunning?"dot-running":"dot-completed"}"></div>
              <div>
                <div style="font-size:13px;font-weight:600;">${target.name||target.url.replace(/^https?:\/\//,"").substring(0,30)}</div>
                <div style="font-size:11px;color:var(--text-muted);">${target.url}</div>
              </div>
            </div>
            <div style="display:flex;gap:6px;">
              ${isRunning ? `<button class="btn-danger" style="font-size:11px;padding:5px 10px;" onclick="abortTask('${task.id}')">Stop Scan</button>` : ""}
              <button class="btn-secondary" style="font-size:11px;padding:5px 10px;" onclick="newScan()">New Scan</button>
            </div>
          </div>
          <div style="display:flex;justify-content:space-between;margin-bottom:6px;">
            <span style="font-size:11px;color:var(--text-muted);">${completed} / ${total} stages completed</span>
            <span style="font-size:11px;color:var(--text-muted);">${pct}%</span>
          </div>
          <div class="progress-bar-track">
            <div class="progress-bar-fill" style="width:${pct}%;"></div>
          </div>
        </div>

        <!-- Stage cards -->
        <div class="card" style="flex:1;overflow-y:auto;padding:10px;">
          ${stages.map(s => {
            const active = AppState.selectedStageId === s.stage_id;
            return `<div class="stage-card ${s.status} ${active?"active":""}" id="stage-${s.stage_id}"
              onclick="AppState.selectedStageId=${s.stage_id};render()">
              <span class="stage-icon">${stageIcon(s.status)}</span>
              <div style="flex:1;min-width:0;">
                <div style="font-size:12px;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
                  <span style="color:var(--text-muted);margin-right:6px;">${s.position}</span>${s.name}
                </div>
              </div>
              ${s.status==="running" ? `<span style="font-size:10px;color:var(--blue);">Running</span>` : ""}
              ${s.status==="completed" ? `<svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M2 6.5l3 3 5-5" stroke="var(--green)" stroke-width="1.5" stroke-linecap="round"/></svg>` : ""}
            </div>`;
          }).join("")}
        </div>
      </div>

      <div class="resize-handle-h" onmousedown="startScanResize(event)"></div>

      <!-- Right: Results -->
      <div style="flex:1;display:flex;flex-direction:column;gap:12px;min-width:0;">
        ${renderResultsPanel(task, target)}
      </div>
    </div>
  </div>`;
}

function renderResultsPanel(task, target) {
  const stageList = target.stages || [];
  const selectedStage = stageList.find(s => s.stage_id === AppState.selectedStageId);

  // If a completed stage is selected → show its output
  if (selectedStage && selectedStage.status === "completed" && selectedStage.output) {
    return `
    <div class="card" style="padding:14px 16px;flex-shrink:0;">
      <div style="display:flex;align-items:center;gap:10px;">
        <span style="color:var(--green);">✓</span>
        <span style="font-size:13px;font-weight:600;">${selectedStage.name}</span>
        <span class="badge-count" style="margin-left:auto;cursor:pointer;" onclick="AppState.selectedStageId=null;render()">✕ Close</span>
      </div>
    </div>
    <div class="card" style="flex:1;overflow-y:auto;padding:16px;">
      ${renderVulnStageOutput(selectedStage.output)}
    </div>`;
  }

  // If final stage completed → show final report
  const finalStage = stageList[stageList.length - 1];
  if (finalStage && finalStage.status === "completed" && target.score !== null) {
    return renderFinalReport(target);
  }

  // Scanning in progress — show live log viewer
  const completed = stageList.filter(s => s.status === "completed").length;
  const total = stageList.length;
  const runningStage = stageList.find(s => s.status === "running");
  const logHtml = AppState.logLines.length
    ? AppState.logLines.map(l => `<div class="log-line">${escapeHtml(l)}</div>`).join("")
    : `<div style="color:var(--text-muted);text-align:center;padding-top:24px;font-family:sans-serif;">Waiting for logs…</div>`;
  return `
  <div class="card" style="flex:1;display:flex;flex-direction:column;min-height:0;overflow:hidden;">
    <div style="padding:10px 16px;border-bottom:1px solid var(--border);flex-shrink:0;display:flex;align-items:center;justify-content:space-between;gap:12px;">
      <div style="display:flex;align-items:center;gap:8px;min-width:0;">
        ${target.status==="failed"
          ? `<span style="color:var(--red);font-size:12px;">✕</span><span style="font-size:12px;font-weight:600;color:var(--red);">Scan Failed</span>`
          : runningStage
            ? `<span class="dot dot-running" style="flex-shrink:0;"></span><span style="font-size:12px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${runningStage.name}</span>`
            : `<span style="font-size:12px;color:var(--text-muted);">Waiting to start…</span>`}
        ${target.error ? `<span style="font-size:11px;color:var(--red);margin-left:4px;">${escapeHtml(target.error)}</span>` : ""}
      </div>
      <span style="font-size:11px;color:var(--text-muted);flex-shrink:0;">${completed} / ${total} stages</span>
    </div>
    <div id="log-viewer" style="flex:1;overflow-y:auto;padding:10px 14px;font-family:'Courier New',monospace;font-size:11px;line-height:1.6;color:#9ca3af;background:#0d0d12;">
      ${logHtml}
    </div>
  </div>`;
}

function renderFinalReport(target) {
  const sc = target.score;
  const clr = scoreColor(sc);
  const circumference = 2 * Math.PI * 15.9;
  const dash = (sc / 100) * circumference;

  const vulns = target.vulnerabilities || [];
  const vulnRows = vulns.map((v,i) => {
    const open = AppState.expandedVulns.has(v.id);
    return `
    <div class="vuln-row">
      <div class="vuln-header" onclick="toggleVuln('${v.id}')">
        <span style="flex:1;font-size:13px;font-weight:500;">${v.title}</span>
        ${v.tool_name ? `<code style="font-size:10px;padding:2px 6px;background:rgba(96,165,250,0.12);color:#60a5fa;border-radius:4px;margin-right:4px;white-space:nowrap;">${escapeHtml(v.tool_name)}</code>` : ""}
        <span style="font-size:11px;color:var(--text-muted);margin-right:8px;">${v.risk_type||""}</span>
        ${levelBadge(v.level)}
        <span style="color:var(--text-muted);font-size:12px;margin-left:8px;">${open?"▲":"▼"}</span>
      </div>
      ${open ? `<div class="vuln-body">
        <div style="margin-bottom:10px;">
          <div style="font-size:11px;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.05em;margin-bottom:4px;">Description</div>
          <div class="markdown-body" style="font-size:12px;">${renderMarkdown(v.description||"")}</div>
        </div>
        <div>
          <div style="font-size:11px;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.05em;margin-bottom:4px;">Suggestion</div>
          <div class="markdown-body" style="font-size:12px;">${renderMarkdown(v.suggestion||"")}</div>
        </div>
      </div>` : ""}
    </div>`;
  }).join("");

  return `
  <!-- Score header -->
  <div class="card" style="padding:16px;flex-shrink:0;">
    <div style="display:flex;align-items:center;gap:20px;">
      <svg viewBox="0 0 36 36" style="width:80px;height:80px;flex-shrink:0;">
        <circle cx="18" cy="18" r="15.9" fill="none" stroke="rgba(255,255,255,0.06)" stroke-width="2.5"/>
        <circle cx="18" cy="18" r="15.9" fill="none"
          stroke="${clr}" stroke-width="2.5"
          stroke-dasharray="${(sc/100)*100} ${100-sc}"
          stroke-linecap="round"
          transform="rotate(-90 18 18)"
          style="transition:stroke-dasharray 0.8s ease;"/>
        <text x="18" y="21" text-anchor="middle" font-size="9" fill="${clr}" font-weight="700">${sc}</text>
      </svg>
      <div style="flex:1;">
        <div style="font-size:13px;color:var(--text-muted);margin-bottom:4px;">Security Score</div>
        <div style="font-size:24px;font-weight:700;color:${clr};">${sc} <span style="font-size:14px;font-weight:400;">/ 100</span></div>
        <div style="font-size:12px;color:var(--text-muted);margin-top:4px;">
          Found ${vulns.length} issues ·
          High ${vulns.filter(v=>v.level&&(v.level.toLowerCase().includes("high")||v.level.includes("高"))).length} ·
          Medium ${vulns.filter(v=>v.level&&(v.level.toLowerCase().includes("med")||v.level.includes("中"))).length}
        </div>
      </div>
      ${target.url ? `<div style="font-size:11px;color:var(--text-muted);text-align:right;">${target.url}</div>` : ""}
    </div>
  </div>

  <!-- Vuln list -->
  ${vulns.length > 0 ? `
  <div class="card" style="padding:16px;flex-shrink:0;max-height:300px;overflow-y:auto;">
    <div style="font-size:13px;font-weight:600;margin-bottom:12px;">Vulnerabilities</div>
    ${vulnRows}
  </div>` : ""}

  <!-- Full report -->
  ${target.readme ? `
  <div class="card" style="flex:1;overflow-y:auto;padding:16px;">
    <div style="font-size:13px;font-weight:600;margin-bottom:12px;">Full Report</div>
    <div class="markdown-body">${renderMarkdown(target.readme)}</div>
  </div>` : ""}`;
}

