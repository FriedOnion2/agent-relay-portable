const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, '../app/web/index.html'), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1].split('\ninit().catch')[0];

test('late corpus search and document responses cannot replace current results',async()=>{
  const t=setup();t.el('#corpusQuery').value='旧';
  const old=t.app.searchCorpus();t.el('#corpusQuery').value='新';const latest=t.app.searchCorpus();
  t.response(1,{ok:true,indexed:true,results:[{key:'new',title:'new',source:'codex',snippet:'<script>unsafe</script>'}]});await latest;
  t.response(0,{ok:true,indexed:true,results:[{key:'old',title:'old',source:'claude'}]});await old;
  assert.equal(t.el('#corpusResults').children[0].children[0].textContent,'new');
  assert.equal(t.el('#corpusResults').children[0].children[2].textContent,'<script>unsafe</script>');
  const first=t.app.openCorpusDocument('old');const second=t.app.openCorpusDocument('new');
  t.response(3,{ok:true,title:'new',can_open:false,conversation:{turns:[]}});await second;
  t.response(2,{ok:true,title:'old',can_open:true,conversation:{turns:[]}});await first;
  assert.equal(t.el('#corpusDocument').children[0].textContent,'new');
  assert.equal(t.el('#corpusDocument').children.length,2);
});

test('Skill candidates are unselected and export requires editing review, captures text and prevents duplicate writes',async()=>{
  const t=setup();t.app.bind();
  t.app.renderDraftCandidates([{id:'draft',name:'workflow',markdown:'draft text',evidence_count:3,score:6,evidence:[]}]);
  assert.equal(t.app.corpusState.selected,null);
  await t.app.exportDraft();assert.equal(t.requests.length,0);
  t.el('#draftCandidates').children[0].children[1].onclick();
  assert.equal(t.el('#confirmDraft').checked,false);
  await t.app.exportDraft();assert.equal(t.requests.length,0);
  t.el('#draftDirectory').value='/output';t.el('#confirmDraft').checked=true;
  t.el('#draftMarkdown').oninput();assert.equal(t.el('#confirmDraft').checked,false);
  t.el('#confirmDraft').checked=true;
  const pending=t.app.exportDraft();await t.app.exportDraft();
  assert.equal(t.requests.length,1);const payload=JSON.parse(t.requests[0].options.body);
  assert.equal(payload.markdown,'draft text');assert.equal(payload.directory,'/output');assert.equal(payload.confirmed,true);
  t.response(0,{ok:true,path:'/output/workflow/SKILL.md'});await pending;
  assert.equal(t.el('#confirmDraft').checked,false);
});

test('index jobs capture disabled thought option and cancellation targets the active job',async()=>{
  const t=setup();t.el('#indexThinking').checked=false;t.el('#indexPackages').checked=true;
  const pending=t.app.startCorpusJob('index');await t.app.startCorpusJob('extract');
  assert.equal(t.requests.length,1);
  assert.equal(JSON.parse(t.requests[0].options.body).include_thinking,false);
  t.response(0,{ok:true,id:'job-a',status:'running'});
  await new Promise(resolve=>setImmediate(resolve));
  t.response(1,{ok:true,id:'job-a',kind:'index',status:'running',progress:{processed:1}});await pending;
  const canceled=t.app.cancelCorpusJob();assert.equal(JSON.parse(t.requests[2].options.body).id,'job-a');
  t.response(2,{ok:true});await canceled;
  const poll=t.app.pollCorpusJob();t.response(3,{ok:true,id:'job-a',kind:'index',status:'canceled',result:{canceled:true}});await poll;
  assert.equal(t.app.corpusState.busy,false);assert.equal(t.el('#cancelCorpus').disabled,true);
});

test('progress uses Chinese counts and reviewed evidence links follow the actual server port',async()=>{
  const t=setup();const poll=t.app.pollCorpusJob();
  t.response(0,{ok:true,id:'job',kind:'extract',status:'completed',result:{processed:3,segments:3,candidates:[{
    id:'draft',name:'workflow',evidence_count:3,score:6,evidence:[],markdown:'[evidence](http://127.0.0.1:8745/?document=key)'}]}});
  await poll;
  assert.match(t.el('#corpusStatus').textContent,/提炼：已完成/);
  assert.match(t.el('#corpusStatus').textContent,/已扫描 3 条/);
  assert.equal(t.el('#corpusStatus').textContent.includes('"processed"'),false);
  t.el('#draftCandidates').children[0].children[1].onclick();
  assert.equal(t.el('#draftMarkdown').value,'[evidence](http://127.0.0.1:18945/?document=key)');
  assert.equal(t.el('#confirmDraft').checked,false);
});

