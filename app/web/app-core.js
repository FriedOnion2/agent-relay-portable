// 全局状态、界面语言、API 调用、勾选与按钮状态、toast
// 经典脚本，由 index.html 按顺序加载并共享全局作用域。
const AGENTS = {workbuddy:'WorkBuddy', dsh:'DeepSeek Harness', codebuddy:'CodeBuddy', claude:'Claude Code', claude_sdk:'Claude Agent SDK', codex:'OpenAI Codex', yuanbao:'Tencent Yuanbao'};
const state = {source:'workbuddy', target:'claude', sources:[], sessions:[], current:null, turnLimit:40,
  listRequest:0, sessionRequest:0, transferring:false, detail:null, yuanbaoResult:null};

const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

/* ================= 国际化：界面语言（zh / en） ================= */
const LANG_KEY = 'agentrelay.lang';
function detectLang(){
  try{
    const asked = new URLSearchParams(globalThis.location?.search || '').get('lang');
    if(asked === 'en' || asked === 'zh') return asked;
    const saved = globalThis.localStorage?.getItem(LANG_KEY);
    if(saved === 'en' || saved === 'zh') return saved;
  }catch(e){}
  const nav = globalThis.navigator?.language || '';
  return !nav || /^zh/i.test(nav) ? 'zh' : 'en';
}
let lang = detectLang();
function tr(key, vars){return RelayI18n.translate(lang,key,vars);}
function sep(){return lang === 'en' ? ': ' : '：';}
const PLACEHOLDER_TITLES = {'未命名会话':'ui.untitled_session', 'Claude 读取受限':'ui.claude_read_restricted',
  'DSH 会话':'ui.dsh_session_title', 'CodeBuddy 会话':'ui.codebuddy_session_title'};
function displayTitle(title){const key = PLACEHOLDER_TITLES[title]; return key ? tr(key) : title;}
function ts(value){return RelayI18n.message(lang,value);}
function tm(row,field){return ts(row?.[field+'_message'] ?? row?.[field]);}
function tms(row,field){return (row?.[field+'_messages'] ?? row?.[field] ?? []).map(ts);}
function applyStatic(){RelayI18n.apply(lang,document);}
function setLang(next){
  if(next !== 'zh' && next !== 'en') return;
  lang = next;
  try{globalThis.localStorage?.setItem(LANG_KEY, lang);}catch(e){}
  applyLang();
}
function applyLang(){
  document.title = tr('ui.agentrelay_conversation_migration');
  if(document.documentElement) document.documentElement.lang = lang === 'en' ? 'en' : 'zh-CN';
  applyStatic();
  $('#btnLang').textContent = lang === 'en' ? '中文' : 'English';
  renderChips();
  buildTabs();
  buildTarget();
  renderList();
  renderDetail();
  updateActions();
  renderHome();renderWorkflow();renderOperationResult();renderYuanbaoResult();renderSelectedPackage();
  if(corpusState.indexStatus)renderIndexSummary(corpusState.indexStatus);
  if(corpusState.resultCount!=null)renderSearchSummary(corpusState.resultCount);
}

async function api(url, options){
  const response = await fetch(url, options);
  const result = await response.json();
  if(!response.ok || !result.ok){
    const error=new Error(tm(result,'error') || tr('ui.request_failed_status',{status:response.status}));
    error.error_message=result.error_message;throw error;
  }
  return result;
}

