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
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
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


if __name__ == "__main__":
    unittest.main()
