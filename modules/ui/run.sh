#!/usr/bin/env bash
# Start the Crypto Lab UI (activates the project venv automatically):
#   ./run.sh [--port 8501]
set -euo pipefail
cd "$(dirname "$0")"
if [ -z "${VIRTUAL_ENV:-}" ] && [ -f ../../.venv/bin/activate ]; then
  # shellcheck disable=SC1091
  source ../../.venv/bin/activate
fi
exec python run.py "$@"
