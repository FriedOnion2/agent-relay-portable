# Changelog

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循语义化版本（当前为 `0.x` 开发阶段，接口可能调整）。
每个 Release 的完整说明见 [Releases](https://github.com/FriedOnion2/agent-relay-portable/releases)。

## [Unreleased]

### Fixed
- 迁移到 Codex 的会话可在真实 Codex 中续聊（正确的 `model_provider` 与 turn 事件）。
- 迁移到 DSH 的会话保留原始时间戳。
- DSH 会话 id 可直接作为命令行参数；没有任何轮次的源会话不再被迁移。

### Added
- LICENSE（MIT）、SECURITY、CONTRIBUTING、CODE_OF_CONDUCT、CODEOWNERS、issue / PR 模板。
- ruff、CodeQL、Dependabot。

## [0.4.0-dev.2] - 2026-10-08
## [0.4.0-dev.1] - 2026-10-07
## [0.3.0-dev.1] - 2026-10-07
## [0.2.0-dev.2] - 2026-10-07
## [0.2.0-dev.1] - 2026-10-07

早期开发版本，详见对应的 Release 页面。
