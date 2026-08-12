const VISUAL_MIN_CLIP_SECONDS=0.1;
state.visualTimeline=state.visualTimeline||{draggedClipId:null,probeCache:{},masterActive:false,masterPlaying:false,masterIndex:0,masterTime:0,switching:false,advancing:false};

function visualTrackZero(){return (state.current?.editor?.clips||[]).filter(row=>Number(row.track)===0)}
function visualMasterDuration(){return visualTrackZero().reduce((sum,row)=>sum+Math.max(0,Number(row.end)-Number(row.start)),0)}
function visualClipDuration(clip){return Math.max(0,Number(clip.end)-Number(clip.start))}
function visualFormatTime(seconds){const value=Math.max(0,Number(seconds)||0);const mins=Math.floor(value/60);const secs=value-mins*60;return `${mins}:${secs.toFixed(2).padStart(5,'0')}`}
function visualLocateMasterTime(seconds){
  const clips=visualTrackZero();let cursor=0;const target=Math.max(0,Math.min(Number(seconds)||0,visualMasterDuration()));
  for(let index=0;index<clips.length;index++){
    const duration=visualClipDuration(clips[index]);
    if(target<=cursor+duration||index===clips.length-1)return{clip:clips[index],index,offset:Math.max(0,Math.min(duration,target-cursor)),masterStart:cursor};
    cursor+=duration;
  }
  return null;
}
async function visualProbe(assetId){
  if(state.visualTimeline.probeCache[assetId])return state.visualTimeline.probeCache[assetId];
  const row=await api(`/api/projects/${state.current.project.id}/assets/${assetId}/probe`);state.visualTimeline.probeCache[assetId]=row;return row;
}

