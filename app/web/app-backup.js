// Three export modes share a verified native-backup import workflow.
const backupState={job:null,plan:null,projects:[],skills:[]};
function buildBackupAgents(){
  const box=$('#backupAgents'), previous=new Map();
  for(const input of box.querySelectorAll('input'))previous.set(input.value,input.checked);
  box.innerHTML='';
  for(const [key,label] of Object.entries(AGENTS)){
    const node=document.createElement('label');node.className='opt';
    const input=document.createElement('input');input.type='checkbox';input.value=key;
    input.checked=previous.has(key)?previous.get(key):!!state.sources.find(s=>s.name===key)?.available;
    node.appendChild(input);const text=document.createElement('span');text.textContent=label;node.appendChild(text);box.appendChild(node);
  }
}
function invalidateBackupPlan(){backupState.plan=null;$('#importBackup').disabled=true;}
function backupOptions(){
  return {projects:Object.fromEntries(backupState.projects.map(row=>[row.key,row.input.value.trim()])),
    skills:Object.fromEntries(backupState.skills.map(row=>[row.key,row.input.value.trim()])),conflict:$('#backupConflict').value};
}
function backupBusy(busy){
  state.transferring=busy;updateActions();
  for(const id of ['backupAll','backupSessions','backupMarkdown','backupFile','backupPath','inspectBackup','previewBackup','backupConflict'])$('#'+id).disabled=busy;
  for(const input of $('#backupAgents').querySelectorAll('input'))input.disabled=busy;
  for(const row of [...backupState.projects,...backupState.skills])row.input.disabled=busy;
  $('#cancelBackup').disabled=!busy||!backupState.job;
  $('#importBackup').disabled=busy||!backupState.plan||!!backupState.plan.blocked;
}
function backupErrors(errors){return (errors||[]).map(row=>[row.agent,row.id||row.title||row.path,tm(row,'error')].filter(Boolean).join(' · '));}
async function watchBackupJob(job){
  backupState.job=job.id;$('#cancelBackup').disabled=false;
  for(;;){
    const current=await api('/api/job');
    if(current.id!==job.id)throw new Error(tr('msg.backup_job_changed'));
    if(current.status!=='running'){
      if(current.status==='failed')throw new Error(tm(current,'error'));
      return {...current.result,canceled:current.status==='canceled'};
    }
    $('#backupReport').textContent=tr('msg.backup_progress',{n:current.progress?.processed||0});
    await new Promise(resolve=>setTimeout(resolve,650));
  }
}
async function exportBackup(mode){
  if(state.transferring)return;
  const agents=Array.from($('#backupAgents').querySelectorAll('input')).filter(input=>input.checked).map(input=>input.value);
  if(!agents.length)return toast(tr('msg.backup_select_agents'),true);
  invalidateBackupPlan();backupBusy(true);$('#backupDownload').innerHTML='';
  try{
    const job=await api('/api/backup-export',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({mode,agents,include_thinking:$('#backupThinking').checked,lang})});
    const result=await watchBackupJob(job);
    const status=result.canceled?tr('msg.backup_canceled'):result.ok?tr('msg.backup_complete'):tr('msg.backup_partial');
    $('#backupReport').textContent=[status,tr('msg.backup_exported',{n:result.processed||0}),result.path||'',...backupErrors(result.errors)].join('\n');
    if(result.download){
      const link=document.createElement('a');link.className='btn primary';link.href=result.download;
      link.textContent=tr('msg.backup_download');link.setAttribute('download','');$('#backupDownload').appendChild(link);
      // The durable copy remains in storage/backups even if a browser blocks a download.
      link.click();
    }
  }catch(e){$('#backupReport').textContent=e.message;toast(e.message,true);}
  finally{backupState.job=null;backupBusy(false);}
}
function renderBackupMapping(summary){
  invalidateBackupPlan();backupState.projects=[];backupState.skills=[];
  const box=$('#backupMapping');box.innerHTML='';
  for(const [kind,keys] of [['projects',summary.projects||[]],['skills',summary.skill_agents||[]]]){
    for(const key of keys){
      const label=document.createElement('label');label.className='field';
      const text=document.createElement('span');text.textContent=kind==='projects'?tr('msg.backup_project',{path:key||tr('ui.unknown')}):tr('msg.backup_skills_root',{agent:AGENTS[key]||key});
      const input=document.createElement('input');input.className='input';input.value=kind==='projects'?key:'';
      input.placeholder=tr(kind==='projects'?'msg.backup_project_hint':'msg.backup_skills_hint');
      input.oninput=invalidateBackupPlan;label.appendChild(text);label.appendChild(input);box.appendChild(label);
      backupState[kind].push({key,input});
    }
  }
  $('#backupReport').textContent=[tr('msg.backup_loaded',{n:summary.count}),...backupErrors(summary.errors)].join('\n');
}
async function inspectBackup(upload=false){
  if(state.transferring)return;
  invalidateBackupPlan();backupBusy(true);
  try{
    let summary;
    if(upload){
      const file=$('#backupFile').files?.[0];if(!file)return;
      if(file.size>262*1024*1024)throw new Error(tr('msg.backup_limit'));
      summary=await api('/api/backup-upload',{method:'POST',headers:{'Content-Type':'application/zip'},body:file});
      $('#backupPath').value=summary.path;
    }else summary=await api('/api/backup-inspect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({package:$('#backupPath').value.trim()})});
    renderBackupMapping(summary);
  }catch(e){$('#backupReport').textContent=e.message;toast(e.message,true);}
  finally{backupBusy(false);}
}
async function previewBackup(){
  if(state.transferring)return;
  invalidateBackupPlan();backupBusy(true);
  try{
    const payload={package:$('#backupPath').value.trim(),options:backupOptions()};
    const report=await api('/api/backup-preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    backupState.plan={...report,payload};
    const statuses={ready:tr('msg.backup_status_ready'),skip:tr('msg.backup_status_skip'),blocked:tr('msg.backup_status_blocked')};
    $('#backupReport').textContent=[tr('msg.backup_plan',{ready:report.ready,skip:report.skip,blocked:report.blocked}),
      ...report.rows.map(row=>[AGENTS[row.agent]||row.agent,row.title||row.key,statuses[row.status],row.cwd||row.destination,tm(row,'reason')].filter(Boolean).join(' · ')),
      ...backupErrors(report.errors)].join('\n');
  }catch(e){$('#backupReport').textContent=e.message;toast(e.message,true);}
  finally{backupBusy(false);}
}
async function importBackup(){
  if(state.transferring||!backupState.plan||backupState.plan.blocked)return;
  const plan=backupState.plan;
  if(JSON.stringify(plan.payload.options)!==JSON.stringify(backupOptions())||plan.payload.package!==$('#backupPath').value.trim()){
    invalidateBackupPlan();return toast(tr('msg.backup_preview_again'),true);
  }
  invalidateBackupPlan();backupBusy(true);
  try{
    const job=await api('/api/backup-import',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...plan.payload,preview_token:plan.token})});
    const result=await watchBackupJob(job);
    $('#backupReport').textContent=[result.canceled?tr('msg.backup_canceled'):result.ok?tr('msg.backup_complete'):tr('msg.backup_partial'),
      tr('msg.backup_imported',{restored:result.restored?.length||0,skipped:result.skipped?.length||0,errors:result.errors?.length||0}),
      ...(result.restored||[]).map(row=>[AGENTS[row.agent]||row.agent,row.title,row.result.to?.path||row.result.path].filter(Boolean).join(' · ')),
      ...backupErrors(result.errors)].join('\n');
    await loadSources();
  }catch(e){$('#backupReport').textContent=e.message;toast(e.message,true);}
  finally{backupState.job=null;backupBusy(false);}
}
function bindBackup(){
  $('#backupAll').onclick=()=>exportBackup('all');$('#backupSessions').onclick=()=>exportBackup('sessions');
  $('#backupMarkdown').onclick=()=>exportBackup('markdown');$('#backupFile').onchange=()=>inspectBackup(true);
  $('#inspectBackup').onclick=()=>inspectBackup();$('#previewBackup').onclick=previewBackup;$('#importBackup').onclick=importBackup;
  $('#backupPath').oninput=invalidateBackupPlan;$('#backupConflict').onchange=invalidateBackupPlan;
  $('#cancelBackup').onclick=async()=>{try{await api('/api/job-cancel',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:backupState.job})});$('#cancelBackup').disabled=true;}catch(e){toast(e.message,true);}};
  buildBackupAgents();
}
