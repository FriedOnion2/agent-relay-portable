# Changelog

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循语义化版本（当前为 `0.x` 开发阶段，接口可能调整）。
每个 Release 的完整说明见 [Releases](https://github.com/FriedOnion2/agent-relay-portable/releases)。

## [Unreleased]

### Fixed
- 迁移到 Codex 的会话在真实 Codex 中重建出完整 items（session_meta 补 `history_mode: paginated`）。
- 迁移到 Codex 的会话可在真实 Codex 中续聊（正确的 `model_provider` 与 turn 事件）。
- 迁移到 DSH 的会话保留原始时间戳。
- DSH 会话 id 可直接作为命令行参数；没有任何轮次的源会话不再被迁移。

### Added
- 插件开发体验：新增 `plugins check`（隔离进程里逐项自检，不保存配置）、第二个示例 `examples/jsonl_adapter.py` 和 [插件编写指南](docs/writing-a-plugin.md)。
=======
- CI 增加 mypy 类型检查与覆盖率统计（下限 75%），ruff 规则加入 bugbear 等。
- `relay --version`；推送 `v*` tag 自动构建并发布 Release，说明取自本文件，附构建来源证明。
- LICENSE（MIT）、SECURITY、CONTRIBUTING、CODE_OF_CONDUCT、CODEOWNERS、issue / PR 模板。
- ruff、CodeQL、Dependabot。

## [0.4.0-dev.2] - 2026-10-08

### Added
- 「搜索与提炼」：便携 SQLite/FTS5 全文索引（中文短词、中英混合，来源 / 项目 / 日期 / 工具筛选）。
- 从至少三条独立完整会话提炼带证据的 Skill 草稿；审核后显式导出，不安装、不执行、不调用模型。
- 环境检查新增 SQLite/FTS5 实际探测。

### Fixed
- WorkBuddy 空工具返回被当成非空 JSON 的读取问题；目录枚举权限错误明确报告，不再误判为删除。

## [0.4.0-dev.1] - 2026-10-07
## [0.3.0-dev.1] - 2026-10-07
## [0.2.0-dev.2] - 2026-10-07
## [0.2.0-dev.1] - 2026-10-07

早期开发版本，详见对应的 Release 页面。
