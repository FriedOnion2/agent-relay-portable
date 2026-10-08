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

退出服务请点网页右上角「退出服务」或在终端按 Ctrl+C；关闭网页不会停止后台服务。目标软件的实际续聊、依赖与设备权限仍需自行核对，详见 [当前限制](https://github.com/{repo}/blob/{tag}/docs/limitations.md)。

---

## 更新内容

{changelog}
