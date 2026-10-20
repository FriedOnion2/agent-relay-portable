# Compatibility summary

The development build adds [WorkBuddy AI International](../reference/formats/workbuddy_ai.md): static checks of the installed 5.8.4 package, isolated synthetic tests, and a synthetic conversation created through the Windows client. Native reading and ZIP file roundtrip passed. The restored copy has no desktop history index and was absent from the sidebar and global search; restored-session resume has not passed validation. Domestic WorkBuddy and the international edition are configured separately.

A summary of the Chinese page [reference/compatibility.md](../reference/compatibility.md), which holds the full evidence and wins if the two differ.

## WorkBuddy edition transfer matrix

The 2026-10-20 isolated regressions cover 14 writable directions, six imports from read-only sources, and six rejected reverse attempts. No user history, model calls, or historical tool execution is involved.

| Other endpoint | Domestic WorkBuddy (`workbuddy`) | WorkBuddy AI International (`workbuddy_ai`) |
|---|---|---|
| Domestic WorkBuddy | — | Bidirectional file conversion passed |
| WorkBuddy AI International | Bidirectional file conversion passed | — |
| DSH | Bidirectional file conversion passed | Bidirectional file conversion passed |
| Claude Code | Bidirectional file conversion passed | Bidirectional file conversion passed |
| Codex | Bidirectional file conversion passed | Bidirectional file conversion passed |
| CodeBuddy CLI | Import passed; reverse rejected | Import passed; reverse rejected |
| Claude Agent SDK shared store | Import passed; reverse rejected | Import passed; reverse rejected |
| Compatible Yuanbao JSON exports | Import passed; reverse rejected | Import passed; reverse rejected |

Writable routes check text, readable reasoning, tool order, arguments, results and error flags, title, project mapping, unchanged source files, and conversion back to the original edition. Tool names follow existing mappings; this does not prove target tool interface compatibility. Read-only sources retain representable content: CodeBuddy uses CLI JSONL here, the SDK uses shared Claude JSONL without inferring its creator, and Yuanbao contains text and reasoning only.

Another regression places the same session ID with different content in each edition and checks separate listing identities, archive `agent` / `source` fields, restore destinations, and unchanged source files. Codex roundtrip previously lost tool-result error flags; Relay-generated records now preserve an explicit annotation (see the [format contract](../reference/formats/codex.md)). These are file-level checks. They do not establish domestic client recovery, international desktop indexing, or resumed conversations in either edition.

All 14 directions also passed actual CLI `transfer --json` invocations against temporary stores, checking source/target identities, content, error flags, project mapping, and unchanged source files. Local Codex `0.163.0-alpha.10.2` read the imported fixture through `app-server thread/resume` (two turns, 5 / 2 history items), confirming that the annotation does not block history recovery in this version. No new model turn was requested, and this is not evidence of WorkBuddy client resume.

## Supported systems

Windows 10/11 x64, Ubuntu 22.04+ / glibc 2.35+ x64, macOS ARM64 14+ / Intel 15+. The four runtimes ship in one bundle and do not depend on the target machine's Python or Node. Client installation and sign-in, external Skill dependencies, mount permissions and a vendor's actual resumption still have to be checked on the target device.

The web page **Environment** checks the OS, CPU, write access to the data directory, free space, the runtime directory actually in use, Python and Zstandard. The bundle launcher verifies the runtime archive's SHA-256 on start; the panel never reports an already-unpacked cache as integrity-verified. Read-only media can be browsed; choose a writable local directory for storage, and saving device settings needs a writable portable root.

## What was verified for 1.0.0

On 2026-10-10 a cross-system run used a real Codex `0.162.1` and completed a native session-package round trip Windows → Ubuntu 22.04 → Windows. At each stop it checked text, reasoning, and the arguments / results / error status of two tool calls; after mapping to the current device's project it resumed the conversation and restarted the client to read back the added content. It also checked package checksums, that the source package is unchanged, and that a same-id conflict stops with the target files untouched.

The samples and agent roots were temporary directories. The resumed answer came from a loopback Responses test endpoint: no sign-in, no paid model, no historical tool execution. It verifies client resumption and on-disk recovery, **not** online models, real project environments or external tools. The release pipeline runs this gate again and also validates the four frozen runtimes and the final bundle's launch.

In the same three-system client check, Codex `0.162.1` history recovery and DSH `0.2.0-rc.2` listing, v0 → v4 upgrade and recovery passed. The DSH test did not write a new turn to disk. Automatic client tests for Claude / WorkBuddy / CodeBuddy were explicitly skipped and do not count as passed. A Mac test passed by user report, without a client scope. The Ubuntu environment was a GitHub-hosted Ubuntu 22.04, not a dual-boot partition on the maintainer's machine.

1.0.0 keeps these source limits: CodeBuddy / SDK read-only, WorkBuddy / Claude verified at file level only, and attachments and desktop indexes out of scope. Portable package manifest v1 and SQLite index schema v1 stay as released; unknown versions are still refused. See [Known limitations](limitations.md).

## Format health check

The page's "format self-check" only generates samples in a temporary directory; it does not read real conversations, run historical tools or call models. The CLI can export JSON and a static HTML report:

```sh
python app/cli.py health --output health-output
```

A [daily format regression](https://github.com/FriedOnion2/agent-relay-portable/actions/workflows/format-health.yml) produces a downloadable artifact on Windows, Linux and Mac (kept 30 days). A sample passing means the sample was read successfully; only sources that support native read-back verify that ability. When the client version has no firm evidence it shows "unknown"; latest-version compatibility stays `unknown` and real resumption `not-tested`, and a passing regression never turns them green.

## Migration preview

- The generic migration, Windows/Ubuntu native migration and package restore first list what is kept, degraded, dropped or unknown, and only run after you confirm; cancelling writes nothing. Tool-name mapping does not convert arguments; an image description or reasoning text is not the same as native-feature preservation. Native migration keeps the records, but attachments, sub-agent side files, desktop indexes and resumption state are outside the full guarantee.
- The CLI migration commands and `restore-session` accept `--dry-run` for a preview only. Pass the returned `token` to the same command with `--preview-token`; it is refused if the source records, options or target directory changed. Calls without a token skip that consistency check.
- A token binds the IR, the readable native source files / IDE referenced messages, and the options; a package preview fully validates the SHA-256 and declarations in the package. A preview does not lock third-party software, so stop the source and target tools from writing before you run. Target-id conflicts, strict native format validation and unique IDE workspace matching are still checked at run time, so a successful preview does not prove that the restore will succeed.
- **Several Codex rollouts with one id (dev build, not in 1.0.0):** each file uses `<native-id>@<suffix>` as its selection id; the JSON list keeps `native_id` and `variant_count`. An ambiguous id stops the operation, and a vanished selected file never falls back to another rollout. Nothing is merged or assumed to be the latest or complete.
