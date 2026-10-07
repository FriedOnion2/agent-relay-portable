#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/app/linux-common.sh"
cd -- "$RELAY_ROOT"
relay_find_python
printf 'AgentRelay · Linux\nPython: %s\n' "$RELAY_LINUX_PYTHON"
# No implicit installation or desktop requirement. Ctrl+C stops this process.
exec "$RELAY_LINUX_PYTHON" app/cli.py serve "$@"
