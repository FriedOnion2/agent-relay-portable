# Command-line reference

The entry point is `app/cli.py`, identical on all three platforms (use `python` instead of `python3` on Windows):

```bash
python3 app/cli.py <command> [options]
python3 app/cli.py <command> --help      # all options of that command
```

Commands are grouped by purpose below. `--help` is authoritative for full options; this page lists the common ones and the pitfalls. Chinese original: [reference/cli.md](../reference/cli.md).

## Output language

Command-line output (including `--help` and error messages) is Chinese by default. For English, put `--lang en` **before** the subcommand, or set the environment variable `RELAY_LANG=en`:

```bash
python3 app/cli.py --lang en sources
RELAY_LANG=en python3 app/cli.py doctor
```

`--lang` wins over the environment variable, and an unknown language falls back to Chinese. The language is **not** taken from your system locale, so existing scripts keep their output. `--json` output is unaffected; the Markdown written by `export` follows the chosen language.

## Source names

In `list`, `show`, `transfer` and similar commands, a "source" is one of:

| Name | Meaning |
|---|---|
| `workbuddy` `dsh` `codebuddy` `claude` `claude_sdk` `codex` `yuanbao` | Sessions of that tool on this machine |
| `windows_<name>` | The same tool's sessions on a mounted Windows partition (Ubuntu dual boot, read-only) |
| `ubuntu_<name>` | Sessions in a backed-up Ubuntu user directory that Windows can access (read-only) |

`yuanbao` is only available from export files brought in with `import-yuanbao`. **Migration targets** (`--to`) are limited to `workbuddy`, `dsh`, `claude` and `codex`; CodeBuddy, Claude Agent SDK and Yuanbao can only be read and exported.

Use the full session id from `list` (CodeBuddy and DSH ids may carry a path prefix); an abbreviation that matches several sessions is an error.

## Inspect the environment and sessions

| Command | Purpose |
|---|---|
| `doctor` | Environment check: Python, each source's session directory and count. Run it first on a new machine |
| `sources [--json]` | Which sources are available and how many sessions each has |
| `list <source> [-f keyword] [-n count] [--json]` | List sessions; `-f` filters by title, directory or id |
| `show <source> <id> [--role …] [--head N] [--max-chars N] [--json]` | View content |
| `health [--output dir]` | Self-check with temporary synthetic samples; it does **not** verify that real clients can resume |
| `device-config [--agent name] [--home dir]` | Show the device check; set this machine's session root for a tool (omit `--home` value to restore auto-detect), without affecting other devices |

## Migrate and verify

| Command | Purpose |
|---|---|
| `transfer <source> <id> --to <target>` | Migrate one session to another tool |
| `batch <source> --to <target>` | Migrate many; **dry run by default, add `--yes` to write** |
| `diff <source> <id> <source2> <id2> [--max N] [--json]` | Compare two sessions (check nothing was lost). Exit code 1 when they differ |
| `scan <source> <id> [--json]` | Look for suspected keys, tokens and passwords; reports type, position and length only |
| `history [--limit N] [--json]` | List the write operations performed on target tools |
| `undo <operation-id> [--force]` | Undo a write: delete created files, truncate appended indexes. Files modified after writing are kept unless `--force` |

Common `transfer` options:

| Option | Meaning |
|---|---|
| `--cwd dir` | Working directory in the target; defaults to the source session's. Required as a local absolute path when migrating across systems (a Windows session on a Mac) |
| `--session-id ID` | New session id; never overwrites an existing one, must not contain path separators |
| `--title text` | Override the title |
| `--no-thinking` | Do not migrate reasoning |
| `--keep-tool-names` | Do not translate tool names |
| `--redact-secrets` | Replace suspected secrets with `[REDACTED:<type>]` before writing |
| `--dry-run` | Produce a fidelity report without writing. The report contains a `token` |
| `--preview-token token` | Run a confirmed preview; refused if the source or options changed meanwhile |

