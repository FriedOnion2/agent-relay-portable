# 贡献指南 / Contributing

感谢你愿意改进 AgentRelay Portable！

## 开发环境

- Python 3.8+（CI 覆盖 3.8、3.12、3.14）；Node.js 22（仅网页脚本测试需要）。
- 可选依赖 `zstandard`（读写 DSH 压缩历史需要）。

```bash
python3 -m venv .venv && . .venv/bin/activate
python -m pip install -r requirements-optional.txt
python -m unittest discover -s tests          # Python 测试
node tests/web.test.cjs                       # 网页脚本测试
python app/cli.py health --output health-output   # 格式健康度自检
```

Ubuntu 也可以直接运行 `Ubuntu首次准备.sh` 建立隔离环境。

## 提交前请确认

1. **不要使用真实会话测试。** 用合成样本；测试写入请用 `RELAY_<AGENT>_HOME` / `RELAY_STORAGE_HOME` 指向临时目录，避免改动你自己的 `~/.claude`、`~/.codex` 等。
2. 新行为配套测试；修复 bug 的测试应当在旧代码上失败。
3. 本地测试全部通过，`ruff check .` 无报错。
4. 不提交 `config.json`、`storage/`、`index/`、日志或任何真实对话内容。

## 分支与 PR

- 从 `main` 切出分支（例如 `fix/xxx`、`feat/xxx`、`docs/xxx`），一个 PR 只做一件事。
- 提交信息建议使用 `type(scope): 概述`（`fix` / `feat` / `docs` / `test` / `chore`）。
- PR 描述写清动机、改动、测试方式，关联 issue 使用 `Fixes #N` 或 `Refs #N`。
- `main` 要求 CI 通过后合并，采用 squash 合并。

## 新增来源适配器

见 [docs/adapters.md](docs/adapters.md) 与 [examples/plaintext_adapter.py](examples/plaintext_adapter.py)。
新格式请同时补充 `docs/formats/` 下的格式说明与合成样本测试。

## 报告问题

使用 issue 模板；安全问题请看 [SECURITY.md](SECURITY.md)。

---

**English summary:** use synthetic fixtures (never real conversations), point `RELAY_*_HOME` at temp dirs,
add tests, run `python -m unittest discover -s tests` and `ruff check .`, keep PRs focused, and report
vulnerabilities privately (see SECURITY.md).
