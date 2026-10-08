"""Build a standalone user package; source/tests/developer docs are never copied."""
import argparse
import os
import platform
import plistlib
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build(tag, output):
    if not tag.startswith('v') or any(c not in '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ.-' for c in tag):
        raise ValueError('Expected a version tag such as v0.2.0-dev.1')
    system = {'Darwin': 'macos', 'Windows': 'windows', 'Linux': 'linux'}[platform.system()]
    arch = {'AMD64': 'x64', 'x86_64': 'x64', 'arm64': 'arm64', 'aarch64': 'arm64'}[platform.machine()]
    name = 'AgentRelay-%s-%s-%s' % (tag, system, arch)
    work = ROOT / 'build' / name
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    output.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir', '--windowed' if system == 'macos' else '--console',
        '--name', 'AgentRelay', '--paths', str(ROOT / 'app'),
        '--distpath', str(work / 'compiled'), '--workpath', str(work / 'work'),
        '--specpath', str(work), '--add-data', str(ROOT / 'app/web') + os.pathsep + 'web',
        '--collect-submodules', 'relay', '--collect-all', 'zstandard',
        '--hidden-import', 'cli', '--hidden-import', 'server',
        '--hidden-import', 'sqlite3', '--hidden-import', '_sqlite3',
        str(ROOT / 'app/portable.py'),
    ], check=True, cwd=ROOT)
    stage = work / name
    stage.mkdir()
    compiled = work / 'compiled/AgentRelay'
    if system == 'macos':
        app = stage / 'AgentRelay.app'
        shutil.copytree(work / 'compiled/AgentRelay.app', app, symlinks=True)
        binary_dir = app / 'Contents/MacOS'
        info = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
        info['CFBundleShortVersionString'] = info['CFBundleVersion'] = tag.lstrip('v').split('-')[0]
        info['LSMinimumSystemVersion'] = '14.0' if arch == 'arm64' else '15.0'
        info['LSUIElement'] = True
        info['CFBundleGetInfoString'] = 'AgentRelay: local conversation and Skill storage'
        (app / 'Contents/Info.plist').write_bytes(plistlib.dumps(info))
        subprocess.run(['codesign', '--force', '--sign', '-', str(app)], check=True)
        binary = binary_dir / 'AgentRelay'
    else:
        shutil.copytree(compiled, stage, dirs_exist_ok=True, symlinks=True)
        binary = stage / ('AgentRelay.exe' if system == 'windows' else 'AgentRelay')
    # Verify the exact relocated distribution before archiving, with isolated data.
    subprocess.run([sys.executable, str(ROOT / 'scripts/smoke_release.py'), str(binary)], check=True, cwd=ROOT)
    if system == 'linux':
        asset = output / (name + '.tar.gz')
        with tarfile.open(asset, 'w:gz') as archive:
            archive.add(stage, arcname=name)
    elif system == 'macos':
        asset = output / (name + '.zip')
        subprocess.run(['ditto', '-c', '-k', '--keepParent', str(stage), str(asset)], check=True)
    else:
        asset = output / (name + '.zip')
        with zipfile.ZipFile(asset, 'w', zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(stage.rglob('*')):
                if path.is_file():
                    archive.write(path, name + '/' + path.relative_to(stage).as_posix())
    print('ASSET=' + str(asset))
    return asset


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--tag', required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/release')
    args = parser.parse_args()
    build(args.tag, args.output.resolve())
