# WorkBuddy 格式契约

- 位置：`~/.workbuddy/projects`，根目录环境变量 `WORKBUDDY_HOME` / `RELAY_WORKBUDDY_HOME`。
- 识别：Tencent JSONL：message / function_call，extra 可为对象或 JSON 字符串。
- 能力：读取、导出、通用写入、同款原生迁移/存包恢复。
- 验证与限制：当前 JSONL writer 样本回读；记录结构缺少公开生产端协议，真实新版续聊未知。

Windows 与 Ubuntu 用户目录备份通过独立只读来源读取。迁移必须指定目标系统实际项目目录；正文、工具参数中的旧路径不重写，同 ID 不覆盖。附件、子代理旁路文件和完整客户端运行状态不在原生包保证范围。

格式证据与详细识别规则见 [来源格式](../source-formats.md)，验证层级及每日报告见 [兼容状态](../compatibility.md)。适配器 API v1；当前健康度样本版本 1，客户端版本没有依据时显示未知。
