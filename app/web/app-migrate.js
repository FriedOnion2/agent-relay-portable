// 环境检查、元宝导入、迁移确认对话框
// 经典脚本，由 index.html 按顺序加载并共享全局作用域。
/* ================= 迁移 ================= */
function showEnvironment(r){
  const yes = ok => ok ? tr('ui.yes') : tr('ui.no');
  $('#environmentResult').textContent=[r.system+' / '+r.architecture,tr('ui.data_directory_v',{v:r.data_root}),
    tr('ui.device_config_v',{v:r.config_path}),tr('ui.data_directory_writable_v',{v:yes(r.writable)}),
    r.free_bytes==null?'':tr('ui.free_space_v_gib',{v:(r.free_bytes/1024/1024/1024).toFixed(1)}),
    r.runtime?tr('ui.python_py_kind_zstandard_z',{py:r.runtime.python,kind:r.runtime.bundled?tr('ui.bundled_with_the_release'):tr('ui.source_interpreter'),z:r.runtime.zstandard?tr('ui.available'):tr('ui.missing')}):'',
    r.runtime?tr('ui.runtime_directory_v',{v:r.runtime.directory}):'',r.runtime?tm(r.runtime,'checksum'):'',
    r.runtime?tr('ui.sqlite_sqlite_fts5_fts',{sqlite:r.runtime.sqlite||tr('ui.unavailable'),fts:r.runtime.fts5?tr('ui.available'):tr('ui.missing')}):'',
    tm(r,'write_error'),tm(r,'note'),...tms(r,'warnings'),...tms(r,'plugin_errors')].filter(Boolean).join('\n');
}
async function saveDeviceHome(){
  if(state.transferring) return;
  const payload={agent:$('#deviceAgent').value,home:$('#deviceHome').value.trim()};
  state.transferring=true;updateActions();$('#saveDeviceHome').disabled=true;
  try{
    showEnvironment(await api('/api/device-home',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}));
    await loadSources();buildTabs();buildTarget();await loadSessions();toast(tr('ui.directory_saved'));
  }catch(e){toast(tr('ui.save_failed_error',{error:e.message}),true);}
  finally{state.transferring=false;$('#saveDeviceHome').disabled=false;updateActions();}
}
function renderYuanbaoResult(){
  $('#yuanbaoImportResult').textContent=state.yuanbaoResult?ts(state.yuanbaoResult):'';
}
async function importYuanbao(){
  if(state.transferring) return;
  const path=$('#yuanbaoPath').value.trim();
  if(!path) return toast(tr('err.yuanbao_input_path'),true);
  state.transferring=true;updateActions();state.yuanbaoResult=null;renderYuanbaoResult();
  try{
    const r=await api('/api/import-yuanbao',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path})});
    state.yuanbaoResult={code:'ui.yuanbao_imported',params:{count:r.imported,skipped:r.skipped}};renderYuanbaoResult();
    state.source='yuanbao';$('#q').value='';
    await loadSources();buildTabs();await loadSessions();
  }catch(e){
    state.yuanbaoResult={code:'ui.yuanbao_import_failed',params:{error:e.error_message||e.message}};
    renderYuanbaoResult();toast(ts(state.yuanbaoResult),true);
  }finally{state.transferring=false;updateActions();}
}
async function runHealth(){
  const button=$('#runHealth');if(button.disabled) return;button.disabled=true;
  $('#healthResult').textContent=tr('ui.verifying_temporary_samples');
  try{
    const r=await api('/api/health');const box=$('#healthResult');box.innerHTML='';
    const note=document.createElement('p');note.textContent=tm(r,'note')+'\n'+r.checked_at+' / '+r.system;box.appendChild(note);
    for(const row of r.adapters||[]){
      const item=document.createElement('div');item.className='meta';item.style.padding='10px';
      const status={passed:tr('ui.sample_passed'),failed:tr('ui.sample_failed'),unavailable:tr('ui.dependency_unavailable'),'not-tested':tr('ui.not_verified')};
      item.textContent=tr('ui.label_status_client_version_version_generic_write_write_real_resume_not_verified',
          {label:tm(row,'label'),status:status[row.status]||row.status,version:row.client_version||tr('ui.unknown'),write:row.write?tr('ui.supported'):tr('ui.read_only_2')})+
          (row.coverage?'\n'+tr('ui.sample_scope_v',{v:tm(row,'coverage')}):'')+(row.error?'\n'+tm(row,'error'):'');box.appendChild(item);
    }
  }catch(e){$('#healthResult').textContent=tr('ui.self_check_failed_error',{error:e.message});}
  finally{button.disabled=false;}
}
// 页面内确认对话框；浏览器不支持 <dialog> 时退回原生 confirm(plainText)。
// sections: [{meta:'说明文字'} | {group:'preserved|degraded|dropped|unknown', label, rows:['项（数量）']} | {warn:'提示'}]
function askConfirm(title,sections,plainText,okLabel=tr('ui.confirm')){
  const dialog=$('#confirmDialog');
  if(!dialog||typeof dialog.showModal!=='function') return Promise.resolve(confirm(plainText));
  $('#confirmTitle').textContent=title;
  const body=$('#confirmBody');body.innerHTML='';
  for(const section of sections){
    if(section.group){
      const box=document.createElement('div');box.className='confirm-group g-'+section.group;
      const head=document.createElement('div');head.className='label';
      const name=document.createElement('span');name.textContent=section.label;
      const count=document.createElement('span');count.textContent=section.rows.length===1?tr('ui.step_1_item'):tr('ui.n_items',{n:section.rows.length});
      head.appendChild(name);head.appendChild(count);box.appendChild(head);
      const list=document.createElement('ul');
      for(const row of section.rows){const li=document.createElement('li');li.textContent=row;list.appendChild(li);}
      box.appendChild(list);body.appendChild(box);
    }else{
      const p=document.createElement('div');p.className=section.warn?'confirm-warn':'confirm-meta';
      p.textContent=section.warn||section.meta;body.appendChild(p);
    }
  }
  $('#confirmOk').textContent=okLabel;
  dialog.returnValue='';
  return new Promise(resolve=>{
    dialog.onclose=()=>{dialog.onclose=null;resolve(dialog.returnValue==='ok');};
    dialog.showModal();
  });
}
async function confirmMigration(payload,mode='convert'){
  const r=await api('/api/preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...payload,mode})});
  const labels={preserved:tr('ui.preserved'),degraded:tr('ui.degraded'),dropped:tr('ui.dropped'),unknown:tr('ui.unknown_needs_checking')};
  const targetName=AGENTS[r.target]||tm(state.sources.find(s=>s.name===r.target),'label')||r.target;
  const where=tr('ui.target_name',{name:targetName})+'\n'+tr('ui.project_cwd',{cwd:r.target_cwd||tr('ui.same_as_the_source')});
  const lines=[tr('ui.migration_fidelity_preview'),...where.split('\n')];
  const sections=[{meta:where}];
  for(const [key,label] of Object.entries(labels)){
    const rows=(r[key]||[]).map(row=>tr('ui.item_count',{item:tm(row,'item'),count:row.count}));
    for(const row of rows) lines.push(label+'：'+row);
    if(rows.length) sections.push({group:key,label,rows});
  }
  const warnings=tms(r,'warnings');
  lines.push(...warnings);
  for(const warning of warnings) sections.push({warn:warning});
  if((r.blockers_messages||r.blockers||[]).length){toast(tr('ui.migration_cannot_run_list',{list:tms(r,'blockers').join(tr('ui.semicolon'))}),true);return null;}
  return (await askConfirm(tr('ui.migration_fidelity_preview'),sections,lines.join('\n')+'\n\n'+tr('ui.run_this_migration'),tr('ui.run_migration'))) ? r.token : null;
}
