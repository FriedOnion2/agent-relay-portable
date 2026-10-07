# AgentRelay Portable

本地会话迁移工具，在 **Claude Code、OpenAI Codex、DSH / WorkBuddy** 之间转换对话记录，
也可导出 Markdown 交接文档。程序只使用 Python 标准库，无需安装第三方依赖。

## 快速启动

- **Windows**：双击 `启动_AgentRelay.bat`。
- **macOS**：首次在项目目录运行 `bash Mac首次准备.command`，然后双击 `AgentRelay.app` 或 `启动_AgentRelay.command`。
- **Linux / 命令行**：运行 `python3 app/cli.py serve`。

需要 Python **3.8 或更新版本**。Windows 可将完整的嵌入式 Python 解压到 `runtime/python/`。
也可通过 `RELAY_PYTHON` 指定解释器。默认网址为 `http://127.0.0.1:8745/`。

```sh
python app/cli.py doctor
python app/cli.py list codex
python app/cli.py transfer codex <session-id> --to claude
python app/cli.py export codex <session-id> -o handoff.md
```

详细步骤见 [使用说明](使用说明.md)。

## 配置与数据

复制 `config.example.json` 为 `config.json` 后可配置会话根目录、端口和是否打开浏览器。
目录覆盖优先级为：配置文件 → `RELAY_<AGENT>_HOME` → agent 环境变量 → 当前用户默认目录。

程序只监听本机地址。转换读取源会话，并向目标 agent 的会话目录写入新文件；
同名目标不会被覆盖。日志、本机配置、Python 运行时、缓存和真实会话数据不应上传 GitHub，
仓库已提供对应忽略规则。

## 验证

```sh
python -m unittest discover -s tests -v
node --test tests/web.test.cjs
```

Python 测试覆盖六个迁移方向的文本和工具顺序、Claude 父记录链、长消息、截断标记、
UUIDv7、配置以及 HTTP 接口。Node.js 仅用于网页回归测试，运行应用不需要 Node.js。
所有测试均使用临时合成数据，不修改真实会话目录。

GitHub Actions 在 Windows、Linux 和 macOS 上运行测试，包含 Python 3.8、3.12 和 3.14；
macOS 的 Python 3.8 因 runner 架构限制不在矩阵中。

## 当前限制

- 单个源文件最多读取 32MB，超出时显示截断提示；不会完整迁移超出部分。
- 图片、加密思考及厂商特有元数据不能保证完整保留。
- 工具名转换不会安装目标工具，也不会转换各家工具的参数协议。
- Codex Desktop 可能需要自己的数据库索引；生成 JSONL 不保证会话自动出现在桌面列表。
- 目标 agent 的格式可能变化，程序回读测试通过不能替代目标 agent 的实际续聊验证。
- macOS 的应用启动、Gatekeeper 和原生会话续聊仍需在真实 Mac 上验证。
