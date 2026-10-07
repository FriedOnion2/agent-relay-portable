const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, '../app/web/index.html'), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1].split('\ninit().catch')[0];

function setup(){
  class Element {
    constructor(){ this.children=[]; this.value=''; this.checked=true; this.disabled=false;
      this.style={}; this.dataset={}; this.classList={add(){}, remove(){}}; this._html=''; }
    set innerHTML(value){this._html=value; this.children=[];}
    get innerHTML(){return this._html;}
    appendChild(child){this.children.push(child); return child;}
  }
  const elements = new Map();
  const requests=[];
  const document={
    querySelector(selector){if(!elements.has(selector)) elements.set(selector,new Element()); return elements.get(selector);},
    querySelectorAll(){return [];},
    createElement(){return new Element();},
    createTextNode(text){return {textContent:text};},
  };
  const context = vm.createContext({document, encodeURIComponent, Blob, URL, navigator:{},
    setTimeout(){return 1;}, clearTimeout(){},
    fetch(url,options){return new Promise((resolve,reject)=>requests.push({url,options,resolve,reject}));},
  });
  vm.runInContext(script + '\n globalThis.app={state,loadSessions,openSession,doTransfer,doImportWindows,updateActions,bind,buildTarget,buildTabs,loadSources};',context);
  const response = (index,body,status=200)=>requests[index].resolve({ok:status<400,status,json:async()=>body});
  return {app:context.app, elements, requests, response, el:document.querySelector};
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
  t.response(0,{ok:false,error:'先创建原生工作区'},400);
  await importing;
  assert.equal(t.app.state.transferring,false);
  assert.equal(t.el('#btnImport').disabled,false);
  assert.match(t.el('#toast').children[0].textContent,/原生工作区/);
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
