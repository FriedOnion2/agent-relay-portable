// Windows 导入、迁移、批量迁移
// 经典脚本，由 index.html 按顺序加载并共享全局作用域。
async function doImportWindows(){
  const selected = state.current;
  const btn = $('#btnImport');
  const mode = selected && nativeMode(selected.source);
  if(!selected || btn.disabled || state.transferring || !mode) return;
  const payload = {source:selected.source, id:selected.id, cwd:$('#cwd').value.trim(),
                   session_id:$('#importId').value.trim() || null};
  if(mode==='export-windows') payload.project_path = $('#projectPath').value.trim();
  if(!payload.cwd) return toast(tr('ui.enter_the_target_project_directory_first'),true);
  state.transferring = true;
  btn.innerHTML = tr('ui.span_class_spinner_span_importing');
  updateActions();
  try{
    const token=await confirmMigration(payload,mode);if(!token) return;
    payload.preview_token=token;
    const r = await api('/api/'+mode,{
      method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)
    });
    const result = $('#importResult');
    result.innerHTML = '';
    const details = document.createElement('div');
    const targetOS = r.target_os || (mode==='import-windows' ? 'Ubuntu' : 'Windows');
    details.textContent = tr('ui.migrated_to_os_agent_session_id_id_file_path',{os:targetOS,agent:AGENTS[r.to.source.replace(/^(windows_|ubuntu_)/,'')],id:r.to.native_id,path:r.to.path}) +
      (r.resume_command ? tr('ui.resume_command_cmd_2',{cmd:r.resume_command}) : '') + '\n' + tms(r,'notes').join('\n');
    result.appendChild(details);
    const button = document.createElement('button');
    button.className = 'btn';
    button.textContent = tr('ui.view_os_session',{os:targetOS});
    button.onclick = async()=>{
      try{
        state.source = r.to.source;
        await loadSources();
        buildTabs();
        await loadSessions();
        const row = state.sessions.find(s=>s.id===r.to.id);
        if(row) await openSession(row);
        else toast(tr('ui.search_for_the_session_id_in_the_target_source'),true);
      }catch(e){toast(tr('ui.refresh_failed_error',{error:e.message}),true);}
    };
    result.appendChild(button);
    result.style.display = '';
    showOperationResult(r,'ui.native_session_migrated');
    toast(tr('ui.migrated_to_the_os_counterpart',{os:targetOS}));
    await loadSources();
  }catch(e){toast(tr('ui.import_failed_error',{error:e.message}),true);}
  finally{
    state.transferring = false;
    updateActions();
  }
}

async function doTransfer(){
  const btn = $('#btnGo');
  if(!state.current || btn.disabled) return;
  state.transferring = true;
  btn.innerHTML = tr('ui.span_class_spinner_span_migrating');
  btn.disabled = true;
  updateActions();
  const payload = {
    source: state.current.source,
    id: state.current.id,
    target: state.target,
    cwd: (nativeMode(state.current.source)==='export-windows' ? $('#projectPath').value : $('#cwd').value).trim() || null,
    remap_tools: $('#remap').checked,
    include_thinking: $('#think').checked,
    redact_secrets: $('#redact').checked,
  };
  // Keep the ID we send to the writer for the completion card. Older browsers
  // can still use the writer's default ID and locate the result by file path.
  const sessionId=globalThis.crypto?.randomUUID?.();
  if(sessionId)payload.session_id=sessionId;
  let r;
  try{
    const token=await confirmMigration(payload);if(!token) return;
    payload.preview_token=token;
    r = await api('/api/transfer', {
      method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)
    });
  }catch(e){
    return toast(tr('ui.migration_failed_error',{error:e.message}), true);
  }finally{
    state.transferring = false;
    btn.textContent = tr('ui.migrate_to_target');
    updateActions();
  }
  if(sessionId)r.to.native_id=sessionId;
  showOperationResult(r,'ui.session_migrated');
  const p = r.to.path;
  toast(tr('ui.migrated_to_agent_path',{agent:AGENTS[r.to.source],path:p}), false, {
    label:tr('ui.copy_path'),
    fn:()=>{ navigator.clipboard?.writeText(p).then(()=>toast(tr('ui.path_copied')),()=>{}); }
  });
  loadSources().catch(e=>toast(tr('ui.refresh_failed_error',{error:e.message}), true));
}

/* ---------- 批量迁移 ---------- */
async function doBatch(){
  if(state.transferring) return;
  const ids=[...selections.sessions.selected];
  if(!ids.length || !state.target) return;
  const payload={source:state.source,target:state.target,ids,cwd:$('#cwd').value.trim()||null,
    remap_tools:$('#remap').checked,include_thinking:$('#think').checked,redact_secrets:$('#redact').checked,
    on_conflict:'skip',dry_run:true};
  const post=body=>api('/api/batch',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  state.transferring=true;updateActions();
  try{
    const plan=await post(payload);
    const names=rows=>{
      const shown=rows.slice(0,15).map(item=>tm(item,'title')||item.id);
      if(rows.length>15) shown.push(tr('ui.and_n_more',{n:rows.length-15}));
      return shown;
    };
    const by=status=>plan.items.filter(item=>item.status===status);
    const go=by('would-migrate'),skip=by('skipped'),bad=by('failed');
    if(!go.length){
      toast(skip.length&&!bad.length?tr('ui.all_selected_sessions_were_already_migrated_nothing_to_do'):tr('ui.no_sessions_can_be_migrated'),true);
      return;
    }
    const targetName=AGENTS[state.target]||state.target;
    const sections=[{meta:tr('ui.target_name',{name:targetName})+'\n'+tr('ui.project_cwd',{cwd:payload.cwd||tr('ui.same_as_the_source')})}];
    sections.push({group:'preserved',label:tr('ui.will_migrate'),rows:names(go)});
    if(skip.length) sections.push({group:'degraded',label:tr('ui.already_migrated_skipped'),rows:names(skip)});
    if(bad.length) sections.push({group:'dropped',label:tr('ui.cannot_migrate'),rows:bad.slice(0,15).map(item=>(tm(item,'title')||item.id)+sep()+(tm(item,'error')||''))});
    sections.push({warn:tr('ui.batch_migration_does_not_preview_fidelity_one_by_one_preview_a_single_session_fi')});
    const plain=tr('ui.migrate_n_sessions_to_name',{n:go.length,name:targetName});
    if(!(await askConfirm(tr('ui.batch_migration_preview'),sections,plain,tr('ui.confirm_batch_migration')))) return;
    const done=await post({...payload,dry_run:false});
    const lines=[tr('ui.batch_migration_finished_ok_migrated_skip_skipped_bad_failed',{ok:done.migrated,skip:done.skipped,bad:done.failed})];
    for(const item of done.items) if(item.status==='failed') lines.push(tr('ui.failed_name_error',{name:item.title||item.id,error:tm(item,'error')||''}));
    const box=$('#importResult');box.textContent=lines.join('\n');box.style.display='';
    toast(lines[0],done.failed>0);
    selections.sessions.selected.clear();
    await loadSources();
  }catch(e){toast(tr('ui.batch_migration_failed_error',{error:e.message}),true);}
  finally{state.transferring=false;updateActions();}
}
