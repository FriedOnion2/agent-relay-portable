# 维护者手册

## 仓库设置（需要管理员权限）

- **分支保护 / Ruleset（`main`）**：要求通过 PR 合并；必需状态检查为 Tests 的各矩阵任务与 `ruff`；
  禁止强推与删除；评审人数设为 0（允许作者自己审核自己的 PR），保留“解决评论后才能合并”。
- **合并策略**：仅开启 squash merge，开启“合并后自动删除分支”。
- **安全**：开启 Dependabot alerts / security updates、Secret scanning 与 push protection、
  Private vulnerability reporting、Code scanning（CodeQL 工作流上传结果）。
- **Actions**：外部贡献者的工作流需维护者批准；默认 `GITHUB_TOKEN` 权限设为只读。
- **元信息**：补 topics（例如 `ai-agents`、`claude-code`、`codex`、`conversation-export`）与简介链接。

## 版本号与发布规则

只有两种对外产物，没有第三种：

| 产物 | 触发 | GitHub 上的形态 | 版本标签 |
|---|---|---|---|
| **滚动开发版** | 每次合并到 `main`（只改文档的合并除外），或手动运行工作流且不填 tag | 固定 tag `dev`，标为 Pre-release；每次构建**先全平台验证通过，再删除旧的、创建新的**，所以始终只有一个 | 文件名里带 `v<下一版本>-dev.<提交短哈希>`，例如 `AgentRelay-v0.5.0-dev.1a2b3c4-universal.zip` |
| **正式版** | 推送 `vX.Y.Z` tag | 普通 Release，标为 Latest | `vX.Y.Z` |

不再创建 `v0.5.0-dev.1` 这类带序号的预发布 tag：工作流会拒绝非 `vX.Y.Z` 的 tag。

### 版本号

- 遵循语义化版本，`1.x` 中不兼容的公开接口 / 存储格式调整升 MAJOR；兼容的新功能升 MINOR，修复升 PATCH。历史 `0.x`：**新功能或不兼容的调整升 MINOR**（0.5.0 → 0.6.0），**只修问题升 PATCH**（0.5.0 → 0.5.1）。首个正式版本为 `1.0.0`，来源实测与文件层支持边界见兼容表。
- `main` 上的 `app/relay/__init__.py` 的 `__version__` 始终是**下一个计划版本加 `-dev`**，如 `1.0.1-dev`（正式发布准备期间可暂用对应正式版本，有测试校验版本和发布说明）。开发版用它命名；`CHANGELOG.md` 的 `[Unreleased]` 段就是开发版的更新说明。
- 刚发完 `1.0.0` 后，下一个 PR 把 `__version__` 改成 `1.0.1-dev` 或 `1.1.0-dev`，按预期的下一版选。
- 正式版的 `__version__` 不带 `-dev`，必须与 tag 一致，并在 `CHANGELOG.md` 里有对应的 `## [X.Y.Z] - 日期` 段。

### 发正式版

1. 开一个只做发布的 PR：`__version__` 改为 `X.Y.Z`；`CHANGELOG.md` 把 `[Unreleased]` 的内容移到 `## [X.Y.Z] - YYYY-MM-DD`（并留一个空的 `[Unreleased]`）；同步 README / `docs/install.md` 里的版本提示。合并到 `main`。
2. 在 `main` 上打 tag 并推送：`git tag vX.Y.Z && git push origin vX.Y.Z`。
3. 紧接着再开一个 PR，把 `__version__` 改回下一个 `-dev`。
4. `Build and publish release` 工作流自动运行：校验 tag 为 `vX.Y.Z` 且与 `__version__`、CHANGELOG 一致 → 四平台构建与测试 → 组装总包并在四类设备上验证，并完成真实 Codex 的 Windows → Ubuntu → Windows 原生包续聊往返门槛 → 生成构建来源证明 → 创建 Release（说明取自 CHANGELOG 与 `.github/release-notes-template.md`）。
5. 失败时不会产生 Release；修复后删除并重打 tag，或在 Actions 里手动运行并填入 tag。
6. 发布后核对 Release 页面，并用 `gh attestation verify` 抽查总包。

### 滚动开发版

- 不需要任何手动操作；合并到 `main` 后约半小时内更新。说明取自 `[Unreleased]` 与 `.github/release-notes-dev-template.md`，并标明对应提交。
- 构建失败或某个平台验证失败时，上一个开发版保持不变。
- 想立即重建：Actions → `Build and publish release` → Run workflow，不填 tag。

本地预览说明：

```sh
python3 scripts/release_notes.py --tag v0.5.0 --output /tmp/notes.md      # 正式版
python3 scripts/release_notes.py --sha "$(git rev-parse HEAD)" --output /tmp/notes.md   # 开发版
```

## 日常

- PR 合并前确认 Tests、Lint、CodeQL 全绿。
- 每日格式健康检查失败时优先排查（可能是外部软件的存储格式变化）。
