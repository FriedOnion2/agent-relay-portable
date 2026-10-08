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
