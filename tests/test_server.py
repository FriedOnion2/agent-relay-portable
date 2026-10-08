import http.client
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_corpus_reads_are_readonly_and_export_requires_confirmation(self):
        from relay import corpus
        with tempfile.TemporaryDirectory() as folder, patch.object(corpus,'project_root',return_value=Path(folder)):
            headers={'Content-Type':'application/json'}
            for endpoint in ('/api/corpus','/api/search?q=%E5%8F%91'):
                status,raw=self.request('GET',endpoint)
                self.assertEqual(status,200)
            self.assertFalse((Path(folder)/'index').exists())
            for payload in ({'sources':'workbuddy'},{'sources':['invalid']},{'include_thinking':'yes'},{'packages':1}):
                self.assertEqual(self.request('POST','/api/index',json.dumps(payload),headers)[0],400)
            md='---\nname: checked-draft\ndescription: "Synthetic workflow"\n---\nReviewed body\n'
            payload={'markdown':md,'directory':folder}
            self.assertEqual(self.request('POST','/api/export-draft',json.dumps(payload),headers)[0],400)
            self.assertFalse((Path(folder)/'checked-draft').exists())
            payload['confirmed']=True
            self.assertEqual(self.request('POST','/api/export-draft',json.dumps(payload),headers)[0],200)
            self.assertEqual(self.request('POST','/api/export-draft',json.dumps(payload),headers)[0],409)
            self.assertEqual(self.request('GET','/api/search?limit=-1')[0],400)
            self.assertFalse((Path(folder)/'index').exists())

    def test_corpus_job_progress_cancel_and_stale_job_rejection(self):
        from relay import corpus
        entered=threading.Event()
        def work(self,**kwargs):
            kwargs['progress']({'processed':1});entered.set()
            kwargs['cancel'].wait(3)
            return {'ok':True,'canceled':kwargs['cancel'].is_set()}
        headers={'Content-Type':'application/json'}
        with patch.object(corpus.Corpus,'update',work):
            status,raw=self.request('POST','/api/index','{}',headers)
            self.assertEqual(status,200);key=json.loads(raw)['id'];self.assertTrue(entered.wait(2))
            self.assertEqual(self.request('POST','/api/extract','{}',headers)[0],400)
            self.assertEqual(self.request('POST','/api/job-cancel','{"id":"stale"}',headers)[0],400)
            status,raw=self.request('GET','/api/job');self.assertEqual(json.loads(raw)['progress']['processed'],1)
            self.assertEqual(self.request('POST','/api/device-home','{"agent":"codex","home":""}',headers)[0],400)
            self.assertEqual(self.request('POST','/api/job-cancel',json.dumps({'id':key}),headers)[0],200)
            self.srv.jobs.thread.join(3);self.assertFalse(self.srv.jobs.thread.is_alive())

    def test_real_preview_is_readonly_and_changed_source_cannot_be_written(self):
        from relay import ir, device
        from relay.adapters.workbuddy import WorkBuddyAdapter
        from relay.adapters.codex import CodexAdapter
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = WorkBuddyAdapter(home=str(root / 'workbuddy'))
            target = CodexAdapter(home=str(root / 'codex'))
            path = Path(source.write(ir.Conversation(cwd=folder, turns=[
                ir.Turn(ir.USER, [ir.Block.text_block('original')])]), session_id='fixture'))
            payload = {'source':'workbuddy', 'id':'fixture', 'target':'codex', 'cwd':folder}
            headers = {'Content-Type':'application/json'}
            with patch.dict(server.registry._CACHE, {'workbuddy':source, 'codex':target}, clear=True), \
                 patch.dict(device.blocked_homes, {}, clear=True):
                status, raw = self.request('POST', '/api/preview', json.dumps(payload), headers)
                self.assertEqual(status, 200)
                self.assertFalse((root / 'codex').exists())
                plan = json.loads(raw)
                path.write_text(path.read_text(encoding='utf-8').replace('original', 'changed'), encoding='utf-8')
                status, _ = self.request('POST', '/api/transfer', json.dumps(dict(payload, preview_token=plan['token'])), headers)
                self.assertEqual(status, 400)
                self.assertFalse((root / 'codex').exists())
                _, raw = self.request('POST', '/api/preview', json.dumps(payload), headers)
                status, raw = self.request('POST', '/api/transfer', json.dumps(dict(payload, preview_token=json.loads(raw)['token'])), headers)
                self.assertEqual(status, 200)
                self.assertTrue(json.loads(raw)['ok'])

    def test_batch_route_dry_runs_by_default_and_validates_input(self):
        headers = {'Content-Type':'application/json'}
        with patch('relay.batch.run', return_value={'ok':True, 'items':[]}) as run:
            status, _ = self.request('POST', '/api/batch', json.dumps({'source':'claude', 'target':'codex'}), headers)
            self.assertEqual(status, 200)
            self.assertTrue(run.call_args.kwargs['dry_run'])
            self.assertEqual(run.call_args.kwargs['on_conflict'], 'skip')
            self.request('POST', '/api/batch', json.dumps({'source':'claude', 'target':'codex', 'dry_run':False}), headers)
            self.assertFalse(run.call_args.kwargs['dry_run'])
        for body in ({'source':'claude'}, {'source':'claude', 'target':'codex', 'ids':'a'}, {'source':'claude', 'target':'codex', 'limit':'x'}):
            self.assertEqual(self.request('POST', '/api/batch', json.dumps(body), headers)[0], 400)
    def test_diff_route_compares_two_sessions_and_validates_input(self):
        from relay import ir
        headers = {'Content-Type':'application/json'}
        one = ir.Conversation(turns=[ir.Turn(ir.USER, [ir.Block.text_block('hi')])])
        two = ir.Conversation(turns=[ir.Turn(ir.USER, [ir.Block.text_block('hi there')])])
        with patch.object(server.registry, 'read_conversation', side_effect=[one, two]):
            status, raw = self.request('POST', '/api/diff', json.dumps({'source':'a', 'id':'1', 'source2':'b', 'id2':'2'}), headers)
        self.assertEqual(status, 200)
        self.assertFalse(json.loads(raw)['identical'])
        self.assertEqual(self.request('POST', '/api/diff', json.dumps({'source':'a', 'id':'1'}), headers)[0], 400)

    def test_health_failure_is_visible_and_device_home_requires_valid_directory(self):
        from relay import device
        with patch('relay.health.report', return_value={'ok':False, 'adapters':[{'status':'failed'}]}):
            status, raw = self.request('GET', '/api/health')
            self.assertEqual(status, 200)
            self.assertTrue(json.loads(raw)['ok'])
            self.assertFalse(json.loads(raw)['healthy'])
        with tempfile.TemporaryDirectory() as folder, patch.object(device, 'project_root', return_value=Path(folder)):
            headers = {'Content-Type':'application/json'}
            for payload in ({'agent':'codex','home':str(Path(folder) / 'missing')}, {'agent':'sample','home':folder}, {'agent':'codex','home':42}):
                self.assertEqual(self.request('POST', '/api/device-home', json.dumps(payload), headers)[0], 400)
            self.assertFalse(device.config_path().exists())
            with patch('bootstrap.apply_config'), patch('bootstrap.load_config', return_value={}), \
                 patch.dict(server.registry._CACHE, {}, clear=True):
                status, raw = self.request('POST', '/api/device-home', json.dumps({'agent':'codex', 'home':folder}), headers)
                self.assertEqual(status, 200)
                self.assertEqual(device.read()['agent_homes']['codex'], str(Path(folder).resolve()))

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
                                             session_id="new", dsh_compression="none", preview_token=None)
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
                importer.assert_called_once_with("codex", "s", "D:\\project", preview_token=None, **options)
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
            restore.assert_called_once_with("/portable/session.zip", "/project", "new", "zstd", None)
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

    def test_operations_route_lists_history_and_undo_validates_input(self):
        headers = {"Content-Type":"application/json"}
        with patch("relay.oplog.list_operations", return_value=[{"id":"op-1"}]) as listing:
            status, raw = self.request("GET", "/api/operations?limit=5")
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(raw)["operations"], [{"id":"op-1"}])
            listing.assert_called_once_with(5)
        with patch("relay.oplog.undo", return_value={"ok":True, "complete":True}) as undo:
            self.assertEqual(self.request("POST", "/api/undo", json.dumps({"id":"op-1", "force":True}), headers)[0], 200)
            undo.assert_called_once_with("op-1", force=True)
            self.assertEqual(self.request("POST", "/api/undo", json.dumps({"id":"op-1", "force":"yes"}), headers)[0], 200)
            undo.assert_called_with("op-1", force=False)
        with patch("relay.oplog.undo") as undo:
            self.assertEqual(self.request("POST", "/api/undo", json.dumps({}), headers)[0], 400)
            undo.assert_not_called()
        with patch("relay.oplog.undo", side_effect=KeyError("找不到这条操作记录")):
            self.assertEqual(self.request("POST", "/api/undo", json.dumps({"id":"missing"}), headers)[0], 400)


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


class PortTests(unittest.TestCase):
    def test_occupied_port_uses_next_free_port_without_stopping_old_server(self):
        old = server.create_server("127.0.0.1", 0)
        new = None
        try:
            if old.server_port == 65535:
                self.skipTest("No next port")
            new = server.create_server("127.0.0.1", old.server_port)
            self.assertGreater(new.server_port, old.server_port)
            self.assertLessEqual(new.server_port, old.server_port + 5)
            self.assertGreaterEqual(old.fileno(), 0)
        finally:
            old.server_close()
            if new:
                new.server_close()

    def test_only_address_in_use_errors_are_retried(self):
        import errno
        with patch.object(server, "RelayServer", side_effect=OSError(errno.EACCES, "denied")) as factory:
            with self.assertRaises(OSError):
                server.create_server("127.0.0.1", 8745)
            self.assertEqual(factory.call_count, 1)
        with patch.object(server, "RelayServer", side_effect=OSError(errno.EADDRINUSE, "busy")) as factory:
            with self.assertRaisesRegex(OSError, "退出服务"):
                server.create_server("127.0.0.1", 65534)
            self.assertEqual(factory.call_count, 2)
