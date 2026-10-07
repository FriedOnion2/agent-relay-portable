#!/usr/bin/env python3
"""AgentRelay 命令行入口。

    python cli.py sources
    python cli.py list codex
    python cli.py show dsh <id>
    python cli.py export dsh <id> -o /tmp/x.md
    python cli.py transfer codex <id> --to workbuddy
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Windows 控制台默认 GBK，中文标题会炸
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bootstrap  # noqa: E402  —— 便携版引导层：读 U 盘上的配置，按主机定位会话目录

_CFG = bootstrap.load_config()
bootstrap.apply_config(_CFG)

from relay import registry  # noqa: E402
from relay import ir  # noqa: E402

AGENTS = list(bootstrap.SOURCES)
READ_AGENTS = list(dict.fromkeys(AGENTS + ["windows_" + k for k in bootstrap.SOURCES]))


def cmd_windows_users(args):
    from relay.windows import discover_profiles
    rows = discover_profiles()
    if args.json:
        _print_json(rows)
        return
    for row in rows:
        print(f"{row['user']}  {row['home']}\n  来源：{', '.join(row['sources'])}")
    if not rows:
        print("未找到已挂载的 Windows 会话目录。请在 Ubuntu 文件管理器中打开 Windows 分区。")
    print('选择用户： python3 app/cli.py windows-use "/media/用户名/分区/Users/Windows用户名"')


def cmd_windows_use(args):
    from relay.windows import PROFILE_ENV
    import platform
    if platform.system() != "Linux":
        raise ValueError("windows-use 仅用于 Ubuntu / Linux 读取挂载的 Windows 分区")
    if args.clear and args.path:
        raise ValueError("目录与 --clear 不能同时使用")
    path = ""
    if not args.clear:
        if not args.path:
            raise ValueError("请填写 Windows 用户目录，或用 --clear 清除选择")
        profile = Path(args.path).expanduser()
        if not profile.is_absolute() or not profile.is_dir():
            raise ValueError("请填写已挂载且存在的 Windows 用户目录绝对路径（…/Users/用户名）")
        if not os.access(profile, os.R_OK | os.X_OK):
            raise ValueError("Windows 用户目录没有读取权限")
        path = str(profile)
    config = bootstrap.config_path()
    # Preserve unknown keys and refuse to replace a malformed local config.
    cfg = json.loads(config.read_text(encoding="utf-8-sig")) if config.exists() else {}
    if not isinstance(cfg, dict):
        raise ValueError("config.json 不是 JSON 对象，请先修复配置")
    cfg["windows_user_home"] = path
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=str(config.parent),
                                     prefix=".config-", suffix=".partial", delete=False) as f:
        temporary = Path(f.name)
        json.dump(cfg, f, ensure_ascii=False, indent=2)
        f.write("\n")
    try:
        os.replace(str(temporary), str(config))
    finally:
        temporary.unlink(missing_ok=True)
    os.environ[PROFILE_ENV] = path
    registry._CACHE.clear()
    print(f"已保存 Windows 只读用户目录：{path}" if path else "已清除 Windows 用户目录选择")
    print("重启服务后生效；Windows / macOS 启动时会忽略此项。")


def _print_json(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def cmd_sources(args):
    rows = registry.sources_info()
    if args.json:
        _print_json(rows)
        return
    print(f"{'agent':<10} {'状态':<8} {'会话数':>6}  目录")
    print("-" * 78)
    for r in rows:
        avail = ("可用" if r.get("can_write") else "只读") if r["available"] else "缺失"
        cnt = r.get("session_count", 0)
        print(f"{r['name']:<10} {avail:<8} {cnt:>6}  {r.get('home') or ''}")
        if r.get("error"):
            print(f"{'':<26}↳ {r['error']}")
        if r.get("read_note"):
            print(f"{'':<26}↳ {r['read_note']}")


def cmd_list(args):
    rows = registry.list_sessions(args.agent, keyword=args.filter, limit=args.limit)
    if args.json:
        _print_json(rows)
        return
    if not rows:
        print(f"（{args.agent} 没有匹配的会话）")
        return
    print(f"{'#':>3}  {'会话 id':<38} {'更新':<20} {'轮次':>4}  标题")
    print("-" * 100)
    for i, r in enumerate(rows, 1):
        sid = r["id"]
        print(f"{i:>3}  {sid:<38} {r['updated']:<20} {r['turns']:>4}  {r['title'][:50]}")
        if r.get("error"):
            print(f"     读取受限：{r['error']}")
    print(f"\n共 {len(rows)} 条")


def cmd_show(args):
    conv = registry.read_conversation(args.agent, args.id)
    if args.json:
        _print_json(conv.to_dict())
        return
    st = conv.stats()
    print(f"标题: {conv.title or '未命名会话'}")
    print(f"来源: {conv.source}   会话 id: {conv.id}")
    print(f"目录: {conv.cwd}")
    print(f"模型: {conv.model}")
    print(f"轮次: {st['turns']}（用户 {st['user']} / 助手 {st['assistant']}，"
          f"工具调用 {st['tool_call']}，思考 {st['thinking']}）")
    print(f"文件: {conv.path}")
    if conv.truncated:
        print("⚠ 源文件过大，仅读取了部分内容")
    for note in conv.meta.get("notes", []):
        print(f"读取说明: {note}")
    print("=" * 78)
    shown = 0
    for t in conv.turns:
        if args.role and t.role != args.role:
            continue
        txt = t.text()
        if not txt:
            continue
        label = {"user": "👤 用户", "assistant": "🤖 助手", "system": "⚙️ 系统"}.get(t.role, t.role)
        print(f"\n── {label} · {t.ts or ''} ──")
        print(ir.preview_text(txt, args.max_chars))
        shown += 1
        if args.head and shown >= args.head:
            print(f"\n（仅显示前 {args.head} 轮，加 --head 0 显示全部）")
            break


def cmd_export(args):
    md = registry.export_markdown(
        args.agent, args.id,
        include_thinking=not args.no_thinking,
        include_tools=not args.no_tools,
        max_text=args.max_chars,
    )
    if args.output:
        out = os.path.abspath(args.output)
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        with open(out, "w", encoding="utf-8", newline="\n") as f:
            f.write(md)
        print(f"已导出: {out}")
    else:
        print(md)


def cmd_transfer(args):
    res = registry.transfer(
        args.agent, args.id, args.to,
        cwd=args.cwd, session_id=args.session_id,
        remap_tools=not args.keep_tool_names,
        include_thinking=not args.no_thinking,
        new_title=args.title,
    )
    if args.json:
        _print_json(res)
        return
    f = res["from"]
    t = res["to"]
    st = res["stats"]
    print(f"✓ 已迁移")
    print(f"  来源: {f['source']}  {f['title'] or f['id']}")
    print(f"  目标: {t['source']}")
    print(f"  内容: {st['turns']} 轮 / 工具调用 {st['tool_call']} / 思考 {st['thinking']}")
    print(f"  新文件: {t['path']}")
    if res["truncated"]:
        print("  ⚠ 源文件过大，迁移内容可能不完整")
    if t["source"] == "claude":
        print(f"\n提示: 在该目录下执行 `claude --resume {os.path.basename(t['path']).split('.')[0]}` 继续会话")


def cmd_serve(args):
    from server import run
    run(host=args.host, port=args.port,
        open_browser=not args.no_browser and bootstrap.effective_open_browser(_CFG))


def cmd_doctor(args):
    """换机器后先跑这个：看 Python 找没找到、各个来源的目录在哪。"""
    code = bootstrap.print_report(_CFG)
    print()
    if code == 0:
        rows = registry.sources_info()
        print("  会话统计：")
        for r in rows:
            avail = "可用" if r["available"] else "缺失"
            print(f"    {r['name']:<8} {avail:<6} {r.get('session_count', 0):>4} 个会话")
        print()
        print("  下一步： python cli.py serve      （启动界面）")
        print("           python cli.py list codex （列出会话）")
    return code


def build_parser():
    p = argparse.ArgumentParser(
        prog="relay",
        description="读取 WorkBuddy / DeepSeek Harness / CodeBuddy / Claude Code / Claude Agent SDK / Codex 会话",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("sources", help="查看来源是否可用及会话数量")
    p1.add_argument("--json", action="store_true")
    p1.set_defaults(func=cmd_sources)

    p2 = sub.add_parser("list", help="列出某个 agent 的会话")
    p2.add_argument("agent", choices=READ_AGENTS)
    p2.add_argument("--filter", "-f", default="", help="按标题/目录/id 过滤")
    p2.add_argument("--limit", "-n", type=int, default=500)
    p2.add_argument("--json", action="store_true")
    p2.set_defaults(func=cmd_list)

    p3 = sub.add_parser("show", help="查看会话内容")
    p3.add_argument("agent", choices=READ_AGENTS)
    p3.add_argument("id")
    p3.add_argument("--role", choices=["user", "assistant", "system"], help="只看某个角色")
    p3.add_argument("--head", type=int, default=0, help="只显示前 N 轮，0=全部")
    p3.add_argument("--max-chars", type=int, default=2000, help="每轮最多显示多少字符")
    p3.add_argument("--json", action="store_true")
    p3.set_defaults(func=cmd_show)

    p4 = sub.add_parser("export", help="导出为 markdown 交接文档")
    p4.add_argument("agent", choices=READ_AGENTS)
    p4.add_argument("id")
    p4.add_argument("-o", "--output", help="输出文件，省略则打印到标准输出")
    p4.add_argument("--no-thinking", action="store_true", help="不包含思考过程")
    p4.add_argument("--no-tools", action="store_true", help="不包含工具调用")
    p4.add_argument("--max-chars", type=int, default=0, help="单段文本最大长度，0=不限")
    p4.set_defaults(func=cmd_export)

    p5 = sub.add_parser("transfer", help="迁移会话到另一个 agent")
    p5.add_argument("agent", choices=READ_AGENTS, help="来源 agent")
    p5.add_argument("id", help="源会话 id")
    p5.add_argument("--to", "-t", required=True, choices=registry.writable_keys(), help="支持写入的目标 agent")
    p5.add_argument("--cwd", help="写入到哪个工作目录（默认沿用源会话的目录）")
    p5.add_argument("--session-id", help="指定新会话 id（默认自动生成）")
    p5.add_argument("--title", help="覆盖标题")
    p5.add_argument("--keep-tool-names", action="store_true", help="不做工具名互译")
    p5.add_argument("--no-thinking", action="store_true", help="不迁移思考过程")
    p5.add_argument("--json", action="store_true")
    p5.set_defaults(func=cmd_transfer)

    p6 = sub.add_parser("doctor", help="环境体检（换机器后先跑这个）")
    p6.set_defaults(func=cmd_doctor)

    p7 = sub.add_parser("serve", help="启动 Web 界面")
    p7.add_argument("--host", default="127.0.0.1")
    p7.add_argument("--port", type=int, default=bootstrap.effective_port(_CFG))
    p7.add_argument("--no-browser", action="store_true")
    p7.set_defaults(func=cmd_serve)

    p8 = sub.add_parser("windows-users", help="探测已挂载 Windows 分区中的 Agent 用户目录")
    p8.add_argument("--json", action="store_true")
    p8.set_defaults(func=cmd_windows_users)
    p9 = sub.add_parser("windows-use", help="保存 Windows 用户目录选择（Linux 只读来源）")
    p9.add_argument("path", nargs="?")
    p9.add_argument("--clear", action="store_true")
    p9.set_defaults(func=cmd_windows_use)
    # Per-command override can be passed through the Linux launcher. Choices
    # are built before parsing, so recognize Windows source names explicitly.
    for command in (p1, p2, p3, p4, p5, p6, p7):
        command.add_argument("--windows-user", help="临时选择 Windows 用户目录，不保存配置")

    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if getattr(args, "windows_user", None):
            import platform
            from relay.windows import PROFILE_ENV, selected_profile
            if platform.system() != "Linux":
                raise ValueError("--windows-user 仅用于 Ubuntu / Linux")
            os.environ[PROFILE_ENV] = args.windows_user
            _CFG["windows_user_home"] = args.windows_user
            selected_profile()  # validate before using it
            registry._CACHE.clear()
        result = args.func(args)
        return result if isinstance(result, int) else 0
    except KeyboardInterrupt:
        print("\n已取消")
        return 130
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        if os.environ.get("RELAY_DEBUG"):
            import traceback
            traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
