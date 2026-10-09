# 为新的 AI 工具写读取插件

AgentRelay 内置来源之外的工具，可以用一个 Python 文件作为「可信社区插件」接入：只读，能列出会话、导出 Markdown、作为转换迁移的来源。接口约定和信任模型见 [Adapter 接口与可信社区插件](adapters.md)，这里讲怎么写、怎么验。

## 1. 从示例开始

- [`examples/plaintext_adapter.py`](../examples/plaintext_adapter.py)：一个 `.txt` 文件一个会话，最小实现。
- [`examples/jsonl_adapter.py`](../examples/jsonl_adapter.py)：每行一条 `{"role","content"}` 的 JSON Lines 聊天，带角色映射、行号报错、截断标记，是更接近真实格式的起点。

复制一份，改 `name`、`label`、`home` 和 `read()` 里的解析即可。

## 2. 必须实现的接口

| 成员 | 要求 |
|---|---|
| `name` | 小写字母开头，只含小写字母 / 数字 / `_` / `-`，最长 48；不能与内置来源重名，不能以 `windows_` / `ubuntu_` 开头 |
| `api_version` | 目前为 `1` |
| `can_write` | 必须为 `False` |
| `home` | 数据目录（字符串） |
| `available()` | 目录存在 / 可用时返回 `True`；不要用「目录存在」证明客户端装了或能续聊 |
| `discover()` | 产出 `SessionInfo`（`id` 唯一；体积过大的标 `readable=False` 并写 `error`） |
| `read(id)` | 返回 `ir.Conversation`；只接受 `discover()` 给出的 ID，拒绝路径和符号链接 |

## 3. 写法上的约定

- **报告不完整，不要猜。** 解析不了的行直接报错并说明行号；文件被截断就设 `truncated=True`（迁移会因此拒绝，导出会提示）。
- **限制读取量。** 读取前判断文件大小；插件文件本身 ≤ 1 MiB，单次调用 15 秒、输出 ≤ 32 MiB。
- **不联网、不改会话、不在导入时做耗时任务。**
- **角色只用** `ir.USER` / `ir.ASSISTANT` / `ir.SYSTEM`；工具调用用 `Block.tool_call` / `Block.tool_result`，思考用 `Block.thinking_block`。
- 一个真实的插件应附带**格式说明和合成样本**（不要提交真实对话）。

## 4. 自检

```sh
python app/cli.py plugins check jsonl examples/jsonl_adapter.py
```

`check` 在隔离的工作进程里按顺序检查：名称格式、是否覆盖内置来源、文件大小、`info()`、`discover()`、会话 ID 唯一，并对前 3 个可读会话调用 `read()` 后做 Markdown 导出。每项给出 ✅ / ❌ 和原因，全部通过退出码为 0。**不会保存任何配置，也不会启用插件。**

没有样本数据时它会提示「没有可读会话，跳过」——先准备一个合成样本再验。

## 5. 启用

```sh
python app/cli.py plugins enable jsonl examples/jsonl_adapter.py
python app/cli.py list jsonl
python app/cli.py export jsonl chat.jsonl -o chat.md
```

启用时记录文件的 SHA-256，文件被改动后必须重新启用。**独立进程不是安全沙箱**——只启用你审阅过的代码。