function ensureVisualTimelineEditor(){
  const panel=document.querySelector('.timeline-panel');if(!panel)return null;
  let root=$('#visual-track-editor');
  if(root)return root;
  root=el('div','visual-track-editor');root.id='visual-track-editor';
  const head=el('div','visual-track-head');
  const copy=el('div','');copy.append(el('p','eyebrow','EDICIÓN VISUAL'),el('strong','visual-track-title','Master Track 0'));
  const meta=el('span','visual-track-meta','0 clips');meta.id='visual-track-meta';copy.append(meta);
  const controls=el('div','visual-master-controls');
  const preview=el('button','secondary','Previsualizar master');preview.id='visual-master-preview';preview.type='button';preview.addEventListener('click',visualToggleMasterPreview);
  const stop=el('button','','Detener');stop.id='visual-master-stop';stop.type='button';stop.addEventListener('click',()=>visualStopMaster(true));
  controls.append(preview,stop);head.append(copy,controls);
  const rail=el('div','visual-sequence-rail');rail.id='visual-sequence-rail';
  const play=el('div','visual-playhead-row');
  const range=document.createElement('input');range.id='visual-master-playhead';range.type='range';range.min='0';range.max='0';range.step='0.01';range.value='0';range.addEventListener('input',()=>{state.visualTimeline.masterTime=Number(range.value);const label=$('#visual-master-time');if(label)label.textContent=`${visualFormatTime(state.visualTimeline.masterTime)} / ${visualFormatTime(visualMasterDuration())}`;visualHighlightCurrent()});range.addEventListener('change',()=>visualSeekMaster(Number(range.value),false));
  const time=el('strong','visual-master-time','0:00.00 / 0:00.00');time.id='visual-master-time';play.append(range,time);
  const hint=el('p','microcopy','Arrastra clips para cambiar el orden. Arrastra los bordes para trim. El preview continuo usa el audio de los clips; el audio externo se aplica en el render final.');
  root.append(head,rail,play,hint);
  const anchor=$('#sequence-master-bar')||$('#timeline-visual');panel.insertBefore(root,anchor);
  return root;
}
function visualApplyInlineLayout(root){
  root.style.border='1px solid #dedbd2';root.style.borderRadius='12px';root.style.padding='12px';root.style.marginBottom='12px';root.style.background='#f8f7f3';
  const head=root.querySelector('.visual-track-head');head.style.display='flex';head.style.justifyContent='space-between';head.style.gap='12px';head.style.alignItems='center';
  const controls=root.querySelector('.visual-master-controls');controls.style.display='flex';controls.style.gap='6px';
  const rail=root.querySelector('.visual-sequence-rail');rail.style.display='flex';rail.style.minHeight='72px';rail.style.gap='4px';rail.style.alignItems='stretch';rail.style.overflow='hidden';rail.style.borderRadius='10px';rail.style.background='#e8e6df';rail.style.padding='5px';
  const play=root.querySelector('.visual-playhead-row');play.style.display='grid';play.style.gridTemplateColumns='1fr auto';play.style.gap='10px';play.style.alignItems='center';play.style.marginTop='9px';
}
function visualRender(){
  const root=ensureVisualTimelineEditor();if(!root||!state.current)return;visualApplyInlineLayout(root);
  const clips=visualTrackZero(),total=visualMasterDuration(),rail=$('#visual-sequence-rail');rail.replaceChildren();
  $('#visual-track-meta').textContent=`${clips.length} clip${clips.length===1?'':'s'} · ${visualFormatTime(total)}`;
  const range=$('#visual-master-playhead');range.max=String(total);range.value=String(Math.min(total,state.visualTimeline.masterTime||0));
  $('#visual-master-time').textContent=`${visualFormatTime(Number(range.value))} / ${visualFormatTime(total)}`;const preview=$('#visual-master-preview');if(preview)preview.textContent=state.visualTimeline.masterPlaying?'Pausar master':state.visualTimeline.masterActive?'Continuar master':'Previsualizar master';
  clips.forEach((clip,index)=>{visualProbe(clip.asset_id).catch(()=>{});rail.append(visualClipNode(clip,index,total))});
  if(!clips.length)rail.append(el('p','muted','Añade videos a Track 0 para construir el master.'));
  visualHighlightCurrent();
}
function visualClipNode(clip,index,total){
  const node=el('div','visual-sequence-clip');node.dataset.clipId=clip.id;node.dataset.index=String(index);node.draggable=!clip.locked;
  const duration=visualClipDuration(clip);node.style.position='relative';node.style.flex=`${Math.max(duration,0.15)} 1 0`;node.style.minWidth='64px';node.style.padding='8px 12px';node.style.border='1px solid #cbc7bd';node.style.borderRadius='8px';node.style.background=clip.locked?'#e2e0d8':'#fff';node.style.overflow='hidden';node.style.cursor=clip.locked?'default':'grab';
  const label=el('strong','',assetName(clip.asset_id));label.style.display='block';label.style.fontSize='10px';label.style.whiteSpace='nowrap';label.style.overflow='hidden';label.style.textOverflow='ellipsis';
  const meta=el('span','',`${duration.toFixed(2)}s · ${Number(clip.start).toFixed(2)}→${Number(clip.end).toFixed(2)}`);meta.style.display='block';meta.style.fontSize='9px';meta.style.color='#77756d';meta.style.marginTop='4px';
  node.append(label,meta);
  if(!clip.locked){node.append(visualTrimHandle(clip,'left'),visualTrimHandle(clip,'right'))}
  node.addEventListener('click',event=>{if(event.target.closest('.visual-trim-handle'))return;state.selectedClipId=clip.id;renderTimeline();visualRender();previewAsset(clip.asset_id,clip.start).catch(err=>toast(err.message))});
  node.addEventListener('dragstart',event=>{state.visualTimeline.draggedClipId=clip.id;event.dataTransfer.effectAllowed='move';event.dataTransfer.setData('text/plain',clip.id);node.style.opacity='.45'});
  node.addEventListener('dragend',()=>{node.style.opacity='1';state.visualTimeline.draggedClipId=null});
  node.addEventListener('dragover',event=>{event.preventDefault();event.dataTransfer.dropEffect='move';node.style.outline='2px solid #171717'});
  node.addEventListener('dragleave',()=>node.style.outline='');
  node.addEventListener('drop',async event=>{event.preventDefault();node.style.outline='';const source=state.visualTimeline.draggedClipId||event.dataTransfer.getData('text/plain');if(!source||source===clip.id)return;await visualReorderTo(source,index)});
  return node;
}
function visualTrimHandle(clip,side){
  const handle=el('span','visual-trim-handle');handle.dataset.side=side;handle.style.position='absolute';handle.style.top='0';handle.style.bottom='0';handle.style.width='8px';handle.style[side==='left'?'left':'right']='0';handle.style.background='rgba(23,23,23,.16)';handle.style.cursor='ew-resize';
  handle.addEventListener('pointerdown',event=>visualBeginTrim(event,clip,side));return handle;
}
async function visualBeginTrim(event,clip,side){
  event.preventDefault();event.stopPropagation();const handle=event.currentTarget;handle.setPointerCapture(event.pointerId);
  let probe;try{probe=await visualProbe(clip.asset_id)}catch(err){toast(err.message);return}
  const assetDuration=Number(probe.duration)||Number(clip.end);const rail=$('#visual-sequence-rail');const total=Math.max(visualMasterDuration(),VISUAL_MIN_CLIP_SECONDS);const pxPerSecond=Math.max(1,rail.getBoundingClientRect().width/total);const originX=event.clientX,originStart=Number(clip.start),originEnd=Number(clip.end),node=handle.closest('.visual-sequence-clip'),meta=node.querySelector('span');let pending={start:originStart,end:originEnd};
  const move=moveEvent=>{const delta=(moveEvent.clientX-originX)/pxPerSecond;if(side==='left')pending.start=Math.max(0,Math.min(originEnd-VISUAL_MIN_CLIP_SECONDS,originStart+delta));else pending.end=Math.min(assetDuration,Math.max(originStart+VISUAL_MIN_CLIP_SECONDS,originEnd+delta));const duration=pending.end-pending.start;meta.textContent=`${duration.toFixed(2)}s · ${pending.start.toFixed(2)}→${pending.end.toFixed(2)}`;node.style.opacity='.72'};
  const finish=async finishEvent=>{handle.removeEventListener('pointermove',move);handle.removeEventListener('pointerup',finish);handle.removeEventListener('pointercancel',cancel);node.style.opacity='1';if(Math.abs(pending.start-originStart)<.005&&Math.abs(pending.end-originEnd)<.005)return;try{await editorAction({action:'trim',clip_id:clip.id,start:Number(pending.start.toFixed(3)),end:Number(pending.end.toFixed(3))})}catch(err){toast(err.message)}};
  const cancel=()=>{handle.removeEventListener('pointermove',move);handle.removeEventListener('pointerup',finish);handle.removeEventListener('pointercancel',cancel);node.style.opacity='1';visualRender()};
  handle.addEventListener('pointermove',move);handle.addEventListener('pointerup',finish);handle.addEventListener('pointercancel',cancel);
}
async function visualReorderTo(clipId,targetIndex){
  const clips=visualTrackZero(),sourceIndex=clips.findIndex(row=>row.id===clipId);if(sourceIndex<0||sourceIndex===targetIndex)return;
  try{await editorAction({action:'reorder_to',clip_id:clipId,target_position:targetIndex});toast('Orden del master actualizado')}catch(err){toast(err.message)}
}

