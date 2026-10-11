#!/usr/bin/env python3
"""AgentRelay 命令行入口。

    python cli.py sources
    python cli.py list codex
    python cli.py show dsh <id>
    python cli.py export dsh <id> -o /tmp/x.md
    python cli.py transfer codex <id> --to workbuddy
"""

from __future__ import annotations

from relay.messages import text as message_text, lang_text, normalize_lang, render, error_text

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

def _resolve_lang(argv=None):
    """--lang beats RELAY_LANG; the default stays zh so existing scripts keep their output."""
    argv = sys.argv[1:] if argv is None else list(argv)
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument('--lang', type=normalize_lang,
                        default=normalize_lang(os.environ.get('RELAY_LANG', '').strip().lower()))
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args, _ = parser.parse_known_args(argv)
    return args.lang


LANG = _resolve_lang()


def T(code, **params):
    return lang_text(LANG, 'msg.cli_' + code, **params)


def R(value):
    return render(value, LANG)


_CFG = bootstrap.load_config()
bootstrap.apply_config(_CFG)

from relay import registry  # noqa: E402
from relay import ir  # noqa: E402
from relay import plugins  # noqa: E402
plugins.configure(_CFG.get('plugins', []))

AGENTS = list(bootstrap.SOURCES)
READ_AGENTS = AGENTS + [prefix + k for prefix in ("windows_", "ubuntu_") for k in registry.cross_system_keys()]


def cmd_import_yuanbao(args):
    from relay import yuanbao
    _print_json(yuanbao.import_file(args.path))


def cmd_windows_users(args):
    from relay.windows import discover_profiles
    rows = discover_profiles()
    if args.json:
        _print_json(rows)
        return
    for row in rows:
        print(T('win_user_line', user=row['user'], home=row['home'], sources=', '.join(row['sources'])))
    if not rows:
        print(T('win_none'))
    print(T('win_pick'))


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
    print(T('imported', os=result['target_os'], name=bootstrap.SOURCES[native][0]))
    print(T('new_file', path=result['to']['path'], native_id=result['to']['native_id']))
    if result["resume_command"]:
        print(T('resume_cmd', command=result['resume_command']))
    for note in result["notes"]:
        print(f"  · {R(note)}")


def cmd_windows_use(args):
    import platform
    ubuntu = getattr(args, "cmd", "windows-use") == "ubuntu-use"
    from relay.windows import PROFILE_ENV as WINDOWS_ENV
    from relay.ubuntu import PROFILE_ENV as UBUNTU_ENV
    env = UBUNTU_ENV if ubuntu else WINDOWS_ENV
    key = "ubuntu_user_home" if ubuntu else "windows_user_home"
    label = "Ubuntu" if ubuntu else "Windows"
    if platform.system() != ("Windows" if ubuntu else "Linux"):
        raise ValueError(message_text('err.ubuntu_use_is_for_windows_windows_use_is_for_ubuntu_linux'))
    if args.clear and args.path:
        raise ValueError(message_text('err.a_directory_and_clear_cannot_be_used_together'))
    path = ""
    if not args.clear:
        if not args.path:
            raise ValueError(message_text('err.enter_a_user_directory_or_use_clear_to_clear_the_selection'))
        profile = Path(args.path).expanduser()
        if not profile.is_absolute() or not profile.is_dir():
            raise ValueError(message_text('err.enter_an_existing_absolute_user_directory_accessible_from_this_system'))
        if not os.access(profile, os.R_OK | os.X_OK):
            raise ValueError(message_text('err.the_label_user_directory_is_not_readable', label=label))
        path = str(profile)
    config = bootstrap.config_path()
    # Preserve unknown keys and refuse to replace a malformed local config.
    cfg = json.loads(config.read_text(encoding="utf-8-sig")) if config.exists() else {}
    if not isinstance(cfg, dict):
        raise ValueError(message_text('err.config_json_is_not_a_json_object_fix_the_configuration_first'))
    from relay import device
    local = device.read()
    local[key] = path
    device.write(local)
    os.environ[env] = path
    registry._CACHE.clear()
    print(T('use_saved', label=label, path=path) if path else T('use_cleared', label=label))
    print(T('use_restart'))


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
    print(T('sources_header', agent=T('col_agent'), status=T('col_status'), count=T('col_count'), home=T('col_home')))
    print("-" * 78)
    for r in rows:
        avail = (T('avail_ok') if r.get("can_write") else T('avail_ro')) if r["available"] else T('avail_missing')
        cnt = r.get("session_count", 0)
        print(T('sources_header', agent=r['name'], status=avail, count=cnt, home=r.get('home') or ''))
        if r.get("error"):
            print(f"{'':<26}↳ {R(r['error'])}")
        if r.get("read_note"):
            print(f"{'':<26}↳ {R(r['read_note'])}")


