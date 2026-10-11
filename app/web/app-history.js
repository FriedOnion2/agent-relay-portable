// 操作记录与撤销
// 经典脚本，由 index.html 按顺序加载并共享全局作用域。
/* ---------- 操作记录与撤销 ---------- */
function historyTime(iso){
  const date=new Date(iso);
  return isNaN(date.getTime())?String(iso||'').replace('T',' ').slice(0,19):date.toLocaleString(lang==='en'?'en-GB':'zh-CN',{hour12:false});
}
function historyKind(kind){
  return {transfer:tr('ui.converted_migration'),'import-windows':tr('ui.windows_ubuntu_native_migration'),'import-ubuntu':tr('ui.ubuntu_windows_native_migration'),
          'export-windows':tr('ui.ubuntu_windows_native_migration')}[kind]||kind||'';
}
async function openHistory(){
  showPage('history');
  await refreshHistory();
}
async function refreshHistory(){
  try{
    const r=await api('/api/operations?limit=100');
    renderHistory(r.operations||[]);
  }catch(e){toast(tr('ui.failed_to_read_the_history_error',{error:e.message}),true);}
}
function renderHistory(rows){
  const box=$('#historyList');box.innerHTML='';
  if(!rows.length){box.textContent=tr('ui.no_operations_recorded_yet');return;}
  for(const row of rows){
    const item=document.createElement('div');item.className='meta';item.style.padding='10px';
    const details=document.createElement('div');details.style.whiteSpace='pre-wrap';
    const lines=[historyTime(row.time)+' · '+historyKind(row.kind)+' · '+(AGENTS[row.source]||row.source||'?')+' → '+(AGENTS[row.target]||row.target||'?'),
                 row.title||row.session||''];
    if(row.status && row.status!=='ok') lines.push(tr('ui.status_status',{status:row.status})+(row.error?'  '+tm(row,'error'):''));
    lines.push(tr('ui.n_file_s_created_m_appended_to',{n:(row.created||[]).length,m:(row.appended||[]).length}));
    if(row.undone) lines.push(tr('ui.undone_at_time',{time:historyTime(row.undone.time)}));
    else if(!row.undoable && row.undo_blocked) lines.push(tr('ui.cannot_be_undone_automatically_reason',{reason:tm(row,'undo_blocked')}));
    details.textContent=lines.filter(Boolean).join('\n');
    item.appendChild(details);
    if(row.undoable){
      const button=document.createElement('button');button.className='btn';button.textContent=tr('ui.undo_this_migration');
      button.onclick=()=>undoOperation(row);item.appendChild(button);
    }
    box.appendChild(item);
  }
}
async function undoOperation(row){
  if(state.transferring) return;
  const sections=[{meta:tr('ui.undo_deletes_the_files_this_migration_created_and_truncates_the_indexes_it_appen')}];
  if((row.created||[]).length) sections.push({group:'dropped',label:tr('ui.files_to_delete'),rows:row.created});
  if((row.appended||[]).length) sections.push({group:'degraded',label:tr('ui.indexes_to_truncate'),rows:row.appended});
  const plain=tr('ui.undo_this_migration_2')+'\n'+[...(row.created||[]),...(row.appended||[])].join('\n');
  if(!(await askConfirm(tr('ui.undo_migration'),sections,plain,tr('ui.confirm_undo')))) return;
  state.transferring=true;updateActions();
  const post=body=>api('/api/undo',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  try{
    let r=await post({id:row.id});
    if((r.kept||[]).length){
      const kept=r.kept.map(k=>k.path+'：'+tm(k,'reason'));
      const force=await askConfirm(tr('ui.some_files_were_kept'),[{meta:tr('ui.these_files_were_modified_after_the_migration_and_were_not_deleted_forcing_the_u')},{group:'dropped',label:tr('ui.kept_files'),rows:kept}],
        tr('ui.force_delete_these_modified_files')+'\n'+kept.join('\n'),tr('ui.force_undo'));
      if(force) r=await post({id:row.id,force:true});
    }
    $('#historyResult').textContent=tr('ui.undo_finished_n_file_s_deleted_m_index_es_truncated_k_file_s_kept',
      {n:(r.removed||[]).length,m:(r.truncated||[]).length,k:(r.kept||[]).length});
    await refreshHistory();
    await loadSources();
  }catch(e){toast(tr('ui.undo_failed_error',{error:e.message}),true);}
  finally{state.transferring=false;updateActions();}
}