function setup({automaticPreview=true,confirmed=true,randomUUID}={}){
  class Element {
    constructor(){ this.children=[]; this.value=''; this.checked=true; this.disabled=false;
      this.style={}; this.dataset={}; this.classList={add(){}, remove(){}}; this._html=''; }
    setAttribute(name,value){this[name]=value;}
    set innerHTML(value){this._html=value; this.children=[];}
    get innerHTML(){return this._html;}
    appendChild(child){this.children.push(child); return child;}
  }
  const elements = new Map();
  const requests=[];
  const previews=[];
  const document={
    body:new Element(),
    querySelector(selector){if(!elements.has(selector)) elements.set(selector,new Element()); return elements.get(selector);},
    querySelectorAll(){return [];},
    createElement(){return new Element();},
    createTextNode(text){return {textContent:text};},
  };
  const context = vm.createContext({document, encodeURIComponent, Blob, URL, navigator:{}, crypto:randomUUID?{randomUUID}:undefined, location:{origin:'http://127.0.0.1:18945'}, confirm(){return confirmed;},
    setTimeout(){return 1;}, clearTimeout(){},
    fetch(url,options){
      if(url==='/api/preview' && automaticPreview){previews.push({url,options});return Promise.resolve({ok:true,status:200,json:async()=>({ok:true,token:'verified-fixture',target:'claude',blockers:[],warnings:[]})});}
      return new Promise((resolve,reject)=>requests.push({url,options,resolve,reject}));
    },
  });
  vm.runInContext(script + '\n globalThis.app={workflow,showPage,renderOperationResult,selectPackage,selections,selectAll,storeBatch,state,loadSessions,openSession,doTransfer,doImportWindows,updateActions,bind,buildTarget,buildTabs,loadSources,storeCurrent,refreshStorage,restoreStored,buildSkillAgents,loadSkills,refreshSkillPackages,storeSelectedSkill,restoreSelectedSkill,corpusState,searchCorpus,openCorpusDocument,renderDraftCandidates,exportDraft,updateDraftAction,startCorpusJob,pollCorpusJob,cancelCorpusJob,setLang,tr,ts,applyStatic,renderChips,renderList,renderDetail,EN,EN_SERVER,doBatch,openHistory,refreshHistory,renderHistory,undoOperation,getLang:()=>lang};',context);
  const response = (index,body,status=200)=>requests[index].resolve({ok:status<400,status,json:async()=>body});
  return {app:context.app, elements, requests, previews, response, document, el:document.querySelector};
}

test('a late session-list response cannot replace the newly selected source',async()=>{
  const t=setup();
  const old=t.app.loadSessions();
  t.app.state.source='codex';
  const latest=t.app.loadSessions();
  t.response(1,{ok:true,sessions:[{id:'new',title:'new',turns:1}]});
  await latest;
  t.response(0,{ok:true,sessions:[{id:'old',title:'old',turns:1}]});
  await old;
  assert.equal(t.app.state.sessions[0].id,'new');
});

test('migration waits for preview, carries token, and cancellation never writes',async()=>{
  const t=setup({automaticPreview:false});
  t.app.state.current={source:'codex',id:'s'};
  t.app.state.target='claude';
  const pending=t.app.doTransfer();
  assert.equal(t.requests[0].url,'/api/preview');
  assert.equal(t.requests.length,1);
  await t.app.doTransfer();assert.equal(t.requests.length,1);
  t.response(0,{ok:true,token:'source-hash',target:'claude',blockers:[],warnings:[],dropped:[{item:'image',count:1}]});
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(t.requests[1].url,'/api/transfer');
  assert.equal(JSON.parse(t.requests[1].options.body).preview_token,'source-hash');
  t.response(1,{ok:false,error:'source changed'},400);await pending;
  assert.equal(t.app.state.transferring,false);
  const canceled=setup({confirmed:false});
  canceled.app.state.current={source:'codex',id:'s'};
  await canceled.app.doTransfer();
  assert.equal(canceled.previews.length,1);
  assert.equal(canceled.requests.length,0);
  assert.equal(canceled.app.state.transferring,false);
});

test('a preview blocker prevents the write and community sources cannot be stored natively',async()=>{
  const t=setup({automaticPreview:false});t.app.state.current={source:'sample',id:'s'};
  t.app.state.source='sample';
  t.app.state.sources=[{name:'sample',community:true,can_write:false}];
  t.app.updateActions();assert.equal(t.el('#btnStore').disabled,true);
  const pending=t.app.doTransfer();
  t.response(0,{ok:true,target:'claude',blockers:['truncated source'],token:'blocked'});
  await pending;
  assert.equal(t.requests.length,1);
  assert.match(t.el('#toast').children[0].textContent,/truncated source/);
});

test('a late detail response cannot enable migration after changing sources',async()=>{
  const t=setup();
  const old=t.app.openSession({id:'old'});
  t.app.state.source='codex';
  const list=t.app.loadSessions();
  t.response(1,{ok:true,sessions:[]});
  await list;
  t.response(0,{ok:true,info:{title:'old',stats:{}},turns:[]});
  await old;
  assert.equal(t.app.state.current,null);
  assert.equal(t.el('#btnGo').disabled,true);
  assert.equal(t.el('#btnMd').disabled,true);
});

test('rapid detail selections keep the newest conversation',async()=>{
  const t=setup();
  const old=t.app.openSession({id:'old'});
  const latest=t.app.openSession({id:'new'});
  t.response(1,{ok:true,info:{title:'new',stats:{}},turns:[]});
  await latest;
  t.response(0,{ok:true,info:{title:'old',stats:{}},turns:[]});
  await old;
  assert.equal(t.app.state.current.id,'new');
  assert.equal(t.app.state.current.source,'workbuddy');
});

test('transfer captures the selected source and cannot be submitted twice',async()=>{
  const t=setup();
  t.app.state.current={id:'selected',source:'codex'};
  const first=t.app.doTransfer();
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(JSON.parse(t.requests[0].options.body).source,'codex');
  const detail=t.app.openSession({id:'other'});
  t.response(1,{ok:true,info:{title:'other',stats:{}},turns:[]});
  await detail;
  assert.equal(t.el('#btnGo').disabled,true);
  await t.app.doTransfer();
  assert.equal(t.requests.length,2);
  t.response(0,{ok:false,error:'simulated failure'},409);
  await first;
  assert.equal(t.app.state.transferring,false);
  assert.equal(t.el('#btnGo').disabled,false);
});

