# Install and launch

The Release bundle and running from source, ports and quitting. Chinese original: [guide/install.md](../guide/install.md).

## Release bundle (no Python needed)

Stable release: [v1.0.0](https://github.com/FriedOnion2/agent-relay-portable/releases/tag/v1.0.0) (Latest). **Rolling dev build:** [`dev`](https://github.com/FriedOnion2/agent-relay-portable/releases/tag/dev) — rebuilt on every merge to `main`, always exactly one, may be unstable.

Download **`AgentRelay-<version>-universal.zip`** from [GitHub Releases](https://github.com/FriedOnion2/agent-relay-portable/releases), extract it completely and run the launcher for your device. One bundle contains Windows x64, Mac (Apple Silicon / Intel) and Linux x64 runtimes, with Python and `zstandard` built in; you do not need to install Python or Node.js. Do not pick GitHub's automatically generated **Source code** archive; that is the development source.

| Device | Launcher | Supported systems |
|---|---|---|
| Windows | `启动_AgentRelay.bat` | Windows 10/11 x64 |
| Mac | `AgentRelay.app` or `bash 启动_AgentRelay.command` | Apple Silicon: macOS 14+; Intel: macOS 15+ |
| Linux | `bash 启动_AgentRelay.sh` | Ubuntu 22.04+ / glibc 2.35+ x64 |

- The bundle root holds the optional `config.json`, `storage/` and `index/`, shared across devices. Exit the service, then carry the whole bundle on a portable drive; you never need to download another system's build. Copy drafts exported outside the bundle separately.
- The launcher extracts only the runtime for the current platform into a local cache (avoiding `noexec` mounts and Mac symlink differences). Nothing is downloaded at first launch. **Do not delete `runtimes/`** and do not copy only the launcher.
- The target assistants (Claude Code, Codex, …) must still be installed and signed in on that device.
- Device-specific directory choices are saved in `devices/<device-id>.json`; another device starts with automatic detection. If a path in the shared configuration stops working you are prompted to reselect it; saving an empty value restores automatic detection.
- The Mac app is not notarized by Apple. If macOS blocks it, run `bash Mac首次运行.command` in the trusted extracted directory, then launch again.
- Local caches: `%LOCALAPPDATA%/AgentRelay/<version>/` (Windows), `~/Library/Caches/AgentRelay/<version>/` (Mac), `~/.cache/agentrelay/<version>/` (Linux, honouring `XDG_CACHE_HOME`). If extraction was interrupted, delete that version's cache and retry.
- Each version's runtime cache is further separated by the first 16 characters of the archive SHA-256, so rebuilding the same version does not reuse old code. The complete archive checksum is still checked at every launch. Conversations, indexes, configuration and normal operation logs remain beside the portable launchers; local caches are not backups. Standalone means no Python/Node installation is required; a writable local runtime cache is still used.
- Native-package validation now moves the complete distribution after saving an archive and building an index, removes the old path, clears PATH and runs without a data-root override. It checks relative source configuration, listing, archives, offline search, restore and operation logs. Windows passed locally; other systems are checked by their CI jobs. Physical disconnection and every filesystem are not simulated. See [portable storage](../guide/portable-storage.md) (Chinese).
- A separate Windows run moved the latest standalone build from C: to D:, removed the original directory, and passed configuration, archive listing, offline search and restore with PATH empty. Both local volumes were NTFS; no external USB/exFAT drive was mounted for that run.
- Dev builds are marked Pre-release on GitHub and carry `-dev.<commit>` in the file name. Verify downloads against `SHA256SUMS.txt`.

## Run from source

For running the repository source only; Release users can skip this section. You need **Python 3.8 or newer**. Node.js is needed only for the web tests.

| System | First-time setup | Start |
|---|---|---|
| Windows | Install Python, or put a full Windows embeddable Python in `runtime/python/` | double-click `启动_AgentRelay.bat` |
| macOS | `bash Mac首次准备.command` | double-click `AgentRelay.app` or `启动_AgentRelay.command` |
| Ubuntu / Linux | `bash Ubuntu首次准备.sh` (install `python3 python3-venv` first if missing) | `bash 启动_AgentRelay.sh` |

Or run it directly:

```sh
python app/cli.py serve
python app/cli.py serve --no-browser --port 8745
python app/cli.py doctor
```

Use `python3` on Linux / macOS if that is your interpreter name; `RELAY_PYTHON` can point to a specific interpreter. The default address is `http://127.0.0.1:8745/`. If the port is busy, the next 5 are tried; the actual address is shown in the startup output. The program **never kills** whatever occupies a port. To free the port of an old AgentRelay, open its page and click **Stop service**, or press Ctrl+C in its terminal.

### Install with pip / pipx

```sh
pipx install git+https://github.com/FriedOnion2/agent-relay-portable    # recommended: isolated
pip install .                                                         # from a source checkout
pip install ".[dsh]"                                                  # also zstandard (DSH compressed history)
```

This installs two equivalent commands, `relay` and `agent-relay` (same as `python app/cli.py`). The package lives in site-packages but **data is never written there**: `config.json`, `logs/` and `storage/` go to a per-user data directory — `~/.local/share/agent-relay` on Linux (honouring `XDG_DATA_HOME`), `~/Library/Application Support/AgentRelay` on macOS, `%APPDATA%\AgentRelay` on Windows. Set the absolute-path variable `RELAY_PORTABLE_ROOT` to relocate it, for instance onto a portable drive. Running from a source checkout or a Release is unchanged: data stays next to the program.

The installed modules have top-level names (`cli`, `server`, `bootstrap`, `portable`), so use pipx or a dedicated venv rather than a shared environment.

### Quitting and restarting

Click **Stop service** at the top right of the page and confirm to stop the service, including the background service started by `.app`. Requests in flight finish first; other pages using the same service disconnect. In a terminal, press Ctrl+C. Closing the page alone does not stop the service. Run the launcher again to resume; after updating the code, stop the old service and restart.

### DSH dependency and Mac startup

The Release already includes it. Source users install the optional dependency with the interpreter the launcher chose:

```sh
python -m pip install -r requirements-optional.txt
```

On Mac, first-time setup creates a `runtime/macos-<arch>/` virtual environment with `zstandard`; if that fails, rerun `bash Mac安装依赖.command`. Prepare again on every new Mac: the virtual environment depends on the local Python and is not a portable interpreter. Ubuntu setup uses a per-user virtual environment to avoid PEP 668 limits. Without the decoder, DSH sessions are still listed with an install hint; damaged, unfinished, oversized or unknown-version logs are shown as restricted.

The Mac `.app` opens the browser once HTTP is ready and honours `open_browser`. Logs go to the project `logs/`, or to `~/Library/Logs/AgentRelay/` if the external drive refuses writes. Double-clicking from inside the Documents folder once stalled the Python probe; if you see that, use the terminal launcher and check the macOS file and folder access permissions (the root cause is unconfirmed).

## After moving to a new machine: run the check

```bash
python3 app/cli.py doctor      # or python3 app/bootstrap.py
```

It reports whether Python was found and is recent enough, and where each source's session directory is on this host with how many sessions it holds.

## Source users: no Python installed

1. **Python is already installed** (most common): do nothing; it is found automatically (Windows `py` launcher, PATH, `%LOCALAPPDATA%\Programs\Python`; macOS Homebrew including `/opt/homebrew`, system Python, python.org installers).
2. **No Python:** put a portable one on the drive, see [runtime/README.txt](../../runtime/README.txt). On Windows use python.org's "Windows embeddable package" unpacked into `runtime\python\`. On macOS copying an interpreter is discouraged (dynamic-library paths break); a Homebrew Python is easier.