def cmd_list(args):
    rows = registry.list_sessions(args.agent, keyword=args.filter, limit=args.limit)
    if args.json:
        _print_json(rows)
        return
    if not rows:
        print(T('list_none', agent=args.agent))
        return
    print(f"{'#':>3}  {T('col_id'):<38} {T('col_updated'):<20} {T('col_turns'):>4}  {T('col_title')}")
    print("-" * 100)
    for i, r in enumerate(rows, 1):
        sid = r["id"]
        print(f"{i:>3}  {sid:<38} {r['updated']:<20} {r['turns']:>4}  {r['title'][:50]}")
        if r.get("variant_count", 1) > 1:
            print(T('list_variants', count=r['variant_count'], native_id=r['native_id']))
            print(T('list_file', path=r['path']))
        if r.get("error"):
            print(T('list_limited', error=R(r['error'])))
    print(T('list_total', count=len(rows)))


def cmd_show(args):
    conv = registry.read_conversation(args.agent, args.id)
    if args.json:
        _print_json(conv.to_dict())
        return
    st = conv.stats()
    print(T('show_title', title=conv.title or T('untitled')))
    print(T('show_source', source=conv.source, id=conv.id))
    print(T('show_cwd', cwd=conv.cwd))
    print(T('show_model', model=conv.model))
    print(T('show_turns', **st))
    print(T('show_file', path=conv.path))
    if conv.truncated:
        print(T('show_truncated'))
    for note in conv.meta.get("notes", []):
        print(T('show_note', note=R(note)))
    print("=" * 78)
    shown = 0
    for t in conv.turns:
        if args.role and t.role != args.role:
            continue
        txt = t.text()
        if not txt:
            continue
        label = T('role_' + t.role) if t.role in ("user", "assistant", "system") else t.role
        print(f"\n── {label} · {t.ts or ''} ──")
        print(ir.preview_text(txt, args.max_chars))
        shown += 1
        if args.head and shown >= args.head:
            print(T('show_head', count=args.head))
            break



def cmd_diff(args):
    from relay import diff
    res = diff.compare(registry.read_conversation(args.agent, args.id), registry.read_conversation(args.agent2, args.id2))
    if args.json:
        _print_json(res)
    else:
        a, b = res["a"], res["b"]
        print(T('diff_ab', a_source=a["source"], a_id=a["id"], a_items=a["items"], b_source=b["source"], b_id=b["id"], b_items=b["items"]))
        print(T('diff_summary', matched=res["matched"], only_a=res["only_in_a"], only_b=res["only_in_b"], ratio="%.1f" % (res["ratio"] * 100)))
        for row in res["changed"][:args.max]:
            print(T('diff_changed', before="[%s/%s] %s" % (row["before"]["role"], row["before"]["kind"], row["before"]["text"]),
                    after="[%s/%s] %s" % (row["after"]["role"], row["after"]["kind"], row["after"]["text"])))
        for label, key in ((T('diff_only_a'), "only_in_a_samples"), (T('diff_only_b'), "only_in_b_samples")):
            for row in res[key][:args.max]:
                print("  %s  [%s/%s] %s" % (label, row["role"], row["kind"], row["text"]))
        delta = {k: v for k, v in res["stats_delta"].items() if v}
        if delta:
            print(T('diff_delta', items=T('diff_sep').join("%s %+d" % kv for kv in delta.items())))
        print(T('diff_same') if res["identical"] else T('diff_differs'))
    if not res["identical"]:
        sys.exit(1)