test('export failure is shown to the user and does not reject the event handler',async()=>{
  const t=setup();
  t.app.bind();
  t.app.state.current={id:'selected',source:'codex',title:'selected'};
  const exporting=t.el('#btnMd').onclick();
  assert.equal(JSON.parse(t.requests[0].options.body).source,'codex');
  t.requests[0].reject(new Error('offline'));
  await exporting;
  assert.match(t.el('#toast').children[0].textContent,/offline/);
});

test('six source tabs and only supported writable targets are offered',()=>{
  const t=setup();
  t.app.buildTabs();
  assert.deepEqual(t.el('#tabs').children.map(x=>x.textContent),
    ['WorkBuddy','DeepSeek Harness','CodeBuddy','Claude Code','Claude Agent SDK','OpenAI Codex']);
  t.app.state.source='dsh';
  t.app.buildTarget();
  assert.deepEqual(t.el('#target').children.map(x=>x.value),['workbuddy','claude','codex']);
  t.app.state.sources=[{name:'codex',can_write:false}];
  t.app.buildTarget();
  assert.deepEqual(t.el('#target').children.map(x=>x.value),['workbuddy','claude']);
  t.app.state.source='codex';
  t.app.state.sources=[];
  t.app.buildTarget();
  assert.deepEqual(t.el('#target').children.map(x=>x.value),['workbuddy','dsh','claude']);
});

test('SDK selection shows shared-storage attribution and offers only writable targets',()=>{
  const t=setup();
  t.app.state.source='claude_sdk';
  t.app.buildTabs();
  t.app.buildTarget();
  assert.match(t.el('#sourceNote').textContent,/共用会话存储/);
  assert.equal(t.el('#sourceNote').style.display,'');
  assert.deepEqual(t.el('#target').children.map(x=>x.value),['workbuddy','dsh','claude','codex']);
  t.app.state.source='claude';
  t.app.buildTabs();
  assert.equal(t.el('#sourceNote').style.display,'none');
});

test('Windows sources appear separately with paths and never become writable targets',()=>{
  const t=setup();
  t.app.state.sources=[{name:'windows_codex',label:'Windows · OpenAI Codex',can_write:false,
    home:'/media/Win/Users/A/.codex/sessions',read_note:'Windows 只读来源'}];
  t.app.state.source='windows_codex';
  t.app.buildTabs();
  t.app.buildTarget();
  assert.equal(t.el('#tabs').children.length,7);
  assert.equal(t.el('#tabs').children.at(-1).textContent,'Windows · OpenAI Codex');
  assert.match(t.el('#sourceNote').textContent,/\/media\/Win/);
  assert.deepEqual(t.el('#target').children.map(x=>x.value),['workbuddy','dsh','claude','codex']);
  assert.equal(t.app.state.target,'codex');
});

test('same-app Windows import needs a project and captures selection without duplicate submission',async()=>{
  const t=setup();
  t.app.state.source='windows_claude_sdk';
  t.app.state.current={source:'windows_claude_sdk',id:'sdk-session'};
  t.app.updateActions();
  assert.equal(t.el('#btnImport').style.display,'');
  assert.equal(t.el('#btnImport').disabled,true);
  t.el('#cwd').value='/home/alice/project';
  t.el('#importId').value='new-sdk';
  t.app.updateActions();
  assert.equal(t.el('#btnImport').disabled,false);
  const importing=t.app.doImportWindows();
  await new Promise(resolve=>setImmediate(resolve));
  const payload=JSON.parse(t.requests[0].options.body);
  assert.equal(t.requests[0].url,'/api/import-windows');
  assert.equal(payload.source,'windows_claude_sdk');
  assert.equal(payload.cwd,'/home/alice/project');
  assert.equal(payload.session_id,'new-sdk');
  assert.equal('target' in payload,false);
  await t.app.doImportWindows();
  assert.equal(t.requests.length,1);
  t.response(0,{ok:true,to:{source:'claude_sdk',id:'new-sdk',native_id:'new-sdk',path:'/tmp/native.jsonl'},
                  notes:['共享存储'],resume_command:''});
  await new Promise(resolve=>setImmediate(resolve));
  t.response(1,{ok:true,sources:[]});
  await importing;
  assert.equal(t.app.state.transferring,false);
  assert.match(t.el('#importResult').children[0].textContent,/Claude Agent SDK/);
  assert.equal(t.el('#importResult').children[1].textContent,'查看 Ubuntu 会话');
  assert.equal(t.el('#importResult').style.display,'');
});

test('Windows import failure releases buttons and displays the backend reason',async()=>{
  const t=setup();
  t.app.state.source='windows_codebuddy';
  t.app.state.current={source:'windows_codebuddy',id:'ide:0:session'};
  t.el('#cwd').value='/home/alice/project';
  t.app.updateActions();
  const importing=t.app.doImportWindows();
  await new Promise(resolve=>setImmediate(resolve));
  t.response(0,{ok:false,error:'先创建原生工作区'},400);
  await importing;
  assert.equal(t.app.state.transferring,false);
  assert.equal(t.el('#btnImport').disabled,false);
  assert.match(t.el('#toast').children[0].textContent,/原生工作区/);
});

