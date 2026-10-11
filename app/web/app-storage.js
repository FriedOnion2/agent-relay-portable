// Skill 与对话存储、恢复
// 经典脚本，由 index.html 按顺序加载并共享全局作用域。
function buildSkillAgents(){
  const source=$('#skillAgent'),target=$('#skillTargetAgent');
  source.innerHTML=''; target.innerHTML='';
  const labels={...AGENTS};
  state.sources.filter(s=>/^(windows_|ubuntu_)/.test(s.name)).forEach(s=>{labels[s.name]=tm(s,'label')||s.name;});
  for(const [key,label] of Object.entries(labels).filter(([key])=>key.replace(/^(windows_|ubuntu_)/,'')!=='yuanbao')){
    const option=document.createElement('option');option.value=key;option.textContent=label;source.appendChild(option);
  }
  for(const [key,label] of Object.entries(AGENTS).filter(([key])=>key!=='yuanbao')){
    const option=document.createElement('option');option.value=key;option.textContent=label;target.appendChild(option);
  }
  source.value=state.source in labels && state.source!=='yuanbao' ? state.source : 'codex';
  target.value=state.source==='yuanbao' ? 'codex' : state.source.replace(/^(windows_|ubuntu_)/,'');
}

let skillRequest=0;
async function loadSkills(){
  const request=++skillRequest;
  selections.skills=newSelection();
  $('#skillList').innerHTML=esc(tr('ui.loading'));
  updateSelections();
  const agent=$('#skillAgent').value;
  try{
    const r=await api('/api/skills?agent='+encodeURIComponent(agent)+'&skills_dir='+encodeURIComponent($('#skillsDir').value.trim()));
    if(request!==skillRequest || agent!==$('#skillAgent').value) return;
    selections.skills.rows=r.skills||[];
    const box=$('#skillList');box.innerHTML='';
    const note=document.createElement('div');note.className='meta';note.style.padding='10px';
    note.textContent=tr('ui.scanned_directories_list',{list:(r.roots||[]).join(tr('ui.semicolon'))})+((r.errors||[]).length?'\n'+r.errors.map(x=>tm(x,'error')).join('\n'):'');box.appendChild(note);
    for(const row of r.skills||[]){
      const item=document.createElement('div');item.className='meta';item.style.padding='10px';
      item.appendChild(selectionCheckbox('skills',row));
      const label=document.createElement('div');label.textContent=row.name+'\n'+row.path+(row.error?'\n'+tm(row,'error'):'');item.appendChild(label);
      const button=document.createElement('button');button.className='btn';button.textContent=tr('ui.choose_to_store');button.disabled=row.readable===false;
      button.onclick=()=>{$('#skillPath').value=row.path;};item.appendChild(button);box.appendChild(item);
    }
    updateSelections();
  }catch(e){if(request===skillRequest){$('#skillList').textContent=tr('ui.failed_to_read_error',{error:e.message});toast(tr('ui.failed_to_read_skills_error',{error:e.message}),true);}}
}

async function refreshSkillPackages(){
  try{
    const r=await api('/api/stored-skills?storage='+encodeURIComponent($('#skillStorageRoot').value.trim()));
    const box=$('#skillPackages');box.innerHTML='';
    for(const row of r.packages||[]){
      const item=document.createElement('div');item.className='meta';item.style.padding='10px';
      const label=document.createElement('div');label.textContent=row.error ? row.path+'\n'+tm(row,'error') :
        (AGENTS[row.agent]||row.agent)+' · '+(row.skill?.name||tr('ui.skill'))+'\n'+row.path;item.appendChild(label);
      if(!row.error){const button=document.createElement('button');button.className='btn';button.textContent=tr('ui.choose_to_restore');
        button.onclick=()=>{$('#skillPackage').value=row.path;$('#skillTargetAgent').value=row.agent;};item.appendChild(button);}
      box.appendChild(item);
    }
    if(!(r.packages||[]).length) box.textContent=tr('ui.no_skill_packages_yet_default_directory_root',{root:r.root});
  }catch(e){toast(tr('ui.failed_to_read_the_skill_storage_list_error',{error:e.message}),true);}
}

