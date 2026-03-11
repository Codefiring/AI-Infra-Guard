# MCP-Scan Stage Flow Comparison

## Before (4 Stages)

```
┌─────────────────────────────────────────────────────────────┐
│ Stage 1: Info Collection                                    │
│ - Analyze MCP tools list                                    │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Stage 2: Malicious Testing (9 types in ONE prompt)         │
│ - Tool Poisoning (TPA)                                      │
│ - Full Schema Poisoning (FSP)                               │
│ - Advanced Tool Poisoning (ATPA)                            │
│ - Rug Pull Attack                                           │
│ - MCP Configuration Poisoning                               │
│ - Tool Name Spoofing                                        │
│ - Tool Shadowing                                            │
│ - Resource Content Poisoning                                │
│ - MCP Preference Manipulation (MPMA)                        │
│ ⚠️  LLM loses focus, may skip some types                    │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Stage 3: Vulnerability Testing (16 types in ONE prompt)    │
│ - Prompt Injection                                          │
│ - Command Injection                                         │
│ - Remote Code Execution (RCE)                               │
│ - Unauthenticated Access                                    │
│ - Confused Deputy (OAuth Proxy)                             │
│ - Token/Credential Theft                                    │
│ - Token Passthrough                                         │
│ - Path Traversal                                            │
│ - Localhost Bypass (NeighborJack)                           │
│ - Session Management Flaws                                  │
│ - Privilege Abuse/Overbroad Permissions                     │
│ - Cross-Repository Data Theft                               │
│ - SQL Injection                                             │
│ - Context Bleeding                                          │
│ - Configuration File Exposure                               │
│ - Cross-Tenant Data Exposure                                │
│ ⚠️  LLM loses focus, may skip some types                    │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Stage 4: Vulnerability Review                               │
│ - Consolidate findings from Stage 2 & 3                     │
└─────────────────────────────────────────────────────────────┘
```

## After (27 Stages)

```
┌─────────────────────────────────────────────────────────────┐
│ Stage 1: Info Collection                                    │
│ - Analyze MCP tools list                                    │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Stages 2-10: Individual Malicious Behavior Scans           │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Stage 2: Tool Poisoning (TPA)                           │ │
│ └─────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Stage 3: Full Schema Poisoning (FSP)                    │ │
│ └─────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Stage 4: Advanced Tool Poisoning (ATPA)                 │ │
│ └─────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Stage 5: Rug Pull Attack                                │ │
│ └─────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Stage 6: MCP Configuration Poisoning                    │ │
│ └─────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Stage 7: Tool Name Spoofing                             │ │
│ └─────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Stage 8: Tool Shadowing                                 │ │
│ └─────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Stage 9: Resource Content Poisoning                     │ │
│ └─────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Stage 10: MCP Preference Manipulation (MPMA)            │ │
│ └─────────────────────────────────────────────────────────┘ │
│ ✅ Each type gets focused LLM attention                     │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Stages 11-26: Individual Vulnerability Scans                │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Stage 11: Prompt Injection                              │ │
│ └─────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Stage 12: Command Injection                             │ │
│ └─────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Stage 13: Remote Code Execution (RCE)                   │ │
│ └─────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Stage 14: Unauthenticated Access                        │ │
│ └─────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Stage 15: Confused Deputy (OAuth Proxy)                 │ │
│ └─────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Stage 16: Token/Credential Theft                        │ │
│ └─────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Stage 17: Token Passthrough                             │ │
│ └─────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Stage 18: Path Traversal                                │ │
│ └─────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Stage 19: Localhost Bypass (NeighborJack)               │ │
│ └─────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Stage 20: Session Management Flaws                      │ │
│ └─────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Stage 21: Privilege Abuse/Overbroad Permissions         │ │
│ └─────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Stage 22: Cross-Repository Data Theft                   │ │
│ └─────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Stage 23: SQL Injection                                 │ │
│ └─────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Stage 24: Context Bleeding                              │ │
│ └─────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Stage 25: Configuration File Exposure                   │ │
│ └─────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Stage 26: Cross-Tenant Data Exposure                    │ │
│ └─────────────────────────────────────────────────────────┘ │
│ ✅ Each type gets focused LLM attention                     │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Stage 27: Vulnerability Review                              │
│ - Consolidate findings from all 25 individual scans         │
└─────────────────────────────────────────────────────────────┘
```

## Key Improvements

| Aspect | Before | After |
|--------|--------|-------|
| **Total Stages** | 4 | 27 |
| **Prompt Length** | Very long (9+16 types) | Short (1 type per stage) |
| **LLM Focus** | ⚠️ Loses focus | ✅ Focused |
| **Skipped Scans** | ⚠️ Common | ✅ None |
| **Log Traceability** | ⚠️ Hard to trace | ✅ Clear per-type logs |
| **Debugging** | ⚠️ Difficult | ✅ Easy |
| **Maintainability** | ⚠️ Monolithic files | ✅ Modular files |

## Stage Naming Convention

The stage names now clearly indicate the vulnerability type being tested:
- **MCP01-MCP10**: Malicious behavior types (Tool Poisoning, Rug Pull, etc.)
- **MCP11-MCP26**: Traditional vulnerability types (Injection, RCE, etc.)

This aligns with the target naming in `targets.yaml` where targets are named like "MCP01", "MCP02", etc.
