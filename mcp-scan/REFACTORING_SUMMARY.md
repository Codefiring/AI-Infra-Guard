# MCP-Scan Refactoring Summary

## Problem
The original Stage 2 (malicious_behaviour_testing.md) and Stage 3 (vulnerability_testing.md) contained 9 and 16 vulnerability types respectively in single large prompts. This caused the LLM to lose focus during inference and skip some vulnerability types.

## Solution
Refactored the scan process to separate each vulnerability type into its own stage with a dedicated prompt file. This ensures the LLM focuses on one vulnerability type at a time.

## Changes

### New Stage Structure (27 stages total)

**Stage 1: Info Collection** (unchanged)
- Template: `agents/dynamic/project_summary`
- Purpose: Analyze MCP tools list and understand server capabilities

**Stages 2-10: Individual Malicious Behavior Scans** (9 stages)
1. Stage 2: Tool Poisoning (TPA) → `agents/dynamic/malicious/tpa.md`
2. Stage 3: Full Schema Poisoning (FSP) → `agents/dynamic/malicious/fsp.md`
3. Stage 4: Advanced Tool Poisoning (ATPA) → `agents/dynamic/malicious/atpa.md`
4. Stage 5: Rug Pull Attack → `agents/dynamic/malicious/rug_pull.md`
5. Stage 6: MCP Configuration Poisoning → `agents/dynamic/malicious/config_poisoning.md`
6. Stage 7: Tool Name Spoofing → `agents/dynamic/malicious/name_spoofing.md`
7. Stage 8: Tool Shadowing → `agents/dynamic/malicious/tool_shadowing.md`
8. Stage 9: Resource Content Poisoning → `agents/dynamic/malicious/resource_poisoning.md`
9. Stage 10: MCP Preference Manipulation (MPMA) → `agents/dynamic/malicious/mpma.md`

**Stages 11-26: Individual Vulnerability Scans** (16 stages)
1. Stage 11: Prompt Injection → `agents/dynamic/vuln/prompt_injection.md`
2. Stage 12: Command Injection → `agents/dynamic/vuln/command_injection.md`
3. Stage 13: Remote Code Execution (RCE) → `agents/dynamic/vuln/rce.md`
4. Stage 14: Unauthenticated Access → `agents/dynamic/vuln/unauth_access.md`
5. Stage 15: Confused Deputy (OAuth Proxy) → `agents/dynamic/vuln/confused_deputy.md`
6. Stage 16: Token/Credential Theft → `agents/dynamic/vuln/credential_theft.md`
7. Stage 17: Token Passthrough → `agents/dynamic/vuln/token_passthrough.md`
8. Stage 18: Path Traversal → `agents/dynamic/vuln/path_traversal.md`
9. Stage 19: Localhost Bypass (NeighborJack) → `agents/dynamic/vuln/localhost_bypass.md`
10. Stage 20: Session Management Flaws → `agents/dynamic/vuln/session_management.md`
11. Stage 21: Privilege Abuse/Overbroad Permissions → `agents/dynamic/vuln/privilege_abuse.md`
12. Stage 22: Cross-Repository Data Theft → `agents/dynamic/vuln/cross_repo_theft.md`
13. Stage 23: SQL Injection → `agents/dynamic/vuln/sql_injection.md`
14. Stage 24: Context Bleeding → `agents/dynamic/vuln/context_bleeding.md`
15. Stage 25: Configuration File Exposure → `agents/dynamic/vuln/config_exposure.md`
16. Stage 26: Cross-Tenant Data Exposure → `agents/dynamic/vuln/cross_tenant_exposure.md`

**Stage 27: Vulnerability Review** (unchanged)
- Template: `agents/dynamic/general_analyzing_prompt_template`
- Purpose: Consolidate and validate findings from all 25 individual scans

### File Structure
```
mcp-scan/prompt/agents/dynamic/
├── malicious/              # 9 malicious behavior prompt files
│   ├── tpa.md
│   ├── fsp.md
│   ├── atpa.md
│   ├── rug_pull.md
│   ├── config_poisoning.md
│   ├── name_spoofing.md
│   ├── tool_shadowing.md
│   ├── resource_poisoning.md
│   └── mpma.md
└── vuln/                   # 16 vulnerability prompt files
    ├── prompt_injection.md
    ├── command_injection.md
    ├── rce.md
    ├── unauth_access.md
    ├── confused_deputy.md
    ├── credential_theft.md
    ├── token_passthrough.md
    ├── path_traversal.md
    ├── localhost_bypass.md
    ├── session_management.md
    ├── privilege_abuse.md
    ├── cross_repo_theft.md
    ├── sql_injection.md
    ├── context_bleeding.md
    ├── config_exposure.md
    └── cross_tenant_exposure.md
```

### Code Changes

**File: `mcp-scan/agent/agent.py`**

Modified the `dynamic_analysis()` method to:
1. Execute Stage 1 (Info Collection) as before
2. Loop through 25 individual vulnerability type stages (Stages 2-26)
3. Each stage receives the info collection report as context
4. All individual reports are collected
5. Execute Stage 27 (Vulnerability Review) with all reports as context

Key improvements:
- Each vulnerability type gets focused LLM attention
- Logs are more traceable (one log entry per vulnerability type)
- Easier to debug which specific vulnerability type is failing
- Better parallelization potential in the future

## Benefits

1. **Improved LLM Focus**: Each stage has a single, focused task instead of 9-16 tasks
2. **Better Traceability**: Logs clearly show which vulnerability type is being scanned
3. **No Skipped Scans**: LLM won't skip vulnerability types due to prompt length
4. **Easier Debugging**: Can identify exactly which vulnerability type scan failed
5. **Maintainability**: Each vulnerability type is in its own file, easier to update
6. **Extensibility**: Easy to add new vulnerability types by adding new files

## Backward Compatibility

The old prompt files (`malicious_behaviour_testing.md` and `vulnerability_testing.md`) are still present but no longer used. They can be kept as reference or removed.

## Testing

To test the refactored scan:
```bash
cd mcp-scan
python main.py --server_url http://your-mcp-server:port -k YOUR_API_KEY
```

The scan will now execute 27 stages instead of 4, with each vulnerability type scanned individually.
