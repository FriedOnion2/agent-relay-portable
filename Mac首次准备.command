#!/bin/bash
# 在 Mac 上只需要执行这一次。
#
# 文件从 Windows 拷过来时会丢掉"可执行"标记，导致双击 .command / .app 没反应。
# 这个脚本把标记补回来，顺便解掉 macOS 的隔离提示。
#
# 用法：在本文件夹打开终端，执行
#     bash Mac首次准备.command

cd "$(dirname "$0")" || exit 1

printf '\n  AgentRelay 便携版 · Mac 首次准备\n\n'

chmod +x "启动_AgentRelay.command" 2>/dev/null \
  && printf '  ✓ 已赋可执行权限：启动_AgentRelay.command\n'

chmod +x "AgentRelay.app/Contents/MacOS/AgentRelay" 2>/dev/null \
  && printf '  ✓ 已赋可执行权限：AgentRelay.app\n'
chmod +x "Mac安装依赖.command" 2>/dev/null

if command -v xattr >/dev/null 2>&1; then
  xattr -dr com.apple.quarantine . >/dev/null 2>&1
  printf '  ✓ 已解除 macOS 隔离提示（quarantine）\n'
fi

# Gatekeeper 对未签名应用有时会连带隔离整个包，单独再清一次
if command -v xattr >/dev/null 2>&1; then
  xattr -cr "AgentRelay.app" >/dev/null 2>&1
fi

printf '\n  Python 检查一下：\n'
if command -v python3 >/dev/null 2>&1; then
  V=$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null)
  printf '    ✓ python3 %s  （%s）\n' "$V" "$(command -v python3)"
else
  printf '    × 没找到 python3。建议执行： brew install python\n'
fi

printf '\n  准备 DSH 压缩日志依赖（首次需要网络）：\n'
if ! bash "Mac安装依赖.command"; then
  printf '\n  依赖安装未完成。基本功能仍可用，DSH 压缩会话需稍后重跑 Mac安装依赖.command。\n'
  exit 1
fi

printf '\n  会话目录探测：\n'
"$PWD/runtime/macos-$(uname -m)/bin/python3" app/bootstrap.py | sed -n '/会话目录/,$p'

printf '\n  准备完成。现在可以双击「启动_AgentRelay.command」或「AgentRelay.app」了。\n\n'
