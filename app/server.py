#!/usr/bin/env python3
"""AgentRelay 本地服务 —— 给 Web 界面提供 REST API。

只用标准库，无需安装任何依赖。默认只监听 127.0.0.1。
"""

from __future__ import annotations

import errno
import json
import os
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, "web")
sys.path.insert(0, BASE_DIR)

from relay import registry  # noqa: E402

MAX_BODY = 4 * 1024 * 1024


class RelayServer(ThreadingHTTPServer):
    # Preserve in-flight writes when the user stops the service.
    daemon_threads = False
    # Windows SO_REUSEADDR permits a second live listener on the same port.
    allow_reuse_address = sys.platform != "win32"
    allow_reuse_port = False


class Handler(BaseHTTPRequestHandler):
    server_version = "AgentRelay/0.1"

    # ---------------- 基础 ----------------

    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def _local_request(self):
        port = self.server.server_address[1]
        allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if self.headers.get("Host", "").lower() not in allowed:
            self._error("只允许本机访问", 403)
            return False
        origin = self.headers.get("Origin")
        if origin and origin.lower() not in {"http://" + host for host in allowed}:
            self._error("不允许跨站请求", 403)
            return False
        return True

    def log_message(self, fmt, *args):
        if "--quiet" not in sys.argv:
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, code: int, body: bytes, ctype: str = "application/json; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200):
        self._send(code, json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8"))

    def _error(self, msg: str, code: int = 400):
        self._json({"ok": False, "error": msg}, code)

    def _static(self, rel: str):
        rel = unquote(rel).lstrip("/") or "index.html"
        root = os.path.realpath(WEB_DIR)
        path = os.path.realpath(os.path.join(root, rel))
        try:
            contained = os.path.commonpath([root, path]) == root
        except ValueError:
            contained = False
        if not contained:
            return self._error("forbidden", 403)
        if not os.path.isfile(path):
            return self._error("not found", 404)
        ext = os.path.splitext(path)[1]
        ctype = {".html": "text/html; charset=utf-8",
                 ".js": "application/javascript; charset=utf-8",
                 ".css": "text/css; charset=utf-8",
                 ".svg": "image/svg+xml"}.get(ext, "application/octet-stream")
        with open(path, "rb") as f:
            self._send(200, f.read(), ctype)

    # ---------------- 路由 ----------------

    def do_GET(self):
        if not self._local_request():
            return
        u = urlparse(self.path)
        q = parse_qs(u.query)
        path = u.path
        try:
            if path == "/" or path.startswith("/index"):
                return self._static("index.html")
            if path.startswith("/static/"):
                return self._static(path[len("/static/"):])
            if path == "/api/sources":
                return self._json({"ok": True, "sources": registry.sources_info()})
            if path == "/api/stored-sessions":
                from relay.archive import list_packages, storage_root
                from relay.session_store import KIND
                root = (q.get("storage") or [None])[0]
                return self._json({"ok":True, "root":str(storage_root(root)),
                       "packages":list_packages(KIND, (q.get("agent") or [None])[0], root)})
            if path == "/api/skills":
                from relay.skill_store import discover_skills
                return self._json(discover_skills((q.get("agent") or [""])[0], (q.get("skills_dir") or [None])[0]))
            if path == "/api/stored-skills":
                from relay.archive import list_packages, storage_root
                from relay.skill_store import KIND
                root = (q.get("storage") or [None])[0]
                return self._json({"ok":True, "root":str(storage_root(root)),
                                  "packages":list_packages(KIND, (q.get("agent") or [None])[0], root)})
            if path == "/api/sessions":
                agent = (q.get("agent") or [""])[0]
                if not agent:
                    return self._error("缺少 agent 参数")
                rows = registry.list_sessions(agent, keyword=(q.get("q") or [""])[0])
                return self._json({"ok": True, "agent": agent, "sessions": rows})
            if path == "/api/session":
                agent = (q.get("agent") or [""])[0]
                sid = (q.get("id") or [""])[0]
                conv = registry.read_conversation(agent, sid)
                return self._json({
                    "ok": True,
                    "info": {
                        "source": conv.source, "id": conv.id, "title": conv.title,
                        "cwd": conv.cwd, "model": conv.model,
                        "created_at": conv.created_at, "updated_at": conv.updated_at,
                        "path": conv.path, "truncated": conv.truncated,
                        "stats": conv.stats(),
                        "notes": conv.meta.get("notes", []),
                    },
                    "turns": [
                        {
                            "role": t.role, "ts": t.ts, "model": t.model,
                            "text": t.text(),
                            "blocks": [b.__dict__ for b in t.blocks],
                        }
                        for t in conv.turns
                    ],
                })
            if path == "/api/preview-md":
                return self._json({"ok": True, "markdown": registry.export_markdown(
                    (q.get("agent") or [""])[0], (q.get("id") or [""])[0])})
            return self._error("unknown endpoint", 404)
        except FileNotFoundError as e:
            return self._error(str(e), 404)
        except (ValueError, KeyError) as e:
            return self._error(str(e), 400)
        except Exception as e:
            if os.environ.get("RELAY_DEBUG"):
                import traceback
                traceback.print_exc()
            return self._error(str(e), 500)

    def do_POST(self):
        if not self._local_request():
            return
        u = urlparse(self.path)
        if self.headers.get_content_type() != "application/json":
            return self._error("请求必须使用 application/json", 415)
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n < 0:
                return self._error("Content-Length 不能为负数")
            if n > MAX_BODY:
                return self._error("请求体过大", 413)
            raw = self.rfile.read(n) if n else b"{}"
            body = json.loads(raw.decode("utf-8") or "{}")
            if not isinstance(body, dict):
                return self._error("请求体必须是 JSON 对象")
            for key in ("source", "id", "target", "cwd", "session_id", "title", "dsh_compression", "project_path", "storage", "package", "agent", "path", "skills_dir", "name"):
                if key in body and body[key] is not None and not isinstance(body[key], str):
                    return self._error(f"{key} 必须是字符串")
            for key in ("remap_tools", "include_thinking", "include_tools"):
                if key in body and type(body[key]) is not bool:
                    return self._error(f"{key} 必须为 true 或 false")
        except Exception as e:
            return self._error(f"请求体解析失败: {e}")

        try:
            if u.path == "/api/shutdown":
                self._json({"ok": True})
                # shutdown must run outside the serve_forever thread.
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            if u.path == "/api/store-skill":
                from relay.skill_store import store_skill
                if not body.get("agent") or not body.get("path"):
                    return self._error("缺少 Agent / Skill 目录")
                return self._json(store_skill(body["agent"], body["path"], body.get("storage")))
            if u.path == "/api/restore-skill":
                from relay.skill_store import restore_skill
                if not body.get("package"):
                    return self._error("缺少 Skill 包路径")
                return self._json(restore_skill(body["package"], body.get("agent") or None,
                                                body.get("skills_dir") or None, body.get("name") or None))
            if u.path == "/api/store-session":
                from relay.session_store import store_session
                if not body.get("source") or not body.get("id"):
                    return self._error("缺少 Agent / 会话 ID")
                return self._json(store_session(body["source"], body["id"], body.get("storage")))
            if u.path == "/api/restore-session":
                from relay.session_store import restore_session
                if not body.get("package") or not body.get("cwd"):
                    return self._error("缺少存储包路径 / 本机目标项目目录")
                return self._json(restore_session(body["package"], body["cwd"], body.get("session_id") or None,
                                                  body.get("dsh_compression") or "zstd"))
            if u.path in ("/api/import-ubuntu", "/api/export-windows"):
                from relay.native_import import import_ubuntu, export_windows
                if not (body.get("source") and body.get("id") and body.get("cwd")):
                    return self._error("缺少来源 / 会话 ID / Windows 项目路径")
                options = dict(session_id=body.get("session_id") or None,
                               dsh_compression=body.get("dsh_compression") or "zstd")
                if u.path == "/api/export-windows":
                    options["project_path"] = body.get("project_path")
                importer = export_windows if u.path == "/api/export-windows" else import_ubuntu
                return self._json(importer(body["source"], body["id"], body["cwd"], **options))
            if u.path == "/api/import-windows":
                from relay.native_import import import_windows
                if not (body.get("source") and body.get("id") and body.get("cwd")):
                    return self._error("缺少 Windows 来源 / 会话 ID / Ubuntu 项目目录")
                return self._json(import_windows(body["source"], body["id"], body["cwd"],
                                  session_id=body.get("session_id") or None,
                                  dsh_compression=body.get("dsh_compression") or "zstd"))
            if u.path == "/api/transfer":
                source = body.get("source")
                sid = body.get("id")
                target = body.get("target")
                if not (source and sid and target):
                    return self._error("缺少 source / id / target")
                res = registry.transfer(
                    source, sid, target,
                    cwd=body.get("cwd") or None,
                    session_id=body.get("session_id") or None,
                    remap_tools=bool(body.get("remap_tools", True)),
                    include_thinking=bool(body.get("include_thinking", True)),
                    new_title=body.get("title") or None,
                )
                return self._json(res)
            if u.path == "/api/export-md":
                md = registry.export_markdown(
                    body.get("source"), body.get("id"),
                    include_thinking=bool(body.get("include_thinking", True)),
                    include_tools=bool(body.get("include_tools", True)),
                )
                return self._json({"ok": True, "markdown": md})
            return self._error("unknown endpoint", 404)
        except FileExistsError as e:
            return self._error(str(e), 409)
        except FileNotFoundError as e:
            return self._error(str(e), 404)
        except (ValueError, KeyError) as e:
            return self._error(str(e), 400)
        except Exception as e:
            if os.environ.get("RELAY_DEBUG"):
                import traceback
                traceback.print_exc()
            return self._error(str(e), 500)


def create_server(host: str, port: int):
    if host not in ("127.0.0.1", "localhost"):
        raise ValueError("服务只支持本机地址 127.0.0.1 或 localhost")
    if not 0 <= port <= 65535:
        raise ValueError("端口必须在 0 到 65535 之间")
    for candidate in range(port, min(port + 6, 65536)):
        try:
            return RelayServer((host, candidate), Handler)
        except OSError as exc:
            if exc.errno != errno.EADDRINUSE and getattr(exc, "winerror", None) != 10048:
                raise
    raise OSError(errno.EADDRINUSE, f"端口 {port} 及后续端口均被占用，请先在旧页面点击「退出服务」后重试")


def run(host: str = "127.0.0.1", port: int = 8745, open_browser: bool = True):
    srv = create_server(host, port)
    if port and srv.server_address[1] != port:
        print(f"端口 {port} 已被占用，自动改用 {srv.server_address[1]}")
    url = f"http://{host}:{srv.server_address[1]}/"
    print(f"AgentRelay Web 已启动: {url}")
    print("点击网页右上角「退出服务」或按 Ctrl+C 停止")
    if open_browser:
        timer = threading.Timer(0.6, lambda: webbrowser.open(url))
        timer.daemon = True
        timer.start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        srv.server_close()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8745)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    run(a.host, a.port, not a.no_browser)
