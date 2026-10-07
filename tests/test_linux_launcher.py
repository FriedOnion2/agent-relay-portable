"""Launch the actual Bash entry point on Linux with isolated synthetic data."""
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from relay.locations import SOURCES
from relay.adapters.codex import CodexAdapter
from test_relay import sample


@unittest.skipUnless(sys.platform.startswith("linux"), "requires real Linux Bash")
class LinuxLauncherTests(unittest.TestCase):
    def test_launcher_config_argument_override_http_and_sigint(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "中文 relay space !"
            root.mkdir()
            repo = Path(__file__).resolve().parents[1]
            shutil.copytree(repo / "app", root / "app", ignore=shutil.ignore_patterns("__pycache__"))
            shutil.copy2(repo / "启动_AgentRelay.sh", root)
            profile = base / "Windows disk" / "Users" / "Some user"
            original_path = Path(CodexAdapter(home=str(profile / ".codex")).write(sample(), session_id="fixture"))
            original = original_path.read_bytes()
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            (root / "config.json").write_text(json.dumps({"port": port, "open_browser": False,
                       "windows_user_home": str(base / "stale mount")}), encoding="utf-8")
            env = dict(os.environ)
            for key in list(env):
                if key.startswith("RELAY_"):
                    env.pop(key)
            env.update({"RELAY_" + key.upper() + "_HOME": str(base / "empty" / key) for key in SOURCES})
            env.update(RELAY_PYTHON=sys.executable, PYTHONUNBUFFERED="1", BROWSER="/nonexistent/browser")
            url = f"http://127.0.0.1:{port}"
            with (base / "launcher.log").open("w+", encoding="utf-8") as output:
                proc = subprocess.Popen(["bash", str(root / "启动_AgentRelay.sh"), "--no-browser",
                                         "--windows-user", str(profile)], cwd=str(base), env=env,
                                         stdout=output, stderr=subprocess.STDOUT)
                try:
                    deadline = time.monotonic() + 15
                    while time.monotonic() < deadline:
                        if proc.poll() is not None:
                            output.seek(0)
                            self.fail(output.read())
                        try:
                            with urllib.request.urlopen(url + "/api/sources", timeout=1) as res:
                                rows = json.load(res)["sources"]
                            break
                        except OSError:
                            time.sleep(0.1)
                    else:
                        self.fail("Linux launcher did not become ready")
                    self.assertEqual(len(rows), 12)
                    source = next(row for row in rows if row["name"] == "windows_codex")
                    self.assertEqual(source["session_count"], 1)
                    self.assertFalse(source["can_write"])
                    self.assertEqual(source["windows_profile"], str(profile))
                    with urllib.request.urlopen(url + "/api/sessions?agent=windows_codex") as res:
                        sid = json.load(res)["sessions"][0]["id"]
                    request = urllib.request.Request(url + "/api/export-md", data=json.dumps(
                        {"source": "windows_codex", "id": sid}).encode(),
                        headers={"Content-Type": "application/json"})
                    with urllib.request.urlopen(request) as res:
                        self.assertIn("Windows", json.load(res)["markdown"])
                    self.assertEqual(original_path.read_bytes(), original)
                    request = urllib.request.Request(url + "/api/import-windows", data=json.dumps(
                        {"source": "windows_codex", "id": sid, "cwd": str(base)}).encode(),
                        headers={"Content-Type": "application/json"})
                    with urllib.request.urlopen(request) as res:
                        imported = json.load(res)
                    self.assertEqual(imported["to"]["source"], "codex")
                    self.assertTrue(Path(imported["to"]["path"]).is_file())
                    self.assertTrue(str(Path(imported["to"]["path"])).startswith(str(base / "empty" / "codex")))
                    with urllib.request.urlopen(url + "/api/session?agent=codex&id=" + imported["to"]["id"]) as res:
                        self.assertEqual(json.load(res)["info"]["cwd"], str(base))
                    self.assertEqual(original_path.read_bytes(), original)
                    self.assertEqual(json.loads((root / "config.json").read_text())["windows_user_home"],
                                     str(base / "stale mount"))
                    local_bytes = Path(imported["to"]["path"]).read_bytes()
                    request = urllib.request.Request(url + "/api/export-windows", data=json.dumps(
                        {"source":"codex", "id":imported["to"]["id"], "cwd":"D:\\project",
                         "project_path":str(base), "session_id":"11111111-1111-4111-8111-111111111111"}).encode(),
                        headers={"Content-Type":"application/json"})
                    with urllib.request.urlopen(request) as res:
                        reverse = json.load(res)
                    self.assertEqual(reverse["to"]["source"], "windows_codex")
                    self.assertTrue(str(Path(reverse["to"]["path"])).startswith(str(profile / ".codex")))
                    with urllib.request.urlopen(url + "/api/session?agent=windows_codex&id=" + reverse["to"]["id"]) as res:
                        self.assertEqual(json.load(res)["info"]["cwd"].replace("\\", "/"), "D:/project")
                    native = [json.loads(line) for line in Path(reverse["to"]["path"]).read_text(encoding="utf-8").splitlines()]
                    self.assertEqual(native[0]["payload"]["cwd"], "D:\\project")
                    self.assertEqual(original_path.read_bytes(), original)
                    self.assertEqual(Path(imported["to"]["path"]).read_bytes(), local_bytes)
                    proc.send_signal(signal.SIGINT)
                    proc.wait(timeout=8)
                    self.assertIn(proc.returncode, (0, 130))
                    with socket.socket() as sock:
                        self.assertNotEqual(sock.connect_ex(("127.0.0.1", port)), 0)
                finally:
                    if proc.poll() is None:
                        proc.kill()
                        proc.wait(timeout=5)

    def test_invalid_explicit_python_does_not_silently_use_another(self):
        repo = Path(__file__).resolve().parents[1]
        env = {**os.environ, "RELAY_PYTHON": "/nonexistent/python"}
        result = subprocess.run(["bash", str(repo / "启动_AgentRelay.sh"), "--no-browser"],
                                env=env, capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("RELAY_PYTHON", result.stderr)

    def test_prepared_venv_is_selected_before_system_python(self):
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            venv = Path(temporary) / "runtime with spaces"
            (venv / "bin").mkdir(parents=True)
            (venv / "bin/python3").symlink_to(sys.executable)
            env = {k: v for k, v in os.environ.items() if not k.startswith("RELAY_")}
            env["RELAY_VENV"] = str(venv)
            result = subprocess.run(["bash", str(repo / "启动_AgentRelay.sh"), "--help"],
                                    env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Python: " + str(venv / "bin/python3"), result.stdout)


if __name__ == "__main__":
    unittest.main()
