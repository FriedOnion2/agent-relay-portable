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

## 迁移后核对：会话对比

```bash
python app/cli.py diff claude <源会话id> codex <迁移后的会话id>
```

按顺序对齐两个会话里用户 / 助手的正文、工具调用参数和工具结果（空白差异忽略；工具名不参与比较，因为迁移时会按目标软件改名；系统上下文和思考只在数量差里体现）。输出一致项数、仅一侧有的内容样例、被改动的条目、各类数量差和相似度；完全一致退出码为 0，否则为 1。迁移时选了「不含思考」或「脱敏」，对应位置自然会显示为差异或改动，这是预期。
## 敏感信息扫描与脱敏

历史会话里常混着粘贴过的 API 密钥、令牌或口令，迁移会把它们原样复制到另一个软件的目录。预览现在会统计并提示：

- 识别：OpenAI / Anthropic / GitHub / AWS / Google / Slack / Stripe / 腾讯云 / 阿里云密钥、JWT、私钥块、`Bearer` 令牌、URL 里的 `user:pass@`，以及 `password=`、`api_key:`、`密码：` 这类带真实值的赋值（`${VAR}`、`<your-key>`、`xxxx`、环境变量读取等占位写法会被忽略）。
- 报告里只有类型、位置（第几轮第几块的哪个字段）和长度，**不包含密钥的任何片段**，连掩码也不给，避免扫描结果本身被写进日志或截图。预览 JSON 的 `findings` 字段含按类型的计数与位置。
- 单独扫描：`python app/cli.py scan <agent> <id>`，发现时退出码为 2，可接入脚本。
- 脱敏：`transfer` / `export` 加 `--redact-secrets`，API 传 `redact_secrets: true`。命中内容被替换为 `[REDACTED:类型]`；该选项参与预览令牌，改选项后必须重新预览。默认不脱敏，行为与之前一致。

扫描基于规则，只覆盖正文、思考、工具参数与工具结果，不保证发现全部敏感信息，不能代替安全审计。已泄露的密钥请直接作废轮换。

## 批量迁移与重复迁移

```bash
# 预演：看会迁移哪些、哪些会被跳过（不写入）
python app/cli.py batch claude --to codex --filter myproject
# 确认无误后实际执行
python app/cli.py batch claude --to codex --filter myproject --yes
# 指定会话、统一落到某个项目目录、顺便脱敏
python app/cli.py batch claude --to codex --ids a1,b2 --cwd ~/work/app --redact-secrets --yes
```

- 默认只预演；必须加 `--yes` 才写入。一次最多处理 500 条（`--limit`）。
- 目标会话 ID 由「来源 + 源会话 ID + 目标」确定性派生，所以重复执行同一条命令是幂等的：已迁移的会话会按 `--on-conflict` 处理——`skip`（默认）跳过；`new` 另建一个新 ID 的副本；`fail` 遇到即停止。
- 单条失败（源不可读、内容为空等）只记录，不影响其余；加 `--stop-on-error` 可改为遇错即停。退出码：全部成功 0，存在失败 1。
- 与单条迁移不同，批量没有逐条的预览令牌：先预演、再 `--yes` 的两步就是确认流程。需要逐条核对保真度时仍用 `transfer --dry-run`。
- 只对「转换迁移」（`transfer` 同款）生效；原生迁移（保留原始格式）仍逐条进行。
## 操作记录与撤销

每次写入目标软件的迁移或恢复（跨软件迁移、Windows ↔ Ubuntu 原生迁移、存储包恢复）都会在 `logs/operations.jsonl` 记一条：来源、目标、会话、写入了哪些文件。
日志目录可用环境变量 `RELAY_LOG_HOME` 修改；写日志失败不会影响迁移本身。

```sh
python app/cli.py history            # 查看最近的操作，--json 输出机器可读结果
python app/cli.py undo <操作ID>      # 撤销
```

撤销做三件事：删除这次**新建**的会话文件；把被**追加**内容的索引文件（例如 Codex 的 `session_index.jsonl`）截回原长度；删除因此变空的新建目录。
它只动「仍和写入时一模一样」的文件：如果你在目标软件里已经续聊、文件被改过，这个文件会被**保留**并说明原因，
确认可以丢弃再加 `--force`。索引之外被改写（不是追加）的已有文件、或目标目录文件过多（超过 30 万个）时，这条操作会标为不可自动撤销。
撤销只处理记录里的路径，并且路径必须在记录的目标目录之内。同时进行两次写入时，记录可能互相混入，请逐次操作。

## 敏感信息扫描与脱敏

历史会话里常混着粘贴过的 API 密钥、令牌或口令，迁移会把它们原样复制到另一个软件的目录。预览现在会统计并提示：

- 识别：OpenAI / Anthropic / GitHub / AWS / Google / Slack / Stripe / 腾讯云 / 阿里云密钥、JWT、私钥块、`Bearer` 令牌、URL 里的 `user:pass@`，以及 `password=`、`api_key:`、`密码：` 这类带真实值的赋值（`${VAR}`、`<your-key>`、`xxxx`、环境变量读取等占位写法会被忽略）。
- 报告里只有类型、位置（第几轮第几块的哪个字段）和长度，**不包含密钥的任何片段**，连掩码也不给，避免扫描结果本身被写进日志或截图。预览 JSON 的 `findings` 字段含按类型的计数与位置。
- 单独扫描：`python app/cli.py scan <agent> <id>`，发现时退出码为 2，可接入脚本。
- 脱敏：`transfer` / `export` 加 `--redact-secrets`，API 传 `redact_secrets: true`。命中内容被替换为 `[REDACTED:类型]`；该选项参与预览令牌，改选项后必须重新预览。默认不脱敏，行为与之前一致。

扫描基于规则，只覆盖正文、思考、工具参数与工具结果，不保证发现全部敏感信息，不能代替安全审计。已泄露的密钥请直接作废轮换。
