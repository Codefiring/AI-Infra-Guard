// ═══════════════════════════════════════════════════════════════
//  DISPLAY NAME HELPER
// ═══════════════════════════════════════════════════════════════
function taskDisplayName(task) {
  if (task.name) return task.name;
  const target = task.targets?.[0];
  if (!target) return task.id;
  try {
    const u = new URL(target.url);
    const hostPort = u.hostname + (u.port ? `:${u.port}` : "");
    const t = new Date(task.created_at);
    const pad = n => String(n).padStart(2,"0");
    const hms = `${pad(t.getHours())}:${pad(t.getMinutes())}:${pad(t.getSeconds())}`;
    return `${hostPort} @ ${hms}`;
  } catch { return target.url; }
}

// ── Mock data for Phase 1 standalone testing ──
function initMockData() {
  const stages17 = buildStageList([2,3,5,14,18,9,11,12,13,16,23]);
  stages17.forEach((s,i) => {
    if (i < 4) s.status = "completed", s.output = `## Stage ${s.stage_id} Output\n\nNo vulnerabilities detected in this stage.\n\n\`\`\`json\n{"result":"clean"}\n\`\`\``;
    else if (i === 4) s.status = "running";
  });

  AppState.tasks = [
    {
      id: "task-demo-1",
      status: "running",
      created_at: new Date(Date.now() - 180000).toISOString(),
      completed_at: null,
      llm_profile_name: "DeepSeek V3",
      llm_model: "deepseek/deepseek-v3",
      prompt: "",
      language: "zh",
      has_oauth: false,
      current_target_idx: 0,
      error: null,
      targets: [
        {
          id: "tt-1a",
          position: 0,
          name: "MCP Test",
          url: "http://192.168.1.10:8080/sse",
          stage_ids: [2,3,5,14,18,9,11,12,13,16,23],
          status: "running",
          score: null, readme: null,
          stages: stages17,
          vulnerabilities: []
        }
      ]
    },
    {
      id: "task-demo-2",
      status: "completed",
      created_at: new Date(Date.now() - 3600000).toISOString(),
      completed_at: new Date(Date.now() - 3000000).toISOString(),
      llm_profile_name: "DeepSeek V3",
      llm_model: "deepseek/deepseek-v3",
      prompt: "Focus on path traversal vulnerabilities",
      language: "en",
      has_oauth: false,
      current_target_idx: 0,
      error: null,
      targets: [
        {
          id: "tt-2a",
          position: 0,
          name: "MCP Prod",
          url: "http://10.0.0.5:9090/sse",
          stage_ids: [...ALL_STAGE_IDS],
          status: "completed",
          score: 42,
          readme: "## MCP Server Info\n\n- **Server**: FastMCP v1.2\n- **Tools**: 8 registered\n- **Language**: Python\n\n### Tool List\n| Tool | Description |\n|------|-------------|\n| read_file | Read local files |\n| execute_cmd | Run shell commands |\n| fetch_url | HTTP requests |\n",
          stages: buildStageList([...ALL_STAGE_IDS]).map(s => ({ ...s, status: "completed", output: `## ${STAGE_MAP[s.stage_id]?.name || 'Stage'}\n\nAnalysis complete.` })),
          vulnerabilities: [
            { id:"v1", title:"Path Traversal via read_file", risk_type:"MCP18", level:"High",
              description:"The `read_file` tool accepts unsanitized path inputs allowing an attacker to read arbitrary files outside the intended directory.", suggestion:"Validate and sanitize all path inputs. Use `os.path.abspath()` and check it starts with the allowed root." },
            { id:"v2", title:"Unauthenticated Access to Admin Tools", risk_type:"MCP14", level:"Medium",
              description:"Admin-level tools are accessible without authentication tokens.", suggestion:"Implement bearer token validation for all sensitive tool calls." },
            { id:"v3", title:"SQL Injection in query_db tool", risk_type:"MCP23", level:"High",
              description:"User-supplied input is directly concatenated into SQL queries.", suggestion:"Use parameterized queries or an ORM." },
          ]
        }
      ]
    },
    {
      id: "task-demo-3",
      status: "failed",
      created_at: new Date(Date.now() - 7200000).toISOString(),
      completed_at: null,
      llm_profile_name: "DeepSeek V3",
      llm_model: "deepseek/deepseek-v3",
      prompt: "",
      language: "en",
      has_oauth: false,
      current_target_idx: 0,
      error: "Connection refused: http://192.168.1.99:8080/sse",
      targets: [
        { id:"tt-3a", position:0, name:"MCP Dev", url:"http://192.168.1.99:8080/sse",
          stage_ids: [...ALL_STAGE_IDS], status:"failed", score:null, readme:null,
          stages: buildStageList([...ALL_STAGE_IDS]), vulnerabilities:[] }
      ]
    }
  ];

  AppState.llmProfiles = [
    { id:"llm-1", name:"DeepSeek V3", base_url:"https://api.deepseek.com/v1", model:"deepseek/deepseek-v3", is_default:true, created_at:"2026-04-01T10:00:00" },
    { id:"llm-2", name:"OpenRouter Claude", base_url:"https://openrouter.ai/api/v1", model:"anthropic/claude-sonnet-4-6", is_default:false, created_at:"2026-04-02T10:00:00" },
  ];
  AppState.selectedLlmProfileId = "llm-1";
  AppState.selectedTaskId = "task-demo-1";
  AppState.selectedStageId = null;
}