test('Ubuntu export requires both Windows cwd and accessible mount path and captures the request',async()=>{
  const t=setup();
  t.app.state.sources=[{name:'codex',native_export:true}];
  t.app.state.source='codex';
  t.app.state.current={source:'codex',id:'local'};
  t.el('#cwd').value='D:\\project';
  t.app.updateActions();
  assert.equal(t.el('#projectPath').style.display,'');
  assert.equal(t.el('#btnImport').disabled,true);
  t.el('#projectPath').value='/mnt/data/project';
  t.app.updateActions();
  const pending=t.app.doImportWindows();
  await new Promise(resolve=>setImmediate(resolve));
  await t.app.doImportWindows();
  assert.equal(t.requests.length,1);
  assert.equal(t.requests[0].url,'/api/export-windows');
  const body=JSON.parse(t.requests[0].options.body);
  assert.equal(body.cwd,'D:\\project');
  assert.equal(body.project_path,'/mnt/data/project');
  t.app.state.source='claude';
  t.response(0,{ok:true,target_os:'Windows',to:{source:'windows_codex',id:'new',native_id:'new',path:'/mnt/windows/session'},notes:[]});
  await new Promise(resolve=>setImmediate(resolve));
  t.response(1,{ok:true,sources:[]});
  await pending;
  assert.equal(t.el('#importResult').children[1].textContent,'查看 Windows 会话');
  assert.match(t.el('#importResult').children[0].textContent,/OpenAI Codex/);
});

test('Windows imports Ubuntu sources into local counterpart without a mount-path field',async()=>{
  const t=setup();
  t.app.state.source='ubuntu_codex';
  t.app.state.sources=[{name:'ubuntu_codex',label:'Ubuntu · OpenAI Codex',can_write:false}];
  t.app.state.current={source:'ubuntu_codex',id:'backup'};
  t.el('#cwd').value='D:\\project';
  t.app.buildTarget();
  assert.equal(t.app.state.target,'codex');
  assert.equal(t.el('#projectPath').style.display,'none');
  const pending=t.app.doImportWindows();
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(t.requests[0].url,'/api/import-ubuntu');
  assert.equal('project_path' in JSON.parse(t.requests[0].options.body),false);
  t.response(0,{ok:false,error:'目标会话 ID 已存在'},409);
  await pending;
  assert.equal(t.app.state.transferring,false);
  assert.match(t.el('#toast').children[0].textContent,/ID 已存在/);
});

test('generic conversion on Ubuntu uses the accessible project path rather than the Windows cwd',async()=>{
  const t=setup();
  t.app.state.source='codex';
  t.app.state.target='claude';
  t.app.state.sources=[{name:'codex',native_export:true}];
  t.app.state.current={source:'codex',id:'s'};
  t.el('#cwd').value='D:\\project';
  t.el('#projectPath').value='/mnt/data/project';
  t.app.updateActions();
  const pending=t.app.doTransfer();
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(JSON.parse(t.requests[0].options.body).cwd,'/mnt/data/project');
  t.response(0,{ok:false,error:'fixture error'},400);
  await pending;
});

test('storing captures the selected source and package restore captures local cwd with duplicate protection',async()=>{
  const t=setup();
  t.app.state.current={source:'codex',id:'s'};
  t.app.updateActions();
  const storing=t.app.storeCurrent();
  await t.app.storeCurrent();
  assert.equal(t.requests.length,1);
  assert.equal(t.requests[0].url,'/api/store-session');
  assert.equal(JSON.parse(t.requests[0].options.body).source,'codex');
  t.response(0,{ok:true,path:'/storage/codex/p.zip',manifest:{agent:'codex'}});
  await new Promise(resolve=>setImmediate(resolve));
  t.response(1,{ok:true,packages:[],root:'/storage'});
  await storing;
  assert.equal(t.el('#storagePanel').style.display,'');
  assert.match(t.el('#storageResult').textContent,/p.zip/);
  t.el('#packagePath').value='/storage/codex/p.zip';
  t.el('#restoreCwd').value='/home/a/project';
  const restoring=t.app.restoreStored();
  await new Promise(resolve=>setImmediate(resolve));
  await t.app.restoreStored();
  assert.equal(t.requests.length,3);
  assert.equal(t.requests[2].url,'/api/restore-session');
  assert.equal(JSON.parse(t.requests[2].options.body).cwd,'/home/a/project');
  t.response(2,{ok:false,error:'checksum failure'},400);
  await restoring;
  assert.equal(t.el('#restorePackage').disabled,false);
  assert.match(t.el('#toast').children[0].textContent,/checksum failure/);
});

test('skill storage captures agent, full directory and restore destination without duplicate submission',async()=>{
  const t=setup();
  t.app.buildSkillAgents();
  t.el('#skillAgent').value='codex';
  t.el('#skillPath').value='/source/skill';
  t.el('#skillStorageRoot').value='/usb/storage';
  const storing=t.app.storeSelectedSkill();
  await t.app.storeSelectedSkill();
  assert.equal(t.requests.length,1);
  assert.equal(t.requests[0].url,'/api/store-skill');
  assert.equal(JSON.parse(t.requests[0].options.body).path,'/source/skill');
  t.response(0,{ok:true,path:'/usb/storage/skill.zip',manifest:{skill:{name:'sample'},excluded:['.env']}});
  await new Promise(resolve=>setImmediate(resolve));
  t.response(1,{ok:true,packages:[],root:'/usb/storage'});
  await storing;
  assert.match(t.el('#skillResult').textContent,/\.env/);
  t.el('#skillPackage').value='/usb/storage/skill.zip';
  t.el('#skillTargetAgent').value='claude';
  t.el('#targetSkillsDir').value='/target/skills';
  t.el('#skillName').value='copy';
  const restoring=t.app.restoreSelectedSkill();
  await t.app.restoreSelectedSkill();
  assert.equal(t.requests.length,3);
  const payload=JSON.parse(t.requests[2].options.body);
  assert.equal(payload.agent,'claude');
  assert.equal(payload.skills_dir,'/target/skills');
  assert.equal(payload.name,'copy');
  t.response(2,{ok:false,error:'已有同名 Skill'},409);
  await restoring;
  assert.equal(t.el('#restoreSkill').disabled,false);
  assert.match(t.el('#toast').children[0].textContent,/同名/);
});