def cmd_scan(args):
    from relay import sensitive
    result = sensitive.scan_conversation(registry.read_conversation(args.agent, args.id))
    if args.json:
        _print_json(result)
        return
    if not result["total"]:
        print(T('scan_clean'))
        return
    print(T('scan_found', total=result["total"], summary=R(sensitive.summary_line(result))))
    for row in result["locations"][:50]:
        print(T('scan_row', turn=row["turn"] + 1, block=row["block"] + 1, field=row["field"], kind=row["kind"], length=row["length"]))
    print(T('scan_hint'))
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
        label = T('batch_dry') if res["dry_run"] else T('batch_done')
        print(T('batch_summary', label=label, selected=res["selected"], migrated=res["migrated"], would=res["would-migrate"],
                skipped=res["skipped"], failed=res["failed"], stopped=T('batch_stopped') if res["stopped_early"] else ""))
        for item in res["items"]:
            if item["status"] == "failed":
                print(T('batch_failed', id=item["id"], error=R(item["error"])))
        if res["dry_run"]:
            print(T('batch_yes'))
    if not res["ok"]:
        sys.exit(1)


def cmd_export(args):
    md = registry.export_markdown(
        args.agent, args.id,
        include_thinking=not args.no_thinking,
        include_tools=not args.no_tools,
        max_text=args.max_chars,
        redact_secrets=args.redact_secrets,
        lang=LANG,
    )
    if args.output:
        out = os.path.abspath(args.output)
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        with open(out, "w", encoding="utf-8", newline="\n") as f:
            f.write(md)
        print(T('exported', path=out))
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
    print(T('tr_done'))
    print(T('tr_from', source=f['source'], title=f['title'] or f['id']))
    print(T('tr_to', source=t['source']))
    print(T('tr_content', **st))
    print(T('tr_file', path=t['path']))
    if res["truncated"]:
        print(T('tr_truncated'))
    if t["source"] == "claude":
        print(T('tr_claude', id=os.path.basename(t['path']).split('.')[0]))
    elif t["source"] == "dsh":
        sid = os.path.basename(os.path.dirname(t["path"]))
        print(T('tr_dsh_id', id=sid))
        print(T('tr_dsh_hint'))


def cmd_serve(args):
    from server import run
    run(host=args.host, port=args.port,
        open_browser=not args.no_browser and bootstrap.effective_open_browser(_CFG), lang=LANG)


def cmd_history(args):
    from relay import oplog
    rows = oplog.list_operations(args.limit)
    if args.json:
        _print_json({"ok": True, "operations": rows})
        return
    if not rows:
        print(T('hist_none'))
        return
    for row in rows:
        state = T('hist_undone') if row["undone"] else (T('hist_failed') if row["status"] == "failed" else T('hist_ok'))
        flag = T('hist_undoable') if row["undoable"] else ("—" if row["undone"] else T('hist_not_undoable'))
        print(f"{row['id']}  {row['time']}  {row['kind']:<15} {row['source'] or ''} → {row['target'] or ''}  [{state}/{flag}]")
        print(f"    {row['title'] or row['session'] or ''}  {row['path'] or ''}")


def cmd_undo(args):
    from relay import oplog
    result = oplog.undo(args.id, force=args.force)
    if args.json:
        _print_json(result)
        return
    print(T('undo_done', id=args.id, removed=len(result['removed']), truncated=len(result['truncated'])))
    for row in result["kept"]:
        print(T('undo_kept', path=row['path'], reason=R(row['reason'])))
    if not result["complete"]:
        print(T('undo_incomplete'))


