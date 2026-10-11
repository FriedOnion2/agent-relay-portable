import ast
import io
import os
import re
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))

import cli  # noqa: E402
from relay.messages import catalog  # noqa: E402

CJK = re.compile(r'[一-鿿]')


def run(argv, env=None):
    out, err = io.StringIO(), io.StringIO()
    with patch.dict(os.environ, env or {}, clear=False), redirect_stdout(out), redirect_stderr(err):
        try:
            code = cli.main(argv)
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


class CliLanguageTests(unittest.TestCase):
    def tearDown(self):
        cli.LANG = 'zh'

    def test_default_output_stays_chinese(self):
        env = {'RELAY_LANG': ''}
        code, out, _ = run(['sources'], env)
        self.assertEqual(code, 0)
        self.assertIn('状态', out)
        self.assertIn('会话数', out)

    def test_english_flag_and_environment_variable(self):
        _, out, _ = run(['--lang', 'en', 'sources'])
        self.assertIn('Status', out)
        self.assertFalse(CJK.search(out), out)
        _, out, _ = run(['sources'], {'RELAY_LANG': 'en'})
        self.assertIn('Sessions', out)

    def test_flag_beats_environment_and_unknown_falls_back(self):
        _, out, _ = run(['--lang', 'zh', 'sources'], {'RELAY_LANG': 'en'})
        self.assertIn('状态', out)
        _, out, _ = run(['sources'], {'RELAY_LANG': 'fr'})
        self.assertIn('状态', out)

    def test_english_help_has_no_chinese(self):
        for argv in (['--lang', 'en', '--help'], ['--lang', 'en', 'transfer', '--help'], ['--lang', 'en', 'batch', '--help'],
                     ['--lang', 'en', 'export-windows', '--help']):
            code, out, _ = run(argv)
            self.assertEqual(code, 0)
            self.assertFalse(CJK.search(out), (argv, CJK.findall(out)))

    def test_english_error_message(self):
        code, _, err = run(['--lang', 'en', 'windows-use'], {'RELAY_LANG': ''})
        self.assertEqual(code, 1)
        self.assertTrue(err.startswith('Error: '), err)
        self.assertFalse(CJK.search(err), err)

    def test_doctor_report_in_english(self):
        _, out, _ = run(['--lang', 'en', 'doctor'])
        self.assertIn('environment check', out)
        self.assertFalse(CJK.search(out), CJK.findall(out))

    def test_every_cli_key_used_exists_with_matching_slots(self):
        import string
        zh = catalog('zh')
        slots = lambda value: {name for _, name, _, _ in string.Formatter().parse(value) if name}
        for path, names in ((ROOT / 'app/cli.py', ('T',)), (ROOT / 'app/bootstrap.py', ('t',)), (ROOT / 'app/server.py', ('say',))):
            prefix = {'T': 'msg.cli_', 't': 'msg.cli_b_', 'say': 'msg.cli_s_'}
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in names
                        and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                    key = prefix[node.func.id] + node.args[0].value
                    self.assertIn(key, zh, f'{path.name}: {key}')
                    if not any(kw.arg is None for kw in node.keywords):
                        self.assertEqual(slots(zh[key]), {kw.arg for kw in node.keywords}, key)


if __name__ == '__main__':
    unittest.main()
