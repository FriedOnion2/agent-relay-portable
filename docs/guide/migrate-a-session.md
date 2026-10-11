# 教程：把一条会话迁到另一个软件

以「把 Codex 里的一条会话迁到 Claude Code」为例，走一遍从查找到核对、撤销的完整流程。其他来源与目标的步骤相同，只是名字不同。命令的全部参数见 [命令行参考](../reference/cli.md)。

先决条件：已按 [安装](install.md) 准备好程序；两个软件都在本机用过，各有会话目录。

## 1. 体检

```bash
python3 app/cli.py doctor
```

确认 Python 版本够，并且 Codex 和 Claude Code 的会话目录都被找到了。目录不在默认位置时见 [配置](configuration.md)。

## 2. 找到会话

```bash
python3 app/cli.py list codex -f 关键词
```

记下输出里的**完整会话 id**。想确认是不是要找的那条：

```bash
python3 app/cli.py show codex <id> --head 5
```

## 3. 检查有没有敏感信息

会话里可能贴过密钥、令牌或口令，迁移会把它们原样复制到目标软件。

```bash
python3 app/cli.py scan codex <id>
```

只会报告类型、位置和长度，不显示内容；发现疑似内容时退出码为 2。扫描不能保证发现全部敏感信息。如果有命中，后面迁移时加 `--redact-secrets`，命中的内容会被替换成 `[REDACTED:类型]`。

## 4. 预演

```bash
python3 app/cli.py transfer codex <id> --to claude --cwd /path/to/project --dry-run
```

不会写入任何文件，输出一份 JSON 报告：目标位置、各类内容的数量、哪些内容无法完整迁移（`warnings`、`blockers`）。有 `blockers` 时不能继续。记下报告里的 `token`。

`--cwd` 是会话在目标软件里归属的**项目目录**。同一台机器上迁移可省略；来源在别的系统（例如 Windows 会话在 Mac 上迁移）时要填当前机器上存在的绝对路径。

## 5. 正式迁移

把预演时的所有参数原样带上，再加 `--preview-token`：

```bash
python3 app/cli.py transfer codex <id> --to claude --cwd /path/to/project --preview-token <token>
```

预演之后来源会话或选项有变化（例如又聊了几轮、改了参数）时，令牌不再匹配，迁移会被拒绝，需要重新预演。成功后输出新会话 id 和写入的文件路径。

不关心预演，也可以直接 `transfer`（不加 `--dry-run` 和令牌）。

## 6. 核对

```bash
python3 app/cli.py diff codex <源id> claude <新id>
```

给出一致、仅一边有、被改动的条数和相似度；内容完全一致时退出码为 0，否则为 1。正文、工具调用和结果在不同软件间格式不同，出现少量「改动」是正常的，重点看有没有大量「仅 A 有」。

然后打开目标软件，在会话列表里找到该标题。Codex Desktop 的列表还取决于它自己的数据库索引，只写 JSONL 不保证自动出现在桌面列表。迁移**不能保证**目标软件能无缝续聊，见 [已知限制](../reference/limitations.md)。

## 7. 不满意就撤销

```bash
python3 app/cli.py history
python3 app/cli.py undo <操作ID>
```

`history` 列出每次写入的操作 ID。`undo` 删掉这次新建的文件、截回被追加的索引；如果新建的文件在写入后又被改过，默认保留，确认要删再加 `--force`。

## 一次迁移很多条

先预演，再确认：

```bash
python3 app/cli.py batch codex --to claude --filter 关键词           # 只预演
python3 app/cli.py batch codex --to claude --filter 关键词 --yes     # 实际写入
```

目标里已经有同一来源的迁移结果时，默认跳过（`--on-conflict skip`），可改成 `new`（另建新 id）或 `fail`（立即停止）。

## 不想敲命令

网页界面做同样的事：`python3 app/cli.py serve`，按 [网页工作流](web-workflow.md) 操作。
