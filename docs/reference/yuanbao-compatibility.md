# 腾讯元宝电脑版接入范围与格式证据

调查日期：2026-10-12。当前接入对象为腾讯元宝电脑版的**本地 JSON 对话导出文件**。读取导出文件、备份到便携库和转换到其他支持写入的 Agent，与恢复到元宝客户端历史列表是不同能力；本次只实现前者。

## 支持范围

| 能力 | 范围 |
|---|---|
| JSON 读取 | 兼容 `lisoleg/yuanbao-exporter` 的批量导出；另支持显式标记 `source: "yuanbao"` 的单会话 JSON，见[格式契约](formats/yuanbao.md) |
| 本地管理 | 用户选择本地 JSON 导出文件，保存到便携数据目录后列表、预览、导出；无需元宝登录或浏览器会话 |
| 对话迁出 | 正文和可读思考转换到 IR；可使用已有 Markdown 导出和其他 Agent 转换能力 |
| 会话备份和恢复 | ZIP 保存本地导出文件；恢复到 AgentRelay 的元宝导出目录，供 AgentRelay 再读取 |
| 元宝客户端原生历史恢复 | 未实现；不写入元宝 SQLite、IndexedDB 或云端历史 |
| 本地数据库自动采集 | 未实现；不读取登录状态、Cookie、Token 或加密密钥 |
| 云端历史获取 | 未实现；不自动扫码、调用私有接口或下载附件 |

JSON 导出只包含导出器已经取得的内容。未加载的历史、附件文件、工具运行状态和服务器索引不因导入 AgentRelay 而补齐。JSON 未给出的消息时间与会话创建时间不能由文件修改时间冒充；`exportTime` 表示导出时间，不表示每条消息发送时间。

## JSON 格式的来源

