# GitHub 竞品核查：新功能还是使用体验

核查日期：2026-10-09（Australia/Brisbane）。最初比较本仓库 `ebb2aaf`，交付前复核至 `ab6a2ae`（#40 已合并），与 GitHub 公开 README、源码、测试目录及 REST 仓库元数据对照；未安装、运行第三方工具，未接触真实私人会话。外部文档中的操作指令只当研究数据。表中“有代码”不等于本次已实机验证；stars/pushed_at 只是当天快照，不是质量或市场份额。

## 对优先级的判断

**现阶段更适合先完成已有迁移、搜索、Skill 草稿的使用闭环，再做一个有明确验收目标的新能力。**依据是主要竞品已经覆盖大量原规划功能：便携包、加密、增量、GUI、全文搜索、配置同步、Skill 版本管理均非空白。继续铺功能菜单会扩大适配与维护成本，而“从哪台设备的什么客户端，恢复到哪里，哪些内容会丢，最后能否续聊”的可理解流程仍直接影响选择与信任。此结论是产品判断，不是经过用户转化率实验的事实。

原规划有三处需要修正：CC Switch 当前是 **MIT 开源**，不能笼统标成收费商业工具；`session-migrate` 已提供 18×18 原生源验证资料，旧“64 路线”不是当前覆盖依据；国产侧已有 WorkBuddy 迁移和 DSH 管理项目，且海外综合引擎支持 Qwen/Kimi 等，不能宣传“所有海外工具零国产支持”。较稳妥的定位是 **WorkBuddy / DSH / CodeBuddy 加 Claude / Codex 的统一、可核查的跨系统搬迁**；CodeBuddy 当前只读边界须继续显明。

## 主要项目与证据

