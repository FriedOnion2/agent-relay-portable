import ast
import copy
import http.client
import json
import re
import string
import sys
import tempfile
import threading
import unittest
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
import server
from relay import ir, oplog, sensitive
from relay.jobs import Jobs
from relay.messages import annotate, catalog, error_text, join_text, restore_text, text


class MessageTests(unittest.TestCase):
    def test_catalog_keys_and_parameters_cover_business_calls(self):
        zh = catalog()
        en = json.loads((ROOT / 'app/web/locales.en.json').read_text(encoding='utf-8'))
        self.assertEqual(set(zh), set(en))
        slots = lambda value: sorted(name for _, name, _, _ in string.Formatter().parse(value) if name)
        for key in zh:
            self.assertRegex(key, r'^(ui|msg|err)\.[a-z][a-z0-9_]*$')
            self.assertNotRegex(key, r'\.message(?:_\d+)?$')
            self.assertEqual(slots(zh[key]), slots(en[key]), key)
            self.assertNotRegex(en[key].replace('Mac安装依赖.command', ''), r'[\u4e00-\u9fff]', key)
        for path in (ROOT / 'app').rglob('*.py'):
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                        and node.func.id == 'message_text' and node.args and isinstance(node.args[0], ast.Constant)):
                    key = node.args[0].value
                    self.assertIn(key, zh, str(path))
                    self.assertEqual(set(slots(zh[key])), {kw.arg for kw in node.keywords}, key)

    def test_static_chinese_text_and_attributes_require_explicit_keys(self):
        testcase = self
        class Bindings(HTMLParser):
            def __init__(self):
                super().__init__()
                self.stack = []

            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                for name in ('placeholder', 'title', 'aria-label'):
                    if re.search(r'[\u4e00-\u9fff]', attrs.get(name, '')):
                        testcase.assertIn(attrs.get('data-i18n-' + name), catalog())
                if tag not in ('input', 'br', 'hr', 'img', 'meta', 'link'):
                    self.stack.append((tag, attrs))

            def handle_endtag(self, tag):
                while self.stack:
                    if self.stack.pop()[0] == tag:
                        break

            def handle_data(self, data):
                if self.stack and self.stack[-1][0] not in ('script', 'style') and re.search(r'[\u4e00-\u9fff]', data):
                    testcase.assertIn(self.stack[-1][1].get('data-i18n'), catalog(), data)
        Bindings().feed((ROOT / 'app/web/index.html').read_text(encoding='utf-8'))

    def test_string_output_and_additive_metadata_preserve_user_content(self):
        message = text('err.source_unreadable', detail=text('msg.session_unreadable'))
        self.assertEqual(message, '源会话不可读：会话无法读取')
        result = annotate({'error': message, 'notes': [message, 'raw external detail'],
                           'conversation': {'text': '源会话不可读：会话无法读取'}})
        encoded = json.loads(json.dumps(result, ensure_ascii=False))
        self.assertEqual(encoded['error'], str(message))
        self.assertEqual(encoded['error_message']['params']['detail']['code'], 'msg.session_unreadable')
        self.assertEqual(encoded['notes_messages'][1], 'raw external detail')
        self.assertNotIn('text_message', encoded['conversation'])
        self.assertEqual(copy.deepcopy(message).descriptor(), message.descriptor())

    def test_code_is_independent_of_chinese_copy_and_unknown_details_are_kept(self):
        key = 'msg.session_unreadable'
        before = text(key).descriptor()
        with patch.dict(catalog(), {key: '修改后的说明'}):
            self.assertEqual(text(key), '修改后的说明')
            self.assertEqual(text(key).descriptor()['code'], before['code'])
        message = text(key)
        for exception in (ValueError(message), KeyError(message), OSError(22, message)):
            retained = error_text(exception)
            self.assertEqual(retained, str(exception))
            self.assertEqual(retained.code, key)
        self.assertEqual(error_text(RuntimeError('unrecognized detail')).descriptor()['params'],
                         {'detail': 'unrecognized detail'})

    def test_nested_join_and_secret_labels_remain_structured(self):
        joined = join_text([text('msg.session_unreadable'), text('msg.no_file_changes_recorded')], '; ')
        self.assertEqual(joined, '会话无法读取; 没有记录到文件变化')
        self.assertEqual(joined.descriptor()['params']['rest']['code'], 'msg.no_file_changes_recorded')
        conv = ir.Conversation(turns=[ir.Turn(ir.USER, [ir.Block.text_block('-----BEGIN PRIVATE KEY-----fixture-----END PRIVATE KEY-----')])])
        summary = sensitive.summary_line(sensitive.scan_conversation(conv))
        self.assertEqual(summary, '私钥 1 处')
        self.assertEqual(summary.descriptor()['params']['label']['code'], 'msg.secret_private_key')

    def test_background_job_failure_keeps_code_after_deepcopy(self):
        jobs = Jobs()
        def fail(progress, cancel):
            raise ValueError(text('msg.session_unreadable'))
        jobs.start('index', fail)
        jobs.close()
        status = annotate(jobs.status())
        self.assertEqual(status['status'], 'failed')
        self.assertEqual(status['error_message']['code'], 'msg.session_unreadable')

    def test_operation_log_keeps_message_metadata_after_restart(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(oplog, 'log_path', return_value=Path(folder) / 'operations.jsonl'):
            oplog._append({'id': 'fixture', 'undo_blocked': text('msg.undo_scan_incomplete'), 'created': [], 'appended': []})
            row = oplog.list_operations()[0]
            self.assertEqual(row['undo_blocked_message']['code'], 'msg.undo_scan_incomplete')
            with self.assertRaises(ValueError) as raised:
                oplog.undo('fixture')
            descriptor = error_text(raised.exception).descriptor()
            self.assertEqual(descriptor['params']['value']['code'], 'msg.undo_scan_incomplete')
        self.assertEqual(restore_text('old log', {'code':'future.unknown'}), 'old log')


class MessageHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = server.RelayServer(('127.0.0.1', 0), server.Handler)
        cls.thread = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.thread.join(timeout=3)

    def request(self, path, body=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.srv.server_port, timeout=5)
        try:
            connection.request('POST' if body is not None else 'GET', path, body=body,
                               headers={'Content-Type': 'application/json'})
            response = connection.getresponse()
            return response.status, response.headers.get('Content-Type'), response.read()
        finally:
            connection.close()

    def test_static_locales_load_over_http_and_match_the_backend(self):
        for language in ('zh', 'en'):
            status, mime, body = self.request('/static/locales.' + language + '.json')
            self.assertEqual(status, 200)
            self.assertEqual(mime, 'application/json; charset=utf-8')
            self.assertEqual(set(json.loads(body)), set(catalog()))
        status, _, body = self.request('/static/i18n.js')
        self.assertEqual(status, 200)
        self.assertIn(b'RelayI18n', body)

    def test_http_errors_preserve_status_text_and_stable_codes(self):
        from relay import registry
        for exception, expected_status in ((ValueError, 400), (FileNotFoundError, 404), (FileExistsError, 409)):
            with patch.object(registry, 'transfer', side_effect=exception(text('msg.session_unreadable'))):
                status, _, raw = self.request('/api/transfer', '{"source":"codex","id":"fixture","target":"claude"}')
                result = json.loads(raw)
                self.assertEqual(status, expected_status)
                self.assertEqual(result['error'], '会话无法读取')
                self.assertEqual(result['error_message']['code'], 'msg.session_unreadable')


if __name__ == '__main__':
    unittest.main()
