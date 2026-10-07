# 来源格式与识别依据

核查日期：2026-10-07。外部资料仅用作格式证据。

## DeepSeek Harness

- [官方 home-paths](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/util/home-paths/src/index.ts)：`DSH_HOME`，默认 `~/.dsh`。
- [默认 persistence 配置](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/bundle/base/cordis.patch.yml)：`sessions` 根目录。
- [官方 JSONL backend](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/session/session-persistence-jsonl)：版本化世代及多个独立 Zstd frames。
- [官方 v4 说明](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/persistence-changes/2026-09-16-session-format-v4.md)：v4 工具结果使用独立 tool role；v0–v3 使用嵌套 tool-result。

读取 `sessions/<project>/<encoded-id>/session[.vN].jsonl[.zstd]` 的最大 canonical 世代；未知最新版本不退回旧世代。
普通与压缩日志同时存在视为歧义。工具调用按 call ID 去重；完成消息优先于流式 chunks，旧版 packed chunks 展开后处理。
读取输出为事件历史，保留来源元数据，不声称能重建原会话压缩/替换后的当前运行上下文。

写入使用官方已发布 v0 协议：`sessions/<projectKey>/<id>/session.jsonl.zstd`；projectKey 按 UTF-16 码元采用官方 `~XXXX` 编码。header 和各个事件使用独立、带校验和的 Zstd frames。日志包含连续 seq、消息 ID、surface append、助手块流及其 sourceEventSeqs、成对工具生命周期、已关闭 turn/step 和 end-seed 标记；导入标题使用用户指定标题语义。源会话 ID 不复用，目标 ID 全局防重，不覆盖现有世代。

通过本机官方 `dsh-session-persistence-jsonl` 0.1.2-rc.1 的 list/prepare/deriveMessages/追加消息/退出落盘/重新读取验证；另通过官方 `dsh-session-format-catalog` 0.2.1-alpha.1 严格恢复，将生成的 v0 历史迁移到 v4。验证使用临时合成会话，不发送模型请求，不修改用户历史。可选验证脚本为 `tests/dsh_native_smoke.mjs` 和 `tests/dsh_catalog_smoke.mjs`。

未完成或重复 ID 的工具调用保留为文字，避免恢复出待执行调用；图片/未知块降级为完整标注 JSON。来源工具参数不转换，也不安装工具。新会话模型仍由 DSH profile 的当前配置选择，导入消息里的模型仅表示来源历史。

Windows ↔ Ubuntu 的对应软件迁移复制完整 v4 原生事件，保留运行状态事件而不经 IR 重建；
路径编码遵循官方 `format.ts` 的 UTF-16 `encodeSegment` / `projectKey`，Zstd 首帧仅含 header。
分叉先迁父会话；旧版、损坏或子代理的单独导入会停止。

## WorkBuddy 与 CodeBuddy

- WorkBuddy 使用原有 Tencent JSONL adapter，根目录独立为 `.workbuddy/projects`。
- [tokscale CodeBuddy CLI reader](https://github.com/junhoyeo/tokscale/blob/main/crates/tokscale-core/src/sessions/codebuddy.rs)：`.codebuddy/projects` 与 `message/function_call` 同族记录。
- [AgentsView CodeBuddy IDE reader](https://github.com/kenn-io/agentsview/blob/main/internal/parser/codebuddy.go)：`history/<workspace>/<session>/index.json` 与 `messages/<id>.json`，按 manifest 顺序读取。
- [AgentsView 格式来源记录](https://github.com/kenn-io/agentsview/blob/main/docs/internal/session-format-sources.md)：CodeBuddy 缺少公开生产端协议依据。

CodeBuddy 分别处理 CLI 与 IDE，ID 带格式和路径前缀以避免重名。message/extra 可为对象或 JSON 字符串；正文、思考、工具调用和结果映射到 IR。
引用路径必须是安全文件名；缺少 message 文件会拒绝迁移，不静默导出部分历史。IDE 根目录可含多个 profile。

WorkBuddy 与 CodeBuddy CLI 的部分记录结构相同，产品身份由独立配置和根目录确定，不能从同一备份里仅凭相同 JSON 字段推断来源。
CodeBuddy 不提供任意 IR 的通用 writer。对应软件迁入只复制已验证的原生记录：CLI JSONL 或 IDE 的 manifest/messages。
IDE 复用 Ubuntu 已有且 cwd 唯一匹配的工作区，追加 conversations 条目并保留原索引字段，不猜 workspace hash。
索引更新失败撤回本次新会话，原有会话保留。操作需先关闭目标软件；格式依据来自消费者观测，
回读测试仍不能替代厂商对应版本的实际续聊验证。

## Claude Agent SDK

- [官方 session-storage](https://code.claude.com/docs/en/agent-sdk/session-storage) 与 [sessions](https://code.claude.com/docs/en/agent-sdk/sessions)：默认与 Claude Code 共用 `~/.claude/projects`，尊重 `CLAUDE_CONFIG_DIR`。
- [Python SDK 原生 session reader](https://github.com/anthropics/claude-agent-sdk-python/blob/main/src/claude_agent_sdk/_internal/sessions.py)：list/get API 读取共享存储；可见消息沿 parentUuid 链构建，不回溯 logicalParentUuid，排除 sidechain/meta/team 消息。
- [官方合成 fixture](https://github.com/anthropics/claude-agent-sdk-python/blob/main/tests/test_sessions.py)：明确对应 CLI on-disk JSONL，包含 user/assistant/tool_use/tool_result。
- [Python SDK subprocess](https://github.com/anthropics/claude-agent-sdk-python/blob/main/src/claude_agent_sdk/_internal/transport/subprocess_cli.py)：驱动 CLI，进程设置 `CLAUDE_CODE_ENTRYPOINT=sdk-py`，没有据此保证日志会持久保存创建者字段。
- [TS SDK reference](https://code.claude.com/docs/en/agent-sdk/typescript)：persistSession=false 不保存可恢复历史；SDK stream 消息与 native transcript 是不同层次。

SDK 独立入口为 `claude_sdk`。默认显示共享记录，`shared_store=true, creator=unknown`，不凭 userType/agentName 猜创建者。
因此它和 Claude Code 默认可能显示同一会话；独立 RELAY_CLAUDE_SDK_HOME 只决定读取范围，不是来源证明。
官方默认文件按主链读取；wire session_id/stream 输出会明确拒绝当作 native transcript。
SDK 不作为通用 IR 转换目标，可迁出；Windows ↔ Ubuntu 对应软件迁移保留原生记录，写入目标系统
SDK 配置的 Claude 共享存储。不会自动调用 SDK resume 或模型请求。
Claude 新项目编码依据官方 session reader 的 `_sanitize_path` 与 long-path hash，已有目录优先复用。

Claude / SDK 的链算法依照官方 reader 语义独立实现；缺父节点或循环会拒绝迁移。
未知内容块保存至 IR RAW，导出原始 JSON；迁移时降级为标注文本，不承诺厂商功能能在目标运行。