def cmd_doctor(args):
    """换机器后先跑这个：看 Python 找没找到、各个来源的目录在哪。"""
    code = bootstrap.print_report(_CFG, LANG)
    print()
    if code == 0:
        rows = registry.sources_info()
        print(T('doc_stats'))
        for r in rows:
            avail = T('doc_ready') if r["available"] else T('doc_missing')
            print(T('doc_row', name=r['name'], avail=avail, count=r.get('session_count', 0)))
        print()
        print(T('doc_next'))
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
            raise ValueError(message_text('err.enabling_requires_a_plugin_name_and_trusted_python_file'))
        result = plugins.enable(args.name, args.path)
    elif args.action == 'disable':
        if not args.name:
            raise ValueError(message_text('err.enter_a_plugin_name'))
        result = plugins.disable(args.name)
    elif args.action == 'check':
        if not args.name or not args.path:
            raise ValueError(message_text('err.self_check_requires_a_plugin_name_and_python_file'))
        result = plugins.check(args.name, args.path)
        for row in result['checks']:
            print('%s %s%s' % ('✅' if row['ok'] else '❌', row['check'], '：' + row['detail'] if row['detail'] else ''))
        print(T('check_pass') if result['ok'] else T('check_fail'))
        return 0 if result['ok'] else 1
    else:
        result = {'ok':True, 'enabled':list(plugins.entries.values()), 'errors':plugins.errors,
                  'note':message_text('msg.cli_plugins_note')}
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
        result = extract(store, lang=LANG)
    else:
        path = Path(args.markdown)
        if path.stat().st_size > 1024 * 1024:
            raise ValueError(message_text('err.draft_exceeds_1_mib'))
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
        allow_abbrev=False,
        description=T('desc'),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    from relay import __version__
    p.add_argument("--version", action="version", version="%(prog)s " + __version__)
    p.add_argument("--lang", type=normalize_lang, default=LANG, metavar="{zh,en}", help=T('lang_help'))
    sub = p.add_subparsers(dest="cmd", required=True)
    yuanbao_import = sub.add_parser('import-yuanbao', help=T('h_import_yuanbao'))
    yuanbao_import.add_argument('path', help=T('h_import_yuanbao_path'))
    yuanbao_import.set_defaults(func=cmd_import_yuanbao)
    index = sub.add_parser('index', help=T('h_index'))
    index.add_argument('--source', action='append', choices=read_agents)
    index.add_argument('--include-thinking', action='store_true')
    index.add_argument('--no-packages', action='store_true')
    index.set_defaults(func=cmd_corpus)
    search = sub.add_parser('search', help=T('h_search'))
    search.add_argument('query', nargs='?', default='')
    for field in ('source','project','tool','after','before'):
        search.add_argument('--' + field, default='')
    search.add_argument('--include-thinking', action='store_true')
    search.add_argument('--limit',type=int,default=50)
    search.add_argument('--offset',type=int,default=0)
    search.set_defaults(func=cmd_corpus)
    document = sub.add_parser('indexed-session', help=T('h_indexed_session'))
    document.add_argument('key')
    document.add_argument('--include-thinking',action='store_true')
    document.set_defaults(func=cmd_corpus)
    extract = sub.add_parser('extract-skills', help=T('h_extract_skills'))
    extract.set_defaults(func=cmd_corpus)
    draft = sub.add_parser('export-draft', help=T('h_export_draft'))
    draft.add_argument('markdown', help=T('h_export_draft_md'))
    draft.add_argument('--directory',required=True,help=T('h_export_draft_dir'))
    draft.add_argument('--confirm',action='store_true',help=T('h_export_draft_confirm'))
    draft.set_defaults(func=cmd_corpus)

    p1 = sub.add_parser("sources", help=T('h_sources'))
    p1.add_argument("--json", action="store_true")
    p1.set_defaults(func=cmd_sources)

    p2 = sub.add_parser("list", help=T('h_list'))
    p2.add_argument("agent", choices=read_agents)
    p2.add_argument("--filter", "-f", default="", help=T('h_list_filter'))
    p2.add_argument("--limit", "-n", type=int, default=500)
    p2.add_argument("--json", action="store_true")
    p2.set_defaults(func=cmd_list)

    p3 = sub.add_parser("show", help=T('h_show'))
    p3.add_argument("agent", choices=read_agents)
    p3.add_argument("id")
    p3.add_argument("--role", choices=["user", "assistant", "system"], help=T('h_show_role'))
    p3.add_argument("--head", type=int, default=0, help=T('h_show_head'))
    p3.add_argument("--max-chars", type=int, default=2000, help=T('h_show_max'))
    p3.add_argument("--json", action="store_true")
    p3.set_defaults(func=cmd_show)

    p4 = sub.add_parser("export", help=T('h_export'))
    p4.add_argument("agent", choices=read_agents)
    p4.add_argument("id")
    p4.add_argument("-o", "--output", help=T('h_export_output'))
    p4.add_argument("--no-thinking", action="store_true", help=T('h_no_thinking_export'))
    p4.add_argument("--no-tools", action="store_true", help=T('h_no_tools'))
    p4.add_argument("--max-chars", type=int, default=0, help=T('h_export_max'))
    p4.add_argument("--redact-secrets", action="store_true", help=T('h_redact_export'))
    p4.set_defaults(func=cmd_export)

    p4b = sub.add_parser("scan", help=T('h_scan'))
    p4b.add_argument("agent", choices=read_agents)
    p4b.add_argument("id")
    p4b.add_argument("--json", action="store_true")
    p4b.set_defaults(func=cmd_scan)

    pd = sub.add_parser("diff", help=T('h_diff'))
    pd.add_argument("agent", choices=read_agents)
    pd.add_argument("id")
    pd.add_argument("agent2", choices=read_agents)
    pd.add_argument("id2")
    pd.add_argument("--max", type=int, default=20, help=T('h_diff_max'))
    pd.add_argument("--json", action="store_true")
    pd.set_defaults(func=cmd_diff)


    p5 = sub.add_parser("transfer", help=T('h_transfer'))
    p5.add_argument("agent", choices=read_agents, help=T('h_src_agent'))
    p5.add_argument("id", help=T('h_src_id'))
    p5.add_argument("--to", "-t", required=True, choices=registry.writable_keys(), help=T('h_to_agent'))
    p5.add_argument("--cwd", help=T('h_tr_cwd'))
    p5.add_argument("--session-id", help=T('h_tr_session_id'))
    p5.add_argument("--title", help=T('h_tr_title'))
    p5.add_argument("--keep-tool-names", action="store_true", help=T('h_keep_tools'))
    p5.add_argument("--no-thinking", action="store_true", help=T('h_no_thinking_tr'))
    p5.add_argument("--redact-secrets", action="store_true", help=T('h_redact_tr'))
    p5.add_argument("--json", action="store_true")
    p5.add_argument('--dry-run', action='store_true', help=T('h_dry_run_tr'))
    p5.add_argument('--preview-token', help=T('h_preview_token'))
    p5.set_defaults(func=cmd_transfer)

    history = sub.add_parser("history", help=T('h_history'))
    history.add_argument("--limit", type=int, default=20)
    history.add_argument("--json", action="store_true")
    history.set_defaults(func=cmd_history)

    undo = sub.add_parser("undo", help=T('h_undo'))
    undo.add_argument("id", help=T('h_undo_id'))
    undo.add_argument("--force", action="store_true", help=T('h_undo_force'))
    undo.add_argument("--json", action="store_true")
    undo.set_defaults(func=cmd_undo)

    pb = sub.add_parser("batch", help=T('h_batch'))
    pb.add_argument("agent", choices=read_agents, help=T('h_src_agent'))
    pb.add_argument("--to", "-t", required=True, choices=registry.writable_keys(), help=T('h_to_agent'))
    pb.add_argument("--ids", help=T('h_batch_ids'))
    pb.add_argument("--filter", default="", help=T('h_batch_filter'))
    pb.add_argument("--limit", type=int, default=100, help=T('h_batch_limit'))
    pb.add_argument("--cwd", help=T('h_batch_cwd'))
    pb.add_argument("--on-conflict", choices=("skip", "new", "fail"), default="skip",
                    help=T('h_batch_conflict'))
    pb.add_argument("--redact-secrets", action="store_true", help=T('h_batch_redact'))
    pb.add_argument("--keep-tool-names", action="store_true", help=T('h_keep_tools'))
    pb.add_argument("--no-thinking", action="store_true", help=T('h_no_thinking_tr'))
    pb.add_argument("--stop-on-error", action="store_true", help=T('h_batch_stop'))
    pb.add_argument("--yes", action="store_true", help=T('h_batch_yes'))
    pb.add_argument("--json", action="store_true")
    pb.set_defaults(func=cmd_batch)

    p6 = sub.add_parser("doctor", help=T('h_doctor'))
    p6.set_defaults(func=cmd_doctor)

    p7 = sub.add_parser("serve", help=T('h_serve'))
    p7.add_argument("--host", default="127.0.0.1")
    p7.add_argument("--port", type=int, default=bootstrap.effective_port(_CFG))
    p7.add_argument("--no-browser", action="store_true")
    p7.set_defaults(func=cmd_serve)

    p8 = sub.add_parser("windows-users", help=T('h_windows_users'))
    p8.add_argument("--json", action="store_true")
    p8.set_defaults(func=cmd_windows_users)
    p9 = sub.add_parser("windows-use", help=T('h_windows_use'))
    p9.add_argument("path", nargs="?")
    p9.add_argument("--clear", action="store_true")
    p9.set_defaults(func=cmd_windows_use)
    p10 = sub.add_parser("import-windows", help=T('h_import_windows'))
    p10.add_argument("agent", choices=[key for key in READ_AGENTS if key != 'yuanbao'])
    p10.add_argument("id", help=T('h_iw_id'))
    p10.add_argument("--cwd", required=True, help=T('h_iw_cwd'))
    p10.add_argument("--session-id", help=T('h_iw_session_id'))
    p10.add_argument("--dsh-compression", choices=["zstd", "none"], default="zstd")
    p10.add_argument("--json", action="store_true")
    p10.add_argument('--dry-run', action='store_true')
    p10.add_argument('--preview-token')
    p10.set_defaults(func=cmd_import_windows)
    p11 = sub.add_parser("ubuntu-use", help=T('h_ubuntu_use'))
    p11.add_argument("path", nargs="?")
    p11.add_argument("--clear", action="store_true")
    p11.set_defaults(func=cmd_windows_use)
    native_commands = []
    for name, help_text in (("export-windows", T('h_export_windows')),
                            ("import-ubuntu", T('h_import_ubuntu'))):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("agent", choices=registry.cross_system_keys() if name == "export-windows" else
                             [key for key in READ_AGENTS if key != 'yuanbao'])
        command.add_argument("id")
        command.add_argument("--cwd", required=True, help=T('h_ew_cwd'))
        if name == "export-windows":
            command.add_argument("--project-path", required=True, help=T('h_ew_project'))
        command.add_argument("--session-id")
        command.add_argument("--dsh-compression", choices=["zstd", "none"], default="zstd")
        command.add_argument("--json", action="store_true")
        command.add_argument('--dry-run', action='store_true')
        command.add_argument('--preview-token')
        command.set_defaults(func=cmd_import_windows)
        native_commands.append(command)
    store = sub.add_parser("store-sessions", help=T('h_store_sessions'))
    store.add_argument("agent", choices=READ_AGENTS)
    store.add_argument("ids", nargs="*")
    store.add_argument("--all", action="store_true", help=T('h_store_all'))
    store.add_argument("--storage", help=T('h_storage_dir'))
    store.set_defaults(func=cmd_storage)
    stored = sub.add_parser("stored-sessions", help=T('h_stored_sessions'))
    stored.add_argument("--agent", choices=AGENTS)
    stored.add_argument("--storage")
    stored.set_defaults(func=cmd_storage)
    restore = sub.add_parser("restore-session", help=T('h_restore_session'))
    restore.add_argument("package")
    restore.add_argument("--cwd", required=True)
    restore.add_argument("--session-id")
    restore.add_argument("--dsh-compression", choices=["zstd", "none"], default="zstd")
    restore.add_argument('--dry-run', action='store_true')
    restore.add_argument('--preview-token')
    restore.set_defaults(func=cmd_storage)
    skills = sub.add_parser("skills", help=T('h_skills'))
    skills.add_argument("agent", choices=[key for key in READ_AGENTS if key != 'yuanbao'])
    skills.add_argument("--skills-dir")
    skills.set_defaults(func=cmd_skill_storage)
    skill_store = sub.add_parser("store-skills", help=T('h_store_skills'))
    skill_store.add_argument("agent", choices=[key for key in READ_AGENTS if key != 'yuanbao'])
    skill_store.add_argument("paths", nargs="*")
    skill_store.add_argument("--all", action="store_true")
    skill_store.add_argument("--skills-dir", help=T('h_store_skills_dir'))
    skill_store.add_argument("--storage")
    skill_store.set_defaults(func=cmd_skill_storage)
    stored_skills = sub.add_parser("stored-skills", help=T('h_stored_skills'))
    stored_skills.add_argument("--agent", choices=[key for key in AGENTS if key != 'yuanbao'])
    stored_skills.add_argument("--storage")
    stored_skills.set_defaults(func=cmd_skill_storage)
    skill_restore = sub.add_parser("restore-skill", help=T('h_restore_skill'))
    skill_restore.add_argument("package")
    skill_restore.add_argument("--agent", choices=[key for key in READ_AGENTS if key != 'yuanbao'], help=T('h_restore_skill_agent'))
    skill_restore.add_argument("--skills-dir", help=T('h_restore_skill_dir'))
    skill_restore.add_argument("--name", help=T('h_restore_skill_name'))
    skill_restore.set_defaults(func=cmd_skill_storage)
    health = sub.add_parser('health', help=T('h_health'))
    health.add_argument('--output', help=T('h_health_output'))
    health.set_defaults(func=cmd_health)
    device = sub.add_parser('device-config', help=T('h_device'))
    device.add_argument('--agent', choices=AGENTS)
    device.add_argument('--home', help=T('h_device_home'))
    device.set_defaults(func=cmd_device)
    plugin = sub.add_parser('plugins', help=T('h_plugins'))
    plugin.add_argument('action', choices=['list','enable','disable','check'], nargs='?', default='list')
    plugin.add_argument('name', nargs='?')
    plugin.add_argument('path', nargs='?')
    plugin.set_defaults(func=cmd_plugins)
    # Per-command override can be passed through the Linux launcher. Choices
    # are built before parsing, so recognize Windows source names explicitly.
    for command in (p1, p2, p3, p4, p5, p6, p7, p10, store, skills, skill_store, skill_restore, *native_commands):
        command.add_argument("--windows-user", help=T('h_windows_user'))
        command.add_argument("--ubuntu-user", help=T('h_ubuntu_user'))

    return p


