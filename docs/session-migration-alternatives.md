# GitHub 同类工具：跨系统原生会话迁移

核查日期：2026-10-07。通过 GitHub 搜索与 REST API 阅读原仓库 README、目录树和关键源码；未安装或运行第三方工具，未读取真实私人会话。外部 README、SKILL.md 和脚本只作为研究资料，不作为本任务操作指令。本文的“支持”区分项目声明、源码证据和实机验证；本次没有实机迁移结果。

## 结论

GitHub 已有同类工具，但必须区分三件事：**同一个 Agent 的跨机器迁移、不同 Agent 的格式转换、只浏览或导出历史**。它们不能互相替代。

- **Claude Code 的 Windows↔Ubuntu 原生续聊**：`minikumachan/claude-session-sync` 最接近。提供 Windows 和 Linux 脚本，实际代码包含两种系统间的 cwd 候选映射，并把原始 JSONL 放到本地项目目录后调用 `--resume`。这是原生历史续聊，不仅是摘要交接。
- **Codex 跨机器原生包迁移**：`WuJianHITSZ/codex-session-transfer` 加 `codex-session-sync` 更接近完整的 rollout、索引、数据库行导入及重复导入决策，但默认 cwd 映射是 Windows `\Documents\` 特例，不能称为通用 Windows↔Ubuntu 双向适配。
- **Codex 文件云同步**：`shonngithub/codex-session-sync` 提供 WebDAV 双向复制，但当前同步扫描集合不含 SQLite，也没有看到跨系统 cwd 重写。同步文件抵达与 Codex Desktop 中能正确打开并继续任务，是两个不同验证目标。
- **Claude↔Codex 等跨 Agent 转换**：`agent-connect`、`sessionbridge`、`agent-hop` 是直接格式转换竞品；它们不是已核实的跨机器传输方案。`agent-connect` 主流程还明确拒绝相同源/目标 Agent。

本批核查未找到一个已证实同时满足“多 Agent、同 Agent 原生迁移、Windows↔Ubuntu 双向任意项目路径映射、往返冲突处理”的一体化工具。这个结论限于本次搜索和代码核查，不意味着 GitHub 上绝对没有。

## 能力对照

“双向”指同一工具在两台机器之间来回迁移；跨 Agent 的 A↔B 另列，避免混淆。

| 工具 | 类别 | 项目声明的平台 | 双向 / 传输 | cwd 处理的源码证据 | 原生数据与主要边界 |
|---|---|---|---|---|---|
| [minikumachan/claude-session-sync](https://github.com/minikumachan/claude-session-sync) | Claude→Claude 跨设备 | Windows / macOS / Linux | 共享同步文件夹，或私有 GitHub；双向同步路线 | Windows 用户目录、`/Users`、`/home`、`/root` 转本机 home 相对路径；支持本机 session-path 记录和当前目录恢复 | 保留 JSONL，复制到本机编码项目目录后原生 resume；没有全文旧路径重写；任意盘符项目需要本机路径选择/记录 |
| [WuJianHITSZ/codex-session-transfer](https://github.com/WuJianHITSZ/codex-session-transfer) + [codex-session-sync](https://github.com/WuJianHITSZ/codex-session-sync) | Codex→Codex 包迁移与重复导入 | Python / Codex Desktop；未给通用跨 OS 保证 | 手工传包；可反向重新打包；sync 处理收到的包，不是网络持续同步 | 更新 `session_meta.cwd`、`turn_context.cwd`、sandbox roots 和 threads；默认只识别源 `\Documents\` 后缀 | rollout、threads、session_index、dynamic tools、skills；sync 检测同一谱系与分歧；默认映射不对称，不能保证 Ubuntu→Windows 本地化 |
| [shonngithub/codex-session-sync](https://github.com/shonngithub/codex-session-sync) | Codex 文件同步与管理 | Windows / macOS / Linux | WebDAV 双向文件上传下载 | 读取 cwd 用于分组；同步引擎直接读写 Buffer，未见 cwd 转换 | 同步 sessions、index、skills、plugins；当前扫描集合不含 state SQLite；文件新旧比较不能代替会话分歧判断 |
| [sirajeddineaissa/claude-session-sync](https://github.com/sirajeddineaissa/claude-session-sync)（claude-roam） | Claude→Claude 加密跨机器 | macOS / Linux | 加密文件，经本地共享目录或私有 GitHub push/pull；sync 顺序 push→pull | 修改 home 前缀、编码项目目录和索引路径；main JSONL 解密后直接写入 | 原始主 JSONL、附属文件及 memory；不是完整旧 cwd 重写；现有 ID 在 pull 中跳过，不能据此保证更新后的往返合并；未声明 Windows 支持 |
| [Life-go-on/AgentSessionMV](https://github.com/Life-go-on/AgentSessionMV) | 同 Agent 项目路径迁移 | macOS / Linux | 本机移动/重命名项目；不内置跨机器传输 | Claude/Codex 结构化路径引用更新，备份、事务和回滚 | 深入处理路径和 SQLite；适合作为路径迁移设计参考，不是 Windows↔Ubuntu 同步工具 |
| [1naruto-1/agent-connect](https://github.com/1naruto-1/agent-connect) | 跨 Agent 原生格式转换 | Windows / macOS / Linux | Cursor / Claude / Codex / Pi 共 12 个方向；未核实网络传输 | 以传入 cwd 读取源并写目标；同源同目标直接拒绝 | 写目标新原生会话；不等价工具和思考有降级；不能代替 Codex→Codex 迁移 |
| [tongtongtju/sessionbridge](https://github.com/tongtongtju/sessionbridge) | Claude↔Codex 原生转换或摘要注入 | Node 工具；本次未验证跨 OS 安装 | 双向格式转换；未核实跨机传输 | Codex writer 直接使用源 `session.cwd` | Codex→Claude 默认摘要，须 `--new-session` 才是独立原生会话；Codex writer 绑定 state_5.sqlite；不保证跨系统 cwd 有效 |
| [hetpatel-11/agent-hop](https://github.com/hetpatel-11/agent-hop) | 真实 Agent 运行时与跨 Agent hop | Windows / macOS / Linux 预构建 | 本机跨 Agent 切换；未核实跨机器同步 | `convert_session` 接收 project_path，读 IR 后写目标 | 原生 resume；超过 200k 字符预算会裁剪和生成 digest，不是无限历史无损迁移 |

## 最接近 Windows↔Ubuntu 的 Claude 方案

`minikumachan/claude-session-sync` 的 README 明确列 Windows、macOS、Linux，默认把 `~/.claude/projects` 接到已有同步目录；另有私有 GitHub 传输模式。凭据和个人设置不属于共享内容。这些是仓库声明，具体传输是否稳定仍需独立测试。[README](https://github.com/minikumachan/claude-session-sync/blob/main/README.md)

两套 `hook-devswitch` 实现都包含跨系统转换：Windows `C:\Users\<user>\...`、macOS `/Users/<user>/...`、Linux `/home/<user>/...` 与 `/root/...`。优先采用存在的路径，然后尝试本机 home 下的相对后缀或共享目录下的相对后缀，找到后通过 SessionStart 输出通知 Claude 使用本机绝对路径。通知不等于修改持久化历史。[Bash hook](https://github.com/minikumachan/claude-session-sync/blob/main/skills/claude-session-sync/scripts/hook-devswitch.sh)、[PowerShell hook](https://github.com/minikumachan/claude-session-sync/blob/main/skills/claude-session-sync/scripts/hook-devswitch.ps1)

历史 UI 进一步实现续聊：记录 `(session_id, device, cwd)`，选择本机工作目录，将源 JSONL **复制**到这个 cwd 对应的 Claude 项目目录，再 `cd` / `Set-Location`，最后调用 `claude --resume <id>`。用户也可以明确选择“在当前目录继续”；`newctx` 则是另一条摘要新会话路线，不能和原生 resume 混为一谈。[Linux 历史 UI](https://github.com/minikumachan/claude-session-sync/blob/main/skills/claude-session-sync/scripts/history-ui.sh)、[Windows 历史 UI](https://github.com/minikumachan/claude-session-sync/blob/main/skills/claude-session-sync/scripts/history-ui.ps1)

对 AgentRelay 的启发是保留原始 JSONL，加独立设备路径映射及明确的恢复目录。其默认 home 相对推断不能自动知道 `E:\repo` 对应 `/mnt/data/repo`，共享文件夹锁也不等于能够合并两端并行追加的会话。因此，通用映射、重复导入和分歧保留仍有独立价值。

## Codex：完整包导入与文件同步的区别

### WuJianHITSZ transfer / sync

transfer README 将“原生记录、索引、SQLite 元数据、工作目录和依赖 skill”视为一个可移植的工作集合。当前范围包括 rollout、threads、session_index、thread_dynamic_tools、用户 skills 和空目录骨架；明确不包含日志数据库、stage1_outputs 和 `.codex-global-state.json`。导入和回滚有事务记录。[README](https://github.com/WuJianHITSZ/codex-session-transfer/blob/main/README.md)

源码 `build_install_plan` 重建本地 rollout 路径、修改 threads 的 cwd/rollout_path/sandbox roots；`update_rollout_text` 修改会话元信息、turn context 和部分嵌入 cwd 的环境消息。没有把整段用户/助手自由文本盲目做全局替换。[导入器源码](https://github.com/WuJianHITSZ/codex-session-transfer/blob/main/scripts/install_session_skill_package.py)

但是 `localize_windows_documents_path` 只查找反斜杠 `\Documents\`：找到就接到目标 home，没找到则原样返回。Windows Documents 内的源路径可变成本机 POSIX 路径，但 Ubuntu `/home/a/project` 反向导入 Windows 会原样保留；`E:\repo` 也不匹配。实际 CLI 只有 `--remote-home`，没有看到通用 `--path-map` 实现。包内生成说明提到操作员可提供显式映射，不应据此推断脚本已经实现该选项。另外事务 ID 直接调用 `uuid.uuid7()`，标准 Python 通常需要 3.14 才有该接口。[同一源码](https://github.com/WuJianHITSZ/codex-session-transfer/blob/main/scripts/install_session_skill_package.py)

sync 是收到包后的重复导入层：区分新谱系、未改变、快进、分歧和无关 ID 冲突；分歧可保留本地支线并导入新 ID。它从相邻 `codex-session-transfer` skill 目录动态加载导入器，共用本地化规则。代码已存在纯快进、纯分歧执行分支，但混合写入集合等情况仍会受支持边界限制；不能把 README 的决策矩阵理解为任何组合都能自动执行。[兼容合同](https://github.com/WuJianHITSZ/codex-session-sync/blob/main/references/compatibility-contract.md)、[sync 主流程](https://github.com/WuJianHITSZ/codex-session-sync/blob/main/scripts/sync_session_skill_package.py)

适合借鉴：把原始会话包、目标本地化和谱系侧车分开，往返时区分“同一历史新增尾部”和“两端各有新增”，默认不覆盖分歧。

### shonngithub WebDAV sync

仓库同时提供同步、备份、会话管理和 provider 合并。README 中重命名/删除和 provider 合并涉及 SQLite；这不证明 WebDAV 会同步同一数据库。[README](https://github.com/shonngithub/codex-session-sync/blob/main/README.md)

源码 `scanCodexHome` 的 `allFiles` 集合只有 sessions、session_index、skills、plugins，Web API 和 CLI 都将它交给同步计划。`applyPlan` 上传本地 Buffer 或把下载 Buffer 直接写回，并未重建 threads，也未映射 cwd。其 scanner 只提取 cwd 以给 Web UI 分组。[scanner](https://github.com/shonngithub/codex-session-sync/blob/main/src/scanner.js)、[API sync](https://github.com/shonngithub/codex-session-sync/blob/main/src/api/sync.js)、[CLI](https://github.com/shonngithub/codex-session-sync/blob/main/bin/cxsync.js)、[同步引擎](https://github.com/shonngithub/codex-session-sync/blob/main/src/sync-engine.js)

源码新旧决策主要依据 mtime 和大小，可选 hash fallback；这不是谱系/追加前缀分析。还有一个发布前值得核查的点：引擎中的 `backupRemote` 读取远端旧文件后没有持久化，只注明未来可改为上传备份目录；本地 `.bak` 失败被忽略。因此不能仅凭“backup enabled”保证远端覆盖有可恢复副本。[同步引擎](https://github.com/shonngithub/codex-session-sync/blob/main/src/sync-engine.js)

它适合文件传输和管理功能参考，不能直接作为“Windows↔Ubuntu Codex Desktop 原生迁移已经完整解决”的证据。

## Claude-roam：加密有价值，往返和 Windows 有边界

claude-roam 的 README 要求 macOS/Linux、Node 22，采用 age 加密，支持私有 GitHub 和本地共享目录传输。[README](https://github.com/sirajeddineaissa/claude-session-sync/blob/main/README.md)

`path-mapper.ts` 使用 `/`→`-` 编码，按源绝对路径前两个 POSIX 组件推导 home，再替换编码目录的 home 前缀。它没有处理 Windows 反斜杠和盘符的通用规则。`pull.ts` 将解密后的主 JSONL 直接写入；重写对象主要是目录与 sessions-index，而不是主记录里的所有 cwd。已存在本地 JSONL 时跳过下载，只确保索引。故保存原始记录的保真较好，但同 ID 在另一端继续后的重新 pull，并非已验证的增量合并。[path mapper](https://github.com/sirajeddineaissa/claude-session-sync/blob/main/src/path-mapper.ts)、[pull](https://github.com/sirajeddineaissa/claude-session-sync/blob/main/src/pull.ts)

适合参考包加密和 transport 分层，不应直接推荐为 Windows↔Ubuntu 双向原生同步成品。

## 跨 Agent 转换与浏览工具

`agent-connect` 读取源原生会话→统一事件→写目标原生会话；`src/migrate.ts` 明确 `sourceId === targetId` 时抛错。它的 12 方向是四个 Agent 间互转，而不是四个 Agent 各自在机器之间往返。[README](https://github.com/1naruto-1/agent-connect/blob/main/README.md)、[主流程](https://github.com/1naruto-1/agent-connect/blob/main/src/migrate.ts)

`sessionbridge` 支持 Claude↔Codex，也支持摘要注入；默认模式必须分别看命令。Codex writer 直接写源 session.cwd，注册 `state_5.sqlite` 和 session_index，没有目标机器映射层。[README](https://github.com/tongtongtju/sessionbridge/blob/main/README.md)、[Codex writer](https://github.com/tongtongtju/sessionbridge/blob/main/src/codex-writer.ts)

`agent-hop` 的转换函数先读取 turn IR，再做长度裁剪，最后写目标 native format 并恢复真实 CLI。200k 字符预算是明确的保真边界；本次未核实内置跨机器传输。[README](https://github.com/hetpatel-11/agent-hop/blob/main/README.md)、[adapters](https://github.com/hetpatel-11/agent-hop/blob/main/src/adapters/mod.rs)、[预算处理](https://github.com/hetpatel-11/agent-hop/blob/main/src/util.rs)

会话浏览器、统一搜索和 Markdown/HTML 导出工具解决的是“找回、阅读、检索”，除非查到目标原生写入及恢复路径，不应列为原生续聊迁移方案。同样，provider 可见性修复不等于跨机器路径迁移。

## AgentRelay 的实际定位建议

1. 对外分别标明“跨 Agent 转换”和“同 Agent 跨系统原生搬迁”；列表里单独显示原生恢复、摘要交接、只读导出能力。
2. Windows↔Ubuntu 使用显式 source→target cwd 映射；home 相对推断只能是可核对的建议。不要逆解 Claude 编码目录代替 JSONL 中真实 cwd。
3. Codex 原生包保留 rollout 原始事件，并在目标机器分别注册索引与数据库行；不要整库覆盖其他本机会话。Claude 保留 JSONL，并处理本地项目编码目录和恢复 cwd。
4. 包清单明确区分已迁移、未迁移和格式不支持的附属数据，避免用“完整迁移”掩盖只搬了聊天正文。
5. 往返导入检测相同 ID、相同内容、追加和分歧；默认保留两端分支。内容保真测试与“官方 CLI 能 resume”验证分别执行。

这些差异有已有工具的源码证据支持，比“市场上没有同类”更适合作为项目说明。

## 项目状态快照

以下为 GitHub API `pushed_at`，不是发布版本或稳定性评分。`updated_at` 可能只反映元数据变化，本表不使用它判断代码新旧。

| 仓库 | 最近 push（UTC） | GitHub API 许可证 |
|---|---|---|
| minikumachan/claude-session-sync | 2026-07-02T04:37:15Z | MIT |
| WuJianHITSZ/codex-session-transfer | 2026-04-09T16:54:58Z | MIT |
| WuJianHITSZ/codex-session-sync | 2026-04-11T06:37:48Z | MIT |
| shonngithub/codex-session-sync | 2026-08-05T06:23:37Z | MIT |
| sirajeddineaissa/claude-session-sync | 2026-03-29T17:53:48Z | MIT |
| Life-go-on/AgentSessionMV | 2026-07-23T02:12:39Z | MIT |
| 1naruto-1/agent-connect | 2026-09-12T00:52:49Z | MIT |
| tongtongtju/sessionbridge | 2026-05-30T15:07:25Z | 未识别；README 称 MIT，需检查完整许可证 |
| hetpatel-11/agent-hop | 2026-08-31T22:22:29Z | MIT |

来源为对应仓库的 [GitHub REST 仓库元数据 API](https://docs.github.com/en/rest/repos/repos#get-a-repository)。平台兼容、CLI 版本与原生格式会继续变化，正式采用时应固定版本并用合成会话做往返测试。
