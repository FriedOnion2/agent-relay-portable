# CodeBuddy 格式契约

- 位置：CLI：`~/.codebuddy/projects`；IDE：Windows `%LOCALAPPDATA%/CodeBuddyExtension/Data`，Mac `~/Library/Application Support/CodeBuddyExtension/Data`，Linux `~/.config/CodeBuddyExtension/Data`。
- 识别：CLI JSONL 与 IDE history manifest / messages 分别识别，ID 带格式和路径前缀；显式根目录只扫描指定位置。
- 能力：读取、导出、迁出；原生同款迁移/存包恢复，IDE 需唯一匹配的现有工作区；跨软件迁入使用 CLI 的 projects JSONL。
- 验证与限制：健康度覆盖 CLI，不覆盖 IDE；IDE 合成回归验证引用和索引失败撤回。消费者观测格式，Windows CodeBuddy Code 2.187.0 能用 `--resume` 打开迁入的 CLI 会话 ID。此项测试没有发送下一条模型请求。

Windows 与 Ubuntu 用户目录备份通过独立只读来源读取。迁移必须指定目标系统实际项目目录；正文、工具参数中的旧路径不重写，同 ID 不覆盖。附件、子代理旁路文件和完整客户端运行状态不在原生包保证范围。

格式证据与详细识别规则见 [来源格式](../source-formats.md)，验证层级及每日报告见 [兼容状态](../compatibility.md)。适配器 API v1；当前健康度样本版本 1，客户端版本没有依据时显示未知。