async function storeSelectedSkill(){
  if(state.transferring) return;
  const payload={agent:$('#skillAgent').value,path:$('#skillPath').value.trim(),storage:$('#skillStorageRoot').value.trim()||null};
  if(!payload.path) return toast(tr('ui.choose_a_skill_directory_containing_skill_md'),true);
  state.transferring=true;$('#storeSkill').disabled=true;updateActions();
  try{
    const r=await api('/api/store-skill',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    $('#skillResult').textContent=tr('ui.stored_name_package_path_path',{name:r.manifest.skill.name,path:r.path})+
      ((r.manifest.excluded||[]).length?tr('ui.excluded_list',{list:r.manifest.excluded.join(tr('ui.join_separator'))}):'');
    await refreshSkillPackages();
  }catch(e){toast(tr('ui.failed_to_store_the_skill_error',{error:e.message}),true);}
  finally{state.transferring=false;$('#storeSkill').disabled=false;updateActions();}
}

async function restoreSelectedSkill(){
  if(state.transferring) return;
  const payload={package:$('#skillPackage').value.trim(),agent:$('#skillTargetAgent').value,
    skills_dir:$('#targetSkillsDir').value.trim()||null,name:$('#skillName').value.trim()||null};
  if(!payload.package) return toast(tr('ui.enter_the_skill_package_path'),true);
  state.transferring=true;$('#restoreSkill').disabled=true;updateActions();
  try{
    const r=await api('/api/restore-skill',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    $('#skillResult').textContent=tr('ui.restored_name_directory_path',{name:r.name,path:r.path})+tms(r,'notes').join('\n');
  }catch(e){toast(tr('ui.failed_to_restore_the_skill_error',{error:e.message}),true);}
  finally{state.transferring=false;$('#restoreSkill').disabled=false;updateActions();}
}

async function storeCurrent(){
  const selected=state.current;
  if(!selected || $('#btnStore').disabled || state.transferring) return;
  state.transferring=true; updateActions();
  try{
    const r=await api('/api/store-session',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({source:selected.source,id:selected.id,storage:$('#storageRoot').value.trim()||null})});
    showPage('storage');
    $('#storageResult').style.display='';
    $('#storageResult').textContent=tr('ui.stored_a_agent_session_package_path_path_copy_this_zip_or_the_whole_storage_fold',{agent:AGENTS[r.manifest.agent],path:r.path});
    await refreshStorage();
  }catch(e){toast(tr('ui.store_failed_error',{error:e.message}),true);}
  finally{state.transferring=false;updateActions();}
}

async function refreshStorage(){
  const request=++workflow.storageRequest,root=$('#storageRoot').value.trim();
  try{
    const r=await api('/api/stored-sessions?storage='+encodeURIComponent(root));
    if(request!==workflow.storageRequest||root!==$('#storageRoot').value.trim())return;
    const box=$('#storageList'); box.innerHTML='';
    for(const row of r.packages||[]){
      const item=document.createElement('div'); item.className='meta'; item.style.padding='10px';
      const details=document.createElement('div');
      details.textContent=row.error ? tr('ui.path_failed_to_read_error',{path:row.path,error:tm(row,'error')}) :
        (AGENTS[row.agent]||row.agent)+' · '+(row.session?.title||row.session?.id||tr('ui.session'))+'\n'+row.path;
      item.appendChild(details);
      if(!row.error){
        const button=document.createElement('button'); button.className='btn'; button.textContent=tr('ui.choose_to_restore');
        button.onclick=()=>{selectPackage(row);}; item.appendChild(button);
      }
      box.appendChild(item);
    }
    if(!(r.packages||[]).length) box.textContent=tr('ui.no_stored_sessions_yet_default_directory_root',{root:r.root});
  }catch(e){if(request===workflow.storageRequest)toast(tr('ui.failed_to_read_the_storage_list_error',{error:e.message}),true);}
}

async function restoreStored(){
  const payload={package:$('#packagePath').value.trim(),cwd:$('#restoreCwd').value.trim(),session_id:$('#restoreId').value.trim()||null};
  if(state.transferring) return;
  if($('#restoreConflict').value==='new' && !payload.session_id){payload.session_id=generateId('#restoreId');if(!payload.session_id)return;}
  $('#restoreError').textContent='';
  if(!payload.package || !payload.cwd) return toast(tr('ui.enter_the_session_package_path_and_the_target_project_directory_on_this_device'),true);
  state.transferring=true; $('#restorePackage').disabled=true; updateActions();
  try{
    const token=await confirmMigration(payload,'restore-session');if(!token) return;
    payload.preview_token=token;
    const r=await api('/api/restore-session',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    $('#storageResult').textContent=tr('ui.restored_agent_session_id_id_file_path',{agent:AGENTS[r.to.source],id:r.to.native_id,path:r.to.path})+
      (r.resume_command?tr('ui.resume_command_cmd_2',{cmd:r.resume_command}):'')+'\n'+tms(r,'notes').join('\n');
    await loadSources();
    $('#storageResult').style.display='none';showOperationResult(r,'ui.session_restored');toast(tr('ui.session_restored'));
  }catch(e){
    const reason=/ID.*(?:已存在|exists)/i.test(e.message)?tr('ui.this_id_already_exists_choose_create_an_independent_copy_and_preview_again_to_ke'):e.message;
    $('#restoreError').textContent=tr('ui.restore_failed_error',{error:reason});toast(tr('ui.restore_failed_error',{error:reason}),true);
  }
  finally{state.transferring=false;$('#restorePackage').disabled=false;updateActions();}
}
