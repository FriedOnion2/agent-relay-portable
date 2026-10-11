// 会话列表与详情
// 经典脚本，由 index.html 按顺序加载并共享全局作用域。
/* ================= 列表 ================= */
async function loadSessions(){
  selections.sessions=newSelection();
  const request = ++state.listRequest;
  const source = state.source;
  ++state.sessionRequest;
  state.current = null;
  state.detail = null;
  updateActions();
  $('#content').innerHTML = '<div class="placeholders">'+esc(tr('ui.pick_a_session_on_the_left'))+'</div>';
  $('#cwd').value = '';
  $('#projectPath').value = '';
  $('#importId').value = '';
  $('#importResult').style.display = 'none';
  const box = $('#list');
  box.innerHTML = '<div class="empty">'+esc(tr('ui.loading'))+'</div>';
  buildTarget();
  const q = encodeURIComponent($('#q').value.trim());
  let r;
  try{
    r = await api(`/api/sessions?agent=${source}&q=${q}`);
  }catch(e){
    if(request === state.listRequest) box.innerHTML = `<div class="empty">${esc(tr('ui.request_failed_error',{error:e.message}))}</div>`;
    return;
  }
  if(request !== state.listRequest || source !== state.source) return;
  state.sessions = r.sessions || [];
  selections.sessions.rows=state.sessions;
  updateSelections();
  renderList();
}
function renderList(){
  const box = $('#list');
  if(state.listRequest === 0) return;
  box.innerHTML = '';
  selections.sessions.inputs.clear();
  if(!state.sessions.length){
    box.innerHTML = '<div class="empty">'+esc(tr('ui.no_sessions'))+'<p>'+esc(tr('ui.switch_sources_clear_the_title_filter_or_configure_directories_under_environment'))+'</p></div>';
    const configure=document.createElement('button');configure.className='btn';configure.textContent=tr('ui.configure_directories');configure.onclick=()=>$('#btnEnvironment').onclick();box.appendChild(configure);
    return;
  }
  state.sessions.forEach(s=>{
    const el = document.createElement('div');
    el.className = 'item';
    el.dataset.id = s.id;
    el.innerHTML = `
      <h4><button class="session-title" type="button">${esc(s.title || tr('ui.untitled_session'))}</button></h4>
      <div class="meta">
        <span title="${esc(tr('ui.updated'))}">${esc(s.updated)}</span>
        <span>${esc(s.readable===false?tr('ui.restricted'):s.turns===1?tr('ui.step_1_turn'):tr('ui.n_turns',{n:s.turns}))}</span>
        ${s.shared_store?'<span>'+esc(tr('ui.shared_claude_records'))+'</span>':''}
        ${s.variant_count>1?'<span>'+esc(tr('ui.n_records_with_the_same_native_id',{n:s.variant_count}))+'</span>':''}
        <span>${esc(s.size_str)}</span>
      </div>
      ${s.variant_count>1?'<div class="meta">'+esc(tr('ui.native_id_id',{id:s.native_id}))+'</div><div class="meta">'+esc(tr('ui.file_path',{path:s.path}))+'</div>':''}`;
    el.appendChild(selectionCheckbox('sessions',s));
    el.title = `${s.id}\n${s.cwd||''}\n${s.path}\n${tm(s,'error')||''}`;
    if(state.current && state.current.id === s.id) el.classList.add('on');
    el.onclick = ()=>{
      document.querySelectorAll('.item.on').forEach(x=>x.classList.remove('on'));
      el.classList.add('on');
      openSession(s);
    };
    box.appendChild(el);
  });
  updateSelections();
}

