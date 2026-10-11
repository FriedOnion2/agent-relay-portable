# Tutorial: migrate one session to another tool

A walk-through from finding a session to verifying and undoing it, using "move a Codex session to Claude Code" as the example. Other sources and targets work the same way, only the names change. All options are in the [command-line reference](cli.md). Chinese original: [guide/migrate-a-session.md](../guide/migrate-a-session.md).

Prerequisites: the program is set up (see [Install and launch](install.md)), and both tools have been used on this machine and have session directories.

## 1. Check the environment

```bash
python3 app/cli.py doctor
```

Confirm Python is recent enough and that both Codex's and Claude Code's session directories were found. If a directory is not in the default place, see [Configuration](configuration.md).

## 2. Find the session

```bash
python3 app/cli.py list codex -f keyword
```

Note the **full session id** in the output. To confirm it is the right one:

```bash
python3 app/cli.py show codex <id> --head 5
```

## 3. Check for secrets

A session may contain pasted keys, tokens or passwords, and migration copies them unchanged into the target tool.

```bash
python3 app/cli.py scan codex <id>
```

It reports only the type, position and length, never the content, and exits with code 2 when something suspicious is found. The scan cannot guarantee to find everything. If there are hits, add `--redact-secrets` when migrating; matches are replaced with `[REDACTED:<type>]`.

## 4. Dry run

```bash
python3 app/cli.py transfer codex <id> --to claude --cwd /path/to/project --dry-run
```

Nothing is written. You get a JSON report: the target location, counts per kind of content, and anything that cannot be migrated faithfully (`warnings`, `blockers`). If there are `blockers` you cannot continue. Note the `token` in the report.

`--cwd` is the **project directory** the session belongs to in the target tool. On the same machine you can omit it; when the source came from another system (for example a Windows session migrated on a Mac) give an absolute path that exists on this machine.

## 5. Migrate for real

Repeat every option from the dry run and add `--preview-token`:

```bash
python3 app/cli.py transfer codex <id> --to claude --cwd /path/to/project --preview-token <token>
```

If the source session or the options changed since the dry run (you chatted some more, you changed an option), the token no longer matches and the migration is refused; dry-run again. On success you get the new session id and the written file path.

If you don't care about previews you can run `transfer` directly, without `--dry-run` or a token.

## 6. Verify

```bash
python3 app/cli.py diff codex <source-id> claude <new-id>
```

It reports how many items match, are only on one side, or changed, plus a similarity ratio. The exit code is 0 when the content is identical and 1 otherwise. Text and tool calls are shaped differently in different tools, so a few "changed" items are normal; watch for many items that are "only in A".

Then open the target tool and find the session by title. Codex Desktop's list also depends on its own database index, so writing a JSONL file does not guarantee that it appears in the desktop list. Migration **cannot guarantee** that the target tool will continue the conversation seamlessly; see [Known limitations](limitations.md).

## 7. Undo if you are not happy

```bash
python3 app/cli.py history
python3 app/cli.py undo <operation-id>
```

`history` lists the operation id of every write. `undo` removes the files this run created and truncates appended indexes back. A created file that was modified after the write is kept by default; add `--force` to delete it too.

## Migrating many sessions

Dry-run first, then confirm:

```bash
python3 app/cli.py batch codex --to claude --filter keyword           # dry run only
python3 app/cli.py batch codex --to claude --filter keyword --yes     # actually write
```

If the target already holds a migration result from the same source, it is skipped by default (`--on-conflict skip`); use `new` (create a new id) or `fail` (stop at once) instead.

## What the program does while migrating

- **Where it writes:** the target tool's session directory on the host (`~/.claude/projects/…` and so on), not the portable drive.
- **Project directory name:** the program scans the target tool's existing session directories, reads the working directory recorded in each, and looks the directory name up from that. It is the only reliable way, because Windows (`c-Users-alice-proj`) and macOS (`-Users-alice-proj`) name directories differently; only a brand-new directory falls back to heuristics.
- **What is kept:** plain text, plain-text reasoning, and paired tool calls with their results. Tool calls without a result, images and unknown blocks are kept as annotated text. Migration never runs historical tools, installs the source's tools or converts their argument protocols.
- **Read limit:** at most 32 MB per source file; beyond that it is clearly marked, only the marked partial content may be exported, and migration stops.
- **Migrating to DSH:** use `--to dsh` (or choose DeepSeek Harness as the target in the web UI). The command prints DSH's native session id; find the session by title in DSH's list. Reading and importing compressed DSH history needs `zstandard` (built into the Release).
- **Tool names** are translated to the target tool's names by default; `--keep-tool-names` turns that off.
- **Claude Agent SDK** shares `~/.claude/projects` with Claude Code, so both entries showing the same session is normal. The SDK entry is read-only (export and migrate out). Sessions are read along the current `parentUuid` main chain so old branches and sub-agents are not mixed in. A saved stream-json output is not a native resumable session.

## Prefer not to type commands

The web interface does the same: run `python3 app/cli.py serve` and follow the [web workflow](../guide/web-workflow.md) (Chinese).
