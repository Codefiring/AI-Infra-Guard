#!/bin/bash
# Example script for running batch MCP scans

# Set your API key (or export OPENROUTER_API_KEY environment variable)
API_KEY="your-api-key-here"

# Example 1: Basic batch scan
echo "Running basic batch scan..."
python main.py --config targets.yaml -k "$API_KEY"

# Example 2: Batch scan with custom prompt
echo "Running batch scan with custom prompt..."
python main.py --config targets.yaml -k "$API_KEY" -p "Focus on authentication and authorization vulnerabilities"

# Example 3: Batch scan with English output
echo "Running batch scan with English output..."
python main.py --config targets.yaml -k "$API_KEY" --language en

# Example 4: Batch scan with custom headers
echo "Running batch scan with custom headers..."
python main.py --config targets.yaml -k "$API_KEY" \
  --header "Authorization:Bearer token123" \
  --header "X-Custom-Header:value"

# Example 5: Batch scan with debug mode
echo "Running batch scan with debug mode..."
python main.py --config targets.yaml -k "$API_KEY" --debug

echo "All scans completed. Check logs/ directory for results."
