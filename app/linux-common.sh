#!/usr/bin/env bash
# Sourced by both Linux entry points; no changes to the system Python.
RELAY_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)" || return 1
RELAY_LINUX_VENV="${RELAY_VENV:-${XDG_DATA_HOME:-$HOME/.local/share}/agent-relay/venv}"

relay_find_python() {
  local candidate
  local candidates=()
  if [[ -n "${RELAY_PYTHON:-}" ]]; then
    candidates=("$RELAY_PYTHON")
  else
    if [[ "${1:-}" != base ]]; then
      candidates+=("$RELAY_LINUX_VENV/bin/python3")
    fi
    candidates+=("$RELAY_ROOT/runtime/linux/bin/python3"
                 "$RELAY_ROOT/runtime/python/bin/python3"
                 "$RELAY_ROOT/runtime/python/bin/python"
                 "$(command -v python3 || true)" "$(command -v python || true)")
  fi
  for candidate in "${candidates[@]}"; do
    [[ -n "$candidate" ]] || continue
    if "$candidate" -c 'import sys;raise SystemExit(sys.version_info < (3,8))' >/dev/null 2>&1; then
      RELAY_LINUX_PYTHON="$candidate"
      return 0
    fi
  done
  printf '%s\n' '未找到可运行的 Python ≥3.8。Ubuntu 安装命令：' \
    '  sudo apt install python3 python3-venv' \
    '若设置了 RELAY_PYTHON，请检查该解释器是否可用。' >&2
  return 1
}
