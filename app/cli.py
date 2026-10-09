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
import re
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
from relay import plugins  # noqa: E402
plugins.configure(_CFG.get('plugins', []))

AGENTS = list(bootstrap.SOURCES)
READ_AGENTS = AGENTS + [prefix + k for prefix in ("windows_", "ubuntu_") for k in AGENTS]


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


def cmd_import_windows(args):
    from relay import native_import
    options = dict(session_id=args.session_id, dsh_compression=args.dsh_compression)
    if getattr(args, 'dry_run', False):
        from relay import preview
        _print_json(preview.native(args.agent, args.id, args.cmd, args.cwd, args.session_id,
                                   getattr(args, 'project_path', None), args.dsh_compression))
        return
    options['preview_token'] = getattr(args, 'preview_token', None)
    if args.cmd == "export-windows":
        options["project_path"] = args.project_path
    result = getattr(native_import, args.cmd.replace("-", "_"))(args.agent, args.id, args.cwd, **options)
    if args.json:
        _print_json(result)
        return
    native = result['to']['source']
    if native.startswith("windows_"):
        native = native[len("windows_"):]
    print(f"✓ 已迁到 {result['target_os']} {bootstrap.SOURCES[native][0]}")
    print(f"  新文件: {result['to']['path']}\n  原生会话 ID: {result['to']['native_id']}")
    if result["resume_command"]:
        print(f"  续聊命令: {result['resume_command']}")
    for note in result["notes"]:
        print(f"  · {note}")


def cmd_windows_use(args):
    import platform
    ubuntu = getattr(args, "cmd", "windows-use") == "ubuntu-use"
    from relay.windows import PROFILE_ENV as WINDOWS_ENV
    from relay.ubuntu import PROFILE_ENV as UBUNTU_ENV
    env = UBUNTU_ENV if ubuntu else WINDOWS_ENV
    key = "ubuntu_user_home" if ubuntu else "windows_user_home"
    label = "Ubuntu" if ubuntu else "Windows"
    if platform.system() != ("Windows" if ubuntu else "Linux"):
        raise ValueError("ubuntu-use 用于 Windows；windows-use 用于 Ubuntu / Linux")
    if args.clear and args.path:
        raise ValueError("目录与 --clear 不能同时使用")
    path = ""
    if not args.clear:
        if not args.path:
            raise ValueError("请填写用户目录，或用 --clear 清除选择")
        profile = Path(args.path).expanduser()
        if not profile.is_absolute() or not profile.is_dir():
            raise ValueError("请填写当前系统可访问且存在的用户目录绝对路径")
        if not os.access(profile, os.R_OK | os.X_OK):
            raise ValueError(f"{label} 用户目录没有读取权限")
        path = str(profile)
    config = bootstrap.config_path()
    # Preserve unknown keys and refuse to replace a malformed local config.
    cfg = json.loads(config.read_text(encoding="utf-8-sig")) if config.exists() else {}
    if not isinstance(cfg, dict):
        raise ValueError("config.json 不是 JSON 对象，请先修复配置")
    from relay import device
    local = device.read()
    local[key] = path
    device.write(local)
    os.environ[env] = path
    registry._CACHE.clear()
    print(f"已保存 {label} 用户目录：{path}" if path else f"已清除 {label} 用户目录选择")
    print("重启服务后生效；切换系统时忽略不适用的来源配置。")