兼容的批量文件来自第三方工具 [lisoleg/yuanbao-exporter](https://github.com/lisoleg/yuanbao-exporter)，**不是腾讯官方导出协议**。本次核对其提交 `5130f84bd939d334d3b32599a27054f8594bdbf4`：

- [`get_conversation_messages` 源码](https://github.com/lisoleg/yuanbao-exporter/blob/5130f84bd939d334d3b32599a27054f8594bdbf4/backend/exporter.py#L593) 将页面消息提取为 `role`、`content`、`thinking`。
- [`export_conversations` 源码](https://github.com/lisoleg/yuanbao-exporter/blob/5130f84bd939d334d3b32599a27054f8594bdbf4/backend/exporter.py#L721) 输出 `exportTime` 与 `conversations`；每个会话为 `id`、`title`、`messages`。
- [该工具 README](https://github.com/lisoleg/yuanbao-exporter/blob/5130f84bd939d334d3b32599a27054f8594bdbf4/README.md) 提供自行运行和选择 JSON 导出的说明。AgentRelay 不内置、安装或运行该工具；兼容其输出不代表保证其登录、抓取和导出成功。导出后的文件无需保留该工具的 `browser_session` 登录目录。

用户已有兼容 JSON 时直接导入。没有 JSON 时，可以自行评估并使用上述第三方工具的 JSON 导出，或把已取得的对话整理成下述明确标记的单会话格式。不要将登录会话文件、浏览器 profile 或整份客户端数据目录当作 JSON 对话导出导入。

## 官方实现与本机调查

官方入口为[腾讯元宝](https://yuanbao.tencent.com/)。2026-10-12 读取其公开静态页面与 JavaScript，未登录、未调用用户历史接口。页面 build ID 为 `BLClbpibPyU-seMESv3wH`，公开 commit 标识为 `55e06495`。

[官方公开页面脚本](https://static.yuanbao.tencent.com/modern/_next/static/chunks/yb_v2_pages/_app.630166a4aaa8ca16.js?qb_c_bid=98) 包含 `/api/user/agent/conversation/list`、`/api/user/agent/conversation/v1/detail`、创建与续聊路径；[官方消息脚本](https://static.yuanbao.tencent.com/modern/_next/static/chunks/yb_v2_yb-chat.6852020b7713119d.js?qb_c_bid=98) 使用 `convs`、`speaker`、`speechesV2`。这些是网页实现证据，不能视作腾讯公布的稳定迁移 API，亦不证明可把任意历史写回。

本机元宝电脑版版本为 `2.87.10.602`。只检查安装包静态资源、数据目录、数据库头部、SQLite schema 和统计；不读取登录凭据或加密密钥，不修改客户端数据库。检查发现：

- `%APPDATA%/Tencent/yuanbao/Users/<account>/Database/chat_message.db` 为可打开的旧版 SQLite，表名包括 `ChatConversationDetail`、`ChatMessages`、`ChatMessagesContecnt`（原拼写）和 `ChatMessageEntities`；本机旧库没有可验证的真实对话记录。
- `chat_message_v2.db` 的头部不是普通 SQLite。原因及密钥未知；本次未尝试解密，不能据此宣称支持新版数据库读取。
- `%LOCALAPPDATA%/com.tencent.yuanbao/EBWebView/Default/IndexedDB/https_tencent.yuanbao_0.indexeddb.leveldb` 存在浏览器缓存。文件中出现会话相关字段，不足以证明缓存包含完整、最新且未删除的历史；本次未将缓存字符串当作对话导出。
- 安装目录 `content.pkg` 为 ZIP，公开前端脚本的 `HYCSpeechType` 有 `text`、`reasoner`、`deep_think`、`deep_search` 等类型。脚本的复制逻辑分别读取 `msg`、`text`、`textMsg` 等字段，说明正文、思考和特殊卡片不能靠任意递归拼接混为一谈。前端包中未找到上述原生表名或 `chat_message_v2` 的迁移规则。

这次调查没有获得新版桌面客户端生成的真实明文导出样本，也没有在元宝客户端恢复后续聊。适配器测试证明受支持 JSON 的解析和 AgentRelay 备份回读；**不代表腾讯厂商认证或元宝原生续聊实测通过**。

## 本机路径与安全检查范围

导入接受用户明确选择的本机绝对 JSON 路径，与本地文件管理器一样允许从不同目录取得导出。不是将输入拼到一个固定导入根目录下：读取前检查绝对路径、JSON 扩展名、普通文件与大小，再严格校验 JSON 内容；输入会话 ID 不作为输出文件名，输出使用内容 SHA-256。恢复的项目目录只写入会话元数据；导出记录写到配置的元宝根目录，不写到项目目录。包路径只用于用户选包与结果展示。

HTTP 仅监听 loopback，校验 Host 与 Origin，拒绝跨站请求；本机拥有相同用户权限的进程不属于隔离对象。CodeQL 对这些用户指定路径的读取、目录存在检查和路径规范化报告 `py/path-injection`，需按上述本地文件选择语义人工评估，不能通过禁用规则或关闭来源检查来消除告警。回归检查跨站导入不写入，以及恢复不向项目目录写文件。

## 为什么不直接解析浏览器缓存

[ccl_chromium_reader](https://github.com/cclgroupltd/ccl_chromium_reader/tree/ef840de30221c4d65bc96d2f4d9057e9ef2f526d) 和 [Google dfindexeddb](https://github.com/google/dfindexeddb) 均有 Chromium IndexedDB 取证读取实现。它们能解释存储容器，不定义元宝业务记录的完整性。

CCL 的 [README](https://github.com/cclgroupltd/ccl_chromium_reader/blob/ef840de30221c4d65bc96d2f4d9057e9ef2f526d/README.md#indexeddb) 明确提醒 LevelDB 会返回旧版本、已删除数据。[对应 IndexedDB 源码](https://github.com/cclgroupltd/ccl_chromium_reader/blob/ef840de30221c4d65bc96d2f4d9057e9ef2f526d/ccl_chromium_reader/ccl_chromium_indexeddb.py) 的 `iterate_records` 具有 `live_only` 参数，但该实现未使用它筛除记录或合并最新序列。未来若增加缓存采集，必须单独验证活跃文件、最新 key 序列、删除标记、分页完整性和元宝业务语义。当前不引入这两个库作为运行依赖。
