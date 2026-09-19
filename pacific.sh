#!/usr/bin/env bash
# Pacific launcher for macOS / Linux.  chmod +x pacific.sh && ./pacific.sh
set -euo pipefail
cd "$(dirname "$0")"

if   [ -x ".venv/bin/python" ];   then PY=".venv/bin/python"
elif command -v python3 >/dev/null; then PY="python3"
elif command -v python  >/dev/null; then PY="python"
else
  echo
  echo "  [!] Python was not found. Install Python 3.9+ and try again."
  echo
  exit 1
fi

exec "$PY" run.py "$@"
