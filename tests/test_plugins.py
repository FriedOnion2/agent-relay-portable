import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))

from relay import device, plugins, registry

PLUGIN = '''from relay import ir
from relay.adapters.base import BaseAdapter, SessionInfo
class Adapter(BaseAdapter):
    name = "sample"
    label = "Sample"
    api_version = 1
    can_write = False
    home = "fixture"
    def available(self): return True
    def discover(self):
        yield SessionInfo(self.name, "one", "Sample", "", "", None, None, 0, 1, "fixture")
    def read(self, sid):
        print("plugin diagnostic")
        return ir.Conversation(source=self.name, id=sid, turns=[ir.Turn(ir.USER, [ir.Block.text_block("plugin fixture")])])
'''


class PluginTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        patcher=patch.object(device,'project_root',return_value=self.root)
        patcher.start();self.addCleanup(patcher.stop)
        plugin_root=patch.object(plugins,'project_root',return_value=self.root)
        plugin_root.start();self.addCleanup(plugin_root.stop)
        self.previous=list(plugins.entries.values())
        self.addCleanup(lambda: plugins.configure(self.previous))
        plugins.configure([])
        self.path=self.root/'adapter.py';self.path.write_text(PLUGIN,encoding='utf-8')

    def test_explicit_enable_is_readonly_and_worker_reconstructs_ir_and_exports(self):
        self.assertNotIn('sample',registry.all_keys())
        info=plugins.enable('sample',self.path)
        self.assertTrue(info['community'])
        self.assertFalse(info['can_write'])
        self.assertEqual(registry.list_sessions('sample')[0]['id'],'one')
        self.assertIn('plugin fixture',registry.export_markdown('sample','one'))
        self.assertNotIn('sample',registry.writable_keys())
        self.assertEqual(device.read()['plugins'][0]['path'],'adapter.py')
        plugins.disable('sample')
        self.assertNotIn('sample',registry.all_keys())

    def test_check_reports_each_step_without_saving_anything(self):
        result=plugins.check('sample',self.path)
        self.assertTrue(result['ok'],result)
        self.assertTrue(any('read(one)' in row['check'] and row['ok'] for row in result['checks']))
        self.assertNotIn('sample',plugins.entries)
        self.assertEqual(device.read().get('plugins',[]),[])

    def test_check_flags_bad_names_missing_files_and_broken_plugins(self):
        self.assertFalse(plugins.check('Bad Name',self.path)['ok'])
        self.assertFalse(plugins.check('claude',self.path)['ok'])
        self.assertFalse(plugins.check('sample',self.root/'missing.py')['ok'])
        duplicate=PLUGIN.replace('        yield SessionInfo(self.name, "one", "Sample", "", "", None, None, 0, 1, "fixture")',
            '        for _ in range(2):\n            yield SessionInfo(self.name, "one", "Sample", "", "", None, None, 0, 1, "fixture")')
        self.path.write_text(duplicate,encoding='utf-8')
        failed=[row['check'] for row in plugins.check('sample',self.path)['checks'] if not row['ok']]
        self.assertEqual(failed,['会话 ID 唯一'])
        self.path.write_text(PLUGIN.replace('turns=[ir.Turn(ir.USER, [ir.Block.text_block("plugin fixture")])]','turns=[]'),encoding='utf-8')
        self.assertFalse(plugins.check('sample',self.path)['ok'])
        self.path.write_text(PLUGIN+'\nraise RuntimeError("boom")\n',encoding='utf-8')
        broken=plugins.check('sample',self.path)
        self.assertFalse(broken['ok'])
        self.assertIn('boom',broken['checks'][-1]['detail'])
        self.assertNotIn('sample',plugins.entries)

    def test_changed_bytes_and_api_mismatch_refuse_execution(self):
        plugins.enable('sample',self.path)
        self.path.write_text(PLUGIN+'\nraise RuntimeError("must not execute changed code")\n',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'已改变'):
            registry.read_conversation('sample','one')
        self.path.write_text(PLUGIN.replace('api_version = 1','api_version = 99'),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'版本不匹配'):
            plugins.enable('sample',self.path)

    def test_cannot_shadow_builtins_and_failure_is_isolated_to_community_source(self):
        with self.assertRaisesRegex(ValueError,'内置'):
            plugins.enable('codex',self.path)
        self.path.write_text(PLUGIN.replace('yield SessionInfo(self.name, "one", "Sample", "", "", None, None, 0, 1, "fixture")','raise RuntimeError("broken discovery")'),encoding='utf-8')
        plugins.enable('sample',self.path)
        with patch.object(registry,'all_keys',return_value=['sample','codex']):
            rows=registry.sources_info()
        self.assertFalse(rows[0]['available'])
        self.assertIn('broken discovery',rows[0]['error'])
        self.assertEqual(rows[1]['name'],'codex')

    def test_hanging_plugin_is_stopped_without_blocking_builtin_registry(self):
        self.path.write_text(PLUGIN.replace('print("plugin diagnostic")','while True: pass'),encoding='utf-8')
        plugins.enable('sample',self.path)
        with patch.object(plugins,'TIMEOUT',.7), self.assertRaisesRegex(ValueError,'超时'):
            registry.read_conversation('sample','one')
        self.assertTrue(registry.get('codex').can_write)

    def test_plugin_approval_does_not_apply_to_another_device(self):
        with patch.object(device,'identity',return_value='device-a'):
            plugins.enable('sample',self.path)
            self.assertEqual(len(device.merge({})['plugins']),1)
        with patch.object(device,'identity',return_value='device-b'):
            self.assertEqual(device.merge({})['plugins'],[])


class ShippedExampleTests(unittest.TestCase):
    """The example adapters are documentation: keep them loadable, correct and passing `plugins check`."""

    EXAMPLES = Path(__file__).resolve().parents[1] / 'examples'

    def load(self, filename):
        import importlib.util
        spec = importlib.util.spec_from_file_location('example_' + filename[:-3], self.EXAMPLES / filename)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.Adapter()

    def test_examples_read_a_synthetic_sample_and_export_markdown(self):
        from relay.adapters.markdown import render
        samples = {'jsonl_adapter.py': ('chat.jsonl', '{"role":"user","content":"hi"}\n{"role":"assistant","content":"hello"}\n'),
                   'plaintext_adapter.py': ('note.txt', 'plain text')}
        for filename, (name, content) in samples.items():
            with tempfile.TemporaryDirectory() as folder:
                adapter = self.load(filename)
                adapter.home = folder
                (Path(folder) / name).write_text(content, encoding='utf-8')
                rows = list(adapter.discover())
                self.assertEqual([row.id for row in rows], [name])
                self.assertIn(content[:2] if filename.startswith('plain') else 'hello', render(adapter.read(name)))

    def test_examples_pass_the_contract_self_check(self):
        for name, filename in (('jsonl', 'jsonl_adapter.py'), ('plaintext', 'plaintext_adapter.py')):
            result = plugins.check(name, self.EXAMPLES / filename)
            self.assertTrue(result['ok'], result)

    def test_jsonl_example_names_the_bad_line_and_rejects_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            adapter = self.load('jsonl_adapter.py')
            adapter.home = folder
            (Path(folder) / 'bad.jsonl').write_text('{"role":"user","content":"ok"}\nnot json\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, '第 2 行'):
                adapter.read('bad.jsonl')
            with self.assertRaisesRegex(ValueError, '.jsonl'):
                adapter.read('../etc/passwd')
