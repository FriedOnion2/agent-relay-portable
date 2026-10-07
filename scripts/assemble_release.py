"""One download for all supported devices; unpack native runtimes in local caches."""
import argparse
import hashlib
import json
import plistlib
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLATFORMS = ('windows-x64', 'macos-arm64', 'macos-x64', 'linux-x64')


def assemble(tag, assets, output):
    if not tag.startswith('v') or any(c not in '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ.-' for c in tag):
        raise ValueError('Invalid version tag')
    name = 'AgentRelay-' + tag + '-universal'
    stage = output / name
    if stage.exists():
        shutil.rmtree(stage)
    (stage / 'runtimes').mkdir(parents=True)
    payloads = {}
    for target in PLATFORMS:
        suffix = '.tar.gz' if target.startswith('linux') else '.zip'
        path = assets / ('AgentRelay-' + tag + '-' + target + suffix)
        if not path.is_file():
            raise FileNotFoundError(path)
        shutil.copy2(path, stage / 'runtimes' / path.name)
        payloads[target] = {'file': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    metadata = {'version': tag, 'kind': 'agentrelay-universal', 'runtimes': payloads}
    (stage / 'version.json').write_text(json.dumps(metadata, indent=2) + '\n')
    shutil.copy2(ROOT / 'config.example.json', stage)
    windows = '''param([Parameter(ValueFromRemainingArguments=$true)][string[]]$RelayArguments)
$ErrorActionPreference = 'Stop'
$portableRoot = $PSScriptRoot
$manifest = Get-Content -LiteralPath (Join-Path $portableRoot 'version.json') -Raw | ConvertFrom-Json
$payload = $manifest.runtimes.'windows-x64'
$archivePath = Join-Path (Join-Path $portableRoot 'runtimes') $payload.file
if ((Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLower() -ne $payload.sha256) { throw 'Runtime checksum mismatch' }
$cacheRoot = Join-Path $env:LOCALAPPDATA ('AgentRelay\\' + $manifest.version)
New-Item -ItemType Directory -Force -Path $cacheRoot | Out-Null
$folderName = 'AgentRelay-' + $manifest.version + '-windows-x64'
$destination = Join-Path $cacheRoot $folderName
$lockPath = Join-Path $cacheRoot 'prepare.lock'
$lock = $null
for ($attempt = 0; $attempt -lt 120 -and $null -eq $lock; $attempt++) {
  try { $lock = [System.IO.File]::Open($lockPath, [System.IO.FileMode]::OpenOrCreate, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None) }
  catch [System.IO.IOException] { Start-Sleep -Milliseconds 500 }
}
if ($null -eq $lock) { throw 'Another launcher is preparing the runtime; try again later' }
try {
  if (-not (Test-Path -LiteralPath (Join-Path $destination 'AgentRelay.exe'))) {
    $temporary = Join-Path $cacheRoot ([Guid]::NewGuid().ToString())
    try {
      Expand-Archive -LiteralPath $archivePath -DestinationPath $temporary
      Move-Item -LiteralPath (Join-Path $temporary $folderName) -Destination $destination
    } finally { if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Recurse -Force } }
  }
} finally { $lock.Dispose() }
$env:RELAY_PORTABLE_ROOT = $portableRoot
& (Join-Path $destination 'AgentRelay.exe') serve @RelayArguments
exit $LASTEXITCODE
'''
    (stage / 'Start-AgentRelay.ps1').write_text(windows, encoding='utf-8-sig')
    (stage / '启动_AgentRelay.bat').write_bytes(b'@echo off\r\nchcp 65001 >nul\r\npowershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-AgentRelay.ps1" %*\r\nif errorlevel 1 pause\r\n')
    for system in ('macos', 'linux'):
        targets = ['macos-arm64', 'macos-x64'] if system == 'macos' else ['linux-x64']
        cases = []
        for target in targets:
            arch = 'arm64' if target.endswith('arm64') else 'x86_64'
            item = payloads[target]
            cases.append('  %s) PAYLOAD=%s; EXPECTED=%s; FOLDER=AgentRelay-%s-%s ;;' %
                         (arch, item['file'], item['sha256'], tag, target))
        script = '''#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
case "$(uname -m)" in
@CASES@
  *) printf 'Unsupported CPU architecture.\\n' >&2; exit 1 ;;
esac
ARCHIVE="$ROOT/runtimes/$PAYLOAD"
@HASH@
[ "$ACTUAL" = "$EXPECTED" ] || { printf 'Runtime checksum mismatch.\\n' >&2; exit 1; }
CACHE=@CACHE@
mkdir -p "$CACHE"
DEST="$CACHE/$FOLDER"
LOCK="$CACHE/$FOLDER.lock"
LOCKED=false
for attempt in $(seq 1 120); do
  if mkdir "$LOCK" 2>/dev/null; then LOCKED=true; break; fi
  sleep .5
done
[ "$LOCKED" = true ] || { printf 'Another launcher is preparing the runtime; try again later.\\n' >&2; exit 1; }
TEMP=""
cleanup() { [ -z "$TEMP" ] || rm -rf "$TEMP"; rmdir "$LOCK" 2>/dev/null || true; }
trap cleanup EXIT
if [ ! -x "$DEST/@BINARY@" ]; then
  TEMP="$(mktemp -d "$CACHE/.extract-XXXXXX")"
  @EXTRACT@
  mv "$TEMP/$FOLDER" "$DEST"
fi
cleanup
trap - EXIT
export RELAY_PORTABLE_ROOT="$ROOT"
exec "$DEST/@BINARY@" serve "$@"
'''
        script = script.replace('@CASES@', '\n'.join(cases))
        if system == 'macos':
            script = script.replace('@HASH@', 'ACTUAL="$(/usr/bin/shasum -a 256 "$ARCHIVE" | cut -d " " -f 1)"')
            script = script.replace('@CACHE@', '"$HOME/Library/Caches/AgentRelay/' + tag + '"')
            script = script.replace('@BINARY@', 'AgentRelay.app/Contents/MacOS/AgentRelay')
            script = script.replace('@EXTRACT@', '/usr/bin/ditto -x -k "$ARCHIVE" "$TEMP"\n  xattr -dr com.apple.quarantine "$TEMP/$FOLDER/AgentRelay.app" 2>/dev/null || true')
            filename = '启动_AgentRelay.command'
        else:
            script = script.replace('@HASH@', 'ACTUAL="$(sha256sum "$ARCHIVE" | cut -d " " -f 1)"')
            script = script.replace('@CACHE@', '"${XDG_CACHE_HOME:-$HOME/.cache}/agentrelay/' + tag + '"')
            script = script.replace('@BINARY@', 'AgentRelay')
            script = script.replace('@EXTRACT@', 'tar -xzf "$ARCHIVE" -C "$TEMP"')
            filename = '启动_AgentRelay.sh'
        (stage / filename).write_text(script)
        (stage / filename).chmod(0o755)
    app = stage / 'AgentRelay.app'
    (app / 'Contents/MacOS').mkdir(parents=True)
    info = plistlib.loads((ROOT / 'AgentRelay.app/Contents/Info.plist').read_bytes())
    info['CFBundleShortVersionString'] = info['CFBundleVersion'] = tag.lstrip('v').split('-')[0]
    info['CFBundleGetInfoString'] = 'AgentRelay universal portable launcher'
    info['LSMinimumSystemVersion'] = '14.0'
    (app / 'Contents/Info.plist').write_bytes(plistlib.dumps(info))
    finder = '''#!/bin/bash
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
LOGDIR="$ROOT/logs"
if ! { mkdir -p "$LOGDIR" && touch "$LOGDIR/.writable"; } 2>/dev/null; then LOGDIR="$HOME/Library/Logs/AgentRelay"; fi
mkdir -p "$LOGDIR" || exit 1
LOG="$LOGDIR/server-$(date +%Y%m%d-%H%M%S)-$$.log"
nohup /bin/bash "$ROOT/启动_AgentRelay.command" </dev/null >>"$LOG" 2>&1 &
'''
    (app / 'Contents/MacOS/AgentRelay').write_text(finder)
    (app / 'Contents/MacOS/AgentRelay').chmod(0o755)
    prepare = '''#!/bin/bash
cd "$(dirname "$0")" || exit 1
xattr -dr com.apple.quarantine AgentRelay.app 2>/dev/null || true
chmod +x AgentRelay.app/Contents/MacOS/AgentRelay 启动_AgentRelay.command
printf '准备完成。可双击 AgentRelay.app 或启动_AgentRelay.command。\\n'
'''
    (stage / 'Mac首次运行.command').write_text(prepare)
    (stage / 'Mac首次运行.command').chmod(0o755)
    (stage / '开始使用.txt').write_text('''AgentRelay {tag} 开发预览版 — 一个包切换 Windows / Mac / Linux

本总包内置四套运行时：Windows x64、Mac Apple Silicon / Intel、Linux x64。
无需另装 Python、Node.js 或 zstandard，首次启动不下载依赖。
完整解压到移动盘或本机目录。请保留 runtimes/，不要只复制启动器。

Windows 10/11 x64：双击 启动_AgentRelay.bat。
Mac Apple Silicon（macOS 14+）/ Intel（macOS 15+）：双击 AgentRelay.app，或启动_AgentRelay.command。
  应用未经过 Apple 公证。若被系统阻止，在可信解压目录打开终端，运行
  bash Mac首次运行.command，再启动。终端方式也可 bash 启动_AgentRelay.command。
Linux x64：Ubuntu 22.04+ / 同等 glibc 2.35+，运行 bash 启动_AgentRelay.sh。

启动器只解压当前设备需要的运行时到本机缓存，避免移动盘 noexec、权限和符号链接差异。
Windows 缓存：%LOCALAPPDATA%/AgentRelay/{tag}/
Mac 缓存：~/Library/Caches/AgentRelay/{tag}/
Linux 缓存：~/.cache/agentrelay/{tag}/（尊重 XDG_CACHE_HOME）。
移动盘中共用 config.json、storage/ 和启动器，切换设备无需重新下载其他版本。
首次运行时解压需要等待；后续复用缓存。若解压中断，删除该版本缓存后重试。

浏览器自动打开。默认端口 8745，占用时尝试后续 5 个端口；查看实际网址。
退出：网页右上角「退出服务」；终端启动也可 Ctrl+C。仅关闭网页不会停止服务。
程序不会自动结束占用端口的其他进程。Mac 后台日志位于总包 logs/，或 ~/Library/Logs/AgentRelay/。

对话：左侧选择来源，可预览、导出 Markdown 或迁移到可写目标。
存储：勾选对话/Skill，或全选当前列表，点击「存储所选对话/Skill」。
  Skill 在「Skill 存储」面板先选择 Agent 并查找，必要时填实际根目录。
  每项独立成包，成功项取消勾选，失败项保留勾选。全选仅限当前可读取列表。
恢复：总包根目录的 storage/ 按 Agent 分类保存 ZIP。整个包随移动盘切换设备，或复制 storage/，
  在目标设备存储面板选包、填写本机项目/Skill 目录后恢复。网页恢复逐包操作。
  同 ID/同名不覆盖。关闭正在写入源或目标记录的 Agent 后再操作。
配置：复制 config.example.json 为 config.json。默认自动使用当前设备的 Agent 目录；
  若手动填了原设备绝对路径，换设备需修改。存储包未加密，正文可能含敏感内容。

通用写入目标：WorkBuddy、DSH、Claude Code、Codex。CodeBuddy/SDK 支持读取及对应软件原生恢复。
DSH 导入写入 v0 历史；图片、加密思考及特有工具协议不能保证完整跨工具转换。
Codex Desktop 的索引可能需要额外刷新，JSONL 写入不保证自动出现在桌面列表。
Skill 只复制文件，不执行脚本、不安装依赖或转换目标工具接口。
本地运行，不上传数据、不调用模型。开发预览版请先用副本验证。
完整使用说明：https://github.com/FriedOnion2/agent-relay-portable
'''.format(tag=tag), encoding='utf-8')
    asset = output / (name + '.zip')
    with zipfile.ZipFile(asset, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(stage.rglob('*')):
            if path.is_file():
                archive.write(path, name + '/' + path.relative_to(stage).as_posix())
    checksum = hashlib.sha256(asset.read_bytes()).hexdigest()
    (output / 'SHA256SUMS.txt').write_text(checksum + '  ' + asset.name + '\n')
    print('UNIVERSAL=' + str(asset))
    return asset


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--tag', required=True)
    parser.add_argument('--assets', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assemble(args.tag, args.assets.resolve(), args.output.resolve())