// ═══════════════════════════════════════════════════════════════
//  HELPERS
// ═══════════════════════════════════════════════════════════════
function buildStageList(stageIds) {
  const ids = stageIds || ALL_STAGE_IDS;
  const sorted = [...ids].filter(i => i >= 2 && i <= 26).sort((a,b) => a-b);
  const list = [
    { stage_id:1,  name:"Info Collection",     status:"pending", output:"" },
    ...sorted.map(id => ({
      stage_id: id,
      name: STAGE_MAP[id]?.name || `Stage ${id}`,
      status: "pending",
      output: ""
    })),
    { stage_id:27, name:"Vulnerability Review", status:"pending", output:"" },
  ];
  return list.map((r, i) => ({ ...r, position: i + 1 }));
}

function scoreColor(score) {
  if (score === null || score === undefined) return "var(--text-muted)";
  if (score >= 70) return "var(--green)";
  if (score >= 40) return "var(--amber)";
  return "var(--red)";
}

function levelBadge(level) {
  const l = (level||"").toLowerCase();
  if (l.includes("high") || l.includes("高")) return `<span class="badge badge-high">${level}</span>`;
  if (l.includes("med")  || l.includes("中")) return `<span class="badge badge-medium">${level}</span>`;
  return `<span class="badge badge-low">${level}</span>`;
}

function fmtTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = n => String(n).padStart(2,"0");
  return `${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function renderMarkdown(text) {
  if (!text) return '<span style="color:var(--text-muted);font-size:12px;">No content</span>';
  try { return marked.parse(text); } catch(e) { return `<pre>${text}</pre>`; }
}

function escapeHtml(str) {
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// Parse the structured vuln-stage output format:
//   # Overview  /  # Threats (<threat>…</threat>)  /  # Reasons  /  # Summarization
function parseVulnOutput(text) {
  const sectionLines = { overview: [], threats: [], reasons: [], summary: [] };
  let cur = null;
  for (const line of text.split('\n')) {
    const t = line.trim();
    if (/^#\s+Overview/i.test(t))      { cur = 'overview';  continue; }
    if (/^#\s+Threats/i.test(t))       { cur = 'threats';   continue; }
    if (/^#\s+Reasons/i.test(t))       { cur = 'reasons';   continue; }
    if (/^#\s+Summarization/i.test(t)) { cur = 'summary';   continue; }
    if (t.startsWith('#'))             { cur = null;         continue; }
    if (cur) sectionLines[cur].push(line);
  }

  const threatsText = sectionLines.threats.join('\n');
  const threats = [];
  const re = /<threat>([\s\S]*?)<\/threat>/g;
  let m;
  while ((m = re.exec(threatsText)) !== null) {
    const c = m[1];
    const get = tag => (c.match(new RegExp(`<${tag}>([\\s\\S]*?)<\\/${tag}>`)) || [])[1]?.trim() || '';
    threats.push({
      toolName:   get('tool_name'),
      type:       get('type'),
      confidence: parseFloat(get('confidence') || '0'),
      impact:     get('impact'),
    });
  }

  const reasonsRaw = sectionLines.reasons.join('\n').trim();
  const reasons = reasonsRaw
    ? reasonsRaw.split(/\n\s*-\s+/).map(r => r.trim()).filter(Boolean)
    : [];

  return {
    isRisk:  /yes/i.test(sectionLines.overview.join(' ')),
    threats,
    reasons,
    summary: sectionLines.summary.join('\n').trim(),
  };
}

// Render a vuln-stage output with structured cards when the format is detected;
// falls back to plain markdown rendering otherwise.
function renderVulnStageOutput(text) {
  if (!text) return '<span style="color:var(--text-muted);font-size:12px;">No content</span>';
  if (!/<threat>/.test(text)) return `<div class="markdown-body">${renderMarkdown(text)}</div>`;

  const d = parseVulnOutput(text);

  const impactColor = imp => {
    const i = (imp || '').toLowerCase();
    if (i === 'high' || i === 'critical') return 'var(--red)';
    if (i === 'medium') return 'var(--amber)';
    return 'var(--green)';
  };
  const confColor = c => c >= 0.8 ? 'var(--red)' : c >= 0.6 ? 'var(--amber)' : 'var(--text-muted)';

  // ── Overview badge ──────────────────────────────────────────────
  let html = `<div style="display:flex;align-items:center;gap:8px;margin-bottom:16px;">
    <span style="font-size:12px;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:.05em;">Overview</span>
    <span style="padding:3px 12px;border-radius:999px;font-size:12px;font-weight:700;
      background:${d.isRisk ? 'rgba(248,113,113,0.12)' : 'rgba(52,211,153,0.12)'};
      color:${d.isRisk ? 'var(--red)' : 'var(--green)'};">
      ${d.isRisk ? '⚠ Risk Detected' : '✓ No Risk Detected'}
    </span>
  </div>`;

  // ── Threats ─────────────────────────────────────────────────────
  if (d.threats.length > 0) {
    html += `<div style="margin-bottom:16px;">
      <div style="font-size:11px;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:.05em;margin-bottom:8px;">
        Threats (${d.threats.length})
      </div>
      <div style="display:flex;flex-direction:column;gap:6px;">`;
    for (const t of d.threats) {
      const pct = Math.round(t.confidence * 100);
      html += `<div style="background:rgba(255,255,255,0.03);border:1px solid var(--border);border-radius:8px;padding:10px 12px;">
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
          <code style="font-size:11px;padding:2px 7px;background:rgba(96,165,250,0.12);color:#60a5fa;border-radius:4px;">${escapeHtml(t.toolName)}</code>
          <span style="font-size:12px;font-weight:500;flex:1;min-width:0;">${escapeHtml(t.type)}</span>
          <span style="font-size:11px;font-weight:600;color:${impactColor(t.impact)};">${escapeHtml(t.impact)}</span>
          <span style="font-size:11px;color:${confColor(t.confidence)};">${pct}% conf</span>
        </div>
      </div>`;
    }
    html += `</div></div>`;
  }

  // ── Reasons ─────────────────────────────────────────────────────
  if (d.reasons.length > 0) {
    html += `<div style="margin-bottom:16px;">
      <div style="font-size:11px;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:.05em;margin-bottom:8px;">Reasons</div>
      <div style="display:flex;flex-direction:column;gap:6px;">`;
    for (const r of d.reasons) {
      html += `<div style="font-size:12px;padding:8px 10px;background:rgba(255,255,255,0.02);
        border-left:2px solid var(--border-hl);border-radius:0 4px 4px 0;line-height:1.6;">
        ${renderMarkdown(r)}
      </div>`;
    }
    html += `</div></div>`;
  }

  // ── Summary ──────────────────────────────────────────────────────
  if (d.summary) {
    html += `<div>
      <div style="font-size:11px;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:.05em;margin-bottom:8px;">Summary</div>
      <div class="markdown-body" style="font-size:12px;">${renderMarkdown(d.summary)}</div>
    </div>`;
  }

  return html;
}

function stageIcon(status) {
  if (status === "completed") return `<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="7" stroke="var(--green)" stroke-width="1.5"/><path d="M5 8.5l2 2 4-4" stroke="var(--green)" stroke-width="1.5" stroke-linecap="round"/></svg>`;
  if (status === "running")   return `<svg class="spinner" width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="6" stroke="rgba(59,130,246,0.3)" stroke-width="2"/><path d="M8 2 A6 6 0 0 1 14 8" stroke="var(--blue)" stroke-width="2" stroke-linecap="round"/></svg>`;
  if (status === "error")     return `<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="7" stroke="var(--red)" stroke-width="1.5"/><path d="M8 5v4M8 11v1" stroke="var(--red)" stroke-width="1.5" stroke-linecap="round"/></svg>`;
  return `<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="7" stroke="rgba(107,114,128,0.5)" stroke-width="1.5"/></svg>`;
}

