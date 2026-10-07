# Claude Agent SDK 格式契约

- 位置：官方默认 `~/.claude/projects`，尊重 `CLAUDE_CONFIG_DIR` / `RELAY_CLAUDE_SDK_HOME`，与 Claude Code 共享。
- 识别：native transcript 按官方 reader 的 parentUuid 主链读取，排除 sidechain/meta/team；SDK stream/wire 记录不当作 native transcript。
- 能力：读取、导出、迁出、同款原生迁移/存包恢复；不作为通用写入目标。
- 验证与限制：Claude writer 合成样本回读、官方 reader 语义回归；creator=unknown，不从同一个共享日志猜 SDK 创建者。未执行真实 SDK resume 或模型调用。

Windows 与 Ubuntu 用户目录备份通过独立只读来源读取。迁移必须指定目标系统实际项目目录；正文、工具参数中的旧路径不重写，同 ID 不覆盖。附件、子代理旁路文件和完整客户端运行状态不在原生包保证范围。

格式证据与详细识别规则见 [来源格式](../source-formats.md)，验证层级及每日报告见 [兼容状态](../compatibility.md)。适配器 API v1；当前健康度样本版本 1，客户端版本没有依据时显示未知。
