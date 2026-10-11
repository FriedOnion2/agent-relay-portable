# AgentRelay Portable documentation (English)

AgentRelay Portable is a local tool for migrating, exporting, searching and storing conversations from AI coding assistants (WorkBuddy, DeepSeek Harness, CodeBuddy, Claude Code, Claude Agent SDK, Codex, Tencent Yuanbao). It listens only on the local machine, does not upload data and does not call models. Back to the [project home](../../README.en.md).

> **About these pages.** The English documentation is a translation of selected Chinese pages and is **not complete**. The Chinese pages are the source of truth: when they differ, the Chinese text wins. Pages not translated yet are linked in Chinese.

## Interface language

The web interface is available in full in English and Chinese. On first load it follows the browser language; use the language button at the top right to switch (the choice is remembered), or open `http://127.0.0.1:8745/?lang=en` once. Markdown exports and Skill drafts created from the page are written in the language you are viewing. Command-line messages are currently Chinese only. Button names in these pages are the ones shown in the English interface.

## Guides

| Page | Contents |
|---|---|
| [Install and launch](install.md) | Release bundle, running from source, pip / pipx, ports, quitting |
| [Tutorial: migrate one session](migrate-a-session.md) | Find, scan, dry-run, migrate, verify and undo, with the CLI |
| [Configuration](configuration.md) | Where conversations are looked up, `config.json`, per-device settings |
| [Troubleshooting](troubleshooting.md) | Launch problems, switching devices, search issues |

## Reference

| Page | Contents |
|---|---|
| [Command-line reference](cli.md) | Every command, migration options, exit codes |
| [Compatibility summary](compatibility.md) | Supported systems, what has and has not been verified |
| [Known limitations](limitations.md) | What migration does not guarantee |

## Not yet translated

[Web workflow](../guide/web-workflow.md) · [Storage and migration](../guide/storage-and-migration.md) · [Portable storage](../guide/portable-storage.md) · [Ubuntu dual boot](../guide/ubuntu-dual-boot.md) · [Search and Skills](../guide/search-and-skills.md) · [Source formats](../reference/source-formats.md) · [Developer docs](../dev/adapters.md)
