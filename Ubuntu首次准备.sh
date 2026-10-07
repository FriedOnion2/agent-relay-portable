#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/app/linux-common.sh"
cd -- "$RELAY_ROOT"
relay_find_python base
printf '创建 Ubuntu 独立依赖环境: %s\n' "$RELAY_LINUX_VENV"
if ! "$RELAY_LINUX_PYTHON" -m venv "$RELAY_LINUX_VENV"; then
  printf '%s\n' '环境创建失败。Ubuntu 请先运行 sudo apt install python3-venv。' \
    '请使用 Linux 可执行、支持符号链接且可写的目录；RELAY_VENV 可指定位置。' >&2
  exit 1
fi
"$RELAY_LINUX_VENV/bin/python3" -m pip install -r "$RELAY_ROOT/requirements-optional.txt"
printf '\n准备完成。启动: bash 启动_AgentRelay.sh\n'
printf '双系统探测: "%s" app/cli.py windows-users\n' "$RELAY_LINUX_VENV/bin/python3"
