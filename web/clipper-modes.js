function ensureClipperModeControls(){
  let root=$('#clipper-mode-controls');if(root)return root;
  const run=$('#clipper-run');const form=run?.closest('.inline-form');if(!form)return null;
  root=el('div','clipper-mode-controls');root.id='clipper-mode-controls';root.style.display='grid';root.style.gridTemplateColumns='minmax(140px,1fr) minmax(110px,1fr)';root.style.gap='8px';root.style.marginTop='10px';
  const modeLabel=el('label','','');modeLabel.append(document.createTextNode('Modo'));const mode=document.createElement('select');mode.id='clipper-mode';for(const [value,label] of [['natural','Natural · idea completa'],['objective','Duración objetivo']]){const option=el('option','',label);option.value=value;mode.append(option)}modeLabel.append(mode);
  const targetLabel=el('label','','');targetLabel.append(document.createTextNode('Objetivo por clip (s)'));const target=document.createElement('input');target.id='clipper-target-duration';target.type='number';target.min='3';target.max='180';target.step='1';target.value='30';target.disabled=true;targetLabel.append(target);
  mode.addEventListener('change',()=>{target.disabled=mode.value!=='objective';renderClipperModeHelp()});target.addEventListener('change',()=>renderClipperModeHelp());root.append(modeLabel,targetLabel);form.parentElement.insertBefore(root,form.nextSibling);
  const help=el('p','muted','');help.id='clipper-mode-help';help.style.marginTop='7px';root.parentElement.insertBefore(help,root.nextSibling);renderClipperModeHelp();return root;
}
function renderClipperModeHelp(){const help=$('#clipper-mode-help'),mode=$('#clipper-mode');if(!help||!mode)return;help.textContent=mode.value==='objective'?`Busca cortes cercanos a ${Number($('#clipper-target-duration')?.value||30)}s, pero conserva límites narrativos y evita solapamientos.`:'Prioriza hook + idea autocontenida + cierre/acción; la duración puede variar dentro del mínimo y máximo.'}
function clipperModePayload(){ensureClipperModeControls();const mode=$('#clipper-mode')?.value||'natural';const payload={mode};if(mode==='objective')payload.target_duration=Number($('#clipper-target-duration')?.value||30);return payload}
function decorateNarrativeClipResults(){
  const rows=[...document.querySelectorAll('#clipper-results .result-item')];if(!rows.length)return;
  rows.forEach(node=>{if(node.querySelector('.narrative-meta'))return;const strong=node.querySelector('strong');if(!strong)return;const match=strong.textContent.match(/score\s+([\d.]+)/i);if(!match)return})
}

state.quickFlow=state.quickFlow||{projectId:null,assetId:null,clips:[],busy:false,bulkMode:null,bulkStop:false,bulkStatus:''};

