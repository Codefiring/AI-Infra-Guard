# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI-Infra-Guard (A.I.G) is an AI Red Teaming Platform developed by Tencent Zhuque Lab. It provides comprehensive security testing capabilities for AI infrastructure, including:

- **AI Infrastructure Vulnerability Scanning**: Detects 30+ AI framework components and 400+ CVE vulnerabilities
- **MCP Server Risk Scanning**: AI Agent-powered detection of 14 major security risk categories in Model Context Protocol servers
- **Jailbreak Evaluation**: Assesses prompt security risks with curated datasets and multiple attack methods

The platform is built with Go (backend/CLI) and includes Python components for specialized tasks (AIG-PromptSecurity, mcp-scan).

## Architecture

### Core Components

**Agent-Server Architecture**:
- **Web Server** (`cmd/cli/main.go` → webserver command): Gin-based HTTP server with WebSocket support for real-time communication
- **Agent Service** (`cmd/agent/main.go`): Connects to server via WebSocket and executes tasks (AI Infra Scan, MCP Task, Model Redteam Report)
- **CLI Tool** (`cmd/cli/main.go` → scan command): Standalone scanning without web interface

**Task Execution Flow**:
1. Tasks are created via Web UI or API
2. Server dispatches tasks to agents via WebSocket
3. Agents execute tasks using registered task handlers:
   - `AIInfraScanAgent`: Infrastructure vulnerability scanning
   - `McpTask`: MCP server security analysis
   - `ModelRedteamReport`: Jailbreak evaluation reporting
4. Results are sent back to server and stored in database

**Plugin System**:
- **Fingerprints** (`data/fingerprints/`): YAML-based component detection rules
- **Vulnerabilities** (`data/vuln/`, `data/vuln_en/`): YAML-based vulnerability scan rules (Chinese/English)
- **MCP Rules** (`data/mcp/`): MCP security scan rules
- **Eval Datasets** (`data/eval/`): Jailbreak evaluation datasets

### Key Packages

- `pkg/database/`: GORM-based database layer (SQLite/MySQL) with models for agents, tasks, and scan results
- `pkg/httpx/`: HTTP client utilities with custom headers, encodings, and response handling
- `pkg/vulstruct/`: Vulnerability data structures and scanner logic
- `common/agent/`: Agent task handlers and execution logic
- `common/fingerprints/`: Fingerprint detection and matching engine
- `common/runner/`: Scan orchestration and execution
- `common/websocket/`: WebSocket server and client implementation
- `internal/mcp/`: MCP protocol integration
- `internal/options/`: Configuration management

## Python Environment

All Python commands (mcp-scan, AIG-PromptSecurity, etc.) **must** be run inside the `AI-Infra-Guard` conda environment:

```bash
conda run -n AI-Infra-Guard python ...
# or activate first:
conda activate AI-Infra-Guard
```

When executing Python-related Bash commands, always prefix with `conda run -n AI-Infra-Guard` to ensure the correct environment is used.

## Development Commands

### Building

```bash
# Build CLI tool
go build -o aig-cli cmd/cli/main.go

# Build agent service
go build -o aig-agent cmd/agent/main.go
```

### Running

```bash
# Start web server (default: http://localhost:8088)
go run cmd/cli/main.go webserver

# Start web server on custom address
go run cmd/cli/main.go webserver --server 0.0.0.0:8088

# Run CLI scan
go run cmd/cli/main.go scan -t https://example.com

# Run CLI scan with options
go run cmd/cli/main.go scan -t https://example.com --timeout 10 --limit 100 --lang en

# Run local scan (scans localhost AI services)
go run cmd/cli/main.go scan --localscan

# List available vulnerability templates
go run cmd/cli/main.go scan --list-vul

# Run agent service
go run cmd/agent/main.go --server localhost:8088
# Or use environment variable
export AIG_SERVER=localhost:8088
go run cmd/agent/main.go
```

### Testing

```bash
# Run all tests
go test ./...

# Run tests for specific package
go test ./pkg/database/
go test ./common/agent/

# Run tests with coverage
go test -cover ./...

# Run tests with verbose output
go test -v ./...
```

### Docker Deployment