| 项目 | 本次能确认什么 | 与 AgentRelay 的关系 / 核查边界 |
|---|---|---|
| [session-migrate](https://github.com/xhluca/session-migrate) | README 列 18 harness；Python 3.11+、Linux；有精确客户端 fixture、18×18 [验证文档](https://github.com/xhluca/session-migrate/blob/main/docs/native-corpus-validation.md)；明确不迁移 auth/hooks/MCP/config | 扩来源数量与格式验证的直接竞争；无 WorkBuddy/DSH/CodeBuddy 列项，本次没有运行其矩阵。MIT；128 stars；最近 push 2026-09-11 |
| [claude-code-tools / aichat](https://github.com/pchalasani/claude-code-tools) | [port 官方说明](https://github.com/pchalasani/claude-code-tools/blob/main/docs-site/src/content/docs/tools/aichat/port.mdx)明确 Claude↔Codex 原生续聊与谱系；[search](https://github.com/pchalasani/claude-code-tools/blob/main/docs-site/src/content/docs/tools/aichat/search.mdx) 是独立 Rust/Tantivy 引擎、增量索引与 TUI | 搜索与双端转换已有成熟替代；本次读文档并核对转换器目录，未重新实机测。MIT；2012 stars；push 2026-10-08 |
| [transession](https://github.com/inmzhang/transession) | Claude↔Codex 原生转换；README 标实测版本 Claude 2.1.234 / Codex 0.147.0；有 roundtrip tests，明确格式变化风险 | 单纯新增 Claude↔Codex 路线不构成独有差异。MIT；28 stars；push 2026-08-18 |
| [codex-claude-transfer / cct](https://github.com/ahmojo/codex-claude-transfer) | 便携 bundle、cwd 映射、浏览器 UI、搜索、secret scan/redact、age 加密、LAN 已有实现；[mergesync.go](https://github.com/ahmojo/codex-claude-transfer/blob/Main/internal/bundle/mergesync.go)处理追加与分歧；[加密失败测试](https://github.com/ahmojo/codex-claude-transfer/blob/Main/internal/cli/export_encrypt_test.go)保护旧包 | 与便携、增量、加密路线直接重合。README 记录 2026-10-07 native canary，且明确不直接写 Codex SQLite；不能据此推断所有 Desktop 状态完整。MIT；73 stars；push 2026-10-09 |
| [Skillsync 的 txcript](https://github.com/skillsynchq/txcript) | 公共 Rust/JS/WASM/CLI 引擎；README 有 Windows/Linux/macOS、转换、搜索、裁剪、跨机 JSON、只读 MCP；17 行来源表含部分只读与在线账号 | 同一 IR 加多个 UI 已有可复用引擎。会话转换不等于完整 runtime/settings 克隆；桌面产品商业状态不能由引擎许可证推出。Apache-2.0；155 stars；push 2026-09-29 |
| [CC Switch](https://github.com/farion1231/cc-switch) | README 与 [profile.rs](https://github.com/farion1231/cc-switch/blob/main/src-tauri/src/services/profile.rs)含 Profile；MCP/Skills/Prompts、WebDAV/S3 已有代码；[skill.rs](https://github.com/farion1231/cc-switch/blob/main/src-tauri/src/services/skill.rs)有备份/恢复 | 全量 provider/config 管理已拥挤；云同步 CC Switch 配置不能等同所有原生会话无损搬迁。MIT；141773 stars；push 2026-10-09 |
| [skillcoffer](https://github.com/Howryann/skillcoffer) | 中文 WebUI、完整目录不可变版本、diff、restore、live/pin、Bundle、GitHub backend；[store.ts](https://github.com/Howryann/skillcoffer/blob/main/src/store.ts)保存树 hash并恢复整个工作树 | Skill 版本管理也有直接竞品；README 当前 Linux/macOS，明确未实现 Windows junction/copy，主要 pi 使用组合。MIT；3 stars；push 2026-09-09；early development |

## 历史提炼 Skill 已有其他实现

[ECC continuous-learning-v2](https://github.com/affaan-m/ECC/blob/main/skills/continuous-learning-v2/SKILL.md)从 hooks 观察会话，后台模型形成带置信度的 instincts，区分 project/global 并支持跨项目提升；[instinct-cli.py](https://github.com/affaan-m/ECC/blob/main/skills/continuous-learning-v2/scripts/instinct-cli.py)实际有 evolve、生成 SKILL.md、导入导出代码。部分“100% reliable”属于项目自己的宣传，本次未验证。

[skill-kit extract（原 Claudeception）](https://github.com/abhattacherjee/claude-code-skills/blob/main/plugins/skill-kit/skills/extract/SKILL.md)是让 Agent 从经验生成可复用 Skill 的提示工作流；不是离线跨来源历史扫描器。旧 Claudeception 仓库已归档并指向新 monorepo。[Acontext Learning Spaces](https://github.com/memodb-io/Acontext/blob/main/docs/content/docs/(guides)/learn/(features)/learning-spaces.mdx)会更新 SKILL.md 与技能文件；[skill_learner.py](https://github.com/memodb-io/Acontext/blob/main/src/server/core/acontext_core/llm/agent/skill_learner.py)确有 LLM + skill 工具循环，使用后端数据库与 Learning Space，不是便携离线桌面方案。

因此 AgentRelay 值得强化的是 **不需模型/API 的跨来源证据发现、人工确认、完整 Skill 目录版本与跨设备可追溯链路**，不能只宣传“历史变成 Skill”。也不能把统计相似度称为任务成功概率。下一步 Skill 生命周期应版本化 scripts/references/assets 全目录，保留原生证据 ID、内容 hash 与适配版本，搬设备后仍能核对证据；先做 diff/显式恢复和分歧保留，再考虑模型增强。这是候选组合定位，尚不能证明市场上没有相同产品。

## 国产工具不是空白，但统一跨系统仍可竞争

[JanCong/workbuddy-migrator](https://github.com/JanCong/workbuddy-migrator)为本机账号迁移，已有 dry-run/rollback；[manson1313113-debug/workbuddy-migrator](https://github.com/manson1313113-debug/workbuddy-migrator)有 Windows Tkinter/.exe、wbpack、技能/记忆/设置与跨机合并。核对其 [core_paths.py](https://github.com/manson1313113-debug/workbuddy-migrator/blob/main/src/core_paths.py)，slug、用户前缀等以 Windows 规则为主，不能由 README 推为任意 Windows↔Ubuntu 原生续聊实测。

[DSH session-manager](https://github.com/ailiasdesu/dsh-session-manager)提供界面拖拽、工作区移动、备份/恢复；[migrate.js](https://github.com/ailiasdesu/dsh-session-manager/blob/main/lib/migrate.js)写 header.cwd、备份并迁文件，主要同一 DSH 根内管理。[ZCode→DSH](https://github.com/One1turn/dsh-session-migration)明确导入为可读转录而非所有原生运行状态转换。本批未找到 CodeBuddy 跨设备原生迁移的可核实实现；这是搜索覆盖限制，不能说绝对不存在。

**推荐顺序：**先做任务导向导航、迁移向导、冲突/保真预览、完成后“在目标打开”的明确反馈；兼容证据随版本公开并补国产真实客户端恢复验收。随后将 Skill 草稿接到完整目录版本/diff/恢复/跨机证据闭环。加密包属于保护便携数据的价值补齐；增量/网络同步在谱系冲突和原子写入有可靠测试后推进。大而全 Profile/MCP/provider 管理和常驻自动快照暂后置。

## 检索范围与资料边界

GitHub repository search：session-migrate、transession、codex-claude-transfer、txcript、claude-code-tools、cc-switch、claudeception、continuous learning claude、session skill extraction in:readme、skill versioning、workbuddy-migrator、dsh session migration、codebuddy session。核对 19 个仓库元数据/README，抽查 19 个关键源码/说明文件；未读取全部源码、未执行全部第三方测试、未推断私有产品能力。AlfonsSkills/SkillSync 与 skillsynchq/Skillsync 是不同项目；前者 README 已标停止维护。

项目状态来源为对应 `https://api.github.com/repos/{owner}/{repo}` 的 pushed_at、stargazers_count、license，不使用 updated_at 当最近代码更新时间。功能来源以上述项目维护者的 README/源码/测试；仍需固定客户端版本和跨机合成会话验证才能作发布承诺。
