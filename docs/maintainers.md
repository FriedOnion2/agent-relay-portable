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

1. 更新 `CHANGELOG.md`，把 `[Unreleased]` 改为新版本与日期。
2. 打 tag（如 `v0.5.0-dev.1`）并推送。
3. 在 Actions 手动运行 “Build universal dev release”，输入该 tag，产物自动发布为 Release。
4. 校验 Release 附带的总包可在 Windows / macOS / Ubuntu 上启动。

## 日常

- PR 合并前确认 Tests、Lint、CodeQL 全绿。
- 每日格式健康检查失败时优先排查（可能是外部软件的存储格式变化）。
