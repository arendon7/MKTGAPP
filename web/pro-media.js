const PROXY_ACTIVE=new Set(['PENDING','RUNNING','CANCELLING']);
const PROXY_TERMINAL=new Set(['PASS','FAIL','CANCELLED','INTERRUPTED']);
state.proxyTimer=null;

function uid(prefix){
  if(globalThis.crypto?.randomUUID)return `${prefix}-${crypto.randomUUID().slice(0,8)}`;
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2,7)}`;
}
function proxyRecord(assetId){return state.current?.proxies?.[assetId]||null}
function proxyStatusLabel(row){
  if(!row)return 'Proxy: no generado';
  const size=row.bytes?` · ${fmtBytes(row.bytes)}`:'';
  const dims=row.width&&row.height?` · ${row.width}×${row.height}`:'';
  return `Proxy: ${row.status}${dims}${size}`;
}
function proxyFileUrl(assetId){return `/api/projects/${state.current.project.id}/assets/${assetId}/proxy/file`}
function proxyApiUrl(assetId){return `/api/projects/${state.current.project.id}/assets/${assetId}/proxy`}

function fillComposerSelects(){
  if(!state.current)return;
  const overlay=$('#overlay-asset'),audio=$('#audio-asset');
  const overlayValue=overlay.value,audioValue=audio.value;
  overlay.replaceChildren();audio.replaceChildren();
  const firstOverlay=el('option','','Imagen, logo o video');firstOverlay.value='';overlay.append(firstOverlay);
  const firstAudio=el('option','','Selecciona audio importado');firstAudio.value='';audio.append(firstAudio);
  for(const asset of state.current.assets){
    if(['image','logo','video'].includes(asset.kind)){const option=el('option','',asset.name);option.value=asset.id;overlay.append(option)}
    if(asset.kind==='audio'){const option=el('option','',asset.name);option.value=asset.id;audio.append(option)}
  }
  if([...overlay.options].some(row=>row.value===overlayValue))overlay.value=overlayValue;
  if([...audio.options].some(row=>row.value===audioValue))audio.value=audioValue;
}
function numberInput(value,step='0.1',min=null,max=null){
  const input=document.createElement('input');input.type='number';input.step=step;input.value=String(value);
  if(min!==null)input.min=String(min);if(max!==null)input.max=String(max);return input;
}
function composerField(labelText,input){const label=document.createElement('label');label.append(document.createTextNode(labelText),input);return label}

function renderOverlayList(){
  const root=$('#overlay-list');if(!root||!state.current)return;root.replaceChildren();
  const overlays=state.current.editor.overlays||[];$('#overlay-count').textContent=String(overlays.length);
  for(const row of [...overlays].sort((a,b)=>a.z_index-b.z_index)){
    const card=el('div','composer-row');
    const head=el('div','composer-row-head');head.append(el('strong','',assetName(row.asset_id)),el('span','',`z ${row.z_index}${row.behind_subject?' · capa inferior':''}`));
    const grid=el('div','composer-edit-grid');
    const start=numberInput(row.start,'0.1','0'),end=numberInput(row.end,'0.1','0.1'),x=numberInput(row.x,'0.01','0','1'),y=numberInput(row.y,'0.01','0','1'),scale=numberInput(row.scale,'0.05','0.05','8'),opacity=numberInput(row.opacity,'0.05','0','1'),z=numberInput(row.z_index,'1','-1000','1000');
    grid.append(composerField('Inicio',start),composerField('Fin',end),composerField('X',x),composerField('Y',y),composerField('Escala',scale),composerField('Opacidad',opacity),composerField('Z',z));
    const behind=document.createElement('input');behind.type='checkbox';behind.checked=Boolean(row.behind_subject);const behindLabel=el('label','check-label');behindLabel.append(behind,document.createTextNode(' Capa inferior'));
    const actions=el('div','toolbar composer-toolbar');
    const save=el('button','secondary','Guardar');save.type='button';save.addEventListener('click',()=>editorAction({action:'overlay_edit',id:row.id,start:Number(start.value),end:Number(end.value),x:Number(x.value),y:Number(y.value),scale:Number(scale.value),opacity:Number(opacity.value),z_index:Number(z.value),behind_subject:behind.checked}));
    const del=el('button','','Eliminar');del.type='button';del.addEventListener('click',()=>editorAction({action:'overlay_delete',id:row.id}));
    actions.append(save,del);card.append(head,grid,behindLabel,actions);root.append(card);
  }
  if(!overlays.length)root.append(el('p','muted','No hay capas adicionales.'));
}
function renderSubtitleList(){
  const root=$('#subtitle-list');if(!root||!state.current)return;root.replaceChildren();
  const subtitles=state.current.editor.subtitles||[];$('#subtitle-count').textContent=String(subtitles.length);
  for(const row of subtitles){
    const card=el('div','composer-row');
    const times=el('div','mini-grid');const start=numberInput(row.start,'0.1','0'),end=numberInput(row.end,'0.1','0.1');times.append(composerField('Inicio',start),composerField('Fin',end));
    const text=document.createElement('textarea');text.rows=2;text.value=row.text;
    const actions=el('div','toolbar composer-toolbar');
    const preview=el('button','','▶');preview.type='button';preview.addEventListener('click',()=>{const media=currentMedia();if(media){media.currentTime=row.start;media.play().catch(()=>{})}});
    const save=el('button','secondary','Guardar');save.type='button';save.addEventListener('click',()=>editorAction({action:'subtitle_edit',id:row.id,start:Number(start.value),end:Number(end.value),text:text.value}));
    const del=el('button','','Eliminar');del.type='button';del.addEventListener('click',()=>editorAction({action:'subtitle_delete',id:row.id}));
    actions.append(preview,save,del);card.append(times,text,actions);root.append(card);
  }
  if(!subtitles.length)root.append(el('p','muted','No hay subtítulos todavía.'));
}
function renderAudioState(){
  if(!state.current)return;const row=state.current.editor.audio_track;const root=$('#audio-current');
  $('#audio-state-chip').textContent=row&&row.enabled?'ON':'OFF';
  if(!row){root.textContent='Sin pista externa.';return}
  root.replaceChildren();
  root.append(el('strong','',assetName(row.asset_id)),el('span','',`offset ${Number(row.offset_seconds).toFixed(2)}s · ${Number(row.gain_db).toFixed(1)} dB · ${row.normalize?`${Number(row.target_lufs).toFixed(1)} LUFS`:'sin normalizar'} · ${row.replace_original?'reemplaza cámara':'mezcla con cámara'}`));
  $('#audio-asset').value=row.asset_id;$('#audio-offset').value=row.offset_seconds;$('#audio-gain').value=row.gain_db;$('#audio-lufs').value=row.target_lufs;$('#audio-normalize').checked=Boolean(row.normalize);$('#audio-replace').checked=Boolean(row.replace_original);
}
function renderProxyPanel(){
  const button=$('#proxy-generate'),status=$('#proxy-status'),select=$('#preview-source-select');if(!button||!status)return;
  const asset=state.previewAssetId?assetById(state.previewAssetId):null;
  if(!asset||asset.kind!=='video'){button.disabled=true;status.textContent='Proxy: selecciona un video';select.disabled=true;return}
  select.disabled=false;const row=proxyRecord(asset.id);status.textContent=proxyStatusLabel(row);button.disabled=Boolean(row&&PROXY_ACTIVE.has(row.status));
  button.textContent=row?.status==='PASS'?'Regenerar/verificar proxy':'Generar proxy optimizado';
}
function renderProMedia(){fillComposerSelects();renderOverlayList();renderSubtitleList();renderAudioState();renderProxyPanel();mountCompositionPreview()}

async function refreshProxy(assetId){
  if(!state.current)return null;
  const row=await api(proxyApiUrl(assetId));state.current.proxies=state.current.proxies||{};
  if(row.status==='NONE')delete state.current.proxies[assetId];else state.current.proxies[assetId]=row;
  renderProxyPanel();return row;
}
function scheduleProxyPoll(assetId){
  clearTimeout(state.proxyTimer);const row=proxyRecord(assetId);if(!row||!PROXY_ACTIVE.has(row.status))return;
  state.proxyTimer=setTimeout(async()=>{try{const next=await refreshProxy(assetId);if(next?.status==='PASS'){applyPreviewSource();toast('Proxy listo para preview')}else if(next&&PROXY_ACTIVE.has(next.status))scheduleProxyPoll(assetId);else if(next?.status==='FAIL')toast('El proxy no pudo generarse')}catch(err){toast(err.message)}},800);
}
async function ensureActiveProxy(){
  const asset=state.previewAssetId?assetById(state.previewAssetId):null;if(!asset||asset.kind!=='video'){toast('Selecciona un video');return}
  try{const row=await api(proxyApiUrl(asset.id),{method:'POST',body:{}});state.current.proxies=state.current.proxies||{};state.current.proxies[asset.id]=row;renderProxyPanel();scheduleProxyPoll(asset.id);toast(row.status==='PASS'?'Proxy reutilizado':'Generación de proxy iniciada')}catch(err){toast(err.message)}
}
function applyPreviewSource(){
  const asset=state.previewAssetId?assetById(state.previewAssetId):null;const media=currentMedia();if(!asset||asset.kind!=='video'||!media)return;
  const choice=$('#preview-source-select')?.value||'auto';const proxy=proxyRecord(asset.id);const useProxy=choice==='proxy'||(choice==='auto'&&proxy?.status==='PASS');
  if(choice==='proxy'&&proxy?.status!=='PASS'){toast('El proxy todavía no está disponible');return}
  const desired=useProxy?proxyFileUrl(asset.id):assetFileUrl(asset.id);const absolute=new URL(desired,location.href).href;
  if(media.src===absolute)return;
  const t=Number(media.currentTime)||0;const paused=media.paused;media.src=desired;media.load();media.addEventListener('loadedmetadata',()=>{media.currentTime=Math.min(t,Number.isFinite(media.duration)?media.duration:t);if(!paused)media.play().catch(()=>{})},{once:true});
  const suffix=useProxy?` · preview proxy ${proxy.width||''}×${proxy.height||''}`:' · preview original';if(state.previewProbe)$('#preview-meta').textContent=mediaMeta(state.previewProbe)+suffix;
}

function mountCompositionPreview(){
  const stage=$('#preview-stage'),media=currentMedia();if(!stage||!media||media.tagName!=='VIDEO'||!state.current)return;
  if(media.__binarioCompositionUpdate){
    media.removeEventListener('timeupdate',media.__binarioCompositionUpdate);
    media.removeEventListener('seeked',media.__binarioCompositionUpdate);
  }
  stage.querySelector('.composition-preview-layer')?.remove();
  const layer=el('div','composition-preview-layer');const subtitle=el('div','composition-subtitle');layer.append(subtitle);
  for(const row of state.current.editor.overlays||[]){
    const asset=assetById(row.asset_id);if(!asset||!['image','logo'].includes(asset.kind))continue;
    const img=document.createElement('img');img.className='composition-overlay';img.src=assetFileUrl(asset.id);img.alt=asset.name;img.dataset.overlayId=row.id;img.style.left=`${Number(row.x)*100}%`;img.style.top=`${Number(row.y)*100}%`;img.style.width=`${Math.max(4,Math.min(70,22*Number(row.scale)))}%`;img.style.opacity=String(row.opacity);img.style.zIndex=String(100+Number(row.z_index));layer.append(img);
  }
  if(state.current.editor.audio_track?.enabled){const badge=el('div','composition-audio-badge',`Audio externo · ${assetName(state.current.editor.audio_track.asset_id)}`);layer.append(badge)}
  stage.append(layer);
  const update=()=>updateCompositionPreview(media,layer,subtitle);media.__binarioCompositionUpdate=update;media.addEventListener('timeupdate',update);media.addEventListener('seeked',update);update();
}
function updateCompositionPreview(media,layer,subtitle){
  const t=Number(media.currentTime)||0;
  for(const img of layer.querySelectorAll('.composition-overlay')){const row=(state.current?.editor?.overlays||[]).find(item=>item.id===img.dataset.overlayId);img.hidden=!row||t<row.start||t>row.end}
  const active=(state.current?.editor?.subtitles||[]).filter(row=>t>=row.start&&t<=row.end);subtitle.textContent=active.map(row=>row.text).join('\n');subtitle.hidden=!active.length;
}
function decorateRenderRows(){
  const rows=[...document.querySelectorAll('#render-list .result-item')],jobs=[...(state.current?.renders||[])].reverse();
  rows.forEach((node,index)=>{const job=jobs[index];if(!job)return;if(job.composition_sha256)node.append(el('p','composition-hash',`Composición ${job.composition_sha256.slice(0,12)}…`));if(job.status==='PASS'&&job.subtitle_relative_path){const toolbar=node.querySelector('.toolbar')||el('div','toolbar');const link=el('a','','Descargar SRT');link.href=`/api/renders/${job.id}/subtitles`;link.download=job.subtitle_relative_path.split('/').pop();toolbar.append(link);if(!toolbar.parentElement)node.append(toolbar)}})
}

const baseRenderProject=renderProject;
renderProject=function(){baseRenderProject();renderProMedia()};
const baseRenderRenders=renderRenders;
renderRenders=function(){baseRenderRenders();decorateRenderRows()};
const basePreviewAsset=previewAsset;
previewAsset=async function(assetId,jumpTo=null){await basePreviewAsset(assetId,jumpTo);renderProxyPanel();applyPreviewSource();mountCompositionPreview();const row=proxyRecord(assetId);if(row&&PROXY_ACTIVE.has(row.status))scheduleProxyPoll(assetId)};

$('#proxy-generate').addEventListener('click',ensureActiveProxy);
$('#preview-source-select').addEventListener('change',applyPreviewSource);
$('#overlay-form').addEventListener('submit',async event=>{event.preventDefault();await editorAction({action:'overlay_add',id:uid('ov'),asset_id:$('#overlay-asset').value,start:Number($('#overlay-start').value),end:Number($('#overlay-end').value),x:Number($('#overlay-x').value),y:Number($('#overlay-y').value),scale:Number($('#overlay-scale').value),opacity:Number($('#overlay-opacity').value),z_index:Number($('#overlay-z').value),behind_subject:$('#overlay-behind').checked})});
$('#subtitle-form').addEventListener('submit',async event=>{event.preventDefault();const text=$('#subtitle-text').value.trim();if(!text)return;await editorAction({action:'subtitle_add',id:uid('sub'),start:Number($('#subtitle-start').value),end:Number($('#subtitle-end').value),text});$('#subtitle-text').value=''});
$('#audio-form').addEventListener('submit',async event=>{event.preventDefault();await editorAction({action:'audio_set',asset_id:$('#audio-asset').value,enabled:true,offset_seconds:Number($('#audio-offset').value),gain_db:Number($('#audio-gain').value),normalize:$('#audio-normalize').checked,target_lufs:Number($('#audio-lufs').value),replace_original:$('#audio-replace').checked})});
$('#audio-clear').addEventListener('click',()=>editorAction({action:'audio_clear'}));
window.addEventListener('beforeunload',()=>clearTimeout(state.proxyTimer));