test('unreadable source rows show the error and disable export and migration',async()=>{
  const t=setup();
  t.app.state.current={id:'old',source:'workbuddy'};
  await t.app.openSession({id:'compressed',readable:false,error:'install zstandard'});
  assert.equal(t.requests.length,0);
  assert.equal(t.app.state.current,null);
  assert.equal(t.el('#btnGo').disabled,true);
  assert.equal(t.el('#btnMd').disabled,true);
  assert.match(t.el('#content').innerHTML,/install zstandard/);
});

test('a truncated conversation can be exported but cannot be migrated',async()=>{
  const t=setup();
  const opening=t.app.openSession({id:'large'});
  t.response(0,{ok:true,info:{title:'large',truncated:true,stats:{}},turns:[]});
  await opening;
  assert.equal(t.el('#btnGo').disabled,true);
  assert.equal(t.el('#btnMd').disabled,false);
  await t.app.doTransfer();
  assert.equal(t.requests.length,1);
});


test('exit waits for active transfers, suppresses duplicate requests and reports failures',async()=>{
  const t=setup();
  t.app.bind();
  t.app.state.transferring=true;
  await t.el('#btnExit').onclick();
  assert.equal(t.requests.length,0);
  t.app.state.transferring=false;
  const failing=t.el('#btnExit').onclick();
  await t.el('#btnExit').onclick();
  assert.equal(t.requests.length,1);
  assert.equal(t.requests[0].url,'/api/shutdown');
  assert.equal(t.requests[0].options.method,'POST');
  t.requests[0].reject(new Error('offline'));
  await failing;
  assert.equal(t.el('#btnExit').disabled,false);
  assert.match(t.el('#toast').children[0].textContent,/退出失败/);
  const exiting=t.el('#btnExit').onclick();
  await new Promise(resolve=>setImmediate(resolve));
  t.response(1,{ok:true});
  await exiting;
  assert.equal(t.el('#btnExit').disabled,true);
});


test('session checkboxes select only readable rows, support partial selection and reset on filtering',async()=>{
  const t=setup();
  const loading=t.app.loadSessions();
  t.response(0,{ok:true,sessions:[{id:'a',title:'A'},{id:'b',title:'B'},{id:'bad',readable:false}]});
  await loading;
  t.app.selectAll('sessions',true);
  assert.deepEqual([...t.app.selections.sessions.selected],['a','b']);
  assert.equal(t.el('#selectAllSessions').checked,true);
  const input=t.app.selections.sessions.inputs.get('a');
  input.checked=false;input.onchange();
  assert.equal(t.el('#selectAllSessions').indeterminate,true);
  assert.equal(t.app.selections.sessions.inputs.get('bad').disabled,true);
  const filtering=t.app.loadSessions();
  assert.equal(t.app.selections.sessions.selected.size,0);
  assert.equal(t.el('#storeSessions').disabled,true);
  t.response(1,{ok:true,sessions:[]});await filtering;
});

test('batch conversation storage captures source and destination, continues failures and prevents duplicates',async()=>{
  const t=setup();
  const loading=t.app.loadSessions();
  t.response(0,{ok:true,sessions:[{id:'a'},{id:'b'}]});await loading;
  t.app.selectAll('sessions',true);
  t.el('#storageRoot').value='/usb/storage';
  const storing=t.app.storeBatch('sessions');
  await t.app.storeBatch('sessions');
  assert.equal(t.requests.length,2);
  t.app.state.source='codex';t.el('#storageRoot').value='/other';
  t.response(1,{ok:false,error:'exists'},409);
  await new Promise(resolve=>setImmediate(resolve));
  assert.deepEqual(JSON.parse(t.requests[2].options.body),{source:'workbuddy',id:'b',storage:'/usb/storage'});
  t.response(2,{ok:true,path:'/usb/b.zip'});
  await new Promise(resolve=>setImmediate(resolve));
  t.response(3,{ok:true,packages:[],root:'/other'});await storing;
  assert.equal(t.app.state.transferring,false);
  assert.deepEqual([...t.app.selections.sessions.selected],['a']);
  assert.match(t.el('#storageResult').textContent,/成功 1 项，失败 1 项/);
  assert.match(t.el('#storageResult').textContent,/exists/);
});

test('Skill select all saves each readable directory and clears successful selections',async()=>{
  const t=setup();t.el('#skillAgent').value='codex';
  const loading=t.app.loadSkills();
  t.response(0,{ok:true,skills:[{name:'A',path:'/a'},{name:'B',path:'/b'},{name:'bad',path:'/bad',readable:false}]});
  await loading;t.app.selectAll('skills',true);
  assert.equal(t.app.selections.skills.selected.size,2);
  const storing=t.app.storeBatch('skills');
  t.response(1,{ok:true,path:'/a.zip'});
  await new Promise(resolve=>setImmediate(resolve));
  assert.deepEqual(JSON.parse(t.requests[2].options.body),{agent:'codex',path:'/b',storage:null});
  t.response(2,{ok:true,path:'/b.zip'});
  await new Promise(resolve=>setImmediate(resolve));
  t.response(3,{ok:true,packages:[],root:'/storage'});await storing;
  assert.equal(t.app.selections.skills.selected.size,0);
  assert.equal(t.el('#storeSkills').disabled,true);
});

test('late Skill scans cannot overwrite the latest directory and its selections',async()=>{
  const t=setup();t.el('#skillAgent').value='codex';
  const old=t.app.loadSkills();t.el('#skillsDir').value='/new';
  const latest=t.app.loadSkills();
  t.response(1,{ok:true,skills:[{path:'/new/skill',name:'new'}]});await latest;
  t.app.selectAll('skills',true);
  t.response(0,{ok:true,skills:[{path:'/old/skill',name:'old'}]});await old;
  assert.deepEqual([...t.app.selections.skills.selected],['/new/skill']);
});