def _print_json(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def cmd_storage(args):
    from relay import archive, session_store
    if args.cmd == "store-sessions":
        result = session_store.store_sessions(args.agent, args.ids, args.all, args.storage)
    elif args.cmd == "stored-sessions":
        result = {"ok":True, "packages":archive.list_packages(session_store.KIND, args.agent, args.storage)}
    else:
        if getattr(args, 'dry_run', False):
            from relay import preview
            result = preview.package(args.package, args.cwd, args.session_id, args.dsh_compression)
        else:
            result = session_store.restore_session(args.package, args.cwd, args.session_id, args.dsh_compression,
                                                   getattr(args, 'preview_token', None))
    _print_json(result)
    return 0 if result["ok"] else 1


def cmd_skill_storage(args):
    from relay import archive, skill_store
    if args.cmd == "skills":
        result = skill_store.discover_skills(args.agent, args.skills_dir)
    elif args.cmd == "store-skills":
        result = skill_store.store_skills(args.agent, args.paths, args.all, args.skills_dir, args.storage)
    elif args.cmd == "stored-skills":
        result = {"ok":True, "packages":archive.list_packages(skill_store.KIND, args.agent, args.storage)}
    else:
        result = skill_store.restore_skill(args.package, args.agent, args.skills_dir, args.name)
    _print_json(result)
    return 0 if result["ok"] else 1


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


def cmd_diff(args):
    from relay import diff
    res = diff.compare(registry.read_conversation(args.agent, args.id), registry.read_conversation(args.agent2, args.id2))
    if args.json:
        _print_json(res)
    else:
        a, b = res["a"], res["b"]
        print("A: %s %s（%d 项）\nB: %s %s（%d 项）" % (a["source"], a["id"], a["items"], b["source"], b["id"], b["items"]))
        print("一致 %d 项，仅 A 有 %d 项，仅 B 有 %d 项，相似度 %.1f%%" % (res["matched"], res["only_in_a"], res["only_in_b"], res["ratio"] * 100))
        for row in res["changed"][:args.max]:
            print("  改动  A: [%s/%s] %s\n        B: [%s/%s] %s" % (row["before"]["role"], row["before"]["kind"], row["before"]["text"],
                                                                row["after"]["role"], row["after"]["kind"], row["after"]["text"]))
        for label, key in (("仅 A", "only_in_a_samples"), ("仅 B", "only_in_b_samples")):
            for row in res[key][:args.max]:
                print("  %s  [%s/%s] %s" % (label, row["role"], row["kind"], row["text"]))
        delta = {k: v for k, v in res["stats_delta"].items() if v}
        if delta:
            print("数量差（B−A）：" + "，".join("%s %+d" % kv for kv in delta.items()))
        print("两份会话内容一致。" if res["identical"] else "存在差异。")
    if not res["identical"]:
        sys.exit(1)


def cmd_scan(args):
    from relay import sensitive
    result = sensitive.scan_conversation(registry.read_conversation(args.agent, args.id))
    if args.json:
        _print_json(result)
        return
    if not result["total"]:
        print("未发现疑似敏感信息（扫描不保证发现全部）。")
        return
    print("发现 %d 处疑似敏感信息：%s" % (result["total"], sensitive.summary_line(result)))
    for row in result["locations"][:50]:
        print("  第 %d 轮 块 %d %s  %s  长度 %d" % (row["turn"] + 1, row["block"] + 1, row["field"], row["kind"], row["length"]))
    print("迁移/导出时加 --redact-secrets 可将其替换为 [REDACTED:类型]。")
    sys.exit(2)


def cmd_batch(args):
    from relay import batch

    def show(index, total, item):
        if not args.json:
            print("[%d/%d] %-13s %s %s" % (index, total, item["status"], item["id"][:36], item.get("title", "")[:40]), flush=True)

    ids = [x for x in re.split(r"[,\s]+", args.ids or "") if x]
    res = batch.run(args.agent, args.to, ids=ids, keyword=args.filter, limit=args.limit, cwd=args.cwd,
                    on_conflict=args.on_conflict, redact_secrets=args.redact_secrets,
                    remap_tools=not args.keep_tool_names, include_thinking=not args.no_thinking,
                    dry_run=not args.yes, stop_on_error=args.stop_on_error, progress=show)
    if args.json:
        _print_json(res)
    else:
        label = "预演（未写入）" if res["dry_run"] else "完成"
        print("\n批量迁移%s：选中 %d，已迁移 %d，将迁移 %d，跳过 %d，失败 %d%s" % (
            label, res["selected"], res["migrated"], res["would-migrate"], res["skipped"], res["failed"],
            "，已提前停止" if res["stopped_early"] else ""))
        for item in res["items"]:
            if item["status"] == "failed":
                print("  失败 %s: %s" % (item["id"], item["error"]))
        if res["dry_run"]:
            print("确认无误后加 --yes 实际执行。")
    if not res["ok"]:
        sys.exit(1)


def cmd_export(args):
    md = registry.export_markdown(
        args.agent, args.id,
        include_thinking=not args.no_thinking,
        include_tools=not args.no_tools,
        max_text=args.max_chars,
        redact_secrets=args.redact_secrets,
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
    if args.dry_run:
        from relay import preview
        _print_json(preview.conversion(args.agent, args.id, args.to, args.cwd, args.session_id,
                                       not args.keep_tool_names, not args.no_thinking, args.title, args.redact_secrets))
        return
    res = registry.transfer(
        args.agent, args.id, args.to,
        cwd=args.cwd, session_id=args.session_id,
        remap_tools=not args.keep_tool_names,
        include_thinking=not args.no_thinking,
        new_title=args.title,
        preview_token=args.preview_token,
        redact_secrets=args.redact_secrets,
    )
    if args.json:
        _print_json(res)
        return
    f = res["from"]
    t = res["to"]
    st = res["stats"]
    print("✓ 已迁移")
    print(f"  来源: {f['source']}  {f['title'] or f['id']}")
    print(f"  目标: {t['source']}")
    print(f"  内容: {st['turns']} 轮 / 工具调用 {st['tool_call']} / 思考 {st['thinking']}")
    print(f"  新文件: {t['path']}")
    if res["truncated"]:
        print("  ⚠ 源文件过大，迁移内容可能不完整")
    if t["source"] == "claude":
        print(f"\n提示: 在该目录下执行 `claude --resume {os.path.basename(t['path']).split('.')[0]}` 继续会话")
    elif t["source"] == "dsh":
        sid = os.path.basename(os.path.dirname(t["path"]))
        print(f"\nDSH 会话 ID: {sid}")
        print("提示: 在 DSH 会话列表中选择导入会话，或使用支持 --resume 的 DSH profile 恢复该 ID。")


def cmd_serve(args):
    from server import run
    run(host=args.host, port=args.port,
        open_browser=not args.no_browser and bootstrap.effective_open_browser(_CFG))


def cmd_history(args):
    from relay import oplog
    rows = oplog.list_operations(args.limit)
    if args.json:
        _print_json({"ok": True, "operations": rows})
        return
    if not rows:
        print("还没有操作记录。")
        return
    for row in rows:
        state = "已撤销" if row["undone"] else ("失败" if row["status"] == "failed" else "完成")
        flag = "可撤销" if row["undoable"] else ("—" if row["undone"] else "不可撤销")
        print(f"{row['id']}  {row['time']}  {row['kind']:<15} {row['source'] or ''} → {row['target'] or ''}  [{state}/{flag}]")
        print(f"    {row['title'] or row['session'] or ''}  {row['path'] or ''}")


def cmd_undo(args):
    from relay import oplog
    result = oplog.undo(args.id, force=args.force)
    if args.json:
        _print_json(result)
        return
    print(f"✓ 已撤销 {args.id}：删除 {len(result['removed'])} 个文件，截回 {len(result['truncated'])} 个索引文件")
    for row in result["kept"]:
        print(f"  ⚠ 保留 {row['path']}：{row['reason']}")
    if not result["complete"]:
        print("  有文件被保留；确认可以丢弃后可加 --force 重试。")


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


def cmd_health(args):
    from relay import health
    result = health.report()
    if args.output:
        result['output'] = health.export(result, args.output)
    _print_json(result)
    return 0 if result['ok'] else 1


def cmd_device(args):
    from relay import device
    if args.agent:
        device.set_home(args.agent, args.home or '')
        bootstrap.apply_config(bootstrap.load_config())
        registry._CACHE.clear()
    _print_json(device.environment())


def cmd_plugins(args):
    if args.action == 'enable':
        if not args.name or not args.path:
            raise ValueError('启用需填写插件名与可信 Python 文件')
        result = plugins.enable(args.name, args.path)
    elif args.action == 'disable':
        if not args.name:
            raise ValueError('请填写插件名')
        result = plugins.disable(args.name)
    else:
        result = {'ok':True, 'enabled':list(plugins.entries.values()), 'errors':plugins.errors,
                  'note':'只启用可信插件；独立进程与超时不是安全沙箱。换设备需重新启用。'}
    _print_json(result)


def cmd_corpus(args):
    from relay.corpus import Corpus
    from relay.extraction import extract, export_draft
    store = Corpus()
    if args.cmd == 'index':
        result = store.update(sources=args.source, include_thinking=args.include_thinking, packages=not args.no_packages)
    elif args.cmd == 'search':
        result = store.search(args.query, source=args.source, project=args.project, tool=args.tool,
                              after=args.after, before=args.before, include_thinking=args.include_thinking,
                              limit=args.limit, offset=args.offset)
    elif args.cmd == 'indexed-session':
        result = dict(ok=True, **store.document(args.key, args.include_thinking))
    elif args.cmd == 'extract-skills':
        result = extract(store)
    else:
        path = Path(args.markdown)
        if path.stat().st_size > 1024 * 1024:
            raise ValueError('草稿超过 1 MiB')
        result = export_draft(path.read_text(encoding='utf-8-sig'), args.directory, args.confirm)
    _print_json(result)
    return 0 if result.get('ok',True) else 1


# DSH session ids are "<encoded project dir>/<session>" and the project dir is
# wrapped in "--...--", so argparse would take the id for an option.
DSH_ID_RE = re.compile(r"^--[^\s/]*--/\S+$")


class RelayParser(argparse.ArgumentParser):
    def _parse_optional(self, arg_string):
        if DSH_ID_RE.match(arg_string):
            return None
        return super()._parse_optional(arg_string)


def build_parser():
    read_agents = READ_AGENTS + list(plugins.entries)
    p = RelayParser(
        prog="relay",
        description="读取 WorkBuddy / DeepSeek Harness / CodeBuddy / Claude Code / Claude Agent SDK / Codex 会话",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    from relay import __version__
    p.add_argument("--version", action="version", version="%(prog)s " + __version__)
    sub = p.add_subparsers(dest="cmd", required=True)
    index = sub.add_parser('index', help='更新便携全文索引；默认不保存思考内容')
    index.add_argument('--source', action='append', choices=read_agents)
    index.add_argument('--include-thinking', action='store_true')
    index.add_argument('--no-packages', action='store_true')
    index.set_defaults(func=cmd_corpus)
    search = sub.add_parser('search', help='离线跨来源搜索便携索引，支持中文短词')
    search.add_argument('query', nargs='?', default='')
    for field in ('source','project','tool','after','before'):
        search.add_argument('--' + field, default='')
    search.add_argument('--include-thinking', action='store_true')
    search.add_argument('--limit',type=int,default=50)
    search.add_argument('--offset',type=int,default=0)
    search.set_defaults(func=cmd_corpus)
    document = sub.add_parser('indexed-session', help='打开缓存会话，不读取旧设备路径')
    document.add_argument('key')
    document.add_argument('--include-thinking',action='store_true')
    document.set_defaults(func=cmd_corpus)
    extract = sub.add_parser('extract-skills', help='从完整索引会话提炼待审核 Skill 草稿；不调用模型')
    extract.set_defaults(func=cmd_corpus)
    draft = sub.add_parser('export-draft', help='显式确认后导出已编辑草稿，同名不覆盖')
    draft.add_argument('markdown', help='已审核的 Markdown 文件')
    draft.add_argument('--directory',required=True,help='本机存在的导出父目录')
    draft.add_argument('--confirm',action='store_true',help='确认已审核草稿并写入')
    draft.set_defaults(func=cmd_corpus)

    p1 = sub.add_parser("sources", help="查看来源是否可用及会话数量")
    p1.add_argument("--json", action="store_true")
    p1.set_defaults(func=cmd_sources)

    p2 = sub.add_parser("list", help="列出某个 agent 的会话")
    p2.add_argument("agent", choices=read_agents)
    p2.add_argument("--filter", "-f", default="", help="按标题/目录/id 过滤")
    p2.add_argument("--limit", "-n", type=int, default=500)
    p2.add_argument("--json", action="store_true")
    p2.set_defaults(func=cmd_list)

    p3 = sub.add_parser("show", help="查看会话内容")
    p3.add_argument("agent", choices=read_agents)
    p3.add_argument("id")
    p3.add_argument("--role", choices=["user", "assistant", "system"], help="只看某个角色")
    p3.add_argument("--head", type=int, default=0, help="只显示前 N 轮，0=全部")
    p3.add_argument("--max-chars", type=int, default=2000, help="每轮最多显示多少字符")
    p3.add_argument("--json", action="store_true")
    p3.set_defaults(func=cmd_show)

    p4 = sub.add_parser("export", help="导出为 markdown 交接文档")
    p4.add_argument("agent", choices=read_agents)
    p4.add_argument("id")
    p4.add_argument("-o", "--output", help="输出文件，省略则打印到标准输出")
    p4.add_argument("--no-thinking", action="store_true", help="不包含思考过程")
    p4.add_argument("--no-tools", action="store_true", help="不包含工具调用")
    p4.add_argument("--max-chars", type=int, default=0, help="单段文本最大长度，0=不限")
    p4.add_argument("--redact-secrets", action="store_true", help="把疑似密钥/口令替换为 [REDACTED:类型]")
    p4.set_defaults(func=cmd_export)

    pd = sub.add_parser("diff", help="比较两个会话（迁移后核对有没有丢内容）")
    pd.add_argument("agent", choices=read_agents)
    pd.add_argument("id")
    pd.add_argument("agent2", choices=read_agents)
    pd.add_argument("id2")
    pd.add_argument("--max", type=int, default=20, help="最多显示多少条差异样例")
    pd.add_argument("--json", action="store_true")
    pd.set_defaults(func=cmd_diff)

    p4b = sub.add_parser("scan", help="扫描会话里的疑似密钥、令牌和口令（只显示类型、位置和长度）")
    p4b.add_argument("agent", choices=read_agents)
    p4b.add_argument("id")
    p4b.add_argument("--json", action="store_true")
    p4b.set_defaults(func=cmd_scan)

    p5 = sub.add_parser("transfer", help="迁移会话到另一个 agent")
    p5.add_argument("agent", choices=read_agents, help="来源 agent")
    p5.add_argument("id", help="源会话 id")
    p5.add_argument("--to", "-t", required=True, choices=registry.writable_keys(), help="支持写入的目标 agent")
    p5.add_argument("--cwd", help="写入到哪个工作目录（默认沿用源会话的目录）")
    p5.add_argument("--session-id", help="指定新会话 id（默认自动生成）")
    p5.add_argument("--title", help="覆盖标题")
    p5.add_argument("--keep-tool-names", action="store_true", help="不做工具名互译")
    p5.add_argument("--no-thinking", action="store_true", help="不迁移思考过程")
    p5.add_argument("--redact-secrets", action="store_true", help="写入前把疑似密钥/口令替换为 [REDACTED:类型]")
    p5.add_argument("--json", action="store_true")
    p5.add_argument('--dry-run', action='store_true', help='只预览保真度，不写入文件')
    p5.add_argument('--preview-token', help='执行已确认的预览；内容变化则拒绝')
    p5.set_defaults(func=cmd_transfer)

    pb = sub.add_parser("batch", help="批量迁移多个会话（默认只预演，加 --yes 才写入）")
    pb.add_argument("agent", choices=read_agents, help="来源 agent")
    pb.add_argument("--to", "-t", required=True, choices=registry.writable_keys(), help="支持写入的目标 agent")
    pb.add_argument("--ids", help="会话 id，逗号分隔；省略则按 --filter 选取")
    pb.add_argument("--filter", default="", help="按标题 / 目录 / id 关键字筛选")
    pb.add_argument("--limit", type=int, default=100, help="最多处理多少条（上限 500）")
    pb.add_argument("--cwd", help="统一写入到哪个工作目录（默认沿用各会话原目录）")
    pb.add_argument("--on-conflict", choices=("skip", "new", "fail"), default="skip",
                    help="目标里已有同一来源的迁移结果时：skip 跳过（默认）/ new 另建新 ID / fail 立即停止")
    pb.add_argument("--redact-secrets", action="store_true", help="写入前脱敏疑似密钥/口令")
    pb.add_argument("--keep-tool-names", action="store_true", help="不做工具名互译")
    pb.add_argument("--no-thinking", action="store_true", help="不迁移思考过程")
    pb.add_argument("--stop-on-error", action="store_true", help="任一条失败即停止")
    pb.add_argument("--yes", action="store_true", help="实际写入；不加则只预演")
    pb.add_argument("--json", action="store_true")
    pb.set_defaults(func=cmd_batch)

    history = sub.add_parser("history", help="查看写入目标软件的操作记录")
    history.add_argument("--limit", type=int, default=20)
    history.add_argument("--json", action="store_true")
    history.set_defaults(func=cmd_history)

    undo = sub.add_parser("undo", help="撤销一次迁移 / 恢复：删除新建文件、截回被追加的索引；写入后被改动的文件会保留")
    undo.add_argument("id", help="history 中显示的操作 ID")
    undo.add_argument("--force", action="store_true", help="连同写入后又被修改的新建文件一起删除")
    undo.add_argument("--json", action="store_true")
    undo.set_defaults(func=cmd_undo)

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
    p10 = sub.add_parser("import-windows", help="Windows 会话迁到 Ubuntu 对应软件，保留原生记录")
    p10.add_argument("agent", choices=READ_AGENTS)
    p10.add_argument("id", help="Windows 来源列表中的完整会话 ID")
    p10.add_argument("--cwd", required=True, help="存在的 Ubuntu 项目目录")
    p10.add_argument("--session-id", help="可选新 ID；默认保留 Windows 原生 ID，已有目标不会覆盖")
    p10.add_argument("--dsh-compression", choices=["zstd", "none"], default="zstd")
    p10.add_argument("--json", action="store_true")
    p10.add_argument('--dry-run', action='store_true')
    p10.add_argument('--preview-token')
    p10.set_defaults(func=cmd_import_windows)
    p11 = sub.add_parser("ubuntu-use", help="保存 Windows 可访问的 Ubuntu 用户目录备份")
    p11.add_argument("path", nargs="?")
    p11.add_argument("--clear", action="store_true")
    p11.set_defaults(func=cmd_windows_use)
    native_commands = []
    for name, help_text in (("export-windows", "Ubuntu 会话写入已挂载的 Windows 对应软件"),
                            ("import-ubuntu", "Windows 导入 Ubuntu 用户目录备份中的原生会话")):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("agent", choices=AGENTS if name == "export-windows" else READ_AGENTS)
        command.add_argument("id")
        command.add_argument("--cwd", required=True, help="Windows 绝对项目路径，如 D:\\project")
        if name == "export-windows":
            command.add_argument("--project-path", required=True, help="该项目在 Ubuntu 中的挂载路径")
        command.add_argument("--session-id")
        command.add_argument("--dsh-compression", choices=["zstd", "none"], default="zstd")
        command.add_argument("--json", action="store_true")
        command.add_argument('--dry-run', action='store_true')
        command.add_argument('--preview-token')
        command.set_defaults(func=cmd_import_windows)
        native_commands.append(command)
    store = sub.add_parser("store-sessions", help="按 Agent 保存原生会话包，复制到另一设备后恢复")
    store.add_argument("agent", choices=READ_AGENTS)
    store.add_argument("ids", nargs="*")
    store.add_argument("--all", action="store_true", help="保存该来源全部可读取会话，每条独立成包")
    store.add_argument("--storage", help="便携存储目录；默认项目 storage/")
    store.set_defaults(func=cmd_storage)
    stored = sub.add_parser("stored-sessions", help="列出按 Agent 保存的对话包")
    stored.add_argument("--agent", choices=AGENTS)
    stored.add_argument("--storage")
    stored.set_defaults(func=cmd_storage)
    restore = sub.add_parser("restore-session", help="校验并恢复会话包到当前设备的对应软件")
    restore.add_argument("package")
    restore.add_argument("--cwd", required=True)
    restore.add_argument("--session-id")
    restore.add_argument("--dsh-compression", choices=["zstd", "none"], default="zstd")
    restore.add_argument('--dry-run', action='store_true')
    restore.add_argument('--preview-token')
    restore.set_defaults(func=cmd_storage)
    skills = sub.add_parser("skills", help="列出 Agent 的 SKILL.md 技能目录（可指定实际路径）")
    skills.add_argument("agent", choices=READ_AGENTS)
    skills.add_argument("--skills-dir")
    skills.set_defaults(func=cmd_skill_storage)
    skill_store = sub.add_parser("store-skills", help="保存完整 Skill 目录，按 Agent 分类存储")
    skill_store.add_argument("agent", choices=READ_AGENTS)
    skill_store.add_argument("paths", nargs="*")
    skill_store.add_argument("--all", action="store_true")
    skill_store.add_argument("--skills-dir", help="配合 --all 指定实际 Skill 根目录")
    skill_store.add_argument("--storage")
    skill_store.set_defaults(func=cmd_skill_storage)
    stored_skills = sub.add_parser("stored-skills", help="列出已保存的 Skill 包")
    stored_skills.add_argument("--agent", choices=AGENTS)
    stored_skills.add_argument("--storage")
    stored_skills.set_defaults(func=cmd_skill_storage)
    skill_restore = sub.add_parser("restore-skill", help="校验并恢复 Skill 包；已有同名目录不覆盖")
    skill_restore.add_argument("package")
    skill_restore.add_argument("--agent", choices=READ_AGENTS, help="默认对应软件；可显式改分类")
    skill_restore.add_argument("--skills-dir", help="目标设备实际的 Skill 根目录")
    skill_restore.add_argument("--name", help="可选新目录名，保留已有 Skill")
    skill_restore.set_defaults(func=cmd_skill_storage)
    health = sub.add_parser('health', help='临时合成样本自检，不验证真实客户端续聊')
    health.add_argument('--output', help='导出 health.json 和静态 index.html')
    health.set_defaults(func=cmd_health)
    device = sub.add_parser('device-config', help='查看设备检查，设置本机 Agent 目录（不影响其他设备）')
    device.add_argument('--agent', choices=AGENTS)
    device.add_argument('--home', help='存在的本机目录；省略或空字符串则恢复自动探测')
    device.set_defaults(func=cmd_device)
    plugin = sub.add_parser('plugins', help='启用/禁用可信社区读取插件；不会自动发现执行代码')
    plugin.add_argument('action', choices=['list','enable','disable'], nargs='?', default='list')
    plugin.add_argument('name', nargs='?')
    plugin.add_argument('path', nargs='?')
    plugin.set_defaults(func=cmd_plugins)
    # Per-command override can be passed through the Linux launcher. Choices
    # are built before parsing, so recognize Windows source names explicitly.
    for command in (p1, p2, p3, p4, p5, p6, p7, p10, store, skills, skill_store, skill_restore, *native_commands):
        command.add_argument("--windows-user", help="临时选择 Windows 用户目录，不保存配置")
        command.add_argument("--ubuntu-user", help="临时选择 Windows 可访问的 Ubuntu 用户目录备份")

    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if getattr(args, "ubuntu_user", None):
            from relay.ubuntu import PROFILE_ENV as UBUNTU_ENV, selected_profile as selected_ubuntu
            import platform
            if platform.system() != "Windows":
                raise ValueError("--ubuntu-user 仅用于 Windows")
            os.environ[UBUNTU_ENV] = args.ubuntu_user
            _CFG["ubuntu_user_home"] = args.ubuntu_user
            selected_ubuntu()
            registry._CACHE.clear()
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