function quickVideos(){return (state.current?.assets||[]).filter(asset=>asset.kind==='video')}
function quickAsset(){return quickVideos().find(asset=>asset.id===state.quickFlow.assetId)||null}
function quickTranscriptionRow(){
  const asset=quickAsset();if(!asset)return null;
  if(state.transcription?.assetId===asset.id&&state.transcription.record)return state.transcription.record;
  return state.current?.transcriptions?.[asset.id]||null;
}
function quickStage(row=quickTranscriptionRow()){
  if(!quickAsset())return 1;
  if(!row||row.status!=='PASS')return 2;
  if(!state.quickFlow.clips.length)return 3;
  return 4;
}
function ensureQuickEditorPanel(){
  let panel=$('#quick-editor');if(panel)return panel;
  const hero=document.querySelector('#project-view .project-hero');if(!hero)return null;
  panel=document.createElement('section');panel.id='quick-editor';panel.className='panel quick-editor-panel';
  panel.innerHTML=`
    <div class="section-head quick-editor-head">
      <div><p class="eyebrow">INICIO RÁPIDO</p><h3>De video a clips, en cuatro pasos</h3></div>
      <span id="quick-flow-state" class="quick-flow-state">1 · Carga un video</span>
    </div>
    <p class="quick-intro">Este flujo usa el mismo editor, Whisper local y Clipper narrativo del modo avanzado. No crea copias ni proyectos paralelos.</p>
    <div class="quick-flow-grid">
      <article class="quick-step" data-quick-step="1">
        <div class="quick-step-head"><span class="quick-step-number">1</span><div><strong>Video</strong><small>Elige o carga el material</small></div></div>
        <label>Video activo<select id="quick-asset-select"><option value="">Carga un video para comenzar</option></select></label>
        <div class="quick-step-actions"><button id="quick-upload-video" class="primary" type="button">+ Cargar video</button><button id="quick-preview-video" type="button">Ver</button></div>
        <p id="quick-asset-status" class="quick-step-status">Sin video seleccionado.</p>
      </article>
      <article class="quick-step" data-quick-step="2">
        <div class="quick-step-head"><span class="quick-step-number">2</span><div><strong>Transcripción</strong><small>Whisper local · sin subir audio</small></div></div>
        <label>Idioma<select id="quick-language"><option value="auto">Automático</option><option value="es">Español</option><option value="en">English</option><option value="it">Italiano</option><option value="fr">Français</option><option value="pt">Português</option></select></label>
        <button id="quick-transcribe" class="primary quick-wide" type="button">Transcribir automáticamente</button>
        <p id="quick-transcription-status" class="quick-step-status">Primero selecciona un video.</p>
      </article>
      <article class="quick-step" data-quick-step="3">
        <div class="quick-step-head"><span class="quick-step-number">3</span><div><strong>Selección IA</strong><small>Encuentra los mejores cortes</small></div></div>
        <label>Modo<select id="quick-clip-mode"><option value="natural">Natural · idea completa</option><option value="objective">Duración objetivo</option></select></label>
        <label>Formato<select id="quick-aspect"><option value="9:16">Vertical 9:16 · Reels / TikTok</option><option value="16:9">Horizontal 16:9</option><option value="1:1">Cuadrado 1:1</option><option value="4:5">Feed 4:5</option></select></label>
        <div class="quick-mini-grid"><label>Cantidad<input id="quick-clip-count" type="number" min="1" max="20" value="3"></label><label>Objetivo s<input id="quick-target-duration" type="number" min="3" max="180" step="1" value="30" disabled></label></div>
        <button id="quick-generate-clips" class="primary quick-wide" type="button">Generar mejores clips</button>
        <p id="quick-selection-status" class="quick-step-status">Transcribe el video para continuar.</p>
      </article>
      <article class="quick-step quick-output-step" data-quick-step="4">
        <div class="quick-step-head"><span class="quick-step-number">4</span><div><strong>Resultado</strong><small>Preview, timeline o exportación</small></div></div>
        <div class="quick-step-actions"><button id="quick-add-all-timeline" type="button">+ Todos al timeline</button><button id="quick-export-all" class="primary" type="button">Exportar todos</button></div>
        <p id="quick-bulk-status" class="quick-step-status">Las acciones masivas omiten duplicados y exportan un clip a la vez.</p>
        <div id="quick-clip-results" class="quick-clip-results"><p class="quick-empty">Aquí aparecerán tus clips seleccionados.</p></div>
      </article>
    </div>
    <div class="quick-editor-footer"><span id="quick-flow-hint">Empieza cargando un video.</span><button id="quick-open-advanced" type="button">Abrir editor avanzado</button></div>`;
  hero.insertAdjacentElement('afterend',panel);bindQuickEditor();deemphasizeManualClipper();return panel;
}
function deemphasizeManualClipper(){
  const panel=$('#clipper-input')?.closest('.panel');if(!panel||panel.dataset.quickDeemphasized==='1')return;
  panel.dataset.quickDeemphasized='1';const eyebrow=panel.querySelector('.eyebrow'),title=panel.querySelector('h3'),copy=panel.querySelector(':scope > p.muted');
  if(eyebrow)eyebrow.textContent='MODO AVANZADO';if(title)title.textContent='Clipper manual';if(copy)copy.textContent='Opcional: pega segmentos inicio|fin|texto cuando quieras controlar manualmente el transcript y los límites de selección.';
}
function syncQuickAssetOptions(){
  const select=$('#quick-asset-select');if(!select||!state.current)return;
  const projectId=state.current.project.id;if(state.quickFlow.projectId!==projectId){state.quickFlow.projectId=projectId;state.quickFlow.assetId=null;state.quickFlow.clips=[];state.quickFlow.bulkMode=null;state.quickFlow.bulkStop=false;state.quickFlow.bulkStatus=''}
  const videos=quickVideos();const preview=videos.find(asset=>asset.id===state.previewAssetId);
  if(!videos.some(asset=>asset.id===state.quickFlow.assetId))state.quickFlow.assetId=preview?.id||videos[0]?.id||null;
  const chosen=state.quickFlow.assetId;select.replaceChildren();
  if(!videos.length){const option=el('option','','Carga un video para comenzar');option.value='';select.append(option);select.disabled=true;return}
  select.disabled=false;for(const asset of videos){const option=el('option','',asset.name);option.value=asset.id;select.append(option)}select.value=chosen||videos[0].id;
}
function quickStatusText(row){
  if(!row)return 'Listo para transcribir.';
  if(typeof transcriptionPhase==='function')return transcriptionPhase(row);
  return row.status||'Sin transcribir';
}
function quickClipOnTimeline(asset,clip){
  if(!asset)return false;const start=Number(clip.start),end=Number(clip.end);return (state.current?.editor?.clips||[]).some(row=>row.asset_id===asset.id&&Number(row.track)===0&&Math.abs(Number(row.start)-start)<.05&&Math.abs(Number(row.end)-end)<.05)
}
function quickRenderLabel(index){return `quick-clip-${index+1}`}
function quickRenderJob(asset,clip,index){
  if(!asset)return null;const marker=`-${quickRenderLabel(index)}.mp4`,start=Number(clip.start),end=Number(clip.end);
  return [...(state.current?.renders||[])].reverse().find(job=>job.asset_id===asset.id&&String(job.output_name||'').endsWith(marker)&&Math.abs(Number(job.start)-start)<.05&&Math.abs(Number(job.end)-end)<.05)||null
}
function quickRenderStatus(job){
  if(!job)return '';return ({PENDING:'En cola',RUNNING:'Exportando',CANCELLING:'Cancelando',PASS:'Listo',FAIL:'Error',CANCELLED:'Cancelado',INTERRUPTED:'Interrumpido'})[job.status]||job.status
}
async function quickStartRender(clip,index,{quiet=false}={}){
  const asset=quickAsset();if(!asset||!state.current)return null;const start=Number(clip.start),end=Number(clip.end),aspect=$('#quick-aspect')?.value||'9:16',label=quickRenderLabel(index);
  try{const job=await api(`/api/projects/${state.current.project.id}/renders`,{method:'POST',body:{asset_id:asset.id,start,end,label,aspect}});state.current.renders=[...(state.current.renders||[]),job];renderProject();scheduleRenderPoll();if(!quiet)toast(job.status==='FAIL'?`Render bloqueado: ${job.error}`:`Exportación ${aspect} iniciada`);return job}catch(err){if(!quiet)toast(err.message);return null}
}
function renderQuickRenderState(card,job){
  if(!job)return;const wrap=el('div','result-item quick-render-state'),pct=Math.round((Number(job.progress)||0)*100);wrap.append(el('strong','',`${quickRenderStatus(job)} · ${job.width}×${job.height}`));
  if(ACTIVE_RENDERS.has(job.status)){const progress=document.createElement('progress');progress.max=100;progress.value=pct;progress.title=`${pct}%`;wrap.append(progress,el('span','',` ${pct}%`));const cancel=el('button','','Cancelar');cancel.type='button';cancel.addEventListener('click',()=>cancelRender(job.id));wrap.append(cancel)}
  if(job.status==='PASS'){const meta=el('span','',`${job.bytes?fmtBytes(job.bytes):''}${job.sha256?` · ${job.sha256.slice(0,10)}…`:''}`);wrap.append(meta);const link=el('a','','Descargar');link.href=`/api/renders/${job.id}/file`;link.download=job.output_name;wrap.append(link)}
  if(job.status==='FAIL'&&job.error)wrap.append(el('p','muted',String(job.error).slice(-280)));card.append(wrap)
}
async function quickAddAllTimeline(){
  if(state.quickFlow.bulkMode||!state.current)return;const asset=quickAsset(),clips=state.quickFlow.clips;if(!asset||!clips.length)return;const projectId=state.current.project.id;state.quickFlow.bulkMode='timeline';state.quickFlow.bulkStatus='Añadiendo clips faltantes a Track 0…';renderQuickEditor();let added=0;
  try{for(const clip of clips){if(state.current?.project?.id!==projectId)break;if(quickClipOnTimeline(asset,clip))continue;state.current.editor=await api(`/api/projects/${projectId}/editor/actions`,{method:'POST',body:{action:'add_clip',asset_id:asset.id,start:Number(clip.start),end:Number(clip.end),track:0}});added++}await refreshTimeline();state.quickFlow.bulkStatus=added?`${added} clip${added===1?'':'s'} añadido${added===1?'':'s'} a Track 0.`:'Todos los clips ya estaban en Track 0.';toast(state.quickFlow.bulkStatus)}catch(err){state.quickFlow.bulkStatus=`No pude completar Timeline todos: ${err.message}`;toast(err.message)}finally{state.quickFlow.bulkMode=null;renderProject()}
}
async function quickWaitRender(jobId,projectId){
  while(state.current?.project?.id===projectId){const job=(state.current.renders||[]).find(row=>row.id===jobId);if(job&&!ACTIVE_RENDERS.has(job.status))return job;await new Promise(resolve=>setTimeout(resolve,500))}return null
}
async function quickExportAll(){
  if(state.quickFlow.bulkMode==='export'){state.quickFlow.bulkStop=true;state.quickFlow.bulkStatus='La cola se detendrá después del clip actual.';renderQuickEditor();return}
  if(state.quickFlow.bulkMode||!state.current)return;const asset=quickAsset(),clips=state.quickFlow.clips;if(!asset||!clips.length)return;const projectId=state.current.project.id;state.quickFlow.bulkMode='export';state.quickFlow.bulkStop=false;let passed=0,skipped=0,failed=0;
  try{for(let index=0;index<clips.length;index++){if(state.current?.project?.id!==projectId||state.quickFlow.bulkStop)break;const clip=clips[index];state.quickFlow.bulkStatus=`Exportando ${index+1}/${clips.length} · un render a la vez`;renderQuickEditor();let job=quickRenderJob(asset,clip,index);if(job?.status==='PASS'){skipped++;continue}if(!job||!ACTIVE_RENDERS.has(job.status))job=await quickStartRender(clip,index,{quiet:true});if(!job){failed++;continue}if(ACTIVE_RENDERS.has(job.status))job=await quickWaitRender(job.id,projectId);if(job?.status==='PASS')passed++;else if(job)failed++;if(state.quickFlow.bulkStop)break}const stopped=state.quickFlow.bulkStop?' · cola detenida':'';state.quickFlow.bulkStatus=`${passed} exportado${passed===1?'':'s'} · ${skipped} ya listo${skipped===1?'':'s'} · ${failed} error${failed===1?'':'es'}${stopped}`;toast(state.quickFlow.bulkStatus)}catch(err){state.quickFlow.bulkStatus=`Exportación masiva interrumpida: ${err.message}`;toast(err.message)}finally{state.quickFlow.bulkMode=null;state.quickFlow.bulkStop=false;renderQuickEditor()}
}
function renderQuickResults(){
  const root=$('#quick-clip-results');if(!root)return;root.replaceChildren();const asset=quickAsset();
  if(!state.quickFlow.clips.length){root.append(el('p','quick-empty',quickTranscriptionRow()?.status==='PASS'?'Genera los mejores clips para verlos aquí.':'Aquí aparecerán tus clips seleccionados.'));return}
  state.quickFlow.clips.forEach((clip,index)=>{
    const start=Number(clip.start),end=Number(clip.end),duration=Math.max(0,end-start),job=quickRenderJob(asset,clip,index),onTimeline=quickClipOnTimeline(asset,clip);const card=el('div','quick-clip-card');
    const top=el('div','quick-clip-top');top.append(el('strong','',`Clip ${index+1} · ${duration.toFixed(1)}s`),el('span','',`${start.toFixed(1)}–${end.toFixed(1)}s`));card.append(top,el('p','',clip.text||''));
    if(clip.tone||clip.reasons?.length)card.append(el('span','quick-clip-meta',[clip.tone,...(clip.reasons||[])].filter(Boolean).join(' · ')));
    const actions=el('div','quick-clip-actions');const preview=el('button','','▶ Preview');preview.type='button';preview.addEventListener('click',()=>previewAsset(asset.id,start));
    const timeline=el('button','',onTimeline?'✓ Timeline':'+ Timeline');timeline.type='button';timeline.disabled=onTimeline||Boolean(state.quickFlow.bulkMode);timeline.addEventListener('click',async()=>{await editorAction({action:'add_clip',asset_id:asset.id,start,end,track:0});toast(`Clip ${index+1} añadido al timeline`)});
    const exportBtn=el('button','primary',job&&ACTIVE_RENDERS.has(job.status)?'Exportando…':job?.status==='PASS'?'Exportar de nuevo':'Exportar');exportBtn.type='button';exportBtn.disabled=Boolean(job&&ACTIVE_RENDERS.has(job.status))||Boolean(state.quickFlow.bulkMode);exportBtn.addEventListener('click',()=>quickStartRender(clip,index));actions.append(preview,timeline,exportBtn);card.append(actions);renderQuickRenderState(card,job);root.append(card)
  })
}
function renderQuickEditor(){
  const panel=ensureQuickEditorPanel();if(!panel||!state.current)return;syncQuickAssetOptions();const asset=quickAsset(),row=quickTranscriptionRow(),stage=quickStage(row),active=row&&TRANSCRIPTION_ACTIVE.has(row.status),hasClips=state.quickFlow.clips.length>0;
  $('#quick-flow-state').textContent=active?'2 · Transcribiendo…':stage===1?'1 · Carga un video':stage===2?'2 · Transcribe':stage===3?'3 · Genera clips':'4 · Revisa y exporta';
  document.querySelectorAll('#quick-editor .quick-step').forEach(node=>{const value=Number(node.dataset.quickStep);node.classList.toggle('active',value===stage);node.classList.toggle('done',value<stage)});
  $('#quick-asset-status').textContent=asset?`${asset.name}${asset.bytes?` · ${fmtBytes(asset.bytes)}`:''}`:'Sin video seleccionado.';
  $('#quick-preview-video').disabled=!asset;$('#quick-transcribe').disabled=!asset||Boolean(active)||state.quickFlow.busy||Boolean(state.quickFlow.bulkMode);
  $('#quick-transcription-status').textContent=!asset?'Primero selecciona un video.':row?`${quickStatusText(row)}${row.language?` · ${row.language}`:''}${row.segments_count?` · ${row.segments_count} segmentos`:''}${row.duration?` · ${Number(row.duration).toFixed(1)}s`:''}${row.error?` · ${String(row.error).slice(-140)}`:''}`:'Listo para transcribir.';
  $('#quick-generate-clips').disabled=!asset||row?.status!=='PASS'||state.quickFlow.busy||Boolean(state.quickFlow.bulkMode);
  $('#quick-selection-status').textContent=row?.status==='PASS'?(hasClips?`${state.quickFlow.clips.length} clip${state.quickFlow.clips.length===1?'':'s'} listo${state.quickFlow.clips.length===1?'':'s'}.`:'Transcript listo. Elige modo y genera los cortes.'):'Transcribe el video para continuar.';
  $('#quick-add-all-timeline').disabled=!hasClips||Boolean(state.quickFlow.bulkMode);
  const exportAll=$('#quick-export-all');exportAll.disabled=!hasClips||Boolean(state.quickFlow.bulkMode&&state.quickFlow.bulkMode!=='export');exportAll.textContent=state.quickFlow.bulkMode==='export'?'Detener después del actual':'Exportar todos';
  $('#quick-bulk-status').textContent=state.quickFlow.bulkStatus||(hasClips?'Las acciones masivas omiten duplicados y exportan un clip a la vez.':'Genera clips para habilitar acciones masivas.');
  $('#quick-flow-hint').textContent=stage===1?'Carga tu video y el proyecto conservará el original con SHA-256.':stage===2?(active?'Whisper está procesando localmente; puedes seguir en esta pantalla.':'La transcripción queda guardada dentro del proyecto.'):stage===3?'Natural prioriza ideas completas; Objetivo intenta acercarse a una duración concreta.':'Previsualiza cada corte, llévalo al timeline o expórtalo directamente.';
  if(row&&TRANSCRIPTION_ACTIVE.has(row.status)&&state.transcription.assetId!==asset?.id)setTimeout(()=>setTranscriptionAsset(asset.id),0);
  renderQuickResults()
}
async function quickUploadVideo(){
  if(!state.current||state.quickFlow.busy||state.quickFlow.bulkMode)return;const input=document.createElement('input');input.type='file';input.accept='video/*';input.multiple=false;
  input.addEventListener('change',async()=>{const file=input.files?.[0];if(!file)return;state.quickFlow.busy=true;renderQuickEditor();try{const projectId=state.current.project.id;const response=await fetch(`/api/projects/${encodeURIComponent(projectId)}/assets/upload?filename=${encodeURIComponent(file.name)}&kind=video`,{method:'POST',headers:{'Content-Type':file.type||'application/octet-stream'},body:file});const payload=await response.json().catch(()=>({}));if(!response.ok)throw new Error(payload.error||`HTTP ${response.status}`);state.quickFlow.assetId=payload.id;state.quickFlow.clips=[];state.quickFlow.bulkStatus='';await selectProject(projectId);state.quickFlow.assetId=payload.id;await previewAsset(payload.id);toast('Video cargado. Siguiente paso: transcribir.') }catch(err){toast(err.message)}finally{state.quickFlow.busy=false;renderQuickEditor()}});input.click()
}
async function quickStartTranscription(){
  const asset=quickAsset();if(!asset||state.quickFlow.busy||state.quickFlow.bulkMode)return;state.quickFlow.busy=true;state.quickFlow.clips=[];state.quickFlow.bulkStatus='';renderQuickEditor();
  try{await setTranscriptionAsset(asset.id,false);const language=$('#quick-language').value;const advanced=$('#transcription-language');if(advanced)advanced.value=language;const row=await api(transcriptionUrl(asset.id),{method:'POST',body:{language}});state.transcription.assetId=asset.id;state.transcription.record=row;state.transcription.segments=[];renderTranscriptionPanel();scheduleTranscriptionPoll();toast(row.status==='FAIL'?`Transcripción bloqueada: ${row.error}`:'Transcripción local iniciada') }catch(err){toast(err.message)}finally{state.quickFlow.busy=false;renderQuickEditor()}
}
function quickClipBounds(row,mode){
  const duration=Math.max(.5,Number(row?.duration||75));if(mode==='natural'){const maximum=Math.max(.5,Math.min(75,duration));let minimum=Math.min(15,Math.max(.25,maximum*.25));if(maximum<=minimum)minimum=Math.max(.1,maximum*.5);return {minimum,maximum,target:null}}
  const requested=Math.max(.5,Number($('#quick-target-duration').value||30)),target=Math.min(requested,duration);let minimum=Math.max(.1,target*.6),maximum=Math.min(duration,Math.max(target+.25,target*1.45));if(maximum<=minimum)minimum=Math.max(.1,maximum*.5);return {minimum,maximum,target}
}
async function quickGenerateClips(){
  const asset=quickAsset(),row=quickTranscriptionRow();if(!asset||row?.status!=='PASS'||state.quickFlow.busy||state.quickFlow.bulkMode){toast('Primero completa la transcripción');return}state.quickFlow.busy=true;state.quickFlow.bulkStatus='';renderQuickEditor();
  try{const mode=$('#quick-clip-mode').value,bounds=quickClipBounds(row,mode),payload={target_count:Number($('#quick-clip-count').value||3),min_duration:bounds.minimum,max_duration:bounds.maximum,mode};if(bounds.target!==null)payload.target_duration=bounds.target;const clips=await api(transcriptionUrl(asset.id,'/clips'),{method:'POST',body:payload});state.quickFlow.clips=clips;const advancedMode=$('#clipper-mode');if(advancedMode)advancedMode.value=mode;const advancedTarget=$('#clipper-target-duration');if(advancedTarget){advancedTarget.disabled=mode!=='objective';if(bounds.target!==null)advancedTarget.value=String(Math.round(bounds.target))}const advancedCount=$('#clipper-count');if(advancedCount)advancedCount.value=String(payload.target_count);toast(`${clips.length} clip${clips.length===1?'':'s'} seleccionado${clips.length===1?'':'s'}`)}catch(err){toast(err.message)}finally{state.quickFlow.busy=false;renderQuickEditor()}
}
function bindQuickEditor(){
  const panel=$('#quick-editor');if(!panel||panel.dataset.bound==='1')return;panel.dataset.bound='1';
  $('#quick-upload-video').addEventListener('click',quickUploadVideo);$('#quick-preview-video').addEventListener('click',()=>{const asset=quickAsset();if(asset)previewAsset(asset.id)});$('#quick-transcribe').addEventListener('click',quickStartTranscription);$('#quick-generate-clips').addEventListener('click',quickGenerateClips);$('#quick-add-all-timeline').addEventListener('click',quickAddAllTimeline);$('#quick-export-all').addEventListener('click',quickExportAll);
  $('#quick-asset-select').addEventListener('change',async event=>{if(state.quickFlow.bulkMode)return;state.quickFlow.assetId=event.target.value||null;state.quickFlow.clips=[];state.quickFlow.bulkStatus='';if(state.quickFlow.assetId)await setTranscriptionAsset(state.quickFlow.assetId);renderQuickEditor()});
  $('#quick-clip-mode').addEventListener('change',event=>{$('#quick-target-duration').disabled=event.target.value!=='objective';renderQuickEditor()});$('#quick-target-duration').addEventListener('change',renderQuickEditor);$('#quick-clip-count').addEventListener('change',renderQuickEditor);$('#quick-aspect').addEventListener('change',renderQuickEditor);
  $('#quick-open-advanced').addEventListener('click',()=>document.querySelector('.editor-preview-panel')?.scrollIntoView({behavior:'smooth',block:'start'}))
}

ensureClipperModeControls();
const quickBaseRenderProject=renderProject;
renderProject=function(){quickBaseRenderProject();ensureQuickEditorPanel();renderQuickEditor()};
const quickBaseRenderRenders=renderRenders;
renderRenders=function(){quickBaseRenderRenders();if($('#quick-editor'))renderQuickResults()};
const quickBaseRenderTranscriptionPanel=renderTranscriptionPanel;
renderTranscriptionPanel=function(){quickBaseRenderTranscriptionPanel();renderQuickEditor()};
ensureQuickEditorPanel();
if(state.current)renderQuickEditor();