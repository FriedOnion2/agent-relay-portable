# 当前限制

已知限制与未验证项。回到 [README](../README.md)。

## 当前限制

- WorkBuddy / Claude / SDK / Codex / CodeBuddy CLI 最多读取 32 MiB，超出时可导出带标记的部分内容，迁移会停止；DSH 普通/解压数据与 CodeBuddy IDE 总读取量超过限制会拒绝读取。
- Claude / SDK 默认读取当前 parentUuid 主链，不合并旧分支与子代理；压缩前的旧原文仍在原文件中，但不作为当前上下文重复迁移。
- DSH 导出保留事件历史，不重放 surface replacement、compaction、seed 或 native resume 状态。
- 网页及 CLI 提供 WorkBuddy、DSH、Claude、Codex 四个迁移目标；CodeBuddy、SDK 仍只读。
- DSH 导入写入 v0 原生 Zstd 日志，兼容本机 0.1.2-rc.1，亦已通过官方 0.2.1-alpha.1 格式目录严格迁移到 v4 的验证。导入历史会关闭工具调用；缺失结果的工具调用保留为文字，不作为待执行工作。图片及非原生内容块降级为标注文本。目标工作目录必须是当前系统的绝对路径。
- CodeBuddy/SDK 的通用转换目标限制不影响双向对应软件原生文件迁移；后者保留原生记录，
  DSH 支持完整 v4 和可验证的 v0 seed，分叉先迁父会话，子代理不单独迁入；
  CodeBuddy IDE 需唯一匹配的已有原生工作区，并在关闭软件后导入。
- SDK 自行保存的 stream-json 输出不是 native transcript；关闭 persistence 或仅使用外部 SessionStore 的应用可能没有默认本地历史。
- CodeBuddy CLI/IDE 格式来自第三方消费者观测，未获得厂商原生续聊协议验证；格式依据见 [来源格式说明](source-formats.md)。
- 图片、加密思考及厂商特有元数据不能保证完整保留。
- 工具名转换不会安装目标工具，也不会转换各家工具的参数协议。
- Codex Desktop 可能需要自己的数据库索引；生成 JSONL 不保证会话自动出现在桌面列表。
- 目标 agent 的格式可能变化，程序回读测试通过不能替代目标 agent 的实际续聊验证。
- `.app` 与终端启动已在 Apple Silicon Mac 上实测；其他机器的 Gatekeeper 权限和目标工具原生续聊仍需验证。
