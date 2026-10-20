// 启动、来源与目标选择、事件绑定
// 经典脚本，由 index.html 按顺序加载并共享全局作用域。
/* ================= 初始化 ================= */
async function init(){
  await RelayI18n.load();
  if(lang !== 'zh') applyLang();
  $('#btnLang').textContent = lang === 'en' ? '中文' : 'English';
  await loadSources();
  buildTabs();
  buildTarget();
  bind();
  await loadSessions();
  showPage('home',false);
  const evidence=new URLSearchParams(globalThis.location?.search||'').get('document');
  if(evidence){await openCorpus();await openCorpusDocument(evidence);}
}

async function loadSources(){
  const r = await api('/api/sources');
  state.sources = r.sources || [];
  buildBackupAgents();
  renderChips();
  renderHome();
  if (!state.listRequest && !(r.sources||[]).some(s=>s.available && s.name===state.source)){
    const first = (r.sources||[]).find(s=>s.available);
    if (first) state.source = first.name;
  }
}

function renderChips(){
  const box = $('#chips'); box.innerHTML = '';
  state.sources.forEach(s=>{
    const el = document.createElement('span');
    el.className = 'chip' + (s.available ? '' : ' off');
    el.title = [s.homes ? s.homes.join('\n') : s.home, tm(s,'read_note'), tm(s,'write_note'), tm(s,'error')].filter(Boolean).join('\n');
    el.innerHTML = `<i class="dot"></i>${esc(tm(s,'label')||s.name)}${s.can_write===false?esc(tr('ui.read_only')):''} <b>${s.session_count||0}</b>`;
    box.appendChild(el);
  });
}

function buildTabs(){
  const box = $('#tabs'); box.innerHTML='';
  const note = tm(state.sources.find(s=>s.name===state.source),'read_note') ||
    (state.source==='claude_sdk'?tr('ui.the_sdk_and_claude_code_share_one_session_store_this_tab_shows_the_shared_record'):'');
  const sourceInfo = state.sources.find(s=>s.name===state.source);
  const location = sourceInfo?.homes?.join(tr('ui.semicolon')) || sourceInfo?.home || '';
  const fullNote = [note, location ? tr('ui.read_from') + location : '', tm(sourceInfo,'error')].filter(Boolean).join('\n');
  $('#sourceNote').textContent = fullNote;
  $('#sourceNote').style.display = fullNote ? '' : 'none';
  $('#yuanbaoImport').style.display = state.source === 'yuanbao' ? '' : 'none';
  const labels = {...AGENTS};
  state.sources.forEach(s=>{ labels[s.name] = tm(s,'label') || s.name; });
  Object.keys(labels).forEach(k=>{
    const b = document.createElement('button');
    b.className = 'tab' + (k===state.source?' on':'');
    b.textContent = labels[k];
    b.onclick = ()=>{ if(state.source===k) return; state.source=k; buildTabs(); loadSessions(); };
    box.appendChild(b);
  });
}

function buildTarget(){
  const sel = $('#target'); sel.innerHTML='';
  const opts = [...new Set([...Object.keys(AGENTS),...state.sources.map(s=>s.name)])].filter(k=>k!==state.source &&
    (state.sources.find(s=>s.name===k)?.can_write ?? ['workbuddy','workbuddy_ai','dsh','claude','codex'].includes(k)));
  const same = state.source.replace(/^(windows_|ubuntu_)/,'');
  state.target = opts.includes(same) ? same : (opts.includes(state.target) ? state.target : opts[0]);
  opts.forEach(k=>{
    const o = document.createElement('option');
    o.value = k; o.textContent = tr('ui.migrate_to_name',{name:AGENTS[k]||tm(state.sources.find(s=>s.name===k),'label')||k});
    sel.appendChild(o);
  });
  sel.value = state.target;
  updateActions();
}

