// 全文搜索、索引任务与 Skill 草稿
// 经典脚本，由 index.html 按顺序加载并共享全局作用域。
const corpusState={request:0,documentRequest:0,offset:0,job:null,busy:false,timer:null,rendered:null,selected:null,exporting:false,indexStatus:null,resultCount:null};
async function openCorpus(){
  showPage('corpus');
  for(const id of ['#indexSource','#corpusSource']){
    const selector=$(id),selected=selector.value;
    selector.innerHTML='<option value="">'+esc(tr('ui.all_sources'))+'</option>';
    for(const row of state.sources){const option=document.createElement('option');option.value=row.name;option.textContent=AGENTS[row.name]||row.name;selector.appendChild(option);}
    selector.value=state.sources.some(row=>row.name===selected)?selected:'';
  }
  try{
    const r=await api('/api/corpus');
    renderIndexSummary(r);
    await pollCorpusJob();
  }catch(e){toast(e.message,true);}
}
function corpusBusy(value){
  corpusState.busy=value;
  $('#updateCorpus').disabled=value;$('#updateCorpusQuick').disabled=value;$('#extractDrafts').disabled=value;
  $('#cancelCorpus').disabled=!value;
}
function renderIndexSummary(r){
  corpusState.indexStatus=r;
  $('#indexSummary').textContent=r.exists?tr('ui.the_index_holds_docs_records_thinking_thinking_records',{docs:r.documents,thinking:r.thinking_documents})+
    (r.file_updated_at?' '+tr('ui.index_file_updated_time',{time:r.file_updated_at}):''):tr('ui.no_index_yet_click_update_index');
}
function renderSearchSummary(count){
  corpusState.resultCount=count;
  $('#searchSummary').textContent=tr('ui.n_results_on_this_page_offline_caches_can_be_viewed_writing_requires_an_availabl',{n:count});
}
async function startCorpusJob(kind){
  if(corpusState.busy)return;
  corpusBusy(true);
  if(kind==='extract'){
    corpusState.selected=null;$('#draftEditor').style.display='none';$('#draftCandidates').innerHTML='';
  }
  const payload=kind==='index'?{include_thinking:$('#indexThinking').checked,packages:$('#indexPackages').checked,
    sources:$('#indexSource').value?[$('#indexSource').value]:null}:{};
  try{
    const r=await api('/api/'+kind,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    corpusState.job=r.id;
    await pollCorpusJob();
  }catch(e){corpusBusy(false);toast(e.message,true);}
}
async function pollCorpusJob(){
  clearTimeout(corpusState.timer);
  const r=await api('/api/job');
  if(r.status==='idle')return;
  corpusState.job=r.id;
  corpusBusy(r.status==='running');
  const p=r.result||r.progress||{};
  const labels={running:tr('ui.running'),completed:tr('ui.completed'),canceled:tr('ui.canceled'),failed:tr('ui.failed')};
  const lines=[tr('ui.kind_status',{kind:r.kind==='index'?tr('ui.index'):tr('ui.distill'),status:labels[r.status]||r.status})];
  if(p.processed!=null)lines.push(tr('ui.scanned_n',{n:p.processed})+(r.kind==='index'?tr('ui.indexed_added_updated_unchanged_unchanged',{indexed:p.indexed||0,unchanged:p.unchanged||0}):tr('ui.n_task_segments_found',{n:p.segments||0})));
  if(p.source)lines.push(tr('ui.current_source_v',{v:p.source==='packages'?tr('ui.stored_conversation_packages'):AGENTS[p.source]||p.source}));
  if(p.limited)lines.push(tr('ui.the_limit_for_this_run_was_reached_finished_results_are_kept_narrow_the_sources_'));
  if(r.kind==='extract' && r.status==='completed')lines.push(tr('ui.found_n_drafts_to_review_the_ranking_score_is_not_a_success_probability',{n:p.candidates?.length||0}));
  for(const warning of tms(p,'warnings'))lines.push(warning);
  for(const error of (p.errors||[]).slice(0,5))lines.push(tr('ui.source_id_error',{source:error.source||'',id:error.id||'',error:tm(error,'error')}));
  if((p.errors||[]).length>5)lines.push(tr('ui.n_more_read_errors_narrow_the_sources_to_see_them',{n:p.errors.length-5}));
  if(r.error)lines.push(tm(r,'error'));
  $('#corpusStatus').textContent=lines.join('\n');
  if(r.kind==='extract' && r.status==='completed' && corpusState.rendered!==r.id){
    renderDraftCandidates(p.candidates||[]);corpusState.rendered=r.id;
  }
  if(r.kind==='index'&&r.status!=='running'&&workflow.indexJob!==r.id){
    workflow.indexJob=r.id;
    api('/api/corpus').then(renderIndexSummary).catch(e=>toast(e.message,true));
  }
  if(r.status==='running')corpusState.timer=setTimeout(()=>pollCorpusJob().catch(e=>{corpusBusy(false);toast(e.message,true);}),650);
}
async function cancelCorpusJob(){
  if(!corpusState.job)return;
  try{
    await api('/api/job-cancel',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:corpusState.job})});
    $('#cancelCorpus').disabled=true;$('#corpusStatus').textContent+=tr('ui.canceling_completed_index_transactions_are_kept');
  }catch(e){toast(e.message,true);}
}
async function searchCorpus(offset=0){
  const request=++corpusState.request;
  const filters={q:$('#corpusQuery').value,source:$('#corpusSource').value,project:$('#corpusProject').value,
    tool:$('#corpusTool').value,after:$('#corpusAfter').value,before:$('#corpusBefore').value,
    include_thinking:$('#searchThinking').checked,offset};
  $('#moreCorpus').disabled=true;
  try{
    const url='/api/search?'+Object.entries(filters).map(([k,v])=>k+'='+encodeURIComponent(v)).join('&');
    const r=await api(url);
    if(request!==corpusState.request)return;
    corpusState.offset=offset;$('#corpusResults').innerHTML='';$('#moreCorpus').disabled=!r.more;
    renderSearchSummary(r.results.length);
    if(!r.results.length)$('#corpusResults').textContent=r.indexed?tr('ui.no_matching_sessions'):tr('ui.no_index_yet');
    for(const row of r.results){
      const box=document.createElement('div');box.className='session';
      const title=document.createElement('b');title.textContent=row.title||row.sid;box.appendChild(title);
      const meta=document.createElement('p');meta.textContent=`${row.source} · ${row.origin==='package'?tr('ui.stored_package'):tr('ui.local_record')}${row.offline?tr('ui.offline_cache'):''}${row.partial?tr('ui.partial'):''} · ${row.cwd}`;box.appendChild(meta);
      const snippet=document.createElement('p');snippet.textContent=row.snippet;box.appendChild(snippet);
      const button=document.createElement('button');button.className='btn';button.textContent=tr('ui.view_session');button.onclick=()=>openCorpusDocument(row.key);box.appendChild(button);
      $('#corpusResults').appendChild(box);
    }
  }catch(e){if(request===corpusState.request)toast(e.message,true);}
}
async function openCorpusDocument(key){
  const request=++corpusState.documentRequest;
  try{
    const r=await api('/api/document?key='+encodeURIComponent(key)+'&include_thinking='+$('#searchThinking').checked);
    if(request!==corpusState.documentRequest)return;
    const panel=$('#corpusDocument');panel.innerHTML='';
    const title=document.createElement('h3');title.textContent=r.title||r.sid;panel.appendChild(title);
    const pre=document.createElement('pre');pre.style.whiteSpace='pre-wrap';
    pre.textContent=r.conversation.turns.map(t=>t.role+'\n'+t.blocks.map(b=>b.text||(b.name?b.name+'\n':'')+(b.arguments||b.output||'')).join('\n')).join('\n\n');panel.appendChild(pre);
    if(r.can_open){const button=document.createElement('button');button.className='btn';button.textContent=tr('ui.open_the_local_original_session');button.onclick=async()=>{
      workflow.carrying=false;state.source=r.source;buildTabs();await loadSessions();await openSession({id:r.sid});showPage('sessions');
    };panel.appendChild(button);}
  }catch(e){if(request===corpusState.documentRequest)toast(e.message,true);}
}
function renderDraftCandidates(candidates){
  corpusState.selected=null;$('#draftEditor').style.display='none';$('#draftCandidates').innerHTML='';
  if(!candidates.length){$('#draftCandidates').textContent=tr('ui.no_repeated_workflow_backed_by_at_least_three_independent_sessions_was_found');return;}
  for(const c of candidates){
    const box=document.createElement('div');box.className='session';
    const text=document.createElement('p');text.textContent=tr('ui.name_count_independent_evidence_ranking_score_score',{name:c.name,count:c.evidence_count,score:c.score});box.appendChild(text);
    const button=document.createElement('button');button.className='btn';button.textContent=tr('ui.select_and_edit_this_draft');button.onclick=()=>{
      corpusState.selected=c.id;
      const origin=globalThis.location?.origin||'http://127.0.0.1:8745';
      $('#draftMarkdown').value=c.markdown.split('http://127.0.0.1:8745/').join(origin+'/');$('#confirmDraft').checked=false;
      $('#draftResult').textContent='';$('#draftEditor').style.display='';workflow.draftPath=null;$('#storeExportedDraft').style.display='none';updateDraftAction();
      $('#draftEditor').scrollIntoView?.({block:'start',behavior:'smooth'});
    };box.appendChild(button);
    for(const key of c.evidence){const evidence=document.createElement('button');evidence.className='btn';evidence.textContent=tr('ui.view_evidence_key',{key:key.slice(0,8)});evidence.onclick=()=>openCorpusDocument(key);box.appendChild(evidence);}
    $('#draftCandidates').appendChild(box);
  }
}
function updateDraftAction(){
  $('#exportDraft').disabled=!corpusState.selected||!$('#confirmDraft').checked||!$('#draftDirectory').value.trim()||corpusState.exporting;
}
async function exportDraft(){
  if(!corpusState.selected||!$('#confirmDraft').checked||corpusState.exporting)return;
  corpusState.exporting=true;updateDraftAction();
  try{
    const r=await api('/api/export-draft',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
      markdown:$('#draftMarkdown').value,directory:$('#draftDirectory').value.trim(),confirmed:true})});
    $('#draftResult').textContent=tr('ui.draft_exported_path',{path:r.path});$('#confirmDraft').checked=false;
    workflow.draftPath=r.path;workflow.draftAgent=state.source.replace(/^(windows_|ubuntu_)/,'');$('#storeExportedDraft').style.display='';
  }catch(e){toast(e.message,true);}finally{corpusState.exporting=false;updateDraftAction();}
}
