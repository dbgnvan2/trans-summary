#!/bin/zsh

# Change to script directory
cd "$(dirname "$0")"

# Run the processor
.venv/bin/python3.11 transcript_process.py

# Keep window open
echo ""
echo "Press any key to close..."
read -n 1
