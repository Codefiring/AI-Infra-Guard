# MCP Batch Scanning Guide

This guide explains how to use the batch scanning feature to scan multiple MCP servers from a configuration file.

## Quick Start

1. **Create a targets configuration file** (e.g., `targets.yaml`):

```yaml
targets:
  - "http://192.168.1.100:8080"
  - "http://192.168.1.101:8080"
  - "http://10.0.0.50:9000"
```

2. **Run the batch scan**:

```bash
python main.py --config targets.yaml -k YOUR_API_KEY
```

## Configuration File Format

The configuration file uses YAML format with a simple structure:

```yaml
targets:
  # List of MCP server URLs
  - "http://ip:port"
  - "https://domain:port"
  # Add more targets as needed
```

### Example Configuration

```yaml
targets:
  # Internal servers
  - "http://192.168.1.100:8080"
  - "http://192.168.1.101:8080"
  - "http://192.168.1.102:8080"

  # External servers
  - "https://mcp-server.example.com:8080"
  - "https://api.example.com:9000"
```

## Command Line Options

### Required Options

- `--config` or `-c`: Path to the YAML configuration file containing target list
- `--api_key` or `-k`: API key for the LLM service (or set `OPENROUTER_API_KEY` environment variable)

### Optional Options

- `--prompt` or `-p`: Custom scanning prompt
- `--model` or `-m`: LLM model to use (default: from config)
- `--base_url` or `-u`: API base URL (default: from config)
- `--language`: Output language (`zh` or `en`, default: `zh`)
- `--header`: Custom HTTP headers (can be used multiple times)
- `--debug`: Enable debug mode

### Example Commands

**Basic batch scan:**
```bash
python main.py --config targets.yaml -k YOUR_API_KEY
```

**Batch scan with custom prompt:**
```bash
python main.py --config targets.yaml -k YOUR_API_KEY -p "Focus on authentication vulnerabilities"
```

**Batch scan with English output:**
```bash
python main.py --config targets.yaml -k YOUR_API_KEY --language en
```

**Batch scan with custom headers:**
```bash
python main.py --config targets.yaml -k YOUR_API_KEY --header "Authorization:Bearer token123" --header "X-Custom:value"
```

## Output Structure

When running a batch scan, logs are organized as follows:

```
logs/
└── scan_2026-03-11_14-30-00/          # Timestamp when scan started
    ├── 192_168_1_100_8080.log         # Log for first target
    ├── 192_168_1_101_8080.log         # Log for second target
    └── 10_0_0_50_9000.log             # Log for third target
```

### Log File Naming

- IP addresses: dots (`.`) are replaced with underscores (`_`)
- Ports: separated by underscore
- Example: `192.168.1.100:8080` → `192_168_1_100_8080.log`

### Console Output

During the scan, you'll see:
- Progress indicator (`[1/3]`, `[2/3]`, etc.)
- Current target being scanned
- Real-time scan results
- Summary at the end with success/failure counts

## Error Handling

- If a single target fails, the batch scan continues with remaining targets
- Each target's success/failure status is tracked independently
- Failed scans are logged with error details
- Final summary shows total, successful, and failed scans

## Tips

1. **Test with a small list first**: Start with 2-3 targets to verify configuration
2. **Monitor resource usage**: Scanning multiple targets can be resource-intensive
3. **Use appropriate timeouts**: Consider network latency for remote servers
4. **Check logs**: Each target has its own detailed log file for troubleshooting
5. **Organize configs**: Create separate config files for different environments (dev, staging, prod)

## Troubleshooting

### Config file not found
```
Error: Config file not found: targets.yaml
```
**Solution**: Ensure the config file path is correct and the file exists.

### No targets in config
```
Warning: No targets found in config file
```
**Solution**: Check that your YAML file has a `targets:` section with at least one URL.

### Invalid YAML format
```
Error: Failed to parse YAML config
```
**Solution**: Validate your YAML syntax. Common issues:
- Missing colons after `targets`
- Incorrect indentation
- Missing quotes around URLs with special characters

### API Key not provided
```
Error: API Key not provided
```
**Solution**: Provide API key via `--api_key` flag or set `OPENROUTER_API_KEY` environment variable.

## Single Target Mode (Original Behavior)

To scan a single target without using a config file, use the original command format:

```bash
# Scan a single MCP server
python main.py --server_url http://192.168.1.100:8080 -k YOUR_API_KEY

# Scan a local repository
python main.py --repo /path/to/project -k YOUR_API_KEY
```

The batch scanning feature is only activated when `--config` is provided.
