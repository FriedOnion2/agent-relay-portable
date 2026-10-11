// 任务导航与结果面板
// 经典脚本，由 index.html 按顺序加载并共享全局作用域。
// Task navigation only controls presentation. Writes still use the existing
// preview token, conflict checks and operation log on the local service.
const workflow={page:'home',carrying:false,result:null,storageRequest:0,indexJob:null,draftPath:null,draftAgent:null};
const taskPages={home:'#homePanel',sessions:'#sessionsPanel',storage:'#storagePanel',corpus:'#corpusPanel',
  skills:'#skillPanel',environment:'#environmentPanel',history:'#historyPanel'};
const taskLabels={home:'ui.where_would_you_like_to_start',sessions:'ui.migrate_sessions',storage:'ui.move_between_devices',corpus:'ui.full_text_search_and_skill_drafts',
  skills:'ui.skill_assets',environment:'ui.environment',history:'ui.history'};
const taskDescriptions={home:'ui.choose_a_task_local_records_and_portable_packages_are_processed_by_the_local_ser',
  sessions:'ui.choose_a_source_and_session_then_set_the_target_preserved_degraded_and_unknown_c',
  storage:'ui.save_on_the_original_device_restore_on_the_new_one_choose_the_local_project_dire',
  corpus:'ui.update_the_index_then_search_repeated_workflows_can_become_skill_drafts_requirin',
  skills:'ui.move_complete_skill_directories_existing_names_are_not_overwritten_and_scripts_a',
  environment:'ui.configure_this_device_s_directories_and_review_the_limits_of_format_checks',history:'ui.review_write_operations_content_changed_by_subsequent_sessions_is_kept_by_defaul'};
