# MCP Security TOP 25 - Quick Reference

## Current Coverage: 5/25 (20%)

### ✅ Covered (5)
1. **Prompt Injection** (#1) - `tool_output_prompt_injection.yaml`
2. **Command Injection** (#2) - `malicious_code_execution_detection.yaml`
3. **Tool Poisoning** (#3) - `tool_poisoning_detection.yaml`
4. **RCE** (#4) - `malicious_code_execution_detection.yaml`
8. **Credential Theft** (#8) - `credential_leakage.yaml`
14. **Rug Pull** (#14) - `rug_pull_detection.yaml`

### ❌ Not Covered (20)

**Critical Priority:**
- #5 Unauthenticated Access
- #6 Confused Deputy (OAuth)
- #7 MCP Config Poisoning
- #9 Token Passthrough
- #10 Path Traversal

**High Priority:**
- #11 Full Schema Poisoning
- #12 Tool Name Spoofing
- #13 Localhost Bypass
- #15 Advanced Tool Poisoning
- #16 Session Management Flaws

**Medium Priority:**
- #17 Tool Shadowing
- #18 Resource Content Poisoning
- #19 Privilege Abuse
- #20 Cross-Repository Data Theft
- #21 SQL Injection
- #22 Context Bleeding
- #23 Config File Exposure
- #24 MPMA
- #25 Cross-Tenant Exposure

## Implementation Phases

### Phase 1 (1-2 weeks) → 52% Coverage
Add: #5, #6, #7, #9, #10, #11, #12, #13

### Phase 2 (1-2 months) → 76% Coverage
Add: #15, #16, #17, #18, #19, #20

### Phase 3 (2-3 months) → 100% Coverage
Add: #21, #22, #23, #24, #25

## Next Steps

1. Create YAML definitions for Phase 1 vulnerabilities
2. Update testing agent prompts
3. Add test case generation logic
4. Update documentation (CLAUDE.md, README.md)
5. Test and validate new detections

## Reference
Full analysis: [MCP_TOP25_Coverage_Analysis.md](./MCP_TOP25_Coverage_Analysis.md)
