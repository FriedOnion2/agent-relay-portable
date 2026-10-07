# 兼容状态与验证证据

网页「环境与兼容」检查本机 OS、CPU、数据目录写权限、剩余空间、实际运行时目录、Python 与 Zstandard。总包启动器启动时校验运行时压缩包 SHA-256；面板不会把已解压缓存标成完整性验证成功。只读介质可以查看，存储应在面板选择本机可写目录；保存设备配置需要可写的便携根目录。

支持 Windows 10/11 x64，Ubuntu 22.04+ / glibc 2.35+ x64，macOS ARM64 14+ / Intel 15+。四套运行时随一个总包提供，不依赖目标机 Python/Node。客户端安装、登录、Skill 外部依赖、挂载权限和厂商实际续聊仍需在目标设备检查。

## 样本看板

网页「运行格式自检」只在临时目录生成样本，不读取真实对话，不执行历史工具或调用模型。CLI 可导出 JSON 与静态 HTML：

```sh
python app/cli.py health --output health-output
```

[每日格式回归](https://github.com/FriedOnion2/agent-relay-portable/actions/workflows/format-health.yml) 在 Windows、Linux、Mac 各生成一份可下载 artifact（保留 30 天）。报告含时间、平台、样本版本、覆盖范围、失败信息；静态 HTML 可本地打开。第一版未部署 GitHub Pages。

| 来源 | `health` 样本范围 | 其他仓库回归覆盖 |
|---|---|---|
| WorkBuddy | writer 生成的 JSONL | 原生迁移、存包恢复与冲突 |
| DSH | writer 生成的 v0 seed / Zstd | v0–v4 读取、v4 原生迁移、官方格式目录验证入口 |
| CodeBuddy | CLI JSONL | IDE manifest/messages、工作区匹配与索引撤回 |
| Claude Code | writer 生成的 JSONL | 分支、工具块、原生迁移与路径映射 |
| Claude Agent SDK | Claude writer 生成的共享 JSONL | 官方 reader 主链语义、creator unknown、wire 记录拒绝 |
| Codex | writer 生成的 JSONL | 标题索引、原生迁移、存包与冲突 |

样本通过代表此次样本读取及原生文件回读成功。客户端版本无确切依据显示未知；最新版兼容性 `unknown`、实际续聊 `not-tested`，不会因回归通过变为正常。社区来源显示未测试。测试失败或缺依赖会使内置健康度失败，详情仍可在网页查看。

## 迁移预览

网页通用迁移、Windows/Ubuntu 对应软件迁移和存包恢复先列出保留、降级、丢弃、未知，再确认执行；取消不写入。工具名映射不转换工具参数；图片描述及思考文本不等于原生功能保留。原生迁移保留记录，但附件、子代理旁路文件、Desktop 索引和续聊状态并不包含在完整保证内。

CLI 对迁移命令及 `restore-session` 增加 `--dry-run`，只输出预览；将返回的 `token` 用 `--preview-token` 传给相同命令，源记录、选项或目标目录变化时拒绝执行。旧的直接 CLI/API 调用保持兼容；不传 token 就不校验预览一致性。

token 绑定 IR、可读取的原生源文件/IDE 引用消息及选项；存包预览完整验证包内 SHA-256 和声明。预览不会锁住第三方软件，执行前需停止源和目标软件继续写入。目标 ID 冲突、原生格式严格验证、IDE 工作区唯一匹配仍在执行时检查，预览成功不能证明恢复必然成功。
