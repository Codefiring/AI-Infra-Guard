# MCP-Scan Batch Scanning Implementation Summary

## Overview
Added batch scanning capability to mcp-scan tool, allowing scanning of multiple MCP servers from a configuration file with organized per-IP logging.

## Changes Made

### 1. New Files Created

#### `targets.yaml`
- Sample configuration file for target list
- Simple YAML format with list of MCP server URLs
- Includes comments and examples

#### `BATCH_SCAN_README.md`
- Comprehensive documentation for batch scanning feature
- Usage examples and command-line options
- Troubleshooting guide
- Output structure explanation

#### `batch_scan_example.sh`
- Executable shell script with usage examples
- Demonstrates various scanning scenarios
- Ready-to-use template for users

### 2. Modified Files

#### `main.py`
**Added imports:**
- `yaml` - for parsing YAML config files
- `datetime` - for timestamp generation
- `Path` from `pathlib` - for file path handling
- `urlparse` from `urllib.parse` - for URL parsing

**New command-line argument:**
- `--config` / `-c` - Path to YAML config file for batch scanning

**New functions:**

1. `sanitize_url_for_filename(url: str) -> str`
   - Converts URL to safe filename format
   - Extracts host and port from URL
   - Replaces special characters with underscores
   - Example: `http://192.168.1.100:8080` → `192_168_1_100_8080`

2. `setup_target_logging(output_dir: Path, target_url: str)`
   - Configures loguru for per-target logging
   - Removes existing file handlers
   - Re-adds console handler for real-time output
   - Adds target-specific file handler
   - Returns log file path

3. `load_targets_from_config(config_path: str) -> list`
   - Loads target URLs from YAML config file
   - Validates file existence and format
   - Returns list of target URLs
   - Handles errors gracefully

4. `scan_single_target(target_url, args, llm, specialized_llms, output_dir)`
   - Scans a single target with dedicated logging
   - Sets up per-target log file
   - Creates Agent instance for the target
   - Runs dynamic analysis
   - Handles errors without stopping batch
   - Returns result dictionary with status

5. `batch_scan(targets, args, llm, specialized_llms)`
   - Orchestrates scanning of multiple targets
   - Creates time-stamped output directory
   - Iterates through target list
   - Calls scan_single_target for each
   - Provides progress indicators
   - Generates summary report

**Modified `main()` function:**
- Added check for `--config` argument
- If config provided, runs batch_scan mode
- Otherwise, runs original single-target mode
- Maintains backward compatibility

#### `requirements.txt`
**Added dependency:**
- `PyYAML>=6.0` - for YAML config file parsing

## Features

### Batch Scanning
- Scan multiple MCP servers from a single config file
- Sequential processing of targets
- Independent error handling per target
- Progress tracking with counters

### Organized Logging
- Time-stamped output directories: `logs/scan_YYYY-MM-DD_HH-MM-SS/`
- Per-IP log files: `192_168_1_100_8080.log`
- Separate logs for each target
- Console output for real-time monitoring
- Detailed debug logs in files

### Error Handling
- Individual target failures don't stop batch
- Comprehensive error logging
- Summary report with success/failure counts
- Graceful resource cleanup

### Backward Compatibility
- Original single-target mode unchanged
- Batch mode only activated with `--config` flag
- All existing command-line options work in batch mode

## Usage Examples

### Basic Batch Scan
```bash
python main.py --config targets.yaml -k YOUR_API_KEY
```

### With Custom Prompt
```bash
python main.py --config targets.yaml -k YOUR_API_KEY -p "Focus on security vulnerabilities"
```

### With English Output
```bash
python main.py --config targets.yaml -k YOUR_API_KEY --language en
```

### Single Target (Original Mode)
```bash
python main.py --server_url http://192.168.1.100:8080 -k YOUR_API_KEY
```

## Output Structure

```
logs/
└── scan_2026-03-11_14-30-00/
    ├── 192_168_1_100_8080.log
    ├── 192_168_1_101_8080.log
    └── 10_0_0_50_9000.log
```

## Testing Recommendations

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Create test config:**
   - Edit `targets.yaml` with your test servers
   - Start with 2-3 targets

3. **Run test scan:**
   ```bash
   python main.py --config targets.yaml -k YOUR_API_KEY
   ```

4. **Verify output:**
   - Check `logs/scan_*/` directory
   - Verify each target has its own log file
   - Review console output for progress

## Benefits

1. **Efficiency**: Scan multiple servers without manual intervention
2. **Organization**: Clear log structure with timestamps and IP-based naming
3. **Reliability**: Individual failures don't affect other scans
4. **Traceability**: Each target has complete, isolated logs
5. **Flexibility**: Works with existing command-line options
6. **Compatibility**: Original functionality preserved

## Future Enhancements (Optional)

- Parallel scanning with asyncio.gather()
- Configurable retry logic for failed targets
- JSON/CSV output format for results
- Email notifications on completion
- Integration with CI/CD pipelines
- Web dashboard for monitoring