// ---------- 界面语言 ----------
test('every UI string has an English translation', () => {
  const body = html.split('<script>')[0].split('</head>')[1];
  const strings = new Set();
  for (const m of body.matchAll(/>([^<>]*[\u4e00-\u9fff][^<>]*)</g)) strings.add(m[1].trim());
  for (const m of body.matchAll(/\s(?:placeholder|title|aria-label)="([^"]*[\u4e00-\u9fff][^"]*)"/g)) strings.add(m[1].trim());
  strings.add(html.match(/<title>([^<]*)<\/title>/)[1]);
  for (const m of script.matchAll(/\btr\('((?:[^'\\]|\\.)*)'/g)) strings.add(m[1].replace(/\\n/g, '\n').replace(/\\\\/g, '\\'));
  const t = setup();
  const missing = [...strings].filter(zh => t.app.EN[zh] === undefined && !zh.startsWith('Switch language'));
  assert.deepEqual(missing, []);
  // placeholders in a translation must match the source
  for (const [zh, en] of Object.entries(t.app.EN)) {
    const vars = s => (s.match(/\{\w+\}/g) || []).sort().join();
    assert.equal(vars(en), vars(zh), zh);
  }
});

test('English mode translates client strings and known server messages, and zh restores them', () => {
  const t = setup();
  assert.equal(t.app.getLang(), 'zh');
  t.app.state.sources = [{name: 'codex', label: 'OpenAI Codex', can_write: true, available: true}, {name: 'claude', label: 'Claude Code', can_write: true, available: true}];
  t.app.state.source = 'claude';
  t.app.buildTarget();
  assert.equal(t.el('#target').children[0].textContent.startsWith('迁移到 '), true);
  t.app.setLang('en');
  assert.equal(t.app.getLang(), 'en');
  assert.match(t.el('#target').children[0].textContent, /^Migrate to /);
  assert.equal(t.el('#btnLang').textContent, '中文');
  assert.equal(t.app.tr('已选 {n} 项', {n: 3}), '3 selected');
  assert.equal(t.app.ts('请求体过大'), 'Request body too large');
  assert.equal(t.app.ts('未知块 foo'), 'Unknown block foo');
  assert.match(t.app.ts('SDK 与 Claude Code 共用会话存储；此入口显示共享记录，无法仅凭日志确认创建者。'), /^The SDK and Claude Code share/);
  assert.equal(t.app.ts('没收录的服务端消息'), '没收录的服务端消息');
  t.app.setLang('zh');
  assert.equal(t.el('#btnLang').textContent, 'English');
  assert.equal(t.app.tr('已选 {n} 项', {n: 3}), '已选 3 项');
  assert.equal(t.app.ts('请求体过大'), '请求体过大');
});

test('switching language re-renders the session list and the open conversation without refetching', async () => {
  const t = setup();
  const loading = t.app.loadSessions();
  t.response(0, {ok: true, sessions: [{id: 'a', title: '', turns: 2, updated: 'now', size_str: '1 KB'}]});
  await loading;
  assert.match(t.el('#list').children[0].innerHTML, /未命名会话/);
  assert.match(t.el('#list').children[0].innerHTML, /2 轮/);
  const opening = t.app.openSession({id: 'a'});
  t.response(1, {ok: true, info: {title: '', source: 'codex', stats: {turns: 1, tool_call: 0, thinking: 0}, notes: ['预览描述文件转换效果，不会安装工具或执行历史调用。']},
    turns: [{role: 'user', blocks: []}]});
  await opening;
  const before = t.requests.length;
  t.app.setLang('en');
  assert.equal(t.requests.length, before);
  assert.match(t.el('#list').children[0].innerHTML, /Untitled session/);
  assert.match(t.el('#list').children[0].innerHTML, /2 turns/);
  const hero = t.el('#content').children[0].innerHTML;
  assert.match(hero, /Untitled session/);
  assert.match(hero, /Turns 1 · Tool calls 0 · Thinking 0/);
  assert.match(hero, /The preview describes the file conversion/);
  assert.equal(t.el('#content').children[1].children[0].children[1].children[0].innerHTML.includes('User'), true);
});

test('static page text and attributes are translated and restored from the remembered Chinese original', () => {
  const t = setup();
  const text = {nodeValue: '  对话存储 ', parentNode: {tagName: 'BUTTON'}};
  const script = {nodeValue: '全选当前列表', parentNode: {tagName: 'SCRIPT'}};
  const plain = {nodeValue: 'AgentRelay', parentNode: {tagName: 'DIV'}};
  const input = {attrs: {placeholder: '搜索标题 / 目录 / id…', title: 'abc'}, getAttribute(n) { return n in this.attrs ? this.attrs[n] : null; }, setAttribute(n, v) { this.attrs[n] = v; }};
  t.document.createTreeWalker = () => { const nodes = [text, script, plain]; return {nextNode: () => nodes.shift() || null}; };
  t.document.querySelectorAll = () => [input];
  t.app.setLang('en');
  assert.equal(text.nodeValue, '  Conversation storage ');
  assert.equal(script.nodeValue, '全选当前列表');
  assert.equal(plain.nodeValue, 'AgentRelay');
  assert.equal(input.attrs.placeholder, 'Search title / directory / id…');
  assert.equal(input.attrs.title, 'abc');
  t.document.createTreeWalker = () => { const nodes = [text]; return {nextNode: () => nodes.shift() || null}; };
  t.app.setLang('zh');
  assert.equal(text.nodeValue, '  对话存储 ');
  assert.equal(input.attrs.placeholder, '搜索标题 / 目录 / id…');
});