def main(argv=None):
    global LANG
    LANG = _resolve_lang(argv)
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if getattr(args, "ubuntu_user", None):
            from relay.ubuntu import PROFILE_ENV as UBUNTU_ENV, selected_profile as selected_ubuntu
            import platform
            if platform.system() != "Windows":
                raise ValueError(message_text('err.ubuntu_user_is_only_available_on_windows'))
            os.environ[UBUNTU_ENV] = args.ubuntu_user
            _CFG["ubuntu_user_home"] = args.ubuntu_user
            selected_ubuntu()
            registry._CACHE.clear()
        if getattr(args, "windows_user", None):
            import platform
            from relay.windows import PROFILE_ENV, selected_profile
            if platform.system() != "Linux":
                raise ValueError(message_text('err.windows_user_is_only_available_on_ubuntu_linux'))
            os.environ[PROFILE_ENV] = args.windows_user
            _CFG["windows_user_home"] = args.windows_user
            selected_profile()  # validate before using it
            registry._CACHE.clear()
        result = args.func(args)
        return result if isinstance(result, int) else 0
    except KeyboardInterrupt:
        print(T('cancelled'))
        return 130
    except Exception as e:
        print(T('error', detail=R(error_text(e))), file=sys.stderr)
        if os.environ.get("RELAY_DEBUG"):
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
