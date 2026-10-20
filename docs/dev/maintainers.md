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
- `main` 上的 `app/relay/__init__.py` 的 `__version__` 始终是**下一个计划版本加 `-dev`**，如 `1.1.0-dev`（正式发布准备期间可暂用对应正式版本，有测试校验版本和发布说明）。开发版用它命名；`CHANGELOG.md` 的 `[Unreleased]` 段就是开发版的更新说明。
- 刚发完 `1.0.0` 后，下一个 PR 把 `__version__` 改成 `1.0.1-dev` 或 `1.1.0-dev`，按预期的下一版选。
- 正式版的 `__version__` 不带 `-dev`，必须与 tag 一致，并在 `CHANGELOG.md` 里有对应的 `## [X.Y.Z] - 日期` 段。

### 发正式版

1. 开一个只做发布的 PR：`__version__` 改为 `X.Y.Z`；`CHANGELOG.md` 把 `[Unreleased]` 的内容移到 `## [X.Y.Z] - YYYY-MM-DD`（并留一个空的 `[Unreleased]`）；同步 README / `docs/guide/install.md` 里的版本提示。合并到 `main`。
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

## 网页前端结构

`app/web/` 不用构建工具，也没有框架；`index.html` 只放结构和 `data-i18n` 标记，其余都是外部文件，由本机服务从 `/static/` 提供：

| 文件 | 内容 |
|---|---|
| `app.css`、`workflow.css` | 基础样式、任务导航样式 |
| `i18n.js`、`locales.zh.json`、`locales.en.json` | 界面语言与词条 |
| `app-core.js` | 全局状态、语言切换、`api()`、勾选与按钮状态、toast |
| `app-shell.js` | 启动、来源 / 目标选择、事件绑定 |
| `app-sessions.js` | 会话列表与详情 |
| `app-migrate.js` | 环境检查、元宝导入、迁移确认对话框 |
| `app-storage.js` | Skill 与对话存储、恢复 |
| `app-backup.js` | 整机/对话/Markdown 三种一键导出、ZIP 选择上传、目录映射和批量导入 |
| `app-transfer.js` | Windows 导入、迁移、批量迁移 |
| `app-history.js` | 操作记录与撤销 |
| `app-search.js` | 全文搜索、索引任务、Skill 草稿 |
| `app-workflow.js` | 任务导航与结果面板 |
| `app-start.js` | 调用 `init()`，必须最后加载 |

这些 `app-*.js` 是**经典脚本**（不是 ES 模块），按 `index.html` 里的顺序加载并共享全局作用域，所以：

- 文件顶层只放声明（函数、常量、状态对象），不要在加载时就调用别的文件里的函数；真正的启动只在 `app-start.js`。
- 新增脚本要同时加进 `index.html`（放在 `app-start.js` 之前）；`tests/web.test.cjs` 会按页面里的顺序逐个执行，并检查引用的文件都存在、页面没有内联脚本或样式。
- 打包（wheel 的 `package-data`、便携包的 `--add-data app/web`）按扩展名 / 整个目录收文件，新文件不需要改打包配置；`tests/test_server.py`、wheel 检查与发布冒烟测试会逐个请求页面引用的资源。

## 日常

- PR 合并前确认 Tests、Lint、CodeQL 全绿。
- 每日格式健康检查失败时优先排查（可能是外部软件的存储格式变化）。

## 文档站点

文档用 MkDocs Material 构建，配置在根目录 `mkdocs.yml`，依赖固定在 `docs/requirements.txt`。

```bash
pip install -r docs/requirements.txt
mkdocs serve            # 本地预览
mkdocs build --strict   # 与 CI 相同：任何警告都算失败
```

- 新页面除了登记 `docs/README.md`，还要加进 `mkdocs.yml` 的 `nav`（`tests/test_docs.py` 会检查）。
- `docs/research/` 会被构建但不在导航里。
- 指向 `docs/` 之外的相对链接（如 `../../README.md`）由 `scripts/mkdocs_hooks.py` 在构建时改写成 GitHub 地址。
- GitHub Pages 的 Source 设为 **GitHub Actions**。文档工作流在 PR 中只做严格构建检查，合并到 `main` 后上传并部署站点；也可从 Actions → docs → Run workflow 手动部署 `main`。部署 job 使用 `github-pages` 环境，Pages 写权限只授予这个 job。
- 文档站点：[AgentRelay Portable](https://friedonion2.github.io/agent-relay-portable/)。首次部署要等文档工作流合并到 `main`；文档部署不创建软件 tag 或 Release。
