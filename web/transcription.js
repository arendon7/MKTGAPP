const TRANSCRIPTION_ACTIVE=new Set(['PENDING','EXTRACTING_AUDIO','TRANSCRIBING','CANCELLING']);
state.transcription=state.transcription||{assetId:null,record:null,segments:[],timer:null};

function transcriptionUrl(assetId,suffix=''){return `/api/projects/${state.current.project.id}/assets/${assetId}/transcription${suffix}`}
function activeTranscribableAsset(){const id=state.transcription.assetId||state.previewAssetId;const asset=id?assetById(id):null;return asset&&['video','audio'].includes(asset.kind)?asset:null}
function transcriptionPhase(row){
  if(!row||row.status==='NONE')return 'Sin transcribir';
  const map={PENDING:'En cola',EXTRACTING_AUDIO:'Extrayendo audio',TRANSCRIBING:'Transcribiendo localmente',CANCELLING:'Cancelando',PASS:'Transcript listo',FAIL:'Falló',CANCELLED:'Cancelado',INTERRUPTED:'Interrumpido'};
  return map[row.status]||row.status;
}
function ensureTranscriptionPanel(){
  let panel=$('#transcription-panel');if(panel)return panel;
  const clipper=$('#clipper-input')?.closest('.panel');if(!clipper)return null;
  panel=el('div','transcription-panel');panel.id='transcription-panel';panel.style.marginTop='14px';panel.style.padding='14px';panel.style.border='1px solid #e2e1dc';panel.style.borderRadius='13px';panel.style.background='#f8f7f3';
  const head=el('div','section-head');const copy=el('div','');copy.append(el('p','eyebrow','TRANSCRIPCIÓN'),el('h4','','Video → texto → clips'));const badge=el('span','badge','LOCAL');badge.id='transcription-engine-badge';head.append(copy,badge);
  const controls=el('div','transcription-controls');controls.style.display='grid';controls.style.gridTemplateColumns='minmax(120px,1fr) auto auto';controls.style.gap='7px';controls.style.alignItems='end';
  const langLabel=el('label','','');langLabel.append(document.createTextNode('Idioma'));const lang=document.createElement('select');lang.id='transcription-language';for(const [value,label] of [['auto','Automático'],['es','Español'],['en','English'],['it','Italiano'],['fr','Français'],['pt','Português']]){const opt=el('option','',label);opt.value=value;lang.append(opt)}langLabel.append(lang);
  const start=el('button','primary','Transcribir');start.id='transcription-start';start.type='button';start.addEventListener('click',startTranscription);
  const cancel=el('button','','Cancelar');cancel.id='transcription-cancel';cancel.type='button';cancel.addEventListener('click',cancelTranscription);
  controls.append(langLabel,start,cancel);
  const status=el('div','transcription-status muted','Selecciona un video o audio.');status.id='transcription-status';status.style.marginTop='9px';
  const preview=document.createElement('textarea');preview.id='transcription-preview';preview.rows=6;preview.readOnly=true;preview.placeholder='El transcript aparecerá aquí.';preview.style.marginTop='9px';
  const actions=el('div','toolbar composer-toolbar');actions.style.marginTop='8px';
  const manual=el('button','','Pasar al Clipper manual');manual.id='transcription-to-manual';manual.type='button';manual.addEventListener('click',transcriptToManualClipper);
  const select=el('button','secondary','Elegir mejores clips');select.id='transcription-select-clips';select.type='button';select.addEventListener('click',selectClipsFromTranscript);
  actions.append(manual,select);panel.append(head,controls,status,preview,actions);
  const results=$('#clipper-results');clipper.insertBefore(panel,results);
  return panel;
}
function renderTranscriptionPanel(){
  const panel=ensureTranscriptionPanel();if(!panel)return;const asset=activeTranscribableAsset(),row=state.transcription.record;
  const start=$('#transcription-start'),cancel=$('#transcription-cancel'),manual=$('#transcription-to-manual'),select=$('#transcription-select-clips');
  start.disabled=!asset||Boolean(row&&TRANSCRIPTION_ACTIVE.has(row.status));cancel.disabled=!row||!TRANSCRIPTION_ACTIVE.has(row.status);manual.disabled=!row||row.status!=='PASS';select.disabled=!row||row.status!=='PASS';
  if(!asset){$('#transcription-status').textContent='Selecciona Preview en un video o audio para transcribir.';$('#transcription-preview').value='';return}
  const detail=row?`${transcriptionPhase(row)}${row.language?` · ${row.language}`:''}${row.segments_count?` · ${row.segments_count} segmentos`:''}${row.duration?` · ${Number(row.duration).toFixed(1)}s`:''}`:'Sin transcribir';
  $('#transcription-status').textContent=`${asset.name} · ${detail}${row?.error?` · ${String(row.error).slice(-240)}`:''}`;
  $('#transcription-preview').value=(state.transcription.segments||[]).map(item=>`[${Number(item.start).toFixed(1)}–${Number(item.end).toFixed(1)}] ${item.text}`).join('\n');
}
async function setTranscriptionAsset(assetId,refresh=true){
  const asset=assetId?assetById(assetId):null;if(!asset||!['video','audio'].includes(asset.kind)){state.transcription.assetId=null;state.transcription.record=null;state.transcription.segments=[];renderTranscriptionPanel();return}
  state.transcription.assetId=assetId;if(refresh)await refreshTranscription(assetId);
}
async function refreshTranscription(assetId=state.transcription.assetId){
  if(!state.current||!assetId)return;try{const row=await api(transcriptionUrl(assetId));state.transcription.record=row.status==='NONE'?null:row;if(row.status==='PASS')state.transcription.segments=await api(transcriptionUrl(assetId,'/segments'));else if(row.status==='NONE')state.transcription.segments=[];renderTranscriptionPanel();scheduleTranscriptionPoll()}catch(err){toast(err.message)}
}
function scheduleTranscriptionPoll(){clearTimeout(state.transcription.timer);const row=state.transcription.record;if(row&&TRANSCRIPTION_ACTIVE.has(row.status))state.transcription.timer=setTimeout(()=>refreshTranscription(),900)}
async function startTranscription(){
  const asset=activeTranscribableAsset();if(!asset){toast('Selecciona un video o audio');return}state.transcription.assetId=asset.id;
  try{const row=await api(transcriptionUrl(asset.id),{method:'POST',body:{language:$('#transcription-language').value}});state.transcription.record=row;state.transcription.segments=[];renderTranscriptionPanel();scheduleTranscriptionPoll();toast(row.status==='FAIL'?`Transcripción bloqueada: ${row.error}`:'Transcripción local iniciada')}catch(err){toast(err.message)}
}
async function cancelTranscription(){const asset=activeTranscribableAsset();if(!asset)return;try{state.transcription.record=await api(transcriptionUrl(asset.id,'/cancel'),{method:'POST',body:{}});renderTranscriptionPanel();scheduleTranscriptionPoll();toast('Cancelación solicitada')}catch(err){toast(err.message)}}
function transcriptToManualClipper(){if(!state.transcription.segments.length)return;$('#clipper-input').value=state.transcription.segments.map(row=>`${Number(row.start).toFixed(3)}|${Number(row.end).toFixed(3)}|${row.text}`).join('\n');toast('Transcript cargado al Clipper manual')}
function renderTranscriptClipCandidates(clips,assetId){
  const root=$('#clipper-results');root.replaceChildren();for(const clip of clips){const item=el('div','result-item');item.append(el('strong','',`${clip.start.toFixed(1)}–${clip.end.toFixed(1)}s · score ${clip.score}`),el('p','',clip.text));if(clip.tone)item.append(el('span','narrative-meta',`${clip.tone} · ${(clip.reasons||[]).join(' · ')}`));const actions=el('div','toolbar');const preview=el('button','','Preview');preview.type='button';preview.addEventListener('click',()=>previewAsset(assetId,clip.start));const exportBtn=el('button','secondary','Exportar');exportBtn.type='button';exportBtn.addEventListener('click',()=>startRender({asset_id:assetId,start:clip.start,end:clip.end,label:'auto-clipper'}));actions.append(preview,exportBtn);item.append(actions);root.append(item)}if(!clips.length)root.append(el('p','muted','No hubo candidatos con esos límites.'))
}
async function selectClipsFromTranscript(){
  const asset=activeTranscribableAsset();if(!asset||state.transcription.record?.status!=='PASS'){toast('Primero completa la transcripción');return}
  try{const clips=await api(transcriptionUrl(asset.id,'/clips'),{method:'POST',body:{target_count:Number($('#clipper-count').value),min_duration:Number($('#clipper-min').value),max_duration:Number($('#clipper-max').value),...(globalThis.clipperModePayload?clipperModePayload():{})}});renderTranscriptClipCandidates(clips,asset.id);toast(`${clips.length} clip${clips.length===1?'':'s'} seleccionado${clips.length===1?'':'s'} desde transcript`)}catch(err){toast(err.message)}
}
function decorateTranscriptionAssets(){
  if(!state.current)return;const rows=[...document.querySelectorAll('#asset-list .asset-item')];rows.forEach((node,index)=>{const asset=state.current.assets[index];if(!asset||!['video','audio'].includes(asset.kind)||node.querySelector('.transcribe-asset-button'))return;const actions=node.querySelector('.asset-actions')||node;const button=el('button','transcribe-asset-button','Transcribir');button.type='button';button.addEventListener('click',async event=>{event.stopPropagation();if(asset.kind==='video')await previewAsset(asset.id);await setTranscriptionAsset(asset.id);startTranscription()});actions.prepend(button)})
}

const transcriptionBaseRenderProject=renderProject;
renderProject=function(){transcriptionBaseRenderProject();ensureTranscriptionPanel();decorateTranscriptionAssets();renderTranscriptionPanel()};
const transcriptionBaseRenderAssets=renderAssets;
renderAssets=function(){transcriptionBaseRenderAssets();decorateTranscriptionAssets()};
const transcriptionBasePreviewAsset=previewAsset;
previewAsset=async function(assetId,jumpTo=null){const result=await transcriptionBasePreviewAsset(assetId,jumpTo);const asset=assetById(assetId);if(asset&&['video','audio'].includes(asset.kind))await setTranscriptionAsset(assetId);return result};
window.addEventListener('beforeunload',()=>clearTimeout(state.transcription.timer));
ensureTranscriptionPanel();renderTranscriptionPanel();