/* ================= 详情 ================= */
async function openSession(s){
  const request = ++state.sessionRequest;
  const source = state.source;
  state.current = null;
  state.detail = null;
  updateActions();
  const main = $('#content');
  if(s.readable===false){
    main.innerHTML = `<div class="placeholders">${esc(tm(s,'error')||tr('ui.this_session_cannot_be_read_right_now'))}</div>`;
    return;
  }
  main.innerHTML = '<div class="placeholders">'+esc(tr('ui.reading'))+'</div>';
  $('#btnGo').disabled = true; $('#btnMd').disabled = true;
  let r;
  try{
    r = await api(`/api/session?agent=${source}&id=${encodeURIComponent(s.id)}`);
  }catch(e){
    if(request === state.sessionRequest) main.innerHTML = `<div class="placeholders">${esc(tr('ui.failed_to_read_error',{error:e.message}))}</div>`;
    return;
  }
  if(request !== state.sessionRequest || source !== state.source) return;

  state.current = {id:s.id, title:r.info.title, truncated:!!r.info.truncated, source};
  state.detail = {r, source};
  updateActions();
  renderDetail();
}
function renderDetail(){
  if(!state.detail) return;
  const {r, source} = state.detail;
  const main = $('#content');
  $('#cwd').placeholder = nativeMode(source)==='import-windows' ? tr('ui.required_ubuntu_project_directory_home') :
    (nativeMode(source) ? tr('ui.windows_project_path_d_project') :
    (r.info.cwd ? tr('ui.original_directory_cwd',{cwd:r.info.cwd}) : tr('ui.target_working_directory')));

  const i = r.info, st = i.stats || {};
  const hero = document.createElement('div');
  hero.className = 'hero';
  hero.innerHTML = `
    <h2>${esc(i.title || tr('ui.untitled_session'))}</h2>
    <div class="sub">
      <span>${esc(tr('ui.source'))} <b>${esc(i.source)}</b></span>
      <span>${esc(tr('ui.turns_turns_tool_calls_tools_thinking_thinking',{turns:st.turns||0,tools:st.tool_call||0,thinking:st.thinking||0}))}</span>
      ${i.model ? `<span>${esc(tr('ui.model'))} <code>${esc(i.model)}</code></span>` : ''}
      ${i.created_at ? `<span>${esc(i.created_at)} → ${esc(i.updated_at||'')}</span>` : ''}
    </div>
    ${i.truncated ? '<div class="warn">'+esc(tr('ui.the_source_file_exceeds_the_read_limit_only_the_part_that_was_read_can_be_export'))+'</div>' : ''}
    ${(i.notes_messages||i.notes||[]).map(n=>`<div class="warn">${esc(ts(n))}</div>`).join('')}
  `;

  const feed = document.createElement('div');
  feed.className = 'feed';
  const shown = r.turns.slice(0, state.turnLimit);
  shown.forEach(t=>feed.appendChild(renderTurn(t)));
  if(r.turns.length > shown.length){
    const more = document.createElement('button');
    more.className = 'btn';
    more.style.margin = '0 auto';
    more.textContent = tr('ui.show_the_remaining_n_turns',{n:r.turns.length - shown.length});
    more.onclick = ()=>{
      const rest = document.createDocumentFragment();
      r.turns.slice(state.turnLimit).forEach(t=>rest.appendChild(renderTurn(t)));
      feed.insertBefore(rest, more);
      more.remove();
    };
    feed.appendChild(more);
  }

  main.innerHTML = '';
  main.appendChild(hero);
  main.appendChild(feed);
}

function renderTurn(t){
  const el = document.createElement('div');
  el.className = 'turn ' + (t.role === 'user' ? 'u' : 'a');
  const av = document.createElement('div');
  av.className = 'avatar';
  av.textContent = t.role === 'user' ? 'U' : t.role === 'system' ? 'S' : 'A';
  const bub = document.createElement('div');
  bub.className = 'bubble';

  const who = document.createElement('div');
  who.className = 'who';
  who.innerHTML = `<span>${esc(t.role === 'user' ? tr('ui.user') : t.role === 'system' ? tr('ui.system_context') : tr('ui.assistant'))}</span>${t.ts ? `<span>${esc(t.ts)}</span>`:''}${t.model?`<span>${esc(t.model)}</span>`:''}`;
  bub.appendChild(who);

  const blocks = t.blocks || [];
  if(!blocks.length){
    const b = document.createElement('div');
    b.className = 'body';
    b.textContent = t.text || tr('ui.empty');
    bub.appendChild(b);
  }
  blocks.forEach(b=>bub.appendChild(renderBlock(b)));
  el.appendChild(av); el.appendChild(bub);
  return el;
}

function renderBlock(b){
  if(b.kind === 'text'){
    const d = document.createElement('div');
    d.className = 'body';
    d.textContent = b.text;
    return d;
  }
  if(b.kind === 'thinking'){
    const d = document.createElement('details');
    d.innerHTML = '<summary>'+esc(tr('ui.thinking'))+'</summary>';
    const p = document.createElement('div');
    p.className = 'think';
    p.textContent = b.text;
    d.appendChild(p);
    return d;
  }
  if(b.kind === 'tool_call'){
    const d = document.createElement('div');
    d.className = 'tool';
    const arg = b.arguments && b.arguments.length > 600 ? b.arguments.slice(0,600)+'\n'+tr('ui.truncated') : b.arguments;
    d.innerHTML = `<div class="hd">🔧 <b>${esc(b.name)}</b><code class="k">${esc((b.call_id||'').slice(0,24))}</code></div>`;
    const pre = document.createElement('pre');
    pre.textContent = arg || '';
    d.appendChild(pre);
    return d;
  }
  if(b.kind === 'tool_result'){
    const d = document.createElement('div');
    d.className = 'tool';
    d.innerHTML = `<div class="hd">${b.is_error?'❌':'📤'} ${esc(tr('ui.tool_result'))}<code class="k">${esc((b.call_id||'').slice(0,24))}</code></div>`;
    const pre = document.createElement('pre');
    let out = b.output || '';
    if(out.length > 1500) out = out.slice(0,1500) + '\n' + tr('ui.truncated_n_characters_in_total',{n:out.length});
    pre.textContent = out;
    d.appendChild(pre);
    return d;
  }
  if(b.kind === 'raw'){
    const d = document.createElement('details');
    d.innerHTML = '<summary>'+esc(tr('ui.raw_content_block_unconverted_fields_kept'))+'</summary>';
    const pre = document.createElement('pre');
    const raw = JSON.stringify(b.meta || {}, null, 2);
    pre.textContent = raw.length > 12000 ? raw.slice(0,12000)+'\n'+tr('ui.preview_truncated_export_to_see_everything') : raw;
    d.appendChild(pre);
    return d;
  }
  const d = document.createElement('div');
  d.className = 'body';
  d.style.color = 'var(--text-3)';
  d.textContent = b.kind === 'image' ? tr('ui.image') : tr('ui.unknown_block_kind',{kind:b.kind});
  return d;
}