`batch` also takes `--ids a,b,c` (or `--filter` to select), `--limit` (max 500), `--on-conflict skip|new|fail` (what to do when the target already holds a result from the same source; default `skip`) and `--stop-on-error`.

## Export and import files

| Command | Purpose |
|---|---|
| `export <source> <id> [-o file]` | Export a Markdown hand-off document; `--no-thinking`, `--no-tools`, `--max-chars N`, `--redact-secrets` trim the content |
| `import-yuanbao <JSON file>` | Import a Yuanbao JSON export (never reads or modifies the Yuanbao client database) |

## Windows ↔ Ubuntu native transfer

Keeps native records; see [Ubuntu dual boot](../guide/ubuntu-dual-boot.md) (Chinese). These all support `--dry-run` / `--preview-token` / `--json`.

| Command | Purpose |
|---|---|
| `windows-users` | Detect user directories on mounted Windows partitions |
| `windows-use <path>` / `--clear` | Save / clear the Windows user directory choice |
| `import-windows <source> <id> --cwd <Ubuntu project dir>` | Import a Windows session into the matching Ubuntu tool |
| `export-windows <source> <id> --cwd <D:\project> --project-path <mount path>` | Write an Ubuntu session into the matching tool on a mounted Windows partition |
| `ubuntu-use <path>` / `--clear` | Save / clear the Ubuntu user-directory backup Windows can reach |
| `import-ubuntu <source> <id> --cwd <D:\project>` | Windows imports a native session from the Ubuntu backup |

Many read commands also accept `--windows-user` / `--ubuntu-user` to pick a user directory for one run without saving it.

## Portable storage

See [Portable storage](../guide/portable-storage.md) (Chinese).

| Command | Purpose |
|---|---|
| `store-sessions <source> [id …] [--all] [--storage dir]` | Save sessions as independent packages, sorted by tool |
| `stored-sessions [--agent name] [--storage dir]` | List stored session packages |
| `restore-session <package> --cwd <dir> [--dry-run]` | Verify and restore a package onto this device |
| `skills <source> [--skills-dir dir]` | List SKILL.md directories |
| `store-skills <source> [path …] [--all] [--skills-dir dir]` | Save complete Skill directories |
| `stored-skills [--agent name]` | List stored Skill packages |
| `restore-skill <package> [--agent …] [--skills-dir dir] [--name new]` | Verify and restore; an existing directory of the same name is never overwritten |

Stored packages are **not encrypted**; keep them as safe as you need.

## Search and Skill drafts

See [Search and Skills](../guide/search-and-skills.md) (Chinese).

| Command | Purpose |
|---|---|
| `index [--source source] [--include-thinking] [--no-packages]` | Update the offline full-text index; reasoning is not indexed by default |
| `search [query] [--source …] [--project …] [--tool …] [--after date] [--before date] [--limit N]` | Search across sources; Chinese short terms work |
| `indexed-session <key>` | Open a session cached in the index without reading the old device's paths |
| `extract-skills` | Extract reviewable Skill drafts from indexed sessions (no model calls) |
| `export-draft <Markdown> --directory <dir> --confirm` | Export a reviewed draft; never overwrites, never installs |

## Server and plugins

| Command | Purpose |
|---|---|
| `serve [--host …] [--port N] [--no-browser]` | Start the web interface; default port 8745, the next 5 are tried if busy |
| `plugins [list\|enable\|disable\|check] [name] [path]` | Manage trusted community read plugins; code is never discovered or run automatically, see [writing a plugin](../dev/writing-a-plugin.md) (Chinese) |

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | An error (message on stderr); `diff` found differences; a `batch` entry failed; a storage command failed. Set `RELAY_DEBUG=1` for the full traceback |
| 2 | `scan` found suspected secrets (0 when none), handy as a gate in scripts |
| 130 | Cancelled with Ctrl+C |
