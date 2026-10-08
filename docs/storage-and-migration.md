# 存储、迁移与预览

对话 / Skill 批量存储，跨软件与 Windows ↔ Ubuntu 迁移。回到 [README](../README.md)。

## 对话与 Skill 的批量存储

**对话：** 在左侧当前来源列表勾选会话，或点击 **全选当前列表**，然后点击 **存储所选对话**。
单项预览后的 **存储此会话** 仍可使用。在「对话存储」面板可指定存储目录、查看包和恢复。

**Skill：** 打开 **Skill 存储**，选择来源 Agent，点击 **查找 Skill**；未找到时填写实际 Skill 根目录。
勾选目录或点击 **全选当前列表**，再点击 **存储所选 Skill**。也可直接填写目录进行单项存储。

全选仅包含当前列表中可读取的项目；对话搜索过滤、来源切换或重新扫描 Skill 会清空选择。
每项独立成包，逐项保存并显示成功、失败数量；成功项取消勾选，失败项保留勾选以便重试。
网页批量存储不提供批量恢复，恢复仍按单包操作。

默认目录：

```text
storage/
├── conversations/<agent>/<包ID>.zip
└── skills/<agent>/<包ID>.zip
```

复制 ZIP 或整个 `storage` 文件夹到目标设备后，运行该设备上的 AgentRelay：

- **对话恢复：** 在「对话存储」选择包或填包路径，填写本机已存在的项目目录，恢复到对应软件。
- **Skill 恢复：** 在「Skill 存储」选择包、目标 Agent 和实际技能根目录，再点击「恢复 Skill」。

恢复前校验内容和路径；已有同 ID 对话或同名 Skill 不覆盖，可指定新 ID / 新目录名。
Skill 指令和脚本不会自动执行。包没有加密；应用不会将包上传 GitHub。
对话包用于对应软件的原生恢复，跨软件转换使用「迁移到目标」。具体格式和限制见 [便携存储说明](portable-storage.md)。

```sh
python app/cli.py store-sessions codex <ID1> <ID2>
python app/cli.py store-sessions codex --all
python app/cli.py stored-sessions --agent codex
python app/cli.py restore-session <会话包.zip> --cwd <本机项目绝对路径>
python app/cli.py skills codex
python app/cli.py store-skills codex --all --skills-dir <实际Skill根目录>
python app/cli.py stored-skills --agent codex
python app/cli.py restore-skill <Skill包.zip> --skills-dir <目标Skill根目录>
```

## 跨软件与双系统迁移

通用转换在网页选择来源会话和可写目标，按需填写本机目标项目目录，再点击「迁移到目标」。
向 DSH 导入时写入原生 v0 历史，不执行历史工具调用；跨系统的来源 cwd 应替换为本机绝对路径。

```sh
python app/cli.py list codex
python app/cli.py transfer codex <session-id> --to claude
python app/cli.py transfer codex <session-id> --to dsh
python app/cli.py export codex <session-id> -o handoff.md
```

**Ubuntu / Windows 双系统：** 在 Ubuntu 挂载 Windows 分区后执行：

```bash
python3 app/cli.py windows-users
python3 app/cli.py windows-use "/media/Ubuntu用户名/Windows分区/Users/Windows用户名"
bash 启动_AgentRelay.sh
```

网页同时保留 Ubuntu 来源，并新增六个 **Windows 只读来源**，可浏览、导出和迁出。
选择 Windows 会话、填写 Ubuntu 项目目录，点击 **“迁到 Ubuntu 对应软件”** 可保留原生记录迁入同款软件。
支持 WorkBuddy、Claude、SDK、Codex、DSH v4 / v0 seed、CodeBuddy CLI/IDE；IDE 需先创建本机工作区。
也可运行 `python3 app/cli.py import-windows codex <会话ID> --cwd /home/你的用户/项目`。
迁出时填写已存在的 Ubuntu 项目目录；不会自动改写历史中的 Windows 路径。
完整步骤和挂载排查见 [Ubuntu 双系统说明](ubuntu-dual-boot.md)。

**反向 Ubuntu → Windows：** 在 Ubuntu 来源选择会话，填写 Windows 项目路径和该项目在 Ubuntu
中的挂载路径，点击 **“迁到 Windows 对应软件”**。也可运行：

```bash
python3 app/cli.py export-windows codex <Ubuntu会话ID> --cwd 'D:\project' --project-path /mnt/data/project
```

Windows 中也可用 `python app/cli.py ubuntu-use "D:\UbuntuBackup\alice"` 选择可访问的 Ubuntu
用户目录备份，再用 `import-ubuntu codex <会话ID> --cwd "D:\project"` 导入。Windows 不会直接读取 ext4。
双向搬迁保留源文件、拒绝覆盖同 ID，不自动合并两边继续后的历史；新 ID 可保留另一份。
GitHub 同类项目与源码差异见 [原生会话迁移调研](session-migration-alternatives.md)。

## 敏感信息扫描与脱敏

历史会话里常混着粘贴过的 API 密钥、令牌或口令，迁移会把它们原样复制到另一个软件的目录。预览现在会统计并提示：

- 识别：OpenAI / Anthropic / GitHub / AWS / Google / Slack / Stripe / 腾讯云 / 阿里云密钥、JWT、私钥块、`Bearer` 令牌、URL 里的 `user:pass@`，以及 `password=`、`api_key:`、`密码：` 这类带真实值的赋值（`${VAR}`、`<your-key>`、`xxxx`、环境变量读取等占位写法会被忽略）。
- 报告里只有类型、位置（第几轮第几块的哪个字段）和长度，**不包含密钥的任何片段**，连掩码也不给，避免扫描结果本身被写进日志或截图。预览 JSON 的 `findings` 字段含按类型的计数与位置。
- 单独扫描：`python app/cli.py scan <agent> <id>`，发现时退出码为 2，可接入脚本。
- 脱敏：`transfer` / `export` 加 `--redact-secrets`，API 传 `redact_secrets: true`。命中内容被替换为 `[REDACTED:类型]`；该选项参与预览令牌，改选项后必须重新预览。默认不脱敏，行为与之前一致。

扫描基于规则，只覆盖正文、思考、工具参数与工具结果，不保证发现全部敏感信息，不能代替安全审计。已泄露的密钥请直接作废轮换。
