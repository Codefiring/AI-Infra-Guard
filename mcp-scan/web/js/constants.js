// ═══════════════════════════════════════════════════════════════
//  STAGE CATALOGUE
// ═══════════════════════════════════════════════════════════════
const ALL_STAGES = [
  { id:  1, name: "Prompt Injection",             risk_type: "MCP01" },
  { id:  2, name: "Command Injection",            risk_type: "MCP02" },
  { id:  3, name: "Tool Poisoning (TPA)",          risk_type: "MCP03" },
  { id:  4, name: "Remote Code Execution (RCE)",  risk_type: "MCP04" },
  { id:  5, name: "Unauthenticated Access",        risk_type: "MCP05" },
  { id:  8, name: "Token/Credential Theft",       risk_type: "MCP08" },
  { id: 10, name: "Path Traversal",               risk_type: "MCP10" },
  { id: 11, name: "Full Schema Poisoning (FSP)",   risk_type: "MCP11" },
  { id: 12, name: "Tool Name Spoofing",            risk_type: "MCP12" },
  { id: 14, name: "Rug Pull",                      risk_type: "MCP14" },
  { id: 15, name: "Advanced Tool Poisoning (ATPA)",risk_type: "MCP15" },
  { id: 17, name: "Tool Shadowing",                risk_type: "MCP17" },
  { id: 18, name: "Resource Content Poisoning",   risk_type: "MCP18" },
  { id: 19, name: "Privilege Abuse",              risk_type: "MCP19" },
  { id: 21, name: "SQL Injection",                risk_type: "MCP21" },
];
const ALL_STAGE_IDS = ALL_STAGES.map(s => s.id);
const STAGE_MAP = Object.fromEntries(ALL_STAGES.map(s => [s.id, s]));
STAGE_MAP[0]  = { id:0,  name:"Info Collection"     };
STAGE_MAP[26] = { id:26, name:"Vulnerability Review" };

// ═══════════════════════════════════════════════════════════════
//  APP STATE
// ═══════════════════════════════════════════════════════════════
const AppState = {
  tasks: [],
  llmProfiles: [],
  savedConfigs: [],
  selectedTaskId: null,
  selectedStageId: null,
  showLlmModal: false,
  editingProfileId: null,
  taskSearchQuery: "",
  expandedVulns: new Set(),
  configForm: {
    name: "",
    url: "",
    stage_ids: [...ALL_STAGE_IDS],
    stagesOpen: false,
    prompt: "", language: "en",
    oauth_client_id: "", oauth_client_secret: "",
    oauth_token_url: "", oauth_scope: "",
  },
  llmForm: {
    name: "", base_url: "https://openrouter.ai/api/v1",
    api_key: "", model: "", is_default: false,
  },
  // UI collapse state
  panelOpen: { targets: true, oauth: false, prompt: false },
  llmFormOpen: false,
  // SSE
  eventSource: null,
  // Resizable panel widths
  layout: { sidebarWidth: 240, scanLeftPct: 40 },
  // Live log viewer
  logLines: [],
  logPollTimer: null,
};
