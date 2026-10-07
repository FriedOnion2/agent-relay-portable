#!/usr/bin/env python3
"""AgentRelay 本地服务 —— 给 Web 界面提供 REST API。

只用标准库，无需安装任何依赖。默认只监听 127.0.0.1。
"""

from __future__ import annotations

import json
import os
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, "web")
sys.path.insert(0, BASE_DIR)

from relay import registry  # noqa: E402

MAX_BODY = 4 * 1024 * 1024


class Handler(BaseHTTPRequestHandler):
    server_version = "AgentRelay/0.1"

    # ---------------- 基础 ----------------

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
        rel = rel.lstrip("/") or "index.html"
        path = os.path.normpath(os.path.join(WEB_DIR, rel))
        if not path.startswith(os.path.normpath(WEB_DIR)):
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
        except Exception as e:
            if os.environ.get("RELAY_DEBUG"):
                import traceback
                traceback.print_exc()
            return self._error(str(e), 500)

    def do_POST(self):
        u = urlparse(self.path)
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                return self._error("请求体过大", 413)
            raw = self.rfile.read(n) if n else b"{}"
            body = json.loads(raw.decode("utf-8") or "{}")
        except Exception as e:
            return self._error(f"请求体解析失败: {e}")

        try:
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
        except Exception as e:
            if os.environ.get("RELAY_DEBUG"):
                import traceback
                traceback.print_exc()
            return self._error(str(e), 500)


def run(host: str = "127.0.0.1", port: int = 8745, open_browser: bool = True):
    srv = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}/"
    print(f"AgentRelay Web 已启动: {url}")
    print("按 Ctrl+C 停止")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
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