let exitPending=false;
async function exitService(){
  const btn = $('#btnExit');
  if(state.transferring || btn.disabled || exitPending) return;
  exitPending = true;
  try{
    if(!await askConfirm(tr('ui.stop_service_2'),[{meta:tr('ui.stop_the_agentrelay_service_other_pages_using_it_will_be_disconnected_too')}],tr('ui.stop_the_agentrelay_service_other_pages_using_it_will_be_disconnected_too'),tr('ui.stop_service_2'))) return;
    btn.disabled = true;
    try{
      await api('/api/shutdown', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
      document.body.innerHTML = '<main style="padding:40px"><h2>'+esc(tr('ui.agentrelay_is_exiting'))+'</h2><p>'+esc(tr('ui.the_service_will_stop_once_running_requests_finish_you_can_close_this_page_run_t'))+'</p></main>';
    }catch(e){
      toast(tr('ui.failed_to_stop_error',{error:e.message}), true);
      btn.disabled = false;
    }
  }finally{ exitPending = false; }
}

function bind(){
  bindWorkflow();
  $('#btnCorpus').onclick=openCorpus;
  $('#closeCorpus').onclick=()=>{showPage('sessions');};
  $('#updateCorpus').onclick=()=>startCorpusJob('index');
  $('#extractDrafts').onclick=()=>startCorpusJob('extract');
  $('#cancelCorpus').onclick=cancelCorpusJob;
  $('#searchCorpus').onclick=()=>searchCorpus(0);
  $('#moreCorpus').onclick=()=>searchCorpus(corpusState.offset+50);
  $('#confirmDraft').onchange=updateDraftAction;
  $('#draftMarkdown').oninput=()=>{$('#confirmDraft').checked=false;updateDraftAction();};
  $('#draftDirectory').oninput=updateDraftAction;
  $('#exportDraft').onclick=exportDraft;
  $('#btnEnvironment').onclick=async()=>{
    showPage('environment');
    const selector=$('#deviceAgent');selector.innerHTML='';
    const homes={...AGENTS};
    for(const prefix of ['windows','ubuntu']){
      const key=prefix+'_workbuddy_ai';
      if(state.sources.some(source=>source.name===key))homes[key]=prefix+' · '+AGENTS.workbuddy_ai;
    }
    for(const [key,label] of Object.entries(homes)){
      const option=document.createElement('option');option.value=key;option.textContent=label;selector.appendChild(option);
    }
    try{showEnvironment(await api('/api/environment'));}catch(e){toast(e.message,true);}
  };
  $('#closeEnvironment').onclick=()=>{showPage('sessions');};
  $('#saveDeviceHome').onclick=saveDeviceHome;
  $('#importYuanbao').onclick=importYuanbao;
  $('#runHealth').onclick=runHealth;
  $('#selectAllSessions').onchange=e=>selectAll('sessions',e.target.checked);
  $('#selectAllSkills').onchange=e=>selectAll('skills',e.target.checked);
  $('#storeSessions').onclick=()=>storeBatch('sessions');
  $('#batchMigrate').onclick=doBatch;
  $('#btnHistory').onclick=openHistory;
  $('#refreshHistory').onclick=refreshHistory;
  $('#closeHistory').onclick=()=>{showPage('sessions');};
  $('#storeSkills').onclick=()=>storeBatch('skills');
  $('#btnExit').onclick = exitService;
  $('#btnLang').onclick = ()=>setLang(lang === 'en' ? 'zh' : 'en');
  $('#btnSkillStorage').onclick = ()=>{
    showPage('skills'); buildSkillAgents();
    $('#skillStorageRoot').value=$('#storageRoot').value;
    loadSkills(); refreshSkillPackages();
  };
  $('#closeSkills').onclick = ()=>{showPage('sessions');};
  $('#discoverSkills').onclick=loadSkills;
  $('#skillAgent').onchange=loadSkills;
  $('#storeSkill').onclick=storeSelectedSkill;
  $('#refreshSkillPackages').onclick=refreshSkillPackages;
  $('#restoreSkill').onclick=restoreSelectedSkill;
  $('#btnStore').onclick = storeCurrent;
  $('#btnStorage').onclick = ()=>{ showPage('storage'); refreshStorage(); };
  $('#closeStorage').onclick = ()=>{ showPage('sessions'); };
  $('#refreshStorage').onclick = refreshStorage;
  $('#restorePackage').onclick = restoreStored;
  $('#target').onchange = e => {state.target = e.target.value; updateActions();};
  $('#cwd').oninput = updateActions;
  $('#projectPath').oninput = updateActions;
  let timer;
  $('#q').oninput = e => { clearTimeout(timer); timer = setTimeout(loadSessions, 260); };
  $('#btnGo').onclick = doTransfer;
  $('#btnImport').onclick = doImportWindows;
  $('#btnNewId').onclick = ()=>{
    const id = globalThis.crypto?.randomUUID?.();
    if(id) $('#importId').value = id;
    else toast(tr('ui.this_browser_cannot_generate_a_uuid_enter_a_new_session_id_manually'),true);
  };
  $('#btnMd').onclick = async ()=>{
    if(!state.current) return;
    const selected = state.current;
    try{
      const r = await api('/api/export-md', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({source:selected.source, id:selected.id,
          include_thinking:$('#think').checked, include_tools:true, lang})
      });
      download(`${(selected.title||'session').slice(0,40).replace(/[<>:"/\\|?*\x00-\x1f]/g,'_')}.md`, r.markdown);
      toast(tr('ui.markdown_downloaded'));
    }catch(e){ toast(tr('ui.export_failed_error',{error:e.message}), true); }
  };
}
