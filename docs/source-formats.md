# 来源格式与识别依据

核查日期：2026-10-07。外部资料仅用作格式证据。

## DeepSeek Harness

- [官方 home-paths](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/util/home-paths/src/index.ts)：`DSH_HOME`，默认 `~/.dsh`。
- [默认 persistence 配置](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/bundle/base/cordis.patch.yml)：`sessions` 根目录。
- [官方 JSONL backend](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/session/session-persistence-jsonl)：版本化世代及多个独立 Zstd frames。
- [官方 v4 说明](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/persistence-changes/2026-09-16-session-format-v4.md)：v4 工具结果使用独立 tool role；v0–v3 使用嵌套 tool-result。

读取 `sessions/<project>/<encoded-id>/session[.vN].jsonl[.zstd]` 的最大 canonical 世代；未知最新版本不退回旧世代。
普通与压缩日志同时存在视为歧义。工具调用按 call ID 去重；完成消息优先于流式 chunks，旧版 packed chunks 展开后处理。
输出为事件历史，保留来源元数据，不声称能重建当前运行上下文。原生写回未实现。

## WorkBuddy 与 CodeBuddy

- WorkBuddy 使用原有 Tencent JSONL adapter，根目录独立为 `.workbuddy/projects`。
- [tokscale CodeBuddy CLI reader](https://github.com/junhoyeo/tokscale/blob/main/crates/tokscale-core/src/sessions/codebuddy.rs)：`.codebuddy/projects` 与 `message/function_call` 同族记录。
- [AgentsView CodeBuddy IDE reader](https://github.com/kenn-io/agentsview/blob/main/internal/parser/codebuddy.go)：`history/<workspace>/<session>/index.json` 与 `messages/<id>.json`，按 manifest 顺序读取。
- [AgentsView 格式来源记录](https://github.com/kenn-io/agentsview/blob/main/docs/internal/session-format-sources.md)：CodeBuddy 缺少公开生产端协议依据。

CodeBuddy 分别处理 CLI 与 IDE，ID 带格式和路径前缀以避免重名。message/extra 可为对象或 JSON 字符串；正文、思考、工具调用和结果映射到 IR。
引用路径必须是安全文件名；缺少 message 文件会拒绝迁移，不静默导出部分历史。IDE 根目录可含多个 profile。

WorkBuddy 与 CodeBuddy CLI 的部分记录结构相同，产品身份由独立配置和根目录确定，不能从同一备份里仅凭相同 JSON 字段推断来源。
CodeBuddy 暂只读，不猜测 native writer。现有 WorkBuddy writer 的回读测试不能替代厂商实际续聊验证。
