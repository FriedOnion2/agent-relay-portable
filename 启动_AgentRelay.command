#!/bin/bash
# AgentRelay 便携版 · macOS 终端启动器
# 双击即可；所有路径相对本文件解析，移动硬盘换挂载点也不影响。

cd "$(dirname "$0")" || exit 1
export LC_ALL=en_US.UTF-8 2>/dev/null

clear
printf '\n'
printf '  ╭──────────────────────────────────────────────╮\n'
printf '  │   AgentRelay 便携版                            │\n'
printf '  ╰──────────────────────────────────────────────╯\n'
printf '\n'
printf '  目录： %s\n\n' "$PWD"

# ---------- 1. 找 Python ----------
# 顺序：盘上自带 runtime → Homebrew → 系统 Python → PATH
CANDIDATES=(
  "$PWD/runtime/python/bin/python3"
  "$PWD/runtime/python/bin/python"
  "/opt/homebrew/bin/python3"
  "/usr/local/bin/python3"
  "/Library/Frameworks/Python.framework/Versions/Current/bin/python3"
  "/usr/bin/python3"
  "/usr/local/bin/python"
  "/usr/bin/python"
)
if command -v python3 >/dev/null 2>&1; then CANDIDATES+=("$(command -v python3)"); fi
if command -v python  >/dev/null 2>&1; then CANDIDATES+=("$(command -v python)"); fi

PY=""
if [ -n "${RELAY_PYTHON:-}" ]; then CANDIDATES=("$RELAY_PYTHON" "${CANDIDATES[@]}"); fi
for c in "${CANDIDATES[@]}"; do
  [ -x "$c" ] || continue
  if "$c" -c 'import sys;raise SystemExit(0 if sys.version_info>=(3,8) else 1)' >/dev/null 2>&1; then
    PY="$c"
    break
  fi
done

if [ -z "$PY" ]; then
  printf '  [×] 这台 Mac 上没有找到可用的 Python\n\n'
  printf '      解决办法（任选其一）：\n\n'
  printf '      1. 安装 Homebrew 版 Python：\n'
  printf '           brew install python\n\n'
  printf '      2. 或放一份 Python 到 U 盘的 runtime/python/bin/python3\n\n'
  printf '      3. 或装 Xcode 命令行工具：\n'
  printf '           xcode-select --install\n\n'
  printf '      然后重新双击本文件。\n\n'
  read -r -p "  按回车键关闭…" _
  exit 1
fi

# ---------- 2. 版本门槛 ----------
if ! "$PY" -c 'import sys;raise SystemExit(0 if sys.version_info>=(3,8) else 1)' 2>/dev/null; then
  VER=$("$PY" -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null)
  printf '  [×] Python 版本过低：%s（需要 3.8 以上）\n\n' "$VER"
  printf '      建议安装新版： brew install python\n\n'
  read -r -p "  按回车键关闭…" _
  exit 1
fi

# ---------- 3. 环境体检 ----------
"$PY" app/bootstrap.py
if [ $? -eq 2 ]; then
  printf '\n  需要先解决上面的问题才能继续。\n\n'
  read -r -p "  按回车键关闭…" _
  exit 1
fi

# ---------- 4. 启动 ----------
printf '\n  正在启动 Web 界面，浏览器会自动打开。\n'
printf '  关闭这个窗口即可停止服务。\n\n'
"$PY" app/cli.py serve

printf '\n  服务已停止。\n'
read -r -p "  按回车键关闭…" _