// ---------- 批量迁移 / 操作记录 / 脱敏 ----------
const flush=()=>new Promise(resolve=>setImmediate(resolve));

test('batch migration previews first, executes only after confirmation and sends the chosen options', async () => {
  const t = setup({confirmed: true});
  t.app.state.source = 'claude'; t.app.state.target = 'codex';
  t.app.selections.sessions.selected.add('a'); t.app.selections.sessions.selected.add('b');
  t.el('#redact').checked = true; t.el('#think').checked = false; t.el('#cwd').value = ' /work ';
  const run = t.app.doBatch();
  const dry = JSON.parse(t.requests[0].options.body);
  assert.equal(t.requests[0].url, '/api/batch');
  assert.deepEqual([dry.dry_run, dry.ids, dry.redact_secrets, dry.include_thinking, dry.cwd, dry.on_conflict], [true, ['a', 'b'], true, false, '/work', 'skip']);
  t.response(0, {ok: true, items: [{id: 'a', title: 'A', status: 'would-migrate'}, {id: 'b', title: 'B', status: 'skipped'}]});
  await flush();
  const live = JSON.parse(t.requests[1].options.body);
  assert.equal(live.dry_run, false);
  t.response(1, {ok: true, migrated: 1, skipped: 1, failed: 1, items: [{id: 'a', status: 'migrated'}, {id: 'c', title: 'C', status: 'failed', error: 'boom'}]});
  await flush();
  assert.equal(t.requests[2].url, '/api/sources');       // the source list is refreshed after writing
  t.response(2, {ok: true, sources: []});
  await run;
  assert.match(t.el('#importResult').textContent, /成功 1 项，跳过 1 项，失败 1 项/);
  assert.match(t.el('#importResult').textContent, /失败 C：boom/);
  assert.equal(t.app.selections.sessions.selected.size, 0);
  assert.equal(t.app.state.transferring, false);
});

test('declining the batch preview never writes, and nothing-to-do stops after the preview', async () => {
  let t = setup({confirmed: false});
  t.app.state.source = 'claude'; t.app.state.target = 'codex';
  t.app.selections.sessions.selected.add('a');
  let run = t.app.doBatch();
  t.response(0, {ok: true, items: [{id: 'a', title: 'A', status: 'would-migrate'}]});
  await run;
  assert.equal(t.requests.length, 1);
  assert.equal(t.app.state.transferring, false);
  t = setup({confirmed: true});
  t.app.state.source = 'claude'; t.app.state.target = 'codex';
  t.app.selections.sessions.selected.add('a');
  run = t.app.doBatch();
  t.response(0, {ok: true, items: [{id: 'a', status: 'skipped'}]});
  await run;
  assert.equal(t.requests.length, 1);
});

test('single transfer carries the redact option', async () => {
  const t = setup();
  t.app.state.current = {source: 'codex', id: 's'}; t.app.state.target = 'claude';
  t.el('#redact').checked = true;
  const pending = t.app.doTransfer();
  await flush();
  const body = JSON.parse(t.requests[0].options.body);
  assert.equal(body.redact_secrets, true);
  t.response(0, {ok: true, to: {source: 'claude', path: '/p'}});
  await pending;
});

test('history lists operations and undo asks for confirmation, then offers force only for kept files', async () => {
  const t = setup({confirmed: true});
  const refresh = t.app.refreshHistory();
  t.response(0, {ok: true, operations: [
    {id: 'op-1', time: '2026-10-09T01:02:03Z', kind: 'transfer', source: 'claude', target: 'codex', title: 'T', created: ['/a'], appended: [], undoable: true},
    {id: 'op-0', time: '2026-10-08T01:02:03Z', kind: 'transfer', source: 'claude', target: 'codex', title: 'old', created: ['/b'], appended: [], undoable: false, undone: {time: '2026-10-08T02:00:00Z'}}]});
  await refresh;
  const rows = t.el('#historyList').children;
  assert.equal(rows.length, 2);
  assert.equal(rows[0].children.length, 2);              // text + undo button
  assert.match(rows[1].children[0].textContent, /已于 .* 撤销/);
  assert.equal(rows[1].children.length, 1);              // already undone: no button
  const undo = rows[0].children[1].onclick();
  await flush();
  assert.equal(t.requests[1].url, '/api/undo');
  assert.deepEqual(JSON.parse(t.requests[1].options.body), {id: 'op-1'});
  t.response(1, {ok: true, removed: [], truncated: [], kept: [{path: '/a', reason: 'changed'}]});
  await flush();
  assert.deepEqual(JSON.parse(t.requests[2].options.body), {id: 'op-1', force: true});
  t.response(2, {ok: true, removed: ['/a'], truncated: [], kept: []});
  await flush();
  t.response(3, {ok: true, operations: []});
  await flush();
  t.response(4, {ok: true, sources: []});
  await undo;
  assert.match(t.el('#historyResult').textContent, /删除 1 个文件/);
});

test('history text uses textContent so session titles cannot inject markup', () => {
  const t = setup();
  t.app.renderHistory([{id: 'x', time: '2026-10-09T00:00:00Z', kind: 'transfer', source: 'claude', target: 'codex', title: '<img src=x onerror=alert(1)>', created: [], appended: []}]);
  const row = t.el('#historyList').children[0];
  assert.equal(row.children[0].textContent.includes('<img'), true);
  assert.equal(row.innerHTML, '');
});

