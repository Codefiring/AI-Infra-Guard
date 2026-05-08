function renderConfigMode() {
  const profiles = AppState.llmProfiles;
  const hasProfiles = profiles.length > 0;
  const form = AppState.configForm;

  // LLM selector
  const profileOptions = profiles.map(p =>
    `<option value="${p.id}" ${p.id===AppState.selectedLlmProfileId?"selected":""}>${p.is_default?"★ ":""}${p.name}</option>`
  ).join("");

  const urlInvalid = form.url && !form.url.startsWith("http");
  const noStages = form.stage_ids.length === 0;
  const noProfile = !hasProfiles;
  const noUrl = !form.url;
  const scanDisabled = noProfile || noUrl || urlInvalid || noStages;

  return `
  <div style="display:flex;gap:16px;align-items:flex-start;">
  <div style="flex:1;min-width:0;max-width:700px;">
    <div style="margin-bottom:20px;">
      <h2 style="font-size:18px;font-weight:700;margin-bottom:4px;" class="gradient-text">New Scan Task</h2>
      <div style="font-size:13px;color:var(--text-muted);">Configure target and parameters, then start scan</div>
    </div>

    <!-- Panel 1: Target URL + Stages -->
    <div class="card" style="margin-bottom:14px;">
      <div class="panel-header" onclick="togglePanel('targets')">
        <div style="display:flex;align-items:center;gap:10px;">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="6" stroke="#60a5fa" stroke-width="1.5"/><circle cx="8" cy="8" r="2.5" fill="#60a5fa"/></svg>
          <span style="font-weight:600;font-size:14px;">Scan Target</span>
        </div>
        <span class="panel-arrow ${AppState.panelOpen.targets?"open":""}">▶</span>
      </div>
      ${AppState.panelOpen.targets ? `
      <div class="panel-content">
        <!-- Task name input -->
        <div style="margin-bottom:12px;">
          <label style="font-size:12px;color:var(--text-muted);display:block;margin-bottom:4px;">Task Name <span style="opacity:0.5;">(optional)</span></label>
          <input type="text" value="${escapeHtml(form.name || '')}" placeholder="Leave blank to auto-generate"
            oninput="AppState.configForm.name=this.value"
            style="font-size:12px;padding:7px 10px;">
        </div>
        <!-- URL input -->
        <div style="margin-bottom:12px;">
          <label style="font-size:12px;color:var(--text-muted);display:block;margin-bottom:4px;">Target URL</label>
          <input type="url" value="${form.url}" placeholder="http://host:port/sse"
            style="${urlInvalid ? "border-color:var(--red);" : ""}"
            oninput="AppState.configForm.url=this.value">
          ${urlInvalid ? `<div style="color:var(--red);font-size:11px;margin-top:4px;">⚠ URL must start with http:// or https://</div>` : ""}
        </div>

        <!-- Stage selector toggle -->
        <div style="display:flex;align-items:center;justify-content:space-between;cursor:pointer;padding:6px 8px;border-radius:6px;border:1px solid var(--border);background:rgba(255,255,255,0.02);"
          onclick="AppState.configForm.stagesOpen=!AppState.configForm.stagesOpen;render()">
          <span style="font-size:12px;color:var(--text-muted);">Scan Stages</span>
          <div style="display:flex;align-items:center;gap:8px;">
            <span class="badge-count ${noStages?"badge-high":""}">${form.stage_ids.length}/15 selected</span>
            <span style="font-size:10px;color:var(--text-muted);">${form.stagesOpen?"▲":"▼"}</span>
          </div>
        </div>
        ${noStages ? `<div style="color:var(--red);font-size:11px;margin-top:4px;padding:0 4px;">⚠ Select at least one stage</div>` : ""}

        ${form.stagesOpen ? renderStageCheckboxes(ALL_STAGES, form.stage_ids) : ""}
      </div>` : ""}
    </div>

    <!-- Panel 2: OAuth -->
    <div class="card" style="margin-bottom:14px;">
      <div class="panel-header" onclick="togglePanel('oauth')">
        <div style="display:flex;align-items:center;gap:10px;">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M8 2a3 3 0 0 0-3 3v2H4a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1V8a1 1 0 0 0-1-1h-1V5a3 3 0 0 0-3-3z" stroke="#a78bfa" stroke-width="1.5" fill="none"/></svg>
          <span style="font-weight:600;font-size:14px;">OAuth Auth</span>
          ${form.oauth_client_id ? `<span class="badge-count">Configured</span>` : `<span style="font-size:11px;color:var(--text-muted);">Optional</span>`}
        </div>
        <span class="panel-arrow ${AppState.panelOpen.oauth?"open":""}">▶</span>
      </div>
      ${AppState.panelOpen.oauth ? `
      <div class="panel-content">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
          <div>
            <label style="font-size:12px;color:var(--text-muted);display:block;margin-bottom:4px;">Client ID</label>
            <input type="text" value="${form.oauth_client_id}" placeholder="my-client-id"
              oninput="AppState.configForm.oauth_client_id=this.value">
          </div>
          <div>
            <label style="font-size:12px;color:var(--text-muted);display:block;margin-bottom:4px;">Client Secret</label>
            <input type="password" value="${form.oauth_client_secret}" placeholder="••••••••"
              oninput="AppState.configForm.oauth_client_secret=this.value">
          </div>
          <div>
            <label style="font-size:12px;color:var(--text-muted);display:block;margin-bottom:4px;">Token URL</label>
            <input type="url" value="${form.oauth_token_url}" placeholder="https://auth.example.com/oauth/token"
              oninput="AppState.configForm.oauth_token_url=this.value">
          </div>
          <div>
            <label style="font-size:12px;color:var(--text-muted);display:block;margin-bottom:4px;">Scope <span style="color:var(--text-muted)">(optional)</span></label>
            <input type="text" value="${form.oauth_scope}" placeholder="mcp:read"
              oninput="AppState.configForm.oauth_scope=this.value">
          </div>
        </div>
      </div>` : ""}
    </div>

    <!-- Panel 3: Prompt -->
    <div class="card" style="margin-bottom:14px;">
      <div class="panel-header" onclick="togglePanel('prompt')">
        <div style="display:flex;align-items:center;gap:10px;">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><rect x="2" y="3" width="12" height="10" rx="2" stroke="#34d399" stroke-width="1.5" fill="none"/><path d="M5 7h6M5 10h4" stroke="#34d399" stroke-width="1.5" stroke-linecap="round"/></svg>
          <span style="font-weight:600;font-size:14px;">Custom Prompt</span>
          ${form.prompt ? `<span class="badge-count">Set</span>` : `<span style="font-size:11px;color:var(--text-muted);">Optional</span>`}
        </div>
        <span class="panel-arrow ${AppState.panelOpen.prompt?"open":""}">▶</span>
      </div>
      ${AppState.panelOpen.prompt ? `
      <div class="panel-content">
        <div style="margin-bottom:10px;">
          <label style="font-size:12px;color:var(--text-muted);display:block;margin-bottom:4px;">Scan prompt</label>
          <textarea rows="4" placeholder="e.g. Focus on path traversal and command injection."
            oninput="AppState.configForm.prompt=this.value"
          >${form.prompt}</textarea>
        </div>
        <div style="display:flex;gap:10px;align-items:center;">
          <label style="font-size:12px;color:var(--text-muted);">Output language:</label>
          <select style="width:auto;padding:6px 10px;" onchange="AppState.configForm.language=this.value">
            <option value="zh" ${form.language==="zh"?"selected":""}>Chinese</option>
            <option value="en" ${form.language==="en"?"selected":""}>English</option>
          </select>
        </div>
      </div>` : ""}
    </div>

    <!-- LLM Selector -->
    <div class="card" style="margin-bottom:14px;padding:16px;">
      <div style="font-size:12px;color:var(--text-muted);margin-bottom:8px;font-weight:500;">LLM Service</div>
      ${!hasProfiles ? `
        <div style="padding:14px;border:1px dashed rgba(255,255,255,0.12);border-radius:8px;text-align:center;">
          <div style="color:var(--text-muted);font-size:13px;margin-bottom:8px;">No LLM service configured</div>
          <button class="btn-secondary" onclick="openLlmModal()">⚙ Add LLM Service</button>
        </div>
      ` : `
        <div style="display:flex;gap:10px;align-items:center;">
          <select style="flex:1;" onchange="AppState.selectedLlmProfileId=this.value">
            ${profileOptions}
          </select>
          <button class="btn-secondary" style="white-space:nowrap;" onclick="openLlmModal()">⚙ Manage</button>
        </div>
      `}
    </div>

    <!-- Save / Start -->
    <div class="card" style="padding:16px;">
      <div style="display:flex;gap:10px;margin-bottom:12px;">
        <button class="btn-secondary" style="flex:1;" onclick="saveConfig()">💾 Save Config</button>
      </div>
      <button class="btn-primary" onclick="startScan()" ${scanDisabled?"disabled":""}>
        ${noProfile ? "Configure LLM service first" : "Start Scan"}
      </button>
    </div>
  </div>
  ${renderSavedConfigsPanel()}
  </div>`;
}

