"""Opt-in native Mac launch regression: python3 tests/macos_launch_smoke.py.

Launches the actual .app through LaunchServices, verifies its HTTP service and
stops only the server identified in the new launch log. Does not write sessions.
"""
import os
import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


def main():
    if sys.platform != "darwin":
        raise SystemExit("This smoke test requires macOS.")
    root = Path(__file__).resolve().parents[1]
    log_dirs = [root / "logs", Path.home() / "Library/Logs/AgentRelay"]
    existing = {p for d in log_dirs for p in d.glob("server-*.log")}
    subprocess.run(["/usr/bin/open", "-n", str(root / "AgentRelay.app")], check=True)
    pid = None
    try:
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            for directory in log_dirs:
                for log in directory.glob("server-*.log"):
                    if log in existing:
                        continue
                    data = log.read_text(encoding="utf-8", errors="replace")
                    match = re.search(r"\[AgentRelay\] server_pid=(\d+) port=(\d+)", data)
                    if not match:
                        continue
                    pid, port = map(int, match.groups())
                    try:
                        with urllib.request.urlopen("http://127.0.0.1:%d/" % port, timeout=1) as response:
                            assert response.status == 200
                            assert response.headers.get("Server", "").startswith("AgentRelay/")
                            assert b"AgentRelay" in response.read()
                        # Startup must remain healthy after the launcher exits.
                        time.sleep(2)
                        os.kill(pid, 0)
                        with urllib.request.urlopen("http://127.0.0.1:%d/" % port, timeout=1) as response:
                            assert response.status == 200
                        with urllib.request.urlopen("http://127.0.0.1:%d/api/sources" % port, timeout=20) as response:
                            sources = json.load(response)
                        assert sources["ok"] and len(sources["sources"]) == 6
                        print("PASS: LaunchServices HTTP 200; server survives launcher exit")
                        dsh = next(s for s in sources["sources"] if s["name"] == "dsh")
                        print("DSH sessions:", dsh.get("session_count"), "unreadable:", dsh.get("unreadable_count"), "error:", dsh.get("error", "none"))
                        print("Log:", log)
                        print(match.group(0))
                        return
                    except OSError:
                        pass
            time.sleep(0.2)
        raise AssertionError("LaunchServices did not start a healthy AgentRelay server within 25 seconds")
    finally:
        if pid is not None:
            try:
                os.kill(pid, 15)
            except ProcessLookupError:
                pass


if __name__ == "__main__":
    main()
