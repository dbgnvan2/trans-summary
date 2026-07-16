#!/bin/zsh

set -euo pipefail

cd "$(dirname "$0")"

if [[ -x ".venv/bin/python3.11" ]]; then
  exec .venv/bin/python3.11 ts_gui.py
elif [[ -x ".venv/bin/python3" ]]; then
  exec .venv/bin/python3 ts_gui.py
else
  exec python3 ts_gui.py
fi
