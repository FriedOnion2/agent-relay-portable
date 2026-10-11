# 命令行参考

入口是 `app/cli.py`，三个平台用法一致（Windows 上把 `python3` 换成 `python`）：

```bash
python3 app/cli.py <命令> [参数]
python3 app/cli.py <命令> --help      # 看该命令的全部参数
```

下面按用途列出全部命令。完整参数以 `--help` 为准；这里只写最常用的和容易踩坑的。

## 输出语言

命令行输出（含 `--help` 和错误信息）默认是中文。需要英文时，在子命令**之前**加 `--lang en`，或设置环境变量 `RELAY_LANG=en`：

```bash
python3 app/cli.py --lang en sources
RELAY_LANG=en python3 app/cli.py doctor
```

`--lang` 优先于环境变量；写了不认识的语言会回退到中文。语言**不会**从系统区域设置推断，所以已有脚本的输出不会变。`--json` 输出不受影响；`export` 生成的 Markdown 跟随所选语言。

## 来源名

`list`、`show`、`transfer` 等命令里的「来源」取下列之一：

| 名称 | 含义 |
|---|---|
| `workbuddy` `dsh` `codebuddy` `claude` `claude_sdk` `codex` `yuanbao` | 本机上对应软件的会话 |
| `windows_<名称>` | 已挂载的 Windows 分区里的同款会话（Ubuntu 双系统，只读） |
| `ubuntu_<名称>` | Windows 可访问的 Ubuntu 用户目录备份里的会话（只读） |

`yuanbao` 只能由 `import-yuanbao` 导入的导出文件提供。**迁移目标**（`--to`）只支持 `workbuddy`、`dsh`、`claude`、`codex`；CodeBuddy、Claude Agent SDK、元宝目前只能读取和导出。

会话 id 用 `list` 输出里的完整 id（CodeBuddy 和 DSH 的 id 可能带路径前缀）；简写匹配到多个会话时会报错。

## 查看环境与会话

| 命令 | 作用 |
|---|---|
| `doctor` | 环境体检：Python、各来源的会话目录与数量。换机器后先跑这个 |
| `sources [--json]` | 各来源是否可用、有多少会话 |
| `list <来源> [-f 关键词] [-n 数量] [--json]` | 列出会话；`-f` 按标题、目录、id 过滤 |
| `show <来源> <id> [--role …] [--head N] [--max-chars N] [--json]` | 查看内容 |
| `health [--output 目录]` | 用临时合成样本自检；**不验证**真实客户端能否续聊 |
| `device-config [--agent 名称] [--home 目录]` | 查看设备检查；设置本机某个软件的会话根目录（省略 `--home` 则恢复自动探测），不影响其他设备 |

## 迁移与核对

| 命令 | 作用 |
|---|---|
| `transfer <来源> <id> --to <目标>` | 迁移单个会话到另一个软件 |
| `batch <来源> --to <目标>` | 批量迁移；**默认只预演，加 `--yes` 才写入** |
| `diff <来源> <id> <来源2> <id2> [--max N] [--json]` | 比较两个会话（迁移后核对有没有丢内容）。有差异时退出码为 1 |
| `scan <来源> <id> [--json]` | 扫描疑似密钥、令牌、口令；只报类型、位置、长度，不显示内容 |
| `history [--limit N] [--json]` | 列出写入目标软件的操作记录 |
| `undo <操作ID> [--force]` | 撤销一次写入：删掉新建文件、截回被追加的索引。写入后又被改过的文件默认保留，`--force` 才一并删除 |

`transfer` 常用参数：

| 参数 | 说明 |
|---|---|
| `--cwd 目录` | 目标工作目录，默认沿用源会话的目录。跨系统（Windows 来源、Mac 运行）时必须改成当前机器上的绝对路径 |
| `--session-id ID` | 指定新会话 id；不会覆盖同名会话，id 不能含路径分隔符 |
| `--title 标题` | 覆盖标题 |
| `--no-thinking` | 不迁移思考过程 |
| `--keep-tool-names` | 不做工具名互译 |
| `--redact-secrets` | 写入前把疑似密钥替换成 `[REDACTED:类型]` |
| `--dry-run` | 只出保真度报告，不写入。报告里有 `token` |
| `--preview-token 令牌` | 执行已确认的预览；这期间来源或选项变了就拒绝 |

