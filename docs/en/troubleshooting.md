# Troubleshooting: running and switching devices

Chinese original: [guide/troubleshooting.md](../guide/troubleshooting.md), which wins if the two differ.

1. Download the Release `universal.zip`, extract it completely, and check that `runtimes/` and `version.json` exist. Do not copy only the BAT file or pick the Source code archive.
2. Check the system and CPU: Windows x64, Ubuntu 22.04+ / glibc 2.35+ x64, Mac ARM64 14+ / Intel 15+. On Linux run `bash 启动_AgentRelay.sh` to avoid `noexec` drives; the runtime is unpacked and run from a local cache.
3. After launch, open **Environment** and check the data directory, runtime directory, space and Zstandard. A bundle should show the Release's built-in interpreter. On `Runtime checksum mismatch`, download again and compare against the published SHA256SUMS; never edit the manifest to get around it.
4. The Windows launcher calls the system Windows PowerShell explicitly and adds the system module path in the child process, so it works when started from PowerShell 7. It changes no global user settings. The running version must include this fix.
5. If the port is busy, the next five are tried; the address in the startup output is the real one. To close an old service use **Stop service** in the page — merely closing the page does not quit it. Change the port only if every candidate is busy.
6. If a directory is not accessible, pick the real tool root in **Environment**, not a `projects` / `sessions` subfolder; save an empty value to restore auto-detection. An old explicit path never silently falls back to the default.
7. The local choice is stored in `devices/<device-id>.json`; another device uses its own file. Keep `storage/` to carry packages, and on the new device enter the new project directory before restoring. Same id / name is never overwritten; use a new id / name to keep a second copy.
8. Use `windows-use` / `ubuntu-use` to choose Windows/Ubuntu user directories; they are saved on this machine only. For unreadable mounts, hibernated NTFS, or Windows being unable to read ext4, see the [dual-boot guide](../guide/ubuntu-dual-boot.md) (Chinese). Partition drivers are never installed automatically.
9. A read-only portable drive can be browsed; choose a writable directory in the storage panel. If saving device settings fails, copy the whole bundle to a writable location. Lack of space or permission must be fixed first; a failure is never treated as done.
10. For format errors run `health` and keep the report. Passing synthetic samples does not prove that a real vendor's new version can resume. Keep a copy of the source and stop on an unknown generation, missing messages or damaged records; never edit the original log to get past the check.

If cache extraction was interrupted, quit all AgentRelay processes, delete the current version's cache and restart. Windows: `%LOCALAPPDATA%/AgentRelay/<version>`; Mac: `~/Library/Caches/AgentRelay/<version>`; Linux: `${XDG_CACHE_HOME:-~/.cache}/agentrelay/<version>`. The program never cleans other versions or the source tools' data.

If a community plugin misbehaves, run `plugins disable <name>` and restart the service. A changed file hash must be reviewed and enabled again; copying a device config does not replace approving it again on the new machine. Skills are copied as directories only; the target tool's dependencies and tool interfaces must be set up separately.

## Search and Skill-draft problems

- No search results: "Update index" first, then check the chosen source and filters. Chinese short terms work down to a single character; English matches whole words. Reasoning needs both the index switch and the search switch turned on explicitly.
- A new device only shows the offline cache: that is the old local source. Reselect the new machine's root in **Environment** and update; also carry `storage` to read native packages. The index is only for viewing cached sessions and extraction; it cannot replace a full native restore package.
- An update reports permission, damage or an unknown generation: keep the source files and fix the read condition, then update again. A source error never clears the old cache. A change in quoted messages or the title index also triggers a re-read.
- Scan limit reached: pick one indexed source to narrow it. In this version a single run is capped at 10,000 items / 120 seconds, and extraction uses at most 500 complete independent records. Truncated records are not used for extraction; having no candidate under conservative rules is a normal result.
- SQLite/FTS5 missing: the environment panel shows what was actually detected. The four Release runtimes include the module; from source you need a Python with SQLite/FTS5. Unknown schemas are refused for reading and writing and are backed up before writes; never edit the schema version by hand.
- Exporting a draft with an existing name fails: an existing directory is never overwritten. Change the `name` in the frontmatter, review and tick again, and choose an existing local parent directory. A running task can be cancelled; exit the service before copying or moving the index so that data being written is not carried away.

For details and rebuild steps see [local search and drafts](../guide/search-and-skills.md) (Chinese).
