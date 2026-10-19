# WorkBuddy AI 国际版格式契约

来源键：`workbuddy_ai`。网页显示 **WorkBuddy AI (International)**，与国内版 `workbuddy`、CodeBuddy 分开识别，不自动混合目录。

## 位置和账号选择

- 默认设备根目录：`~/.workbuddy-ai`，Windows、macOS、Linux 的规则一致。
- 旧布局：`projects/<project>/<sessionId>.jsonl`；新版账号布局：`user-<uid>-<enterprise-or-personal>/projects/<project>/<sessionId>.jsonl`。
- 检测到唯一 `user-…` 目录时选择它；多个账号时停止，要求通过「环境与兼容」或下方 CLI 配置明确选择账号。不会把不同账号合并，也不猜当前登录账号。账号目录下的 `sessions` 仅用于补充项目元数据。
- 本机配置键为 `workbuddy_ai`；可独立设置 `RELAY_WORKBUDDY_AI_HOME` / `WORKBUDDY_AI_HOME`，不继承 `WORKBUDDY_HOME` 或 `CODEBUDDY_CONFIG_DIR`。路径填设备根或具体账号根，不填 `projects`。
- 自动选择在来源适配器初始化时生效。切换客户端账号后，在本机目录配置中重新选择具体账号目录，以刷新来源。

## 传输

网页「迁移会话」选国际版后可浏览、预览、导出 Markdown、转换到其他可写来源；也能从国内版、Codex、Claude 等迁入国际版 JSONL。跨软件转换使用现有 WorkBuddy 消息映射，仅保留中间格式可表达的内容。

换设备使用「搬到另一台设备」保存和恢复原生 ZIP；同款恢复保留所选完整 JSONL、未知字段、工具参数，映射目标项目元数据和新 ID。正文及工具参数里的旧路径保持原文。包不包含其他会话、SQLite 账号索引、登录凭据、配置、附件或子代理旁路文件。同 ID 拒绝覆盖，可选择新 ID 创建副本。

```sh
python app/cli.py device-config --agent workbuddy_ai --home "C:/Users/alice/.workbuddy-ai/user-example-personal"
python app/cli.py list workbuddy_ai
python app/cli.py export workbuddy_ai <ID> -o conversation.md
python app/cli.py store-sessions workbuddy_ai <ID>
python app/cli.py restore-session <会话包.zip> --cwd <新设备已存在的项目目录> --dry-run
python app/cli.py restore-session <会话包.zip> --cwd <新设备已存在的项目目录>
```

同盘双系统可使用 `windows_workbuddy_ai` / `ubuntu_workbuddy_ai` 只读来源，以及既有 `import-windows`、`export-windows`、`import-ubuntu` 原生搬迁命令，仍需显式选择挂载用户目录和本机项目，见[双系统指南](../../guide/ubuntu-dual-boot.md)。

## 格式与验证证据

2026-10-19 静态核查本机 WorkBuddy AI **5.8.4** 安装包（`@genie/workbuddy-desktop`），不是厂商验证。ASAR SHA-256：`026a1d0805a2366d06390cef52e157a7277543cdd27dd308e6b1acb47ffffdc1`。REA 分析仅选取部分模块，若干 unpacked 原生文件与 ASAR 声明摘要不一致；这些文件未执行，部分静态分析不作为整包完整性证明。

- `main/workbuddy-product-config.js`：产品独立数据根和配置目录；`main/tar.js`：`userStorageDirName` 与 `WorkbuddyPathService.userDir`。
- `cli/dist/codebuddy-lite-wb.mjs`：`SessionStore.getSessionFilePath`、`PathUtils.getHomeProjectsDir` 与项目编码辅助函数。原生记录包含 `session-meta`、`ai-title`、`message`、`reasoning`、`function_call`、`function_call_result`，复用 WorkBuddy 读取和写入映射。
- 新版项目目录保留大小写、空格和 Unicode，仅将 `/`、`\`、`:` 转为 `-` 并折叠/去除两端 `-`。UTF-8 超过 255 字节时截到完整码点的 180 字节前缀，加上 32 位 DJB2-XOR 的 base36 后缀。未沿用国内旧版的启发式 slug。
- 仅抽取安装包的纯路径辅助函数在 Node 中进行隔离重放，核对 Windows/POSIX、中文、emoji 和长路径输出；没有启动客户端或发送模型请求。
- 合成文件测试验证正文、思考、工具顺序、账号选择、双向转换、未知字段保留、原生包搬到另一设备后恢复、ID 冲突及凭据排除。

当前为**文件层支持**。桌面侧栏使用的 SQLite `sessions` 索引不修改；恢复后能否在客户端显示和继续对话尚未验证。健康检查的 `native_resume` 保持 `not-tested`。压缩/分支重放、图片与附件的完整恢复不在本次保证范围。