function showPage(page,focus=true){
  if(!taskPages[page])return;
  workflow.page=page;
  for(const [key,selector] of Object.entries(taskPages))$(selector).style.display=key===page?'':'none';
  renderWorkflow();
  if(focus)$('#pageTitle').focus?.();
}
function renderWorkflow(){
  $('#pageTitle').textContent=tr(taskLabels[workflow.page]);
  $('#pageDescription').textContent=tr(taskDescriptions[workflow.page]);
  for(const [id,page] of Object.entries({btnHome:'home',btnSessions:'sessions',btnStorage:'storage',btnCorpus:'corpus',btnSkillStorage:'skills',btnEnvironment:'environment',btnHistory:'history'})){
    $('#'+id).setAttribute('aria-current',workflow.page===page?'page':'false');
  }
  const carrying=workflow.carrying&&workflow.page==='sessions';
  $('#migrationSetup').style.display=carrying?'none':'';
  $('#btnGo').style.display=carrying?'none':'';
  if(carrying)$('#btnImport').style.display='none';
  $('#backToStorage').style.display=carrying?'':'none';
  $('#sessionGuide').textContent=carrying?tr('ui.step_1_choose_sessions_2_save_zip_3_copy_to_the_new_device'):tr('ui.step_1_choose_session_2_set_target_and_project_3_preview_and_confirm');
  $('#taskProgress').textContent=workflow.page==='sessions'?(state.current?tr('ui.session_selected_check_the_target_next'):tr('ui.choose_a_session_to_continue')):'';
  const mode=nativeMode();
  $('#mappingNote').textContent=mode?tr('ui.native_transfer_preserves_records_old_paths_in_text_and_tool_arguments_are_not_r'):
    tr('ui.for_a_new_device_enter_its_local_project_directory_on_the_same_device_blank_keep');
}
function renderHome(){
  const box=$('#sourceCards');box.innerHTML='';
  for(const source of state.sources){
    const card=document.createElement('div');card.className='source-card';
    const title=document.createElement('b');title.textContent=tm(source,'label')||AGENTS[source.name]||source.name;card.appendChild(title);
    const status=document.createElement('p');status.className=source.available?'status':'missing';
    status.textContent=source.available?tr('ui.n_sessions_capability',{n:source.session_count||0,capability:source.can_write?tr('ui.read_and_write'):tr('ui.read_only_source')}):tr('ui.directory_missing_or_unreadable');card.appendChild(status);
    const note=document.createElement('p');note.textContent=tm(source,'error')||tm(source,'read_note')||
      (source.available?tr('ui.choose_a_session_from_this_source_and_preview_before_migrating'):tr('ui.ignore_this_if_the_client_is_not_installed_configure_its_directory_if_you_have_r'));card.appendChild(note);
    const button=document.createElement('button');button.className='btn';button.textContent=source.available?tr('ui.browse_sessions'):tr('ui.configure_directories');
    button.onclick=async()=>{
      if(source.available){workflow.carrying=false;state.source=source.name;buildTabs();showPage('sessions');await loadSessions();}
      else{await $('#btnEnvironment').onclick();if(source.name in AGENTS)$('#deviceAgent').value=source.name;$('#deviceHome').focus?.();}
    };card.appendChild(button);box.appendChild(card);
  }
}
function generateId(selector){
  const id=globalThis.crypto?.randomUUID?.();
  if(!id){toast(tr('ui.this_browser_cannot_generate_a_uuid_enter_a_new_session_id_manually'),true);return null;}
  $(selector).value=id;return id;
}
function selectPackage(row){
  workflow.selectedPackage=row;
  $('#packagePath').value=row.path;
  renderSelectedPackage();
  $('#restoreError').textContent='';$('#restoreCwd').focus?.();
}
function renderSelectedPackage(){
  const row=workflow.selectedPackage;if(!row)return;
  $('#selectedPackage').textContent=tr('ui.selected_agent_title_original_project_cwd',{agent:AGENTS[row.agent]||row.agent,title:row.session?.title||row.session?.id||tr('ui.session'),cwd:row.session?.cwd||tr('ui.unknown')});
  if(row.agent==='yuanbao')$('#selectedPackage').textContent+='\n'+tr('ui.yuanbao_package_selected');
}
function bindWorkflow(){
  $('#btnHome').onclick=()=>showPage('home');
  $('#btnSessions').onclick=()=>{workflow.carrying=false;showPage('sessions');updateActions();};
  $('#homeMigrate').onclick=()=>$('#btnSessions').onclick();
  $('#homeMove').onclick=()=>$('#btnStorage').onclick();
  $('#homeSearch').onclick=()=>openCorpus();
  $('#homeSkills').onclick=()=>$('#btnSkillStorage').onclick();
  $('#homeConfigure').onclick=()=>$('#btnEnvironment').onclick();
  $('#chooseToStore').onclick=()=>{workflow.carrying=true;showPage('sessions');updateActions();};
  $('#backToStorage').onclick=()=>$('#btnStorage').onclick();
  $('#restoreConflict').onchange=()=>{
    $('#restoreId').value='';
    if($('#restoreConflict').value==='new')generateId('#restoreId');
  };
  $('#restoreNewId').onclick=()=>{if(generateId('#restoreId'))$('#restoreConflict').value='new';};
  $('#packagePath').oninput=()=>{$('#selectedPackage').textContent='';$('#restoreError').textContent='';};
  $('#updateCorpusQuick').onclick=()=>startCorpusJob('index');
  $('#corpusQuery').onkeydown=e=>{if(e.key==='Enter')searchCorpus(0);};
  $('#showDistill').onclick=()=>$('#draftCandidates').scrollIntoView?.({block:'start',behavior:'smooth'});
  $('#storeExportedDraft').onclick=()=>{
    if(!workflow.draftPath)return;
    showPage('skills');buildSkillAgents();$('#skillAgent').value=workflow.draftAgent in AGENTS?workflow.draftAgent:'codex';
    // Export returns a SKILL.md path. Both Windows and POSIX separators work.
    $('#skillPath').value=workflow.draftPath.replace(/[\\/][^\\/]+$/,'');
    $('#skillStorageRoot').value=$('#storageRoot').value;
    $('#skillResult').textContent=tr('ui.the_exported_draft_directory_is_selected_click_store_skill_to_create_a_portable_');
    $('#storeSkill').focus?.();refreshSkillPackages();
  };
  // Escape returns to the home task; native dialogs handle their own cancel.
  document.addEventListener?.('keydown',e=>{
    if(e.key==='Escape'&&!$('#confirmDialog').open&&!state.transferring){showPage('home');$('#btnHome').focus?.();}
  });
}
function showOperationResult(result,title){
  workflow.result={result,title};renderOperationResult();
}
function renderOperationResult(){
  const box=$('#operationResult');
  if(!workflow.result){box.style.display='none';return;}
  box.innerHTML='';box.style.display='';
  const {result:r,title}=workflow.result;
  const heading=document.createElement('h2');heading.textContent=tr(title);box.appendChild(heading);
  const info=document.createElement('details');
  const summary=document.createElement('summary');summary.textContent=tr('ui.view_project_id_files_and_resume_notes');info.appendChild(summary);box.appendChild(info);
  const details=document.createElement('p');details.textContent=tr('ui.target_agent_project_cwd_session_id_id_file_path',{
    agent:AGENTS[r.to.source.replace(/^(windows_|ubuntu_)/,'')]||r.to.source,cwd:r.to.cwd||tr('ui.unknown'),
    id:r.to.native_id||r.to.id||tr('ui.check_in_the_target_session_list'),path:r.to.path});info.appendChild(details);
  const note=document.createElement('p');note.textContent=tr('ui.files_have_been_written_check_resume_in_the_target_client_a_successful_write_doe')+'\n'+[...new Set([...tms(r,'notes'),...tms(r.preview,'warnings')])].join('\n');info.appendChild(note);
  if(r.resume_command){const command=document.createElement('p');command.textContent=tr('ui.resume_command_cmd',{cmd:r.resume_command});info.appendChild(command);}
  const actions=document.createElement('div');actions.className='result-actions';box.appendChild(actions);
  const add=(label,fn)=>{const button=document.createElement('button');button.className='btn';button.textContent=tr(label);button.onclick=fn;actions.appendChild(button);};
  const copy=async value=>{
    try{if(!navigator.clipboard)throw new Error('clipboard');await navigator.clipboard.writeText(value);toast(tr('ui.copied'));}
    catch(e){toast(tr('ui.copy_failed_please_copy_manually'),true);}
  };
  add('ui.copy_path',()=>copy(r.to.path));
  if(r.resume_command)add('ui.copy_resume_command',()=>copy(r.resume_command));
  add('ui.view_target_session',async()=>{
    try{
      workflow.carrying=false;state.source=r.to.source;$('#q').value=r.to.id||r.to.native_id||'';
      buildTabs();showPage('sessions');await loadSessions();
      const row=state.sessions.find(item=>(r.to.id&&item.id===r.to.id)||item.path?.replace(/\\/g,'/')===r.to.path.replace(/\\/g,'/'));
      if(row)await openSession(row);else toast(tr('ui.search_for_the_session_id_in_the_target_source'),true);
    }catch(e){toast(tr('ui.refresh_failed_error',{error:e.message}),true);}
  });
  add('ui.history',()=>openHistory());
  add('ui.dismiss_result',()=>{workflow.result=null;renderOperationResult();});
}
