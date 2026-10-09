"""Check real-client smoke expectations and shutdown without any real client."""
import copy
import importlib.util
import subprocess
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

path = Path(__file__).resolve().parents[1] / 'scripts' / 'smoke_codex_resume.py'
spec = importlib.util.spec_from_file_location('codex_smoke', path)
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


def thread():
    items = [
        {'type': 'userMessage', 'content': [{'text': '你好'}]},
        {'type': 'reasoning', 'summary': ['先检查目录']},
        {'type': 'dynamicToolCall', 'arguments': {'command': 'pwd'}, 'success': True,
         'contentItems': [{'type': 'inputText', 'text': '/tmp'}]},
        {'type': 'dynamicToolCall', 'arguments': {'path': 'missing.txt'}, 'success': False,
         'contentItems': [{'type': 'inputText', 'text': '文件不存在'}]},
        {'type': 'agentMessage', 'text': '完成'},
    ]
    return {'preview': '你好', 'turns': [{'items': items}, {'items': [
        {'type': 'userMessage', 'content': [{'text': '再来一次'}]}, {'type': 'agentMessage', 'text': '好的'}]}]}


class CodexSmokeTests(unittest.TestCase):
    def test_client_history_requires_tools_reasoning_and_results(self):
        expected = thread()
        self.assertEqual(smoke.history_problems(expected), [])
        for mutation in ('text_only', 'missing_result', 'wrong_arguments', 'wrong_error_status', 'missing_reasoning'):
            actual = copy.deepcopy(expected)
            items = actual['turns'][0]['items']
            if mutation == 'text_only':
                actual['turns'][0]['items'] = [items[0], items[-1]]
            elif mutation == 'missing_result':
                items[2]['contentItems'] = []
            elif mutation == 'wrong_arguments':
                items[2]['arguments'] = {'command': 'other'}
            elif mutation == 'wrong_error_status':
                items[3]['success'] = True
            else:
                items[1]['summary'] = []
            with self.subTest(mutation=mutation):
                self.assertTrue(smoke.history_problems(actual))

    def server(self):
        server = smoke.AppServer.__new__(smoke.AppServer)
        server.proc = MagicMock()
        server.reader = MagicMock()
        server.reader.is_alive.return_value = False
        return server

    def test_shutdown_closes_input_waits_and_joins_reader_before_closing_output(self):
        server = self.server()
        server.close()
        server.proc.stdin.close.assert_called_once()
        server.proc.wait.assert_called_once_with(10)
        server.reader.join.assert_called_once_with(10)
        server.proc.stdout.close.assert_called_once()
        server.proc.terminate.assert_not_called()

    def test_windows_timeout_kills_only_created_process_tree_and_waits_again(self):
        server = self.server()
        server.proc.pid = 123
        server.proc.wait.side_effect = [subprocess.TimeoutExpired('codex', 10), 0]
        with patch.object(smoke.os, 'name', 'nt'), patch.object(smoke.subprocess, 'run') as run:
            server.close()
        self.assertEqual(run.call_args.args[0], ['taskkill', '/PID', '123', '/T', '/F'])
        self.assertEqual(server.proc.wait.call_count, 2)

    def test_cleanup_retries_transient_permission_errors_and_reports_persistent_failure(self):
        directory = MagicMock(name='directory')
        directory.name = 'synthetic-directory'
        directory.cleanup.side_effect = [PermissionError('locked'), None]
        with patch.object(smoke.tempfile, 'TemporaryDirectory', return_value=directory), patch.object(
                smoke.time, 'sleep') as sleep:
            with smoke.temporary_directory() as value:
                self.assertEqual(value, directory.name)
            self.assertEqual(directory.cleanup.call_count, 2)
            sleep.assert_called_once_with(0.1)
        directory.cleanup.side_effect = PermissionError('still locked')
        directory.cleanup.reset_mock()
        with patch.object(smoke.tempfile, 'TemporaryDirectory', return_value=directory), patch.object(
                smoke.time, 'sleep'), self.assertRaises(PermissionError):
            with smoke.temporary_directory():
                pass
        self.assertEqual(directory.cleanup.call_count, 5)


if __name__ == '__main__':
    unittest.main()
