import ast
import io
import json
import os
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))

import cli  # noqa: E402
from relay.messages import catalog, text  # noqa: E402

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
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        homes = {'RELAY_' + source.upper() + '_HOME': str(Path(folder.name) / source)
                 for source in cli.AGENTS}
        homes['RELAY_LANG'] = ''
        env = patch.dict(os.environ, homes)
        env.start()
        self.addCleanup(env.stop)
        cache = patch.dict(cli.registry._CACHE, {}, clear=True)
        cache.start()
        self.addCleanup(cache.stop)

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

    def test_language_options_match_parser_semantics(self):
        for argv, env, expected in (
            (['--lang', 'fr', 'sources'], {'RELAY_LANG': 'en'}, '状态'),
            (['--lang', 'zh', '--lang=en', 'sources'], {}, 'Status'),
            (['sources'], {'RELAY_LANG': 'english'}, '状态'),
        ):
            code, out, _ = run(argv, env)
            self.assertEqual(code, 0)
            self.assertIn(expected, out)
        self.assertEqual(cli._resolve_lang(['--', '--lang', 'en']), 'zh')
        self.assertEqual(run(['--la', 'en', 'sources'])[0], 2)

    def test_plugin_json_is_language_independent(self):
        with patch.object(cli.plugins, 'entries', {}):
            zh = run(['--lang', 'zh', 'plugins', 'list'])[1]
            en = run(['--lang', 'en', 'plugins', 'list'])[1]
        self.assertEqual(json.loads(zh), json.loads(en))

    def test_english_skill_candidate_uses_requested_language(self):
        from relay import corpus
        from test_corpus import workflow
        docs = [dict(key=str(i), source='workbuddy', sid=str(i), canonical=str(i),
                     conversation=corpus._snapshot(workflow(), False)[0]) for i in range(3)]
        for i, doc in enumerate(docs):
            doc['conversation']['id'] = str(i)
        with patch.object(corpus.Corpus, 'evidence', return_value=docs):
            code, out, _ = run(['--lang', 'en', 'extract-skills'])
        self.assertEqual(code, 0)
        result = json.loads(out)
        self.assertEqual(len(result['candidates']), 1)
        draft = result['candidates'][0]
        self.assertIn('Workflow draft awaiting review', draft['markdown'])
        self.assertFalse(CJK.search(draft['description'] + draft['markdown'] + result['score_note']))

    def test_doctor_translates_structured_errors_preserves_external_details(self):
        report = dict(platform='fixture', app_root='/fixture', media_root='/fixture', media_kind='fixture',
                      config='', windows_user_home='',
                      python=dict(ok=True, version='3.12', origin='fixture', cmd='python'),
                      agents=[dict(key='codex', label='Codex', found=True, files=1, data='/fixture',
                                   errors=[text('msg.session_unreadable'), 'original 中文 detail'])])
        out = io.StringIO()
        with patch.object(cli.bootstrap, 'report', return_value=report), redirect_stdout(out):
            cli.bootstrap.print_report(lang='en')
        self.assertIn('Session cannot be read', out.getvalue())
        self.assertIn('original 中文 detail', out.getvalue())

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
