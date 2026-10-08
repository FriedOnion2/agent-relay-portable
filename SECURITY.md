# 安全策略 / Security Policy

AgentRelay 在本机读取、转换和写入 AI 编程助手的会话与 Skill，可能接触到对话内容、路径和凭据片段，因此我们认真对待安全问题。

## 受支持的版本

只维护 `main` 分支和最新的 Release。

## 报告漏洞

**请不要在公开 issue 里披露漏洞细节。**

请使用 GitHub 的私密漏洞报告：仓库页面 → **Security** → **Report a vulnerability**。
报告中请尽量包含：影响范围、复现步骤、涉及的来源软件与系统、最小化的（脱敏的）样本。**不要附带真实会话或凭据。**

我们会在收到报告后尽快确认，修复发布后再公开说明并致谢（如你愿意）。

## 关注范围

- 会话包 / Skill 包恢复中的路径穿越、符号链接、压缩炸弹
- 本地网页服务的跨站请求、DNS 重绑定、越权文件读取
- 命令行参数注入、对 `~` 之外目录的意外写入
- 插件加载与哈希校验的绕过

---

Please do not disclose vulnerabilities in public issues. Use GitHub's private vulnerability reporting
(**Security → Report a vulnerability**) and avoid attaching real conversations or credentials.
