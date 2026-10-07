# Adapter 接口与可信社区插件

API v1 复用 `relay.adapters.base.BaseAdapter` 与 `relay.ir.Conversation`。每个来源有独立 `name`、`label`、`home`、`api_version = 1` 和 `can_write`；`available()` 判断数据目录，`discover()` 返回 `SessionInfo`，`read(id)` 返回统一会话。`info()` 描述能力，不能以目录存在证明客户端已安装或可续聊。

内置来源分别声明读取、Markdown 导出、通用写入、原生打包/恢复、Skill 存储。`write()` 仅用于四个通用目标；原生恢复由专门模块检查格式、ID 冲突与索引并处理失败撤回。新增 writer 必须满足这些约定，不能直接把可写属性打开。

社区首版支持可信的单个 `.py` 文件，使用标准库与 `relay` 接口。它可以读取、导出和作为通用转换来源，不能通过 AgentRelay 原生打包、原生恢复、写入或管理 Skill。不自动扫描执行插件，不通过 pip 自动发现；源码和冻结程序都使用相同 worker 入口。

## 使用示例

在便携根目录创建 `example-conversations/`，放入 UTF-8 `.txt` 文件。仓库提供 [示例](../examples/plaintext_adapter.py)，Release 用户需单独下载这个示例文件。

```sh
python app/cli.py plugins enable plaintext examples/plaintext_adapter.py
python app/cli.py plugins list
python app/cli.py list plaintext
python app/cli.py export plaintext example.txt -o example.md
python app/cli.py plugins disable plaintext
```

冻结版将 `python app/cli.py` 换为实际 `AgentRelay.exe` / `AgentRelay` 可执行文件，并保持 `RELAY_PORTABLE_ROOT` 指向总包的绝对目录。插件启用或禁用后重启已有网页服务；单次 CLI 会加载最新本机配置。

启用时验证名称/API，记录执行字节的 SHA-256；文件改变必须检查并重新启用。便携根内插件使用相对引用，设备批准存入 `devices/<设备ID>.json`，换设备需要重新启用。共享 `config.json` 中的插件列表不会执行。禁止覆盖内置名称及 `windows_` / `ubuntu_` 前缀。

每次调用在独立子进程执行，默认 15 秒超时、返回及诊断各限 32 MiB，列表限 100000 条，插件文件限 1 MiB。失败会显示在对应来源，其他内置来源仍可用。插件不得在导入或读取时执行耗时任务、联网或修改会话；读取应限制文件大小，拒绝越界路径并报告不完整记录。

**独立进程不是安全沙箱。** 可信 Python 插件仍具备当前用户的文件和进程权限，能自行创建进程；超时终止 worker 不保证终止它自行创建的进程。只启用已经审阅的插件，不接收来源不明的代码。插件必须自带真实格式说明、合成样本和测试；内置 `health` 不执行社区插件。
