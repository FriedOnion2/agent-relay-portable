"""Portable search/extraction behavior using synthetic native stores only."""
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import threading
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
from contextlib import closing

sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'app'))
from relay import corpus, device, extraction, ir, registry, session_store
from relay.jobs import Jobs


def workflow(prompt='核对项目发布流程 portable release', error=False, result='verified output'):
    return ir.Conversation(title='发布流程优化', cwd='/fixture/project', updated_at='2026-10-08T10:00:00Z', turns=[
        ir.Turn(ir.USER,[ir.Block.text_block(prompt)]),
        ir.Turn(ir.ASSISTANT,[ir.Block.thinking_block('保密思考 hiddenreason'),
            ir.Block.tool_call('a','Read',json.dumps({'file_path':'/private/secret-config','token':'SECRET_TOKEN'}))]),
        ir.Turn(ir.ASSISTANT,[ir.Block.tool_result('a',result,error)]),
        ir.Turn(ir.ASSISTANT,[ir.Block.tool_call('b','Bash',json.dumps({'command':'echo SECRET_TOKEN; rm dangerous','cwd':'/private'}))]),
        ir.Turn(ir.ASSISTANT,[ir.Block.tool_result('b',result,error)]),
        ir.Turn(ir.ASSISTANT,[ir.Block.text_block('release发布流程 ready')],ts='2026-10-08T10:00:00Z')])


class CorpusTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        values={'RELAY_'+s.upper()+'_HOME':str(self.root/s) for s in registry._ADAPTERS}
        values['RELAY_STORAGE_HOME']=str(self.root/'storage')
        self.env=patch.dict(os.environ,values);self.env.start();self.addCleanup(self.env.stop)
        blocked=patch.dict(device.blocked_homes,{},clear=True);blocked.start();self.addCleanup(blocked.stop)
        self.store=corpus.Corpus(self.root)
        self.source=registry.get('workbuddy',clean=True)
        self.source.write(workflow(),session_id='one')

    def update(self,**kw):
        return self.store.update(sources=['workbuddy'],packages=False,**kw)

    def test_readonly_queries_never_create_an_index(self):
        self.assertFalse(self.store.status()['exists'])
        self.assertEqual(self.store.search('发布')['results'],[])
        self.assertFalse((self.root/'index').exists())

    def test_chinese_short_words_mixed_filters_and_literal_verification(self):
        self.assertTrue(self.update()['ok'])
        for query in ('发','发布','发布流程','release发布','portable 发布','ready'):
            self.assertEqual(len(self.store.search(query)['results']),1,query)
        self.assertEqual(self.store.search('布发')['results'],[])
        self.assertEqual(self.store.search('发布',source='codex')['results'],[])
        self.assertEqual(len(self.store.search('发布',project='fixture',tool='Read',after='2026-10-08',before='2026-10-08')['results']),1)
        self.assertEqual(self.store.search('发布',after='2026-10-09')['results'],[])
        self.assertEqual(self.store.search('" OR NOT * ; DROP TABLE docs')['results'],[])
        with self.assertRaises(ValueError):self.store.search('发布',before='bad date')

    def test_thinking_is_excluded_and_switch_really_purges_cached_content(self):
        self.update()
        self.assertEqual(self.store.search('hiddenreason',include_thinking=True)['results'],[])
        self.update(include_thinking=True)
        self.assertEqual(self.store.search('hiddenreason')['results'],[])
        hit=self.store.search('hiddenreason',include_thinking=True)['results'][0]
        self.assertNotIn('hiddenreason',json.dumps(self.store.document(hit['key'])))
        self.assertIn('hiddenreason',json.dumps(self.store.document(hit['key'],True)))
        shutil.move(self.source.root,self.root/'offline')
        self.update()
        self.assertEqual(self.store.search('hiddenreason',include_thinking=True)['results'],[])
        with closing(sqlite3.connect(self.store.path)) as db:
            self.assertNotIn('hiddenreason',db.execute('SELECT payload FROM docs').fetchone()[0])

    def test_incremental_deletion_offline_and_limits(self):
        self.update()
        result=self.update();self.assertEqual(result['unchanged'],1)
        self.source.write(workflow(),session_id='two')
        result=self.update(max_documents=1);self.assertTrue(result['limited'])
        self.update()
        self.assertEqual(self.store.status()['documents'],2)
        shutil.move(self.source.root,self.root/'offline')
        self.update()
        self.assertTrue(all(r['offline'] for r in self.store.search()['results']))
        shutil.move(self.root/'offline',self.source.root)
        Path(next(r.path for r in self.source.discover() if r.id=='one')).unlink()
        self.update();self.assertEqual(self.store.status()['documents'],1)
        event=threading.Event();event.set()
        self.assertTrue(self.update(cancel=event)['canceled'])
        self.assertEqual(self.store.status()['documents'],1)

    def test_changed_record_reindexes_and_old_scope_is_not_a_local_entry(self):
        self.update();hit=self.store.search()['results'][0]
        self.assertTrue(self.store.document(hit['key'])['can_open'])
        row=next(self.source.discover());path=Path(row.path)
        path.write_text(path.read_text(encoding='utf-8').replace('ready','changedmarker'),encoding='utf-8')
        self.assertEqual(self.update()['indexed'],1)
        self.assertEqual(len(self.store.search('changedmarker')['results']),1)
        other=self.root/'new-home';other.mkdir()
        with patch.dict(os.environ,{'RELAY_WORKBUDDY_HOME':str(other)}):
            self.assertFalse(self.store.document(hit['key'])['can_open'])
            self.update()
            self.assertTrue(self.store.search()['results'][0]['offline'])

    def test_schema_unknown_preserved_backed_up_and_delete_journal(self):
        self.update()
        with closing(sqlite3.connect(self.store.path)) as db:
            self.assertEqual(db.execute('PRAGMA journal_mode').fetchone()[0],'delete')
            db.execute('PRAGMA user_version=99')
            db.commit()
        before=self.store.path.read_bytes()
        with self.assertRaisesRegex(ValueError,'版本'):self.update()
        self.assertEqual(before,self.store.path.read_bytes())
        self.assertEqual(len(list(self.store.path.parent.glob('corpus-schema-99-*.sqlite3'))),1)
        with self.assertRaises(ValueError):self.store.search()

    def test_unreadable_subtree_never_deletes_existing_cache(self):
        self.update()
        def unreadable(root,onerror=None):
            onerror(PermissionError('fixture unreadable directory'))
            return iter(())
        with patch('relay.adapters.base.os.walk',side_effect=unreadable):
            result=self.update()
        self.assertFalse(result['ok']);self.assertEqual(self.store.status()['documents'],1)
        self.assertTrue(self.store.search()['results'][0]['offline'])

    def test_package_and_database_relocation_deduplicate_evidence(self):
        with patch.dict(registry._CACHE,{'workbuddy':self.source},clear=True):
            session_store.store_session('workbuddy','one',self.root/'storage')
        self.assertTrue(self.store.update(sources=['workbuddy'])['ok'])
        self.assertEqual(self.store.status()['documents'],2)
        self.assertEqual(len(self.store.search('发布')['results']),1)
        self.assertEqual(len(self.store.evidence()),1)
        other=self.root/'device-b';other.mkdir()
        shutil.copytree(self.root/'index',other/'index');shutil.copytree(self.root/'storage',other/'storage')
        with patch.object(device,'identity',return_value='different-device'),patch.dict(os.environ,{'RELAY_STORAGE_HOME':str(other/'storage')}):
            moved=corpus.Corpus(other)
            for doc in moved.evidence():self.assertFalse(doc['can_open'])
            with closing(sqlite3.connect(moved.path)) as db:
                key=db.execute("SELECT key FROM docs WHERE origin='local'").fetchone()[0]
                self.assertTrue(moved.document(key)['offline'])
            self.assertTrue(moved.update(sources=[],packages=True)['ok'])
            self.assertEqual(moved.status()['documents'],2)
            self.assertTrue(any(d['origin']=='package' for d in moved.evidence()))

    def test_shared_claude_sdk_sessions_do_not_multiply_evidence(self):
        root=self.root/'claude'
        agent=registry.get('claude',home=str(root))
        agent.write(workflow(),session_id=str(uuid.uuid4()))
        with patch.dict(os.environ,{'RELAY_CLAUDE_SDK_HOME':str(root)}):
            self.assertTrue(self.store.update(sources=['claude','claude_sdk'],packages=False)['ok'])
        self.assertEqual(self.store.status()['documents'],2)
        self.assertEqual(len(self.store.evidence()),1)

    def test_codex_title_index_changes_refresh_without_main_log_change(self):
        agent=registry.get('codex',clean=True);sid=str(uuid.uuid4())
        path=Path(agent.write(workflow(),session_id=sid))
        self.store.update(sources=['codex'],packages=False)
        before=path.read_bytes()
        Path(agent.index_path).write_text(json.dumps({'id':sid,'thread_name':'全新标题标记'})+'\n',encoding='utf-8')
        self.assertEqual(self.store.update(sources=['codex'],packages=False)['indexed'],1)
        self.assertEqual(len(self.store.search('标题标记')['results']),1)
        self.assertEqual(before,path.read_bytes())

    def test_codebuddy_reference_files_and_workspace_index_invalidate(self):
        from test_sources import CodeBuddyTests
        home=self.root/'codebuddy';home.mkdir()
        path=CodeBuddyTests().fixture(str(home))
        self.assertTrue(self.store.update(sources=['codebuddy'],packages=False)['ok'])
        message=next((path/'messages').glob('*.json'))
        message.write_text(message.read_text(encoding='utf-8').replace('fixture','referencechange'),encoding='utf-8')
        self.assertEqual(self.store.update(sources=['codebuddy'],packages=False)['indexed'],1)
        index=path.parent/'index.json';value=json.loads(index.read_text(encoding='utf-8'))
        value['conversations'][0]['title']='工作区标题标记';index.write_text(json.dumps(value),encoding='utf-8')
        self.assertEqual(self.store.update(sources=['codebuddy'],packages=False)['indexed'],1)

    def test_dsh_new_unknown_generation_keeps_old_cache_offline(self):
        from test_sources import write_log, log
        home=self.root/'dsh';write_log(home,log())
        self.store.update(sources=['dsh'],packages=False)
        write_log(home,log(5),5)
        result=self.store.update(sources=['dsh'],packages=False)
        self.assertFalse(result['ok'])
        self.assertTrue(self.store.search()['results'][0]['offline'])

    def test_repeated_workflow_drafts_are_abstract_and_require_three_sessions(self):
        self.source.write(workflow(),session_id='two');self.update()
        self.assertEqual(extraction.extract(self.store)['candidates'],[])
        self.source.write(workflow(),session_id='three');self.update()
        with patch.object(registry,'get',side_effect=AssertionError('extraction must only read the cache')):
            result=extraction.extract(self.store)
        self.assertEqual(len(result['candidates']),1)
        draft=result['candidates'][0]
        self.assertEqual(draft['evidence_count'],3);self.assertFalse(draft['selected'])
        self.assertNotIn('SECRET_TOKEN',draft['markdown']);self.assertNotIn('/private',draft['markdown'])
        self.assertNotIn('rm dangerous',draft['markdown'])
        self.assertEqual(draft['outcomes']['nonempty'],6)
        self.source.write(workflow(),session_id='four');self.update()
        bounded=extraction.extract(self.store,max_documents=3)
        self.assertTrue(bounded['limited']);self.assertEqual(bounded['candidates'][0]['evidence_count'],3)
        with self.assertRaises(ValueError):extraction.export_draft(draft['markdown'],str(self.root))
        path=extraction.export_draft(draft['markdown'],str(self.root),True)['path']
        before=Path(path).read_bytes()
        with self.assertRaises(FileExistsError):extraction.export_draft(draft['markdown'],str(self.root),True)
        self.assertEqual(Path(path).read_bytes(),before)

    def test_noise_failure_empty_unknown_readonly_and_partial(self):
        # Same generic tools with unrelated requests are not sufficient.
        self.source.write(workflow('绘制科学图表'),session_id='two')
        self.source.write(workflow('检查数据库连接'),session_id='three');self.update()
        self.assertEqual(extraction.extract(self.store)['candidates'],[])
        for sid in ('one','two','three'):
            path=next(r.path for r in self.source.discover() if r.id==sid);Path(path).unlink()
            self.source.write(workflow(error=True),session_id=sid)
        self.update();self.assertEqual(extraction.extract(self.store)['candidates'],[])
        # Read-only workflows and empty tool returns still yield cautious drafts.
        for sid in ('one','two','three'):
            Path(next(r.path for r in self.source.discover() if r.id==sid)).unlink()
            conv=workflow(result='');conv.turns[3].blocks[0].name='Grep'
            self.source.write(conv,session_id=sid)
        self.update();draft=extraction.extract(self.store)['candidates'][0]
        self.assertEqual(draft['outcomes']['empty'],6)
        event=threading.Event();event.set()
        self.assertTrue(extraction.extract(self.store,cancel=event)['canceled'])
        self.assertEqual(extraction.extract(self.store,cancel=event)['candidates'],[])
        self.assertTrue(extraction.extract(self.store,max_documents=2)['limited'])
        with patch.object(corpus,'MAX_TEXT',5):self.update(include_thinking=True)
        self.assertEqual(extraction.extract(self.store)['candidates'],[])

    def test_export_frontmatter_and_paths_are_validated_before_writing(self):
        for md in ('no header','---\nname: ../bad\ndescription: x\n---\nbody',
                   '---\nname: con\ndescription: x\n---\nbody',
                   '---\nname: safe\ndescription: \"\"\n---\nbody',
                   '---\nname: safe\nname: twice\ndescription: x\n---\nbody'):
            with self.assertRaises(ValueError):extraction.export_draft(md,str(self.root),True)
        self.assertFalse((self.root/'safe').exists())
        path=extraction.export_draft('---\nname: null\ndescription: true\n---\nbody',str(self.root),True)['path']
        self.assertIn('name: "null"',Path(path).read_text(encoding='utf-8'))
        self.assertIn('description: "true"',Path(path).read_text(encoding='utf-8'))

    def test_job_cancel_and_close_leave_no_writer(self):
        manager=Jobs();entered=threading.Event()
        def work(progress,cancel):
            entered.set();cancel.wait(3)
            return dict(ok=True,canceled=cancel.is_set())
        job=manager.start('fixture',work);self.assertTrue(entered.wait(2))
        with self.assertRaises(ValueError):manager.start('another',work)
        with self.assertRaises(ValueError):manager.cancel('outdated')
        manager.cancel(job['id']);manager.close()
        self.assertFalse(manager.thread.is_alive());self.assertEqual(manager.status()['status'],'canceled')