function visualStopMaster(reset=false){
  state.visualTimeline.masterActive=false;state.visualTimeline.masterPlaying=false;state.visualTimeline.switching=false;state.visualTimeline.advancing=false;
  const media=currentMedia();if(media&&typeof media.pause==='function')media.pause();
  if(reset){state.visualTimeline.masterTime=0;const range=$('#visual-master-playhead');if(range)range.value='0'}
  visualRender();
}
async function visualToggleMasterPreview(){
  if(state.visualTimeline.masterPlaying){const media=currentMedia();media?.pause();state.visualTimeline.masterPlaying=false;visualRender();return}
  if(!visualTrackZero().length){toast('Track 0 no tiene clips');return}
  state.visualTimeline.masterActive=true;state.visualTimeline.masterPlaying=true;
  try{await visualLoadMasterTime(state.visualTimeline.masterTime||0,true)}catch(err){visualStopMaster(false);toast(err.message)}
}
async function visualSeekMaster(seconds,autoplay=false){
  if(!visualTrackZero().length)return;state.visualTimeline.masterTime=Math.max(0,Math.min(visualMasterDuration(),seconds));state.visualTimeline.masterActive=true;
  try{await visualLoadMasterTime(state.visualTimeline.masterTime,autoplay||state.visualTimeline.masterPlaying)}catch(err){toast(err.message)}
}
async function visualLoadMasterTime(seconds,autoplay){
  const located=visualLocateMasterTime(seconds);if(!located)return;state.visualTimeline.masterIndex=located.index;state.visualTimeline.switching=true;
  try{await previewAsset(located.clip.asset_id,Number(located.clip.start)+located.offset)}finally{state.visualTimeline.switching=false}
  const media=currentMedia();if(!media)return;if(media.readyState<1)await new Promise((resolve,reject)=>{const ok=()=>{cleanup();resolve()};const fail=()=>{cleanup();reject(new Error('No fue posible cargar el clip del master'))};const cleanup=()=>{media.removeEventListener('loadedmetadata',ok);media.removeEventListener('error',fail)};media.addEventListener('loadedmetadata',ok,{once:true});media.addEventListener('error',fail,{once:true})});visualAttachMasterMedia(media,located);if(autoplay){state.visualTimeline.masterPlaying=true;await media.play().catch(()=>{})}visualUpdateMasterFromMedia(media,located);visualRender();
}
function visualAttachMasterMedia(media,located){
  if(media.__binarioMasterTimeUpdate){media.removeEventListener('timeupdate',media.__binarioMasterTimeUpdate);media.removeEventListener('ended',media.__binarioMasterEnded)}
  const update=()=>visualUpdateMasterFromMedia(media,located);const ended=()=>visualAdvanceMaster();media.__binarioMasterTimeUpdate=update;media.__binarioMasterEnded=ended;media.addEventListener('timeupdate',update);media.addEventListener('ended',ended);
}
function visualUpdateMasterFromMedia(media,located){
  if(!state.visualTimeline.masterActive)return;const sourceTime=Number(media.currentTime)||Number(located.clip.start);const offset=Math.max(0,Math.min(visualClipDuration(located.clip),sourceTime-Number(located.clip.start)));state.visualTimeline.masterTime=located.masterStart+offset;const range=$('#visual-master-playhead');if(range)range.value=String(state.visualTimeline.masterTime);const label=$('#visual-master-time');if(label)label.textContent=`${visualFormatTime(state.visualTimeline.masterTime)} / ${visualFormatTime(visualMasterDuration())}`;visualApplyMasterCompositionTime(state.visualTimeline.masterTime);visualHighlightCurrent();if(state.visualTimeline.masterPlaying&&sourceTime>=Number(located.clip.end)-.035)visualAdvanceMaster()}
