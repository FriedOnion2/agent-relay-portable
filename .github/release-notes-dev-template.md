> **滚动开发版**：每次合并到 `main` 自动重建，旧的开发版会被替换，始终只有这一个。内容可能不稳定，需要稳定版请到 [Releases](https://github.com/{repo}/releases) 选择不带 Pre-release 标记的版本。

对应提交：[`{sha}`](https://github.com/{repo}/commit/{sha})

## 下载

下载 **`AgentRelay-{tag}-universal.zip`**，完整解压后按当前设备运行启动器。一个总包内置 Windows x64、macOS（Apple Silicon / Intel）与 Linux x64 运行时，**无需另装 Python / Node.js，首次启动不联网**。GitHub 自动生成的 Source code 压缩包是开发源码，普通用户不需要。

| 设备 | 启动入口 | 要求 |
|---|---|---|
| Windows | `启动_AgentRelay.bat` | Windows 10/11 x64 |
| macOS | `AgentRelay.app` 或 `bash 启动_AgentRelay.command` | Apple Silicon：macOS 14+；Intel：macOS 15+（未经 Apple 公证，处理方式见包内 `开始使用.txt`） |
| Linux | `bash 启动_AgentRelay.sh` | Ubuntu 22.04+ / glibc 2.35+ x64 |

## 校验

```sh
sha256sum -c SHA256SUMS.txt                                   # 校验值
gh attestation verify AgentRelay-{tag}-universal.zip --repo {repo}   # 构建来源证明
```

目标软件的实际续聊、依赖与设备权限仍需自行核对，详见 [当前限制](https://github.com/{repo}/blob/{ref}/docs/limitations.md)。

---

## 自上一个正式版以来的更新（未发布）

{changelog}
