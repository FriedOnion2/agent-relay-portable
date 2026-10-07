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
  vm.runInContext(script + '\n globalThis.app={state,loadSessions,openSession,doTransfer,bind};',context);
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
  assert.equal(t.app.state.current.source,'dsh');
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
