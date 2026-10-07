# Claude Code 格式契约

- 位置：`~/.claude/projects`，`CLAUDE_CONFIG_DIR` / `RELAY_CLAUDE_HOME`。
- 识别：native JSONL user / assistant，parentUuid 主链、工具内容块，未知块保留为 RAW。
- 能力：读取、导出、通用写入、同款原生迁移/存包恢复。
- 验证与限制：样本回读与主链回归；工具、思考签名、计费和客户端隐藏状态不能通过 IR 转换完整恢复。真实新版续聊未知。

Windows 与 Ubuntu 用户目录备份通过独立只读来源读取。迁移必须指定目标系统实际项目目录；正文、工具参数中的旧路径不重写，同 ID 不覆盖。附件、子代理旁路文件和完整客户端运行状态不在原生包保证范围。

格式证据与详细识别规则见 [来源格式](../source-formats.md)，验证层级及每日报告见 [兼容状态](../compatibility.md)。适配器 API v1；当前健康度样本版本 1，客户端版本没有依据时显示未知。
