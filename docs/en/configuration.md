# Configuration

Where conversations are looked up and how settings are stored. Chinese original: [guide/configuration.md](../guide/configuration.md).

## Where AgentRelay looks for conversations

Directory overrides are applied in this priority order, and the first hit wins:

1. This device's settings (`devices/<device-id>.json`, or saved in the page **Environment**)
2. The shared `config.json` (`agent_homes`)
3. The `RELAY_<AGENT>_HOME` environment variable
4. The assistant's own environment variable: `CODEX_HOME`, `CLAUDE_CONFIG_DIR`, `DSH_HOME`, `WORKBUDDY_HOME`, `CODEBUDDY_HOME`
5. The default under the user's home: `~/.claude`, `~/.codex`, `~/.workbuddy`, `~/.dsh`, `~/.codebuddy` (CodeBuddy also auto-detects the IDE data directory)

Relative paths are resolved against the portable root, not the working directory. Give the tool's **root directory**, not its `projects` / `sessions` subfolder.

One-off override:

```bash
RELAY_CODEX_HOME=/Volumes/Backup/.codex python3 app/cli.py list codex
```

Persistent: rename `config.example.json` to `config.json` and fill in real paths.

```json
{
  "agent_homes": {
    "claude": "/Users/alice/backup/.claude",
    "claude_sdk": "",
    "codex": "",
    "dsh": "",
    "workbuddy": "",
    "workbuddy_ai": "",
    "codebuddy": ""
  },
  "port": 8745,
  "open_browser": true
}
```

**`config.json` travels with the drive**, and so do the absolute paths in it. After changing machines, edit them; to use each machine's own directories automatically, leave `agent_homes` empty. `open_browser: false` applies to every launcher.

## Per-device settings

Directories saved from the web page only affect the current device. The same via CLI:

```sh
python app/cli.py device-config
python app/cli.py device-config --agent codex --home <this device's Codex root>
python app/cli.py device-config --agent codex --home ""      # back to auto-detect
python app/cli.py health --output health-output
```

`windows-use` / `ubuntu-use` also only save a choice for this machine. A damaged device config is reported and never overwritten; a damaged shared config still lets valid device settings be read.

## Specifics

- **WorkBuddy AI (International)** uses `workbuddy_ai`, `RELAY_WORKBUDDY_AI_HOME` / `WORKBUDDY_AI_HOME`, and defaults to `~/.workbuddy-ai`. It never inherits domestic WorkBuddy or CodeBuddy overrides. A single `user-...` child is selected automatically; with multiple accounts, choose the intended account directory in this device's settings, not its `projects` child. Reselect the directory after switching accounts. See the [format contract](../reference/formats/workbuddy_ai.md) (Chinese).

- **Claude Agent SDK** honours `CLAUDE_CONFIG_DIR` by default; its own override is `agent_homes.claude_sdk` / `RELAY_CLAUDE_SDK_HOME`. It does not inherit `RELAY_CLAUDE_HOME`, which is for Claude Code only.
- **Upgrading an old config:** if `agent_homes.dsh` or `RELAY_DSH_HOME` pointed at `.workbuddy`, move that value to `workbuddy` / `RELAY_WORKBUDDY_HOME`. `dsh` now means DeepSeek Harness only and is never silently aliased to WorkBuddy.
- **CodeBuddy** scans both the CLI and the IDE by default. IDE roots: `%LOCALAPPDATA%/CodeBuddyExtension/Data` (Windows), `~/Library/Application Support/CodeBuddyExtension/Data` (macOS), `~/.config/CodeBuddyExtension/Data` (Linux). An explicitly set CodeBuddy root is scanned alone and may be a backed-up `.codebuddy` or an IDE `Data` root.
- **`windows_user_home` / `RELAY_WINDOWS_USER_HOME`** points at a Windows user directory mounted on Ubuntu; it only takes effect on Linux and adds a read-only source without changing where local writes go. `--windows-user` overrides the saved choice for one command.

## Privacy and data

The service listens on the local address only. Conversion reads the source and writes new files into the target assistant's session directory; an existing target is never overwritten. Logs, local config, Python runtimes, caches and real conversation data should not be uploaded to GitHub; the repository ships ignore rules for them.