test('secret-scan warnings from the server are translated', () => {
  const t = setup();
  const zh = '检测到 2 处疑似敏感信息（私钥 2 处）：迁移会原样复制到目标软件。可勾选「脱敏密钥」或加 --redact-secrets。';
  t.app.setLang('en');
  assert.match(t.app.ts(zh), /^Found 2 suspected secrets/);
  assert.match(t.app.ts('检测到 1 处疑似敏感信息（JWT 1 处），写入时将替换为 [REDACTED:类型]。'), /replaced with \[REDACTED:type\]/);
  assert.match(t.app.ts('检测到 1 处疑似敏感信息（JWT 1 处）：原生迁移原样复制会话文件，不支持脱敏。'), /native migration copies/);
});

test('task navigation shows one workspace, preserves selection and distinguishes saving from conversion', () => {
  const t=setup();t.app.bind();t.app.state.current={id:'selected',source:'codex'};
  t.app.showPage('home');
  assert.equal(t.el('#homePanel').style.display,'');assert.equal(t.el('#sessionsPanel').style.display,'none');
  t.el('#chooseToStore').onclick();
  assert.equal(t.app.workflow.page,'sessions');assert.equal(t.app.state.current.id,'selected');
  assert.equal(t.el('#migrationSetup').style.display,'none');assert.equal(t.el('#btnGo').style.display,'none');
  t.el('#btnSessions').onclick();
  assert.equal(t.el('#migrationSetup').style.display,'');assert.equal(t.el('#btnSessions')['aria-current'],'page');
  assert.equal(t.app.workflow.carrying,false);
  t.app.showPage('skills');
  assert.equal(t.el('#sessionsPanel').style.display,'none');assert.equal(t.el('#skillPanel').style.display,'');
});

test('a slow package listing cannot overwrite a newer storage root or select an unverified package', async () => {
  const t=setup();t.el('#storageRoot').value='/old';const old=t.app.refreshStorage();
  t.el('#storageRoot').value='/new';const latest=t.app.refreshStorage();
  t.response(1,{ok:true,packages:[{agent:'codex',path:'/new/p.zip',session:{title:'latest'}}]});await latest;
  t.response(0,{ok:true,packages:[{agent:'claude',path:'/old/p.zip'}]});await old;
  const row=t.el('#storageList').children[0];assert.match(row.children[0].textContent,/latest/);
  row.children[1].onclick();assert.equal(t.el('#packagePath').value,'/new/p.zip');
  assert.equal(t.el('#restoreCwd').value,''); // source cwd never becomes the default destination
});

test('restoring an independent copy previews the same new ID before writing, and cancellation never writes', async () => {
  const t=setup({automaticPreview:false,randomUUID:()=> 'new-id'});
  t.el('#restoreConflict').value='new';t.el('#packagePath').value='/p.zip';t.el('#restoreCwd').value='/local';
  const restoring=t.app.restoreStored();const plan=JSON.parse(t.requests[0].options.body);
  assert.equal(t.requests[0].url,'/api/preview');assert.equal(plan.session_id,'new-id');
  t.response(0,{ok:true,token:'copy-preview',blockers:[],target:'codex'});await flush();
  const write=JSON.parse(t.requests[1].options.body);
  assert.equal(write.session_id,'new-id');assert.equal(write.preview_token,'copy-preview');
  t.response(1,{ok:false,error:'目标会话 ID 已存在'},409);await restoring;
  assert.match(t.el('#restoreError').textContent,/创建独立副本/);
  const canceled=setup({confirmed:false,randomUUID:()=> 'copy'});
  canceled.el('#restoreConflict').value='new';canceled.el('#packagePath').value='/p.zip';canceled.el('#restoreCwd').value='/local';
  await canceled.app.restoreStored();assert.equal(canceled.requests.length,0);assert.equal(canceled.previews.length,1);
});

test('generic migration retains the sent ID and keeps a safe, translated result after navigation', async () => {
  const t=setup({randomUUID:()=> 'native-id'});t.app.state.current={id:'s',source:'codex'};
  t.app.state.target='claude';const migrating=t.app.doTransfer();await flush();
  const body=JSON.parse(t.requests[0].options.body);assert.equal(body.session_id,'native-id');
  assert.equal(JSON.parse(t.previews[0].options.body).session_id,'native-id');
  t.response(0,{ok:true,to:{source:'claude',path:'/new/<img>.jsonl',cwd:'/work'}});await migrating;
  assert.equal(t.app.workflow.result.result.to.native_id,'native-id');
  t.app.showPage('home');assert.equal(t.el('#operationResult').style.display,'');
  assert.match(t.el('#operationResult').children[1].children[1].textContent,/<img>/);
  t.app.setLang('en');assert.equal(t.el('#operationResult').children[0].textContent,'Session migrated');
  assert.equal(t.el('#operationResult').children[1].children[1].innerHTML,'');
});

test('export-to-package handoff uses the successfully exported directory without an implicit write', async () => {
  const t=setup();t.app.bind();t.app.corpusState.selected='draft';
  t.el('#confirmDraft').checked=true;t.el('#draftDirectory').value='C:\\reviewed';t.el('#draftMarkdown').value='reviewed text';
  const exporting=t.app.exportDraft();t.response(0,{ok:true,path:'C:\\reviewed\\release-check\\SKILL.md'});await exporting;
  assert.equal(t.el('#storeExportedDraft').style.display,'');t.el('#storeExportedDraft').onclick();
  assert.equal(t.app.workflow.page,'skills');assert.equal(t.el('#skillPath').value,'C:\\reviewed\\release-check');
  assert.equal(t.requests.length,2);assert.match(t.requests[1].url,/^\/api\/stored-skills/);
  assert.equal(t.requests.some(r=>r.url==='/api/store-skill'),false);
  t.response(1,{ok:true,packages:[],root:'/storage'});await flush();
});
