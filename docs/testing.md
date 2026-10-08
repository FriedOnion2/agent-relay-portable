# 验证与测试

测试命令与验证范围。回到 [README](../README.md)。

## 验证

```sh
python -m pip install -r requirements-optional.txt
python -m unittest discover -s tests -v
node --test tests/web.test.cjs
```

截至 2026-10-08，第二阶段本机回归为 **140 项 Python 测试（Windows 上 4 项环境相关跳过）与 28 项网页测试**。
GitHub Actions 在 Windows、Ubuntu 和 macOS 上验证 Python 3.8、3.12、3.14，共 8 组；
macOS 不包含 Python 3.8。批量存储已用浏览器和临时样例实测，分别生成两条对话包与两个 Skill 包。
自动测试覆盖格式转换、存储包往返、完整性与冲突保护、端口占用、退出等待、异步列表及批量部分失败。
测试使用临时合成数据，不修改用户真实会话，也不执行 Skill 脚本。

可选实机验证：`python3 tests/macos_launch_smoke.py` 启动实际 `.app`，只读探测本机来源，
验证 HTTP 和退出接口后停止本次服务。DSH 官方原生验证可使用 `tests/dsh_native_smoke.mjs` / `tests/dsh_catalog_smoke.mjs`；运行参数见脚本头部。
Release 构建还在四类设备上验证内置依赖、DSH 导入、共享存储根目录、端口重试、HTTP 与退出，再发布同一个总包。
跨平台 CI 验证的是项目行为，厂商原生续聊、设备权限和挂载仍需在目标环境确认。

## 真实客户端冒烟测试

合成样本只能证明“我们自己能读回”。下面两个脚本用**真实客户端**检验导入结果，使用一次性临时目录，不触碰你自己的会话：

```sh
python scripts/smoke_codex_resume.py   # 需要 PATH 中有 codex：导入会话后用 codex app-server 的 thread/resume 重建 turn 与 items
python scripts/smoke_dsh_native.py     # 需要 dsh + node + zstandard：用 DSH 自带的会话持久化包列出、迁移（v0→v4）并恢复
```

未安装对应客户端时脚本以退出码 77 跳过，`python -m unittest discover -s tests` 中对应测试也会跳过。
`python scripts/smoke_all.py` 会依次运行所有冒烟测试，并把每个软件标记为通过、失败或跳过（附原因）。
GitHub Actions 的「Real client compatibility」工作流每周一并在相关代码变动时，在 Linux、macOS、Windows 上安装最新版 Codex 与 DSH 运行它们，用来尽早发现厂商格式变化；
运行摘要里会汇总出「软件 × 系统」支持表。这些测试都不发送模型请求、不需要登录。

| 软件 | 冒烟测试 | 说明 |
|---|---|---|
| Codex | 有（Linux / macOS / Windows） | 真实 `codex app-server` 的 `thread/resume` |
| DSH | 有（Linux / macOS / Windows） | DSH 自带会话包列出、迁移与恢复 |
| Claude Code | 跳过 | 续聊需要登录，无法无头驱动 |
| CodeBuddy | 跳过 | AgentRelay 只读取它，没有写入路径可测 |
| WorkBuddy | 跳过 | 桌面应用，无法在无界面环境启动 |

实际每个系统的通过情况以最近一次工作流运行摘要为准。

## 格式漂移告警

两个计划任务（每日的 `format-health`、每周的 `real-clients`）失败时，`alert` 作业会调用 `scripts/drift_issue.py`：

- 只在 **定时触发** 且上游作业失败时执行；手动触发和 push 触发由发起人自己看结果。
- 用标签 `format-drift` 找同名的未关闭 issue：没有就新建（`real-clients` 会附上软件×系统支持表），已有就追加评论，不会每周刷出新 issue。
- 问题修复后手动关闭该 issue；下次再失败会重新建一个。
- 需要工作流的 `issues: write` 权限（作业里已声明），不使用任何额外密钥。
