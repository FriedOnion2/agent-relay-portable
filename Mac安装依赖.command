#!/bin/bash
# 为当前 Mac 创建独立运行环境，不修改系统或 Homebrew Python 的包。
cd "$(dirname "$0")" || exit 1

CANDIDATES=(
  "/opt/homebrew/bin/python3"
  "/usr/local/bin/python3"
  "/Library/Frameworks/Python.framework/Versions/Current/bin/python3"
  "/usr/bin/python3"
)
if command -v python3 >/dev/null 2>&1; then CANDIDATES+=("$(command -v python3)"); fi
if [ -n "${RELAY_PYTHON:-}" ]; then CANDIDATES=("$RELAY_PYTHON" "${CANDIDATES[@]}"); fi
PY=""
for candidate in "${CANDIDATES[@]}"; do
  [ -x "$candidate" ] || continue
  if "$candidate" -c 'import sys;raise SystemExit(0 if sys.version_info>=(3,8) else 1)' >/dev/null 2>&1; then
    PY="$candidate"
    break
  fi
done
if [ -z "$PY" ]; then
  printf '未找到 Python 3.8+，请先安装 Python。\n' >&2
  exit 1
fi

ENV_DIR="$PWD/runtime/macos-$(uname -m)"
ENV_PY="$ENV_DIR/bin/python3"
if ! "$ENV_PY" -c 'import sys;raise SystemExit(0 if sys.version_info>=(3,8) else 1)' >/dev/null 2>&1; then
  "$PY" -m venv "$ENV_DIR" || exit 1
fi
if ! "$ENV_PY" -c 'import zstandard' >/dev/null 2>&1; then
  "$ENV_PY" -m pip install --disable-pip-version-check -r requirements-optional.txt || exit 1
fi
printf '✓ Mac 运行环境已准备：%s\n' "$ENV_PY"
"$ENV_PY" -c 'import zstandard; print("✓ DSH 压缩解码：zstandard " + zstandard.__version__)'