async function visualAdvanceMaster(){
  if(!state.visualTimeline.masterPlaying||state.visualTimeline.advancing)return;state.visualTimeline.advancing=true;try{const clips=visualTrackZero(),next=state.visualTimeline.masterIndex+1;if(next>=clips.length){visualStopMaster(false);state.visualTimeline.masterTime=visualMasterDuration();visualRender();return}const before=clips.slice(0,next).reduce((sum,row)=>sum+visualClipDuration(row),0);state.visualTimeline.masterTime=before;await visualLoadMasterTime(before,true)}catch(err){visualStopMaster(false);toast(err.message)}finally{state.visualTimeline.advancing=false}
}
function visualApplyMasterCompositionTime(masterTime){
  const layer=document.querySelector('.composition-preview-layer');if(!layer||!state.current)return;
  for(const img of layer.querySelectorAll('.composition-overlay')){const row=(state.current.editor.overlays||[]).find(item=>item.id===img.dataset.overlayId);if(row)img.hidden=masterTime<Number(row.start)||masterTime>Number(row.end)}
  const subtitle=layer.querySelector('.composition-subtitle');if(subtitle){const active=(state.current.editor.subtitles||[]).filter(row=>masterTime>=Number(row.start)&&masterTime<=Number(row.end));subtitle.textContent=active.map(row=>row.text).join('\n');subtitle.hidden=!active.length}
}
function visualHighlightCurrent(){
  const located=visualLocateMasterTime(state.visualTimeline.masterTime||0);document.querySelectorAll('#visual-sequence-rail .visual-sequence-clip').forEach(node=>{const active=located&&node.dataset.clipId===located.clip.id;node.style.boxShadow=active?'inset 0 0 0 2px #171717':'none'})
}

const visualBaseEditorAction=editorAction;
editorAction=async function(payload){if(state.visualTimeline.masterActive)visualStopMaster(false);return visualBaseEditorAction(payload)};

const visualBaseRenderProject=renderProject;
renderProject=function(){visualBaseRenderProject();visualRender()};
const visualBaseRenderTimeline=renderTimeline;
renderTimeline=function(){visualBaseRenderTimeline();visualRender()};
const visualBasePreviewAsset=previewAsset;
previewAsset=async function(assetId,jumpTo=null){if(!state.visualTimeline.switching&&state.visualTimeline.masterActive)visualStopMaster(false);return visualBasePreviewAsset(assetId,jumpTo)};
window.addEventListener('beforeunload',()=>visualStopMaster(false));