`batch` 另有 `--ids a,b,c`（或用 `--filter` 选取）、`--limit`（上限 500）、`--on-conflict skip|new|fail`（目标里已有同一来源的迁移结果时的处理，默认 `skip`）、`--stop-on-error`。

## 导出与导入文件

| 命令 | 作用 |
|---|---|
| `export <来源> <id> [-o 文件]` | 导出成 Markdown 交接文档；`--no-thinking`、`--no-tools`、`--max-chars N`、`--redact-secrets` 可裁剪内容 |
| `import-yuanbao <JSON 文件>` | 导入元宝导出的 JSON（不读取也不修改元宝客户端的数据库） |

## Windows ↔ Ubuntu 原生搬迁

保留原生记录，详见 [Ubuntu 双系统](../guide/ubuntu-dual-boot.md)。这几条都支持 `--dry-run` / `--preview-token` / `--json`。

| 命令 | 作用 |
|---|---|
| `windows-users` | 探测已挂载 Windows 分区里的用户目录 |
| `windows-use <路径>` / `--clear` | 保存 / 清除 Windows 用户目录选择 |
| `import-windows <来源> <id> --cwd <Ubuntu 项目目录>` | Windows 会话导入到 Ubuntu 对应软件 |
| `export-windows <来源> <id> --cwd <D:\项目> --project-path <挂载路径>` | Ubuntu 会话写入已挂载的 Windows 对应软件 |
| `ubuntu-use <路径>` / `--clear` | 保存 / 清除 Windows 可访问的 Ubuntu 用户目录备份 |
| `import-ubuntu <来源> <id> --cwd <D:\项目>` | Windows 导入 Ubuntu 备份里的原生会话 |

很多读取类命令还接受 `--windows-user` / `--ubuntu-user`，临时指定用户目录而不保存配置。

## 便携存储

详见 [便携存储](../guide/portable-storage.md)。

| 命令 | 作用 |
|---|---|
| `store-sessions <来源> [id …] [--all] [--storage 目录]` | 把会话按软件分类存成独立的包 |
| `stored-sessions [--agent 名称] [--storage 目录]` | 列出已存的会话包 |
| `restore-session <包> --cwd <目录> [--dry-run]` | 校验并恢复会话包到当前设备 |
| `skills <来源> [--skills-dir 目录]` | 列出 SKILL.md 技能目录 |
| `store-skills <来源> [路径 …] [--all] [--skills-dir 目录]` | 保存完整 Skill 目录 |
| `stored-skills [--agent 名称]` | 列出已存的 Skill 包 |
| `restore-skill <包> [--agent …] [--skills-dir 目录] [--name 新名]` | 校验并恢复；已有同名目录不覆盖 |

存储包**不加密**，请按需要自行保管。

## 搜索与 Skill 草稿

详见 [搜索与 Skill](../guide/search-and-skills.md)。

| 命令 | 作用 |
|---|---|
| `index [--source 来源] [--include-thinking] [--no-packages]` | 更新离线全文索引；思考内容默认不索引 |
| `search [关键词] [--source …] [--project …] [--tool …] [--after 日期] [--before 日期] [--limit N]` | 跨来源搜索，支持中文短词 |
| `indexed-session <key>` | 打开索引里缓存的会话，不读旧设备路径 |
| `extract-skills` | 从索引会话提炼待审核的 Skill 草稿（不调用模型） |
| `export-draft <Markdown> --directory <目录> --confirm` | 审核后导出已编辑草稿；同名不覆盖，不自动安装 |

## 服务与插件

| 命令 | 作用 |
|---|---|
| `serve [--host …] [--port N] [--no-browser]` | 启动网页界面，默认端口 8745，被占用时自动试后面 5 个 |
| `plugins [list\|enable\|disable\|check] [名称] [路径]` | 管理可信的社区读取插件；不会自动发现或执行代码，见 [编写插件](../dev/writing-a-plugin.md) |

## 退出码

| 退出码 | 情况 |
|---|---|
| 0 | 成功 |
| 1 | 出错（错误信息写到标准错误）；`diff` 发现内容不一致；`batch` 有条目失败；存储类命令失败。设置环境变量 `RELAY_DEBUG=1` 可看到完整堆栈 |
| 2 | `scan` 发现了疑似敏感信息（没发现时返回 0），方便在脚本里做拦截 |
| 130 | 用户按 Ctrl+C 取消 |
