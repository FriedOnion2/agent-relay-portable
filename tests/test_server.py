import http.client
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import server


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = server.RelayServer(("127.0.0.1", 0), server.Handler)
        cls.thread = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.thread.join(timeout=3)

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.srv.server_port, timeout=5)
        try:
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def test_ui_is_served(self):
        status, body = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"AgentRelay", body)

    def test_static_path_cannot_escape_via_sibling_prefix(self):
        with tempfile.TemporaryDirectory() as root:
            web = Path(root) / "web"
            sibling = Path(root) / "web-private"
            web.mkdir()
            sibling.mkdir()
            (sibling / "secret.txt").write_text("private", encoding="utf-8")
            with patch.object(server, "WEB_DIR", str(web)):
                for path in ("/static/../web-private/secret.txt", "/static/%2e%2e/web-private/secret.txt"):
                    status, body = self.request("GET", path)
                    self.assertEqual(status, 403)
                    self.assertNotIn(b"private", body)

    def test_foreign_host_or_origin_is_rejected_before_transfer(self):
        for headers in ({"Host":"evil.example"}, {"Origin":"https://evil.example"}):
            with patch.object(server.registry, "transfer") as transfer:
                headers["Content-Type"] = "application/json"
                self.assertEqual(self.request("POST", "/api/transfer", "{}", headers)[0], 403)
                transfer.assert_not_called()

    def test_invalid_bodies_and_field_types_are_client_errors(self):
        for body in ("[]", "null", "broken", '{"source":42}', '{"include_thinking":"false"}'):
            self.assertEqual(self.request("POST", "/api/transfer", body,
                {"Content-Type":"application/json"})[0], 400)
        self.assertEqual(self.request("POST", "/api/transfer", "{}")[0], 415)
        self.assertEqual(self.request("POST", "/api/transfer", None,
            {"Content-Type":"application/json", "Content-Length":"-1"})[0], 400)
        self.assertEqual(self.request("POST", "/api/transfer", None,
            {"Content-Type":"application/json", "Content-Length":str(server.MAX_BODY + 1)})[0], 413)

    def test_error_statuses(self):
        body = json.dumps({"source":"codex", "id":"test", "target":"claude"})
        for error, code in ((FileNotFoundError("missing"),404), (FileExistsError("exists"),409),
                            (ValueError("invalid"),400)):
            with patch.object(server.registry, "transfer", side_effect=error):
                self.assertEqual(self.request("POST", "/api/transfer", body,
                    {"Content-Type":"application/json"})[0], code)

    def test_transfer_passes_boolean_options(self):
        payload = {"source":"codex", "id":"test", "target":"claude", "include_thinking":False}
        with patch.object(server.registry, "transfer", return_value={"ok":True}) as transfer:
            status, _ = self.request("POST", "/api/transfer", json.dumps(payload),
                                     {"Content-Type":"application/json"})
            self.assertEqual(status, 200)
            self.assertFalse(transfer.call_args.kwargs["include_thinking"])

    def test_native_windows_import_routes_options_and_rejects_invalid_fields(self):
        payload = {"source":"windows_dsh", "id":"p/s", "cwd":"/home/alice/project",
                   "session_id":"new", "dsh_compression":"none"}
        with patch("relay.native_import.import_windows", return_value={"ok":True}) as importer:
            self.assertEqual(self.request("POST", "/api/import-windows", json.dumps(payload),
                         {"Content-Type":"application/json"})[0], 200)
            importer.assert_called_once_with("windows_dsh", "p/s", "/home/alice/project",
                                             session_id="new", dsh_compression="none")
        for body in ({"source":"windows_codex", "id":"s"}, {**payload, "dsh_compression":False}):
            with patch("relay.native_import.import_windows") as importer:
                self.assertEqual(self.request("POST", "/api/import-windows", json.dumps(body),
                             {"Content-Type":"application/json"})[0], 400)
                importer.assert_not_called()

    def test_reverse_native_routes_options_and_validates_project_path(self):
        for endpoint in ("import-ubuntu", "export-windows"):
            payload = {"source":"codex", "id":"s", "cwd":"D:\\project", "session_id":"new",
                       "dsh_compression":"none", "project_path":"/mnt/data/project"}
            with patch("relay.native_import." + endpoint.replace("-", "_"), return_value={"ok":True}) as importer:
                self.assertEqual(self.request("POST", "/api/" + endpoint, json.dumps(payload),
                                 {"Content-Type":"application/json"})[0], 200)
                options = dict(session_id="new", dsh_compression="none")
                if endpoint == "export-windows":
                    options["project_path"] = "/mnt/data/project"
                importer.assert_called_once_with("codex", "s", "D:\\project", **options)
            for body in ({"source":"codex", "id":"s"}, {**payload,"project_path":False}):
                with patch("relay.native_import." + endpoint.replace("-", "_")) as importer:
                    self.assertEqual(self.request("POST", "/api/" + endpoint, json.dumps(body),
                                     {"Content-Type":"application/json"})[0], 400)
                    importer.assert_not_called()

    def test_session_storage_routes_and_validates_package_fields(self):
        headers = {"Content-Type":"application/json"}
        payload = {"source":"codex", "id":"s", "storage":"/portable"}
        with patch("relay.session_store.store_session", return_value={"ok":True}) as store:
            self.assertEqual(self.request("POST", "/api/store-session", json.dumps(payload), headers)[0], 200)
            store.assert_called_once_with("codex", "s", "/portable")
        payload = {"package":"/portable/session.zip", "cwd":"/project", "session_id":"new"}
        with patch("relay.session_store.restore_session", return_value={"ok":True}) as restore:
            self.assertEqual(self.request("POST", "/api/restore-session", json.dumps(payload), headers)[0], 200)
            restore.assert_called_once_with("/portable/session.zip", "/project", "new", "zstd")
        for payload in ({"package":False,"cwd":"/p"}, {"package":"p.zip"}, {"storage":[]}, {}):
            with patch("relay.session_store.restore_session") as restore:
                self.assertEqual(self.request("POST", "/api/restore-session", json.dumps(payload), headers)[0], 400)
                restore.assert_not_called()

    def test_skill_storage_routes_and_rejects_invalid_options(self):
        headers = {"Content-Type":"application/json"}
        payload = {"agent":"codex", "path":"/source/skill", "storage":"/portable"}
        with patch("relay.skill_store.store_skill", return_value={"ok":True}) as store:
            self.assertEqual(self.request("POST", "/api/store-skill", json.dumps(payload), headers)[0], 200)
            store.assert_called_once_with("codex", "/source/skill", "/portable")
        payload = {"package":"/portable/skill.zip", "agent":"claude", "skills_dir":"/target/skills", "name":"copy"}
        with patch("relay.skill_store.restore_skill", return_value={"ok":True}) as restore:
            self.assertEqual(self.request("POST", "/api/restore-skill", json.dumps(payload), headers)[0], 200)
            restore.assert_called_once_with("/portable/skill.zip", "claude", "/target/skills", "copy")
        for payload in ({"package":"s.zip", "name":False}, {"package":"s.zip", "skills_dir":[]}, {}):
            with patch("relay.skill_store.restore_skill") as restore:
                self.assertEqual(self.request("POST", "/api/restore-skill", json.dumps(payload), headers)[0], 400)
                restore.assert_not_called()


