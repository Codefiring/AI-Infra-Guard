// ═══════════════════════════════════════════════════════════════
//  STAGE CATALOGUE
// ═══════════════════════════════════════════════════════════════
const ALL_STAGES = [
  { id: 11, name: "Prompt Injection",             risk_type: "MCP01" },
  { id: 12, name: "Command Injection",            risk_type: "MCP02" },
  { id:  2, name: "Tool Poisoning (TPA)",          risk_type: "MCP03" },
  { id: 13, name: "Remote Code Execution (RCE)",  risk_type: "MCP04" },
  { id: 14, name: "Unauthenticated Access",        risk_type: "MCP05" },
  { id: 16, name: "Token/Credential Theft",       risk_type: "MCP08" },
  { id: 18, name: "Path Traversal",               risk_type: "MCP10" },
  { id:  3, name: "Full Schema Poisoning (FSP)",   risk_type: "MCP11" },
  { id:  7, name: "Tool Name Spoofing",            risk_type: "MCP12" },
  { id:  5, name: "Rug Pull",                      risk_type: "MCP14" },
  { id:  4, name: "Advanced Tool Poisoning (ATPA)",risk_type: "MCP15" },
  { id:  8, name: "Tool Shadowing",                risk_type: "MCP17" },
  { id:  9, name: "Resource Content Poisoning",   risk_type: "MCP18" },
  { id: 21, name: "Privilege Abuse",              risk_type: "MCP19" },
  { id: 23, name: "SQL Injection",                risk_type: "MCP21" },
];
const ALL_STAGE_IDS = ALL_STAGES.map(s => s.id);
const STAGE_MAP = Object.fromEntries(ALL_STAGES.map(s => [s.id, s]));
STAGE_MAP[1]  = { id:1,  name:"Info Collection"     };
STAGE_MAP[27] = { id:27, name:"Vulnerability Review" };

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
};
