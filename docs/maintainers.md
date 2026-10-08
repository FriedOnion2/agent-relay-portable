# 维护者手册

## 仓库设置（需要管理员权限）

- **分支保护 / Ruleset（`main`）**：要求通过 PR 合并；必需状态检查为 Tests 的各矩阵任务与 `ruff`；
  禁止强推与删除；评审人数设为 0（允许作者自己审核自己的 PR），保留“解决评论后才能合并”。
- **合并策略**：仅开启 squash merge，开启“合并后自动删除分支”。
- **安全**：开启 Dependabot alerts / security updates、Secret scanning 与 push protection、
  Private vulnerability reporting、Code scanning（CodeQL 工作流上传结果）。
- **Actions**：外部贡献者的工作流需维护者批准；默认 `GITHUB_TOKEN` 权限设为只读。
- **元信息**：补 topics（例如 `ai-agents`、`claude-code`、`codex`、`conversation-export`）与简介链接。

## 发布流程

1. 把 `app/relay/__init__.py` 的 `__version__` 改为新版本（如 `0.5.0`、`0.5.0-dev.1`），在 `CHANGELOG.md` 中把 `[Unreleased]` 的内容移到 `## [0.5.0] - YYYY-MM-DD`，合并到 `main`。
2. 在 `main` 上打 tag 并推送：`git tag v0.5.0 && git push origin v0.5.0`。
3. `Build and publish release` 工作流自动运行：校验 tag 与 `__version__`、CHANGELOG 一致 → 四平台构建与测试 → 组装总包并在四类设备上验证 → 生成构建来源证明 → 创建 Release（版本号含 `-` 的标为 Pre-release；说明取自 CHANGELOG 与 `.github/release-notes-template.md`）。
4. 工作流失败时 tag 不会产生 Release；修复后删除并重打 tag，或在 Actions 里手动运行并填入 tag。
5. 发布后核对 Release 页面，并用 `gh attestation verify` 抽查总包。

本地预览说明：`python3 scripts/release_notes.py --tag v0.5.0 --output /tmp/notes.md`。

## 日常

- PR 合并前确认 Tests、Lint、CodeQL 全绿。
- 每日格式健康检查失败时优先排查（可能是外部软件的存储格式变化）。