if __name__ == "__main__":
    unittest.main()


class ShutdownTests(unittest.TestCase):
    def test_shutdown_rejects_foreign_origin_and_stops_only_its_server(self):
        srv = server.RelayServer(("127.0.0.1", 0), server.Handler)
        thread = threading.Thread(target=srv.serve_forever)
        thread.start()
        try:
            for origin, expected in (("https://evil.example", 403), (None, 200)):
                conn = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=3)
                headers = {"Content-Type": "application/json"}
                if origin:
                    headers["Origin"] = origin
                conn.request("POST", "/api/shutdown", "{}", headers)
                response = conn.getresponse()
                self.assertEqual(response.status, expected)
                response.read()
                conn.close()
                if origin:
                    self.assertTrue(thread.is_alive())
            thread.join(timeout=3)
            self.assertFalse(thread.is_alive())
        finally:
            if thread.is_alive():
                srv.shutdown()
            srv.server_close()
            thread.join(timeout=3)

    def test_close_waits_for_inflight_request(self):
        entered, release, closed = threading.Event(), threading.Event(), threading.Event()
        class SlowHandler(server.Handler):
            def do_GET(self):
                entered.set()
                release.wait(timeout=5)
                self._json({"ok": True})
        srv = server.RelayServer(("127.0.0.1", 0), SlowHandler)
        serving = threading.Thread(target=srv.serve_forever)
        serving.start()
        def request():
            conn = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=5)
            try:
                conn.request("GET", "/")
                conn.getresponse().read()
            finally:
                conn.close()
        client = threading.Thread(target=request)
        client.start()
        self.assertTrue(entered.wait(timeout=3))
        srv.shutdown()
        def close():
            srv.server_close()
            closed.set()
        closer = threading.Thread(target=close)
        closer.start()
        try:
            self.assertFalse(closed.wait(timeout=.1))
        finally:
            release.set()
            client.join(timeout=3)
            closer.join(timeout=3)
            serving.join(timeout=3)
        self.assertTrue(closed.is_set())
