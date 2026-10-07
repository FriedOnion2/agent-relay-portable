import json
import os
import unittest
from pathlib import Path

import test_native_import
from relay import ir, preview, registry, native_import, session_store


class PreviewTests(unittest.TestCase):
    setUp = test_native_import.NativeImportTests.setUp
    snapshot = test_native_import.NativeImportTests.snapshot

    def test_preview_never_writes_and_detects_changed_source_and_options(self):
        adapter = self.targets['claude']
        conv = ir.Conversation(source='fixture', cwd=str(self.cwd), turns=[
            ir.Turn(ir.USER, [ir.Block.text_block('original')]),
            ir.Turn(ir.ASSISTANT, [ir.Block.text_block('reply'), ir.Block.thinking_block('analysis')])])
        path = Path(adapter.write(conv, session_id='original'))
        before = self.snapshot(self.root)
        plan = preview.conversion('claude', 'original', 'codex', cwd=str(self.cwd), include_thinking=False)
        self.assertTrue(plan['dropped'])
        self.assertEqual(before, self.snapshot(self.root))
        with self.assertRaisesRegex(ValueError, '重新预览'):
            registry.transfer('claude', 'original', 'codex', cwd=str(self.cwd), preview_token=plan['token'])
        path.write_text(path.read_text(encoding='utf-8').replace('"text": "original"', '"text": "changed"'), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '重新预览'):
            registry.transfer('claude', 'original', 'codex', cwd=str(self.cwd), include_thinking=False, preview_token=plan['token'])
        plan = preview.conversion('claude', 'original', 'codex', cwd=str(self.cwd), include_thinking=False)
        result = registry.transfer('claude', 'original', 'codex', cwd=str(self.cwd), include_thinking=False, preview_token=plan['token'])
        self.assertEqual(result['preview']['token'], plan['token'])

    def test_report_distinguishes_system_images_raw_and_dsh_unpaired_tools(self):
        conv = ir.Conversation(turns=[ir.Turn(ir.SYSTEM,[ir.Block.text_block('system')]),
               ir.Turn(ir.ASSISTANT,[ir.Block(ir.IMAGE,meta={'url':'fixture'}),
                   ir.Block(ir.RAW,meta={'unknown':'retained text'}),
                   ir.Block.tool_call('unpaired','Bash','{}')])])
        options = dict(include_thinking=True, remap_tools=True)
        codex = preview.report(conv,'codex',options,'fixture')
        self.assertIn('图片', str(codex['dropped']))
        self.assertIn('系统', str(codex['dropped']))
        self.assertIn('文本', str(codex['degraded']))
        dsh = preview.report(conv,'dsh',options,'fixture')
        self.assertIn('未配对',str(dsh['degraded']))

    def test_native_preview_and_consistency_token_cover_same_app_import(self):
        # Sources are created in the selected foreign profile by the fixture.
        source = registry.get('windows_codex')
        sid = next(source.discover()).id
        before = self.snapshot(self.root)
        plan = preview.native('windows_codex',sid,'import-windows',str(self.cwd))
        self.assertEqual(plan['mode'],'native')
        self.assertEqual(before,self.snapshot(self.root))
        result = native_import.import_windows('windows_codex',sid,str(self.cwd),preview_token=plan['token'])
        self.assertEqual(result['preview']['token'],plan['token'])

    def test_package_preview_is_checked_before_install_and_rejects_changed_options(self):
        adapter=self.targets['workbuddy']
        adapter.write(ir.Conversation(cwd=str(self.cwd),turns=[ir.Turn(ir.USER,[ir.Block.text_block('fixture')])]),session_id='sample')
        package=session_store.store_session('workbuddy','sample',self.root/'store')['path']
        plan=preview.package(package,str(self.cwd),session_id='copy')
        before=self.snapshot(self.root)
        with self.assertRaisesRegex(ValueError,'重新预览'):
            session_store.restore_session(package,str(self.cwd),session_id='other',preview_token=plan['token'])
        self.assertEqual(before,self.snapshot(self.root))
        restored=session_store.restore_session(package,str(self.cwd),session_id='copy',preview_token=plan['token'])
        self.assertTrue(restored['ok'])
