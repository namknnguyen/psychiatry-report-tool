#!/usr/bin/env bash
# Start PsychReport locally. Requires Python 3.9+ and nothing else.
set -euo pipefail
cd "$(dirname "$0")"
exec python3 -m app.main --port "${PORT:-8765}" --open "$@"
