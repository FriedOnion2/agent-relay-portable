# 腾讯元宝 JSON 导出格式契约

- 来源：腾讯元宝电脑版对话的本地 JSON 导出文件；不直接读取客户端数据库或云端账户。
- 识别：第三方 `lisoleg/yuanbao-exporter` 批量格式，或显式标记 `source: "yuanbao"` 的单会话格式。
- 能力：列表、读取、Markdown 导出、迁出到其他支持写入的 Agent、AgentRelay 本地导出文件的 ZIP 备份与恢复。
- 限制：没有元宝原生 writer；恢复 ZIP 的目标是 AgentRelay 导出目录，不是元宝客户端历史列表。不获取 Cookie、Token、加密密钥或附件。

## 使用方法

1. 先取得兼容 JSON 文件。第三方 [yuanbao-exporter](https://github.com/lisoleg/yuanbao-exporter) 提供导出方式，但 AgentRelay 不内置或运行它，也不保证其登录和采集成功。
2. 网页打开「迁移会话」，选择「腾讯元宝」，输入 JSON 文件的本机绝对路径并导入。也可使用命令：

   ```sh
   python app/cli.py import-yuanbao "C:/exports/yuanbao.json"
   python app/cli.py list yuanbao --json
   python app/cli.py export yuanbao <列表中的选择ID> -o conversation.md
   python app/cli.py store-sessions yuanbao <列表中的选择ID>
   ```

3. 文件保存到便携根目录的 `imports/yuanbao`；环境变量 `RELAY_YUANBAO_HOME` 或「环境与兼容」的设备目录配置可覆盖。共享 `config.json` 的 `agent_homes.yuanbao` 也可设置目录，换设备时优先使用本机设备配置。
4. 跨设备复制生成的 ZIP（或整个 `storage`），在「搬到另一台设备」中选包，填写新设备存在的项目目录，预览并确认。恢复目标是 AgentRelay 元宝导出目录，可继续预览或迁出；不写回元宝客户端。相同原生 ID 会停止恢复，可选择新 ID 创建独立副本。

导入前校验整个 JSON，错误文件不产生部分会话；相同规范内容再次导入会跳过。同 ID 的不同内容保留为独立记录，必须使用列表中的选择 ID；不自动合并。同一批量导出存包时只带走选中的会话。只保留 ID、标题、正文、思考，以及显式提供的项目、模型和创建/更新时间；未知账号字段、导出时间和其他未支持字段不保存。正文和思考中的原文不作脱敏处理。

## 批量导出

```json
{
  "exportTime": "2026-10-12 09:30:00",
  "conversations": [
    {
      "id": "example-yuanbao-conversation",
      "title": "测试对话",
      "messages": [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好！", "thinking": "先理解用户的问候。"}
      ]
    }
  ]
}
```

该结构依据第三方导出工具的[固定提交源码](https://github.com/lisoleg/yuanbao-exporter/blob/5130f84bd939d334d3b32599a27054f8594bdbf4/backend/exporter.py#L721)，不是腾讯官方导出协议。外层 `exportTime` 仅用于识别导出格式，导入后不保留，不当作每条消息的发送时间。每个会话 `messages` 是按导出顺序排列的消息数组，`content` 和可选 `thinking` 为字符串。

## 单会话导出

```json
{
  "source": "yuanbao",
  "id": "example-yuanbao-conversation",
  "title": "测试对话",
  "messages": [
    {"role": "user", "content": "你好"},
    {"role": "assistant", "content": "你好！", "thinking": "先理解用户的问候。"}
  ]
}
```

这是 AgentRelay 定义的导入格式。`source` 必须明确写为 `yuanbao`，避免把其他 Agent 的同形 `messages` JSON 误判为元宝。原始会话 ID 与便携选择 ID 不要求相同；使用 Relay 列表返回的 ID 选择导出记录。

## 内容映射

列表的更新时间优先采用导出中显式提供的 `updated_at`；没有它时显示导出记录文件的修改时间，仅用于排序，不是原始消息发送时间。

同一进程内，未变化文件的列表摘要可以复用；缓存仅保留列表字段，上限为 128 个文件、4096 条会话和总计 256 Ki 字符，超限摘要仍可列举但不缓存。文件身份、大小、修改时间、元数据变化后重新解析；读取失败不缓存。详情、预演、导出与迁移始终重新读取源文件。缓存依赖本地文件系统元数据，不适用于刻意保持全部元数据的文件篡改检测。

`user` 消息映射到用户轮，`assistant` 消息映射到助理轮。`content` 保存正文，`thinking` 保存可读思考；关闭思考选项时不将它并入正文。代码、用户原文和消息中的路径不因语言切换或跨设备复制而改写。输入格式未提供的时间、附件内容和客户端内部状态不推断生成。

JSON 备份可以恢复到另一台设备的 AgentRelay 导出目录，再由元宝来源适配器读取。该过程保留本地导出记录，不能保证元宝电脑版自动显示或继续这份会话。新版加密数据库、浏览器缓存、原生历史恢复和云端采集均不在本格式契约内。

格式来源、本机客户端检查及未验证范围见[元宝兼容调查](../yuanbao-compatibility.md)。
