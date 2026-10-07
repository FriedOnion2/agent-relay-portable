# DeepSeek Harness 格式契约

- 位置：`~/.dsh/sessions`，根目录 `DSH_HOME` / `RELAY_DSH_HOME`。
- 识别：canonical v0–v4 JSONL/Zstd 世代；未知最大世代拒绝回退，独立 Zstd frames。
- 能力：读取、导出、通用写入 v0 seed；原生迁移/恢复限完整 v4 或有效 v0 seed。
- 验证与限制：健康度仅验证生成的 v0 seed；仓库回归含其它世代。官方格式目录严格恢复有独立验证脚本，不代表最新版真实模型续聊。

Windows 与 Ubuntu 用户目录备份通过独立只读来源读取。迁移必须指定目标系统实际项目目录；正文、工具参数中的旧路径不重写，同 ID 不覆盖。附件、子代理旁路文件和完整客户端运行状态不在原生包保证范围。

格式证据与详细识别规则见 [来源格式](../source-formats.md)，验证层级及每日报告见 [兼容状态](../compatibility.md)。适配器 API v1；当前健康度样本版本 1，客户端版本没有依据时显示未知。