function newSelection(){return {rows:[], selected:new Set(), inputs:new Map()};}
const selections = {sessions:newSelection(), skills:newSelection()};
const selectionUI = {
  sessions:['#selectAllSessions','#sessionSelectionCount','#storeSessions'],
  skills:['#selectAllSkills','#skillSelectionCount','#storeSkills']
};
function updateSelections(){
  for(const [kind, group] of Object.entries(selections)){
    const [all, count, button] = selectionUI[kind];
    const community = kind==='sessions' && state.sources.find(s=>s.name===state.source)?.community;
    const eligible = community ? [] : group.rows.filter(row=>row.readable!==false && !row.truncated);
    const eligibleKeys = new Set(eligible.map(row=>kind==='sessions'?row.id:row.path));
    $(all).checked = eligible.length>0 && group.selected.size===eligible.length;
    $(all).indeterminate = group.selected.size>0 && group.selected.size<eligible.length;
    $(all).disabled = !eligible.length || state.transferring;
    $(count).textContent = tr('ui.n_selected',{n:group.selected.size});
    $(button).disabled = !group.selected.size || state.transferring;
    if(kind==='sessions') $('#batchMigrate').disabled = !group.selected.size || state.transferring || !state.target || !!community;
    for(const [key,input] of group.inputs){
      input.checked = group.selected.has(key);
      input.disabled = state.transferring || !eligibleKeys.has(key);
    }
  }
}
function selectAll(kind, checked){
  const group = selections[kind];
  if(state.transferring) return;
  group.selected.clear();
  if(checked) for(const row of group.rows){
    if(row.readable!==false && !row.truncated) group.selected.add(kind==='sessions'?row.id:row.path);
  }
  updateSelections();
}
function selectionCheckbox(kind, row){
  const group=selections[kind], key=kind==='sessions'?row.id:row.path;
  const input=document.createElement('input');input.type='checkbox';input.checked=false;
  input.setAttribute('aria-label',tr('ui.select_name',{name:row.title||row.name||key}));
  input.onclick=e=>e.stopPropagation();
  input.onchange=()=>{
    if(state.transferring) return;
    if(input.checked) group.selected.add(key);else group.selected.delete(key);
    updateSelections();
  };
  group.inputs.set(key,input);
  return input;
}
async function storeBatch(kind){
  if(state.transferring) return;
  const group=selections[kind];
  const rows=group.rows.filter(row=>group.selected.has(kind==='sessions'?row.id:row.path));
  if(!rows.length) return;
  const agent=kind==='sessions'?state.source:$('#skillAgent').value;
  const storage=$(kind==='sessions'?'#storageRoot':'#skillStorageRoot').value.trim()||null;
  const result=$(kind==='sessions'?'#storageResult':'#skillResult');
  result.style.display='';
  if(kind==='sessions') showPage('storage');
  state.transferring=true;updateActions();
  const lines=[];let succeeded=0, completed=0;
  try{
    for(const row of rows){
      const key=kind==='sessions'?row.id:row.path;
      result.textContent=tr('ui.storing_i_n',{i:completed+1,n:rows.length});
      try{
        const payload=kind==='sessions'?{source:agent,id:key,storage}:{agent,path:key,storage};
        const r=await api(kind==='sessions'?'/api/store-session':'/api/store-skill',{
          method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
        succeeded++;lines.push(tr('ui.stored_name_path',{name:row.title||row.name||key,path:r.path}));
        group.selected.delete(key);
      }catch(e){lines.push(tr('ui.failed_name_error',{name:row.title||row.name||key,error:e.message}));}
      completed++;
    }
    result.textContent=tr('ui.done_ok_succeeded_bad_failed',{ok:succeeded,bad:rows.length-succeeded})+'\n'+lines.join('\n');
    if(kind==='sessions') await refreshStorage();else await refreshSkillPackages();
  }finally{state.transferring=false;updateActions();}
}

function nativeMode(source=state.source){
  if(source.startsWith('windows_')) return 'import-windows';
  if(source.startsWith('ubuntu_')) return 'import-ubuntu';
  return state.sources.find(s=>s.name===source)?.native_export ? 'export-windows' : '';
}

function updateActions(){
  updateSelections();
  $('#btnExit').disabled = state.transferring;
  $('#importYuanbao').disabled = state.transferring;
  $('#btnGo').disabled = !state.current || state.current.truncated || !state.target || state.transferring;
  const mode = nativeMode();
  const native = !!mode;
  $('#btnImport').style.display = native ? '' : 'none';
  $('#importId').style.display = native ? '' : 'none';
  $('#btnNewId').style.display = native ? '' : 'none';
  $('#projectPath').style.display = mode==='export-windows' ? '' : 'none';
  $('#projectPathField').style.display = mode==='export-windows' ? '' : 'none';
  $('#nativeOptions').style.display = native ? '' : 'none';
  renderWorkflow();
  if(!state.transferring) $('#btnImport').textContent = mode==='import-windows' ? tr('ui.migrate_to_the_ubuntu_counterpart') : tr('ui.migrate_to_the_windows_counterpart');
  $('#btnImport').title = tr('ui.same_app_migration_keeps_the_complete_native_record_adapt_tool_names_and_keep_th');
  $('#btnImport').disabled = !native || !state.current || state.current.truncated ||
    !$('#cwd').value.trim() || (mode==='export-windows' && !$('#projectPath').value.trim()) || state.transferring;
  $('#btnMd').disabled = !state.current;
  $('#btnStore').disabled = !state.current || state.current.truncated || state.transferring ||
    !!state.sources.find(s=>s.name===state.source)?.community;
}

function toast(msg, bad=false, action=null){
  const t = $('#toast');
  t.className = 'toast show' + (bad ? ' bad' : '');
  t.innerHTML = '';
  t.appendChild(document.createTextNode(msg));
  if (action){
    const b = document.createElement('button');
    b.textContent = action.label;
    b.onclick = action.fn;
    t.appendChild(b);
  }
  clearTimeout(t._t);
  t._t = setTimeout(()=>{ t.className = 'toast' + (bad?' bad':''); }, action ? 7000 : 3200);
}

function download(name, text){
  const b = new Blob([text], {type:'text/markdown;charset=utf-8'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(b);
  a.download = name;
  a.click();
  setTimeout(()=>URL.revokeObjectURL(a.href), 1000);
}
