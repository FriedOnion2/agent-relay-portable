# Changelog

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循语义化版本（当前为 `0.x` 开发阶段，接口可能调整）。
每个 Release 的完整说明见 [Releases](https://github.com/FriedOnion2/agent-relay-portable/releases)。

## [Unreleased]

### Added
- 正式发布增加真实 Codex 的 Windows → Ubuntu 22.04 → Windows 原生包往返门槛：每站恢复历史、通过本地测试接口续聊、重启回读，核对工具与思考及 ID 冲突保护；无需登录、不调用付费模型，仅使用临时合成数据。
- 网页主流程：任务首页与来源状态、互斥任务导航、独立会话保存流程、恢复时显式本机项目映射与 ID 策略、跨页面保留的迁移结果；搜索展示索引概况，已审核导出的草稿可转到 Skill 打包表单，仍需单独确认存储。
- 发布规则：始终只有一个滚动开发版（固定 tag `dev`，每次合并到 `main` 自动重建并替换）；正式版只用 `vX.Y.Z` tag。`main` 上的版本号恒为 `X.Y.Z-dev`。规则见 `docs/maintainers.md`。
- 网页界面：「操作记录」面板（查看写入记录、一键撤销，被改动的文件默认保留并可二次确认强制撤销）、「批量迁移所选」（先预演再确认）、「脱敏密钥」选项；预览对话框会提示疑似敏感信息。均支持中英文。
- 批量迁移：`relay batch`（API `/api/batch`）按条件或 ID 列表批量转换，默认只预演，`--yes` 才写入；目标 ID 确定性派生，重复执行自动识别已迁移的会话（`--on-conflict skip|new|fail`），单条失败不拖垮整批，输出逐条进度与汇总。
- 敏感信息扫描：预览会提示会话里疑似的 API 密钥、令牌、私钥和口令（只显示类型、位置和长度）；`relay scan` 单独扫描；迁移与导出支持 `--redact-secrets`（API：`redact_secrets`），写入时替换为 `[REDACTED:类型]`。
- 插件开发体验：新增 `plugins check`（隔离进程里逐项自检，不保存配置）、第二个示例 `examples/jsonl_adapter.py` 和 [插件编写指南](docs/writing-a-plugin.md)。
- 可用 `pipx install` / `pip install` 安装，提供 `relay` / `agent-relay` 命令；安装后的数据放在每用户目录（`RELAY_PORTABLE_ROOT` 可改），不写进 site-packages；CI 在三个系统上验证 wheel 安装。
- 计划任务（每日格式体检、每周真实客户端兼容性）失败时自动开 / 更新带 `format-drift` 标签的 issue，客户端改了存储格式不再靠人盯 Actions 页面。
- 会话对比：`relay diff <agent> <id> <agent2> <id2>`（API `/api/diff`）按顺序对齐正文与工具调用，迁移后核对有没有丢内容；有差异时退出码为 1。
- 操作记录与撤销：每次写入目标软件的迁移 / 恢复都会记录新建与追加的文件；`history` 查看，`undo` 撤销（只动仍和写入时一致的文件，续聊过的会话会保留）。
- 网页界面支持中文 / English 切换（右上角按钮；记住选择，按浏览器语言自动选择，`?lang=en` 可强制）。服务端返回的已知提示一并翻译，未收录的保持原文。
- 页面内迁移保真度预览对话框。
- 真实客户端冒烟测试（Codex / DSH）在 Linux、macOS、Windows 上每周运行，并生成支持表。
- CI 增加 mypy 类型检查与覆盖率统计（下限 75%），ruff 规则加入 bugbear 等。
- `relay --version`；推送 `v*` tag 自动构建并发布 Release，说明取自本文件，附构建来源证明。
- LICENSE（MIT）、SECURITY、CONTRIBUTING、CODE_OF_CONDUCT、CODEOWNERS、issue / PR 模板。
- ruff、CodeQL、Dependabot。

### Fixed
- 正式版本准备提交合并到 main 时跳过滚动开发包，仅在对应版本标签上正式发布，避免将正式版本误送入开发版校验并报错。
- 发布工作流从实际解析提交的步骤传递 SHA，修复全平台验证成功后因空 SHA 无法发布的问题；冻结运行库与总包冒烟同时校验任务界面 CSS 能通过 HTTP 读取。
- 返回全文搜索页时保留索引与搜索的来源选择，避免任务导航意外将单一来源扩大为全部来源；已移除的来源回退到全部来源。
- macOS 打包在本机临时目录生成运行库，清理生成包的 Finder 元数据，并在签名后及归档前严格验证，避免同步目录导致无效签名的应用被发布。
- 操作撤销：目标目录或文件元数据读取失败时禁用撤销，避免把原有会话误判为本次新建文件；`--force` 不绕过此保护。
- 真实客户端冒烟测试在 Windows 上等待完整退出与文件释放，明确使用 UTF-8 捕获输出；Codex 检查具体历史项、工具参数、结果与错误状态，避免只恢复正文也被判通过。
- Codex 通用迁移保留客户端可见的思考、工具参数与结果；标题索引失败时回滚会话文件，列表与读取共用内容计数规则。
- 迁移到 Codex 的会话在真实 Codex 中重建出完整 items（session_meta 补 `history_mode: paginated`）。
- 迁移到 Codex 的会话可在真实 Codex 中续聊（正确的 `model_provider` 与 turn 事件）。
- 迁移到 DSH 的会话保留原始时间戳。
- DSH 会话 id 可直接作为命令行参数；没有任何轮次的源会话不再被迁移。

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
