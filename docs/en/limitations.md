# Known limitations

Known limits and unverified items. Chinese original: [reference/limitations.md](../reference/limitations.md), which wins if the two differ.

- WorkBuddy / Claude / SDK / Codex / CodeBuddy CLI read at most 32 MiB. Beyond that, marked partial content can be exported but migration stops. DSH data (plain or decompressed) and total CodeBuddy IDE reads over the limit are refused.
- Claude / SDK read the current `parentUuid` main chain by default and do not merge old branches or sub-agents. Original text from before a compaction stays in the source file but is not migrated again as current context.
- DSH export keeps the event history. It does not replay surface replacement, compaction, seed or native resume state.
- The web UI and CLI offer four migration targets: WorkBuddy, DSH, Claude and Codex. CodeBuddy and SDK stay read-only.
- Tencent Yuanbao is supported only through compatible JSON exports: obtain the local JSON first, and ZIPs are restored into AgentRelay's export directory. Reading the desktop database automatically, writing back to Yuanbao, cloud collection and Yuanbao Skill management are not implemented. Synthetic format tests cannot prove that a real export is complete or that the client can resume. See the [Yuanbao format contract](../reference/formats/yuanbao.md) (Chinese).
- DSH import writes v0 native Zstd logs. It is compatible with the local 0.1.2-rc.1 and has also been verified for strict migration to v4 against the official 0.2.1-alpha.1 format catalogue. Imported history has tool calls turned off; a tool call without a result is kept as text and is not pending work. Images and non-native content blocks degrade to annotated text. The target working directory must be an absolute path on the current system.
- The generic-conversion target limit for CodeBuddy/SDK does not affect two-way native file migration between the corresponding tools, which keeps native records. DSH supports full v4 and verifiable v0 seeds; forks migrate the parent session first, and sub-agents are not imported on their own. CodeBuddy IDE needs a uniquely matching existing native workspace and must be imported with the app closed.
- Stream-json output saved by an SDK application is not a native transcript; applications with persistence off or using only an external SessionStore may have no default local history.
- The CodeBuddy CLI/IDE formats come from third-party consumer observation and have not been validated against a vendor-native resume protocol; see [source formats](../reference/source-formats.md) (Chinese).
- Images, encrypted reasoning and vendor-specific metadata are not guaranteed to be preserved.
- Tool-name translation neither installs the target's tools nor converts each tool's argument protocol.
- Codex Desktop may need its own database index; a generated JSONL does not guarantee the session shows up in the desktop list.
- Target tool formats may change; a read-back test passing in this program is no substitute for actually resuming in the target tool.
- Both the `.app` and terminal launches were tested on an Apple Silicon Mac; Gatekeeper permissions on other machines and native resumption in the target tools still need verification.
