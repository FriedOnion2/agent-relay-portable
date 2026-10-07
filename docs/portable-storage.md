# 按 Agent 存储并跨设备转移对话

对话包保存在项目目录 `storage/conversations/<agent>/<包ID>.zip`。把整个 `storage` 文件夹放到移动盘
或复制到另一台设备，启动那台设备上的 AgentRelay 即可恢复。也可以只复制一个 ZIP 包。
默认目录相对程序定位，不依赖原设备的盘符；`--storage` 或 `RELAY_STORAGE_HOME` 可以指定另一存储目录。

## 网页操作

1. 关闭正在写入该会话的 Agent，选择会话，点击“存储此会话”。
2. 结果显示按 Agent 分类保存的包路径。“对话存储”可列出所有已保存的包。
3. 将包复制到目标设备；在“对话存储”中选择包，或填写外部 ZIP 包路径。
4. 填写目标设备上已存在的项目目录，关闭目标 Agent，点击“恢复到对应软件”。

目标已有相同会话 ID 时拒绝覆盖。可填写新的 UUID，另存一份。恢复结果给出新文件路径、会话 ID 和
可用的恢复命令；软件中的真实续聊仍需核对。两端新增内容不自动合并。

## 命令行操作

```sh
# 一条或多条会话；ID 取 list 的输出，压缩 DSH 使用装有 zstandard 的 Python
python app/cli.py store-sessions codex <ID1> <ID2>
python app/cli.py store-sessions claude --all
python app/cli.py store-sessions windows_codebuddy <完整ID> --storage /media/alice/USB/relay-storage
python app/cli.py stored-sessions --agent codex

# 到目标设备后，使用该设备的真实项目路径
python app/cli.py restore-session <会话包.zip> --cwd <本机项目绝对路径>
python app/cli.py restore-session <会话包.zip> --cwd <本机项目绝对路径> --session-id 11111111-1111-4111-8111-111111111111
```

`--all` 每条会话独立成包，失败项会输出 errors 并返回非零状态；成功项的包仍保留。
会话包只恢复到对应 Agent；跨 Agent 转换继续使用 `transfer`，避免混淆两种行为。

## 包内容和边界

每包含原生记录、版本化 manifest、每个文件的字节数与 SHA-256：

- WorkBuddy / Claude / SDK / CodeBuddy CLI：对应原生 JSONL。
- Codex：rollout 和仅属于该会话的标题索引条目；不复制整库、不修改 Desktop SQLite。
- CodeBuddy IDE：会话 manifest、引用的消息文件及仅属于该会话的工作区索引条目。
- DSH：原生 canonical 日志，支持 v4 和可验证的 v0 seed 原生恢复；其他旧世代先由 DSH 升级。

恢复映射 cwd 等项目元数据，正文和历史工具参数保持原样。CodeBuddy IDE 需要目标项目中已存在的
唯一原生工作区：先在目标软件创建一条会话并关闭软件。SDK 仍使用 Claude 共享存储，不能凭日志判断创建者。
DSH 分叉先恢复父会话并保留 ID，子代理不单独恢复。附件与子代理旁路文件不包含在会话包中。

包不包含 Agent 登录配置或凭据；原生会话正文可能包含用户写入的敏感内容，包本身没有加密。
列表只读清单；恢复前才逐文件校验 SHA、CRC、大小和路径。符号链接、越界路径、重复大小写文件名、
未声明条目和损坏包会被拒绝，不向目标目录解压整个归档。
限制为单文件 32 MiB、每包原始文件总计 256 MiB、最多 4096 个文件；损坏或读取截断不会静默保存为完整包。
默认 `storage/` 已从 Git 忽略，发布代码不会附带你的对话包。

## Skill 跨设备存储

Skill 包保存在 `storage/skills/<agent>/<包ID>.zip`，保存 `SKILL.md`、脚本、references 和资源文件。
包的版本、SHA 校验与大小限制和会话包相同；脚本内容仅作为文件，不会执行其中的指令。

网页点击“Skill 存储”，选择 Agent，点击“查找 Skill”。未找到时填写实际 Skill 根目录，或直接填写
一个含 `SKILL.md` 的 Skill 目录，点击“存储 Skill”。复制包到目标设备后，在该面板选包、目标 Agent、
实际 Skill 根目录，点击“恢复 Skill”。已有同名目录（包括空目录）不会覆盖，填写新目录名可以另存一份。

```sh
python app/cli.py skills codex
python app/cli.py skills claude --skills-dir <实际Skill根目录>
python app/cli.py store-skills codex <包含SKILL.md的目录>
python app/cli.py store-skills claude --all --skills-dir <实际Skill根目录>
python app/cli.py stored-skills --agent claude

# 复制 ZIP 或整个 storage 后，在目标设备恢复
python app/cli.py restore-skill <Skill包.zip> --skills-dir <目标设备Skill根目录>
python app/cli.py restore-skill <Skill包.zip> --agent codex --skills-dir <目标Skill根目录> --name <新目录名>
```

默认扫描候选目录：Codex 的 `~/.agents/skills` 和 `~/.codex/skills`，Claude / SDK 的 `.claude/skills`，
其余 Agent 的 `<Agent根目录>/skills`。Codex 默认恢复到 `.agents/skills`；如使用旧目录、项目级 Skill
或插件管理位置，请通过 `--skills-dir` 指定。WorkBuddy / DSH / CodeBuddy 的目录是扫描候选，
不保证每个厂商版本都会从那里自动加载；实际发现位置以软件配置为准。
双系统来源支持 Windows / Ubuntu 用户目录中的相应候选路径。`--storage` 可使用同一移动盘存储目录。

不会收集 `.git`、虚拟环境、node_modules、缓存以及 `.env*`、`auth.json`、credentials、SSH 私钥名、
`.pem` / `.key` 文件；排除项在包清单和网页结果中列出。链接或 Windows reparse point 会被拒绝，
请指定实际文件目录；隐藏的内置 `.system` 目录不会被批量扫描。
复制时保留源脚本执行标记；带 shebang 的脚本在 Linux/macOS 恢复为可执行文件。
空目录不打包。Skill 内的绝对路径、依赖和各 Agent 的工具差异不会自动改写，必要时在目标软件中调整。
跨 Agent 恢复只复制标准目录内容，不保证其指令、权限、插件或工具接口兼容。