function renderSavedConfigsPanel() {
  const configs = AppState.savedConfigs;
  const items = configs.length === 0
    ? `<div style="font-size:12px;color:var(--text-muted);text-align:center;padding:20px 0;">No saved configs</div>`
    : configs.map(c => {
        const cfg = JSON.stringify(c).replace(/\\/g,"\\\\").replace(/"/g,"&quot;");
        return `
        <div onclick="applyConfig(JSON.parse(this.dataset.cfg))" data-cfg="${cfg}"
             style="cursor:pointer;padding:8px 10px;border-radius:8px;margin-bottom:4px;
                    background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);
                    transition:background 0.15s;display:flex;align-items:center;gap:6px;"
             onmouseover="this.style.background='rgba(255,255,255,0.07)'"
             onmouseout="this.style.background='rgba(255,255,255,0.03)'">
          <div style="flex:1;min-width:0;">
            <div style="font-size:12px;font-weight:500;color:var(--text-main);
                        white-space:nowrap;overflow:hidden;text-overflow:ellipsis;"
                 title="${c.name}">${c.name}</div>
            <div style="font-size:10px;color:var(--text-muted);margin-top:2px;
                        white-space:nowrap;overflow:hidden;text-overflow:ellipsis;"
                 title="${c.url}">${c.url}</div>
          </div>
          <button onclick="event.stopPropagation();deleteSavedConfig('${c.id}')"
                  style="flex-shrink:0;background:none;border:none;cursor:pointer;
                         color:#6b7280;font-size:14px;padding:2px 4px;line-height:1;"
                  onmouseover="this.style.color='#f87171'" onmouseout="this.style.color='#6b7280'"
                  title="Delete">✕</button>
        </div>`;
      }).join("");

  return `
  <div style="width:220px;flex-shrink:0;padding-top:2px;">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;">
      <span style="font-size:13px;font-weight:600;color:var(--text-main);">Saved Configs</span>
    </div>
    ${items}
  </div>`;
}

function renderStageCheckboxes(stages, selectedIds) {
  const selSet = new Set(selectedIds);
  const chk = (stage) => {
    const checked = selSet.has(stage.id);
    const label = stage.name.length > 22 ? stage.name.substring(0,22)+"…" : stage.name;
    return `<label style="display:flex;align-items:center;gap:6px;font-size:11px;cursor:pointer;padding:4px;border-radius:4px;transition:background 0.1s;" onmouseover="this.style.background='rgba(255,255,255,0.04)'" onmouseout="this.style.background=''">
      <input type="checkbox" ${checked?"checked":""} onchange="toggleStage(${stage.id},this.checked)">
      <span title="${stage.risk_type} ${stage.name}" style="color:${checked?"var(--text-main)":"var(--text-muted)"};">
        <span style="font-size:10px;color:#60a5fa;margin-right:3px;">${stage.risk_type}</span>${label}
      </span>
    </label>`;
  };

  return `
  <div style="margin-top:10px;padding:10px;background:rgba(0,0,0,0.2);border-radius:8px;border:1px solid var(--border);">
    <!-- Always-on stages -->
    <div style="margin-bottom:10px;display:flex;gap:8px;">
      <div class="stage-locked" style="flex:1;">🔒 <span style="color:#93c5fd;">Info Collection</span> <span style="font-size:10px;margin-left:auto;color:var(--text-muted);">Always on</span></div>
      <div class="stage-locked" style="flex:1;">🔒 <span style="color:#93c5fd;">Vuln Review</span> <span style="font-size:10px;margin-left:auto;color:var(--text-muted);">Always on</span></div>
    </div>

    <!-- Flat stage list -->
    <div style="margin-bottom:6px;">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;">
        <span style="font-size:11px;font-weight:600;color:#9ca3af;">Stages (${stages.length})</span>
        <div style="display:flex;gap:6px;">
          <button class="btn-icon" style="font-size:10px;padding:2px 8px;" onclick="toggleAllStages(true)">Select all</button>
          <button class="btn-icon" style="font-size:10px;padding:2px 8px;" onclick="toggleAllStages(false)">Deselect all</button>
        </div>
      </div>
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:2px;">
        ${stages.map(s => chk(s)).join("")}
      </div>
    </div>
  </div>`;
}

function renderLlmModal() {
  const modal = document.getElementById("llm-modal");
  if (!AppState.showLlmModal) { modal.style.display = "none"; return; }
  modal.style.display = "flex";

  const profiles = AppState.llmProfiles;
  const editing = AppState.editingProfileId;
  const ep = editing ? profiles.find(p=>p.id===editing) : null;
  const f = AppState.llmForm;

  const profileList = profiles.map(p => `
  <div style="display:flex;align-items:center;padding:10px 12px;border-radius:8px;background:rgba(255,255,255,0.03);border:1px solid var(--border);margin-bottom:8px;gap:12px;">
    <div style="flex:1;min-width:0;">
      <div style="font-size:13px;font-weight:500;">${p.is_default?"★ ":""}${p.name}</div>
      <div style="font-size:11px;color:var(--text-muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${p.model} · ${p.base_url}</div>
    </div>
    <button class="btn-icon" onclick="editLlmProfile('${p.id}')">Edit</button>
    <button class="btn-danger" onclick="confirmDeleteLlm('${p.id}')">Del</button>
  </div>`).join("");

  const formHtml = AppState.llmFormOpen ? `
  <hr class="divider" style="margin:16px 0;">
  <div style="font-size:13px;font-weight:600;margin-bottom:12px;">${editing ? "Edit LLM Service" : "Add LLM Service"}</div>
  <div style="display:grid;gap:10px;">
    <div>
      <label style="font-size:12px;color:var(--text-muted);display:block;margin-bottom:4px;">Name</label>
      <input type="text" id="llm-name" value="${f.name}" placeholder="OpenRouter DeepSeek V3" oninput="AppState.llmForm.name=this.value">
    </div>
    <div>
      <label style="font-size:12px;color:var(--text-muted);display:block;margin-bottom:4px;">API URL</label>
      <input type="url" id="llm-url" value="${f.base_url}" placeholder="https://openrouter.ai/api/v1" oninput="AppState.llmForm.base_url=this.value">
    </div>
    <div>
      <label style="font-size:12px;color:var(--text-muted);display:block;margin-bottom:4px;">API Key</label>
      <input type="password" id="llm-key" value="${f.api_key}" placeholder="sk-..." oninput="AppState.llmForm.api_key=this.value">
    </div>
    <div>
      <label style="font-size:12px;color:var(--text-muted);display:block;margin-bottom:4px;">Model</label>
      <input type="text" id="llm-model" value="${f.model}" placeholder="deepseek/deepseek-v3" oninput="AppState.llmForm.model=this.value">
    </div>
    <label style="display:flex;align-items:center;gap:8px;font-size:13px;cursor:pointer;">
      <input type="checkbox" ${f.is_default?"checked":""} onchange="AppState.llmForm.is_default=this.checked">
      Set as default
    </label>
  </div>
  <div style="display:flex;gap:10px;margin-top:16px;">
    <button class="btn-secondary" style="flex:1;" onclick="cancelLlmForm()">Cancel</button>
    <button class="btn-primary" style="flex:1;" onclick="saveLlmProfile()">Save</button>
  </div>` : "";

  document.getElementById("llm-modal-card").innerHTML = `
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:20px;">
    <h3 style="font-size:16px;font-weight:700;" class="gradient-text">LLM Services</h3>
    <button class="btn-icon" onclick="closeLlmModal()">✕</button>
  </div>
  ${profiles.length === 0
    ? `<div style="text-align:center;color:var(--text-muted);padding:20px;font-size:13px;">No LLM services. Add one below.</div>`
    : profileList}
  ${!AppState.llmFormOpen
    ? `<button class="btn-secondary" style="width:100%;margin-top:4px;" onclick="AppState.llmFormOpen=true;AppState.editingProfileId=null;AppState.llmForm={name:'',base_url:'https://openrouter.ai/api/v1',api_key:'',model:'',is_default:false};renderLlmModal()">+ Add LLM Service</button>`
    : ""}
  ${formHtml}`;
}