```bash
# Quick start with pre-built images
docker-compose -f docker-compose.images.yml up -d

# Build and run from source
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

## Project Structure

```
AI-Infra-Guard/
├── cmd/
│   ├── agent/          # Agent service entry point
│   └── cli/            # CLI tool with webserver and scan commands
├── internal/           # Internal packages (not importable by external projects)
│   ├── gologger/       # Logging utilities
│   ├── mcp/            # MCP protocol integration
│   └── options/        # Configuration management
├── pkg/                # Public packages (importable by external projects)
│   ├── database/       # Database models and operations
│   ├── httpx/          # HTTP client utilities
│   └── vulstruct/      # Vulnerability structures
├── common/             # Shared packages
│   ├── agent/          # Agent task handlers
│   ├── fingerprints/   # Fingerprint detection engine
│   ├── middleware/     # HTTP middleware
│   ├── runner/         # Scan orchestration
│   ├── trpc/           # TRPC framework integration
│   ├── utils/          # Utility functions
│   └── websocket/      # WebSocket server/client
├── data/               # Data files (plugins)
│   ├── fingerprints/   # Component detection rules (YAML)
│   ├── vuln/           # Vulnerability rules - Chinese (YAML)
│   ├── vuln_en/        # Vulnerability rules - English (YAML)
│   ├── mcp/            # MCP security rules
│   └── eval/           # Jailbreak evaluation datasets
├── AIG-PromptSecurity/ # Python-based prompt security evaluation
├── mcp-scan/           # Python-based MCP scanning tool
└── docs/               # API documentation (Swagger)
```

## Key Patterns and Conventions

### Adding New Vulnerability Rules

1. Create YAML file in `data/vuln/` (Chinese) or `data/vuln_en/` (English)
2. Follow existing rule format with fingerprint matching and PoC validation
3. Rules are automatically loaded by the fingerprint engine at startup

### Adding New Fingerprint Rules

1. Create YAML file in `data/fingerprints/`
2. Define component name, version detection patterns, and matching rules
3. Fingerprints are used for component identification before vulnerability scanning

### Adding New MCP Security Rules

1. Create rule file in `data/mcp/`
2. Define security check logic for MCP server analysis
3. Rules are executed by the AI Agent during MCP scanning

### MCP Batch Scanning

The `mcp-scan` tool supports batch scanning of multiple MCP servers from a configuration file:

**Configuration File Format** (`mcp-scan/targets.yaml`):
```yaml
targets:
  - name: "MCP01"
    url: "http://109.105.132.36:8001"
  - name: "MCP02"
    url: "http://192.168.1.101:8080"
```

**Running Batch Scans**:
```bash
cd mcp-scan
python main.py --config targets.yaml -k YOUR_API_KEY
```

**Output Structure**:
- Logs are organized in time-stamped directories: `logs/scan_YYYY-MM-DD_HH-MM-SS/`
- Each target gets its own log file named: `{name}_{ip}_{port}.log`
- Example: `MCP01_109_105_132_36_8001.log`

**Features**:
- Named targets for easy identification (e.g., "MCP01" indicates vulnerability type)
- Per-target log files with name prefix
- Sequential scanning with progress tracking
- Individual error handling (one failure doesn't stop the batch)
- Summary report with success/failure counts

**Backward Compatibility**:
- Old format (simple URL strings) is still supported
- Single-target mode works as before with `--server_url` flag

### Agent Task Registration

To add a new task type:
1. Implement the task handler interface in `common/agent/`
2. Register the task handler in `cmd/agent/main.go` using `x.RegisterTaskFunc()`
3. Task handlers receive tasks via WebSocket and return results

### Database Models

- Use GORM for all database operations
- Models are defined in `pkg/database/model.go`
- Support both SQLite (default) and MySQL
- Database is initialized automatically on first run

### Logging

- Use `internal/gologger` for all logging
- Log levels: Debug, Info, Warning, Error, Fatal
- Logs are configured via `trpc_go.yaml`
- Console output (info level) and file output (debug level) are enabled by default

## API Documentation

After starting the web server, access Swagger documentation at:
- `http://localhost:8088/docs/index.html`

API endpoints support:
- Task creation and management
- Scan result retrieval
- Agent registration and status
- Real-time progress via WebSocket

## Multi-Language Support

The project supports Chinese and English:
- Use `--lang zh` or `--lang en` flag for CLI commands
- Web UI language is auto-detected from browser settings
- Vulnerability rules are separated into `data/vuln/` (Chinese) and `data/vuln_en/` (English)
- API responses respect the language parameter

## Security Considerations

- Web server defaults to `127.0.0.1:8088` (localhost only)
- Warning is displayed when binding to non-localhost addresses
- No authentication mechanism - intended for internal/trusted network use only
- Do not expose to public internet without additional security measures
