# Summary of Changes - Named Target Support

## Overview
Enhanced the MCP batch scanning feature to support named targets, allowing users to assign meaningful names to each server for better identification and organization.

## Changes Made

### 1. Updated Configuration Format

**File: `mcp-scan/targets.yaml`**

**New Format (Recommended):**
```yaml
targets:
  - name: "MCP01"
    url: "http://109.105.132.36:8001"
  - name: "MCP02"
    url: "http://192.168.1.101:8080"
```

**Old Format (Still Supported):**
```yaml
targets:
  - "http://192.168.1.100:8080"
  - "http://192.168.1.101:8080"
```

### 2. Code Modifications

**File: `mcp-scan/main.py`**

#### Modified Functions:

1. **`sanitize_url_for_filename(url, name=None)`**
   - Added optional `name` parameter
   - Prepends name to filename if provided
   - Example output: `MCP01_109_105_132_36_8001.log`

2. **`setup_target_logging(output_dir, target_url, target_name=None)`**
   - Added optional `target_name` parameter
   - Passes name to `sanitize_url_for_filename()`

3. **`load_targets_from_config(config_path)`**
   - Now handles both old and new config formats
   - Normalizes all targets to dict format: `{"name": "...", "url": "..."}`
   - Backward compatible with simple URL strings
   - Returns list of dicts instead of raw config data

4. **`scan_single_target(target_url, args, llm, specialized_llms, output_dir, target_name=None)`**
   - Added optional `target_name` parameter
   - Creates display name for logging: `"MCP01 (http://...)"` or just URL
   - Passes name to logging setup
   - Includes name in result dict

5. **`batch_scan(targets, args, llm, specialized_llms)`**
   - Extracts `name` and `url` from target dict
   - Creates display name for progress messages
   - Passes name to `scan_single_target()`

### 3. Documentation Updates

**File: `CLAUDE.md`**
- Added new section "MCP Batch Scanning" under "Key Patterns and Conventions"
- Documented configuration format with named targets
- Explained output structure with name prefixes
- Listed key features and backward compatibility

**File: `mcp-scan/BATCH_SCAN_README.md`**
- Updated Quick Start with new format
- Added "Format 1: Named Targets (Recommended)" section
- Added "Format 2: Simple URLs (Legacy)" section
- Updated example configurations with named targets
- Updated output structure section with examples for both formats
- Updated log file naming documentation

## Benefits

1. **Better Organization**: Name targets by vulnerability type, environment, or purpose
2. **Easy Identification**: Log files clearly show which server they belong to
3. **Backward Compatible**: Old config files still work without modification
4. **Flexible Naming**: Use any naming convention (MCP01, PROD-API, CVE-2024-1234, etc.)
5. **Improved Logging**: Console output shows both name and URL for clarity

## Example Usage

### Configuration
```yaml
targets:
  - name: "MCP01"
    url: "http://109.105.132.36:8001"
  - name: "PROD-API"
    url: "https://api.example.com:8080"
  - name: "CVE-2024-1234"
    url: "http://10.0.0.50:9000"
```

### Command
```bash
python main.py --config targets.yaml -k YOUR_API_KEY
```

### Output Structure
```
logs/scan_2026-03-11_14-30-00/
├── MCP01_109_105_132_36_8001.log
├── PROD-API_api_example_com_8080.log
└── CVE-2024-1234_10_0_0_50_9000.log
```

### Console Output
```
[1/3] Processing target: MCP01 (http://109.105.132.36:8001)
Starting scan for target: MCP01 (http://109.105.132.36:8001)
Logging to: logs/scan_2026-03-11_14-30-00/MCP01_109_105_132_36_8001.log
...
```

## Testing

To test the implementation:

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Verify syntax:**
   ```bash
   python -m py_compile main.py
   ```

3. **Create test config:**
   Edit `targets.yaml` with your test servers

4. **Run test scan:**
   ```bash
   python main.py --config targets.yaml -k YOUR_API_KEY
   ```

5. **Verify output:**
   - Check `logs/scan_*/` directory
   - Verify log files have name prefixes
   - Review console output for named targets

## Backward Compatibility

✅ Old config files (simple URL strings) work without modification
✅ Single-target mode (`--server_url`) unchanged
✅ All existing command-line options work with named targets
✅ Mixed format (some named, some not) is supported
