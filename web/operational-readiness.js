const readinessState={runtime:null,runtimeError:null,timer:null};

function readinessStyles(){
  if(document.querySelector('#operational-readiness-style'))return;
  const style=document.createElement('style');style.id='operational-readiness-style';style.textContent=`
    .readiness-panel{margin:14px 0 18px;border:1px solid #dedbd2;background:#fbfaf7}
    .readiness-head{display:flex;justify-content:space-between;gap:16px;align-items:flex-start}
    .readiness-head h3{margin:2px 0 5px}.readiness-head p{max-width:720px}
    .readiness-progress{height:8px;margin:13px 0;border-radius:999px;background:#e5e2da;overflow:hidden}
    .readiness-progress span{display:block;height:100%;width:0;background:#171717;transition:width .2s ease}
    .readiness-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin:12px 0}
    .readiness-step{min-height:96px;padding:11px;border:1px solid #e1ded5;border-radius:12px;background:#fff}
    .readiness-step.done{background:#f0efe9}.readiness-step strong{display:block;margin:5px 0 3px;font-size:11px}
    .readiness-step p{margin:0;color:#737068;font-size:9px;line-height:1.4;overflow-wrap:anywhere}
    .readiness-marker{display:inline-flex;align-items:center;justify-content:center;min-width:24px;height:24px;padding:0 7px;border-radius:999px;background:#e2dfd7;font-size:9px;font-weight:900}
    .readiness-step.done .readiness-marker{background:#171717;color:#fff}.readiness-actions{margin-top:4px}
    .readiness-next{font-weight:800}.readiness-runtime-error{color:#8a3329}
    @media(max-width:1100px){.readiness-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
    @media(max-width:640px){.readiness-head{display:block}.readiness-grid{grid-template-columns:1fr}.readiness-actions button{width:100%}}
  `;document.head.append(style);
}

function readinessRuntimeEvidence(){
  const rows=Array.isArray(readinessState.runtime)?readinessState.runtime:[];
  const byName=Object.fromEntries(rows.map(row=>[row.name,row]));
  const required=['python','ffmpeg','ffprobe'];
  const ok=required.every(name=>byName[name]?.available===true);
  const embedded=['ffmpeg','ffprobe'].every(name=>String(byName[name]?.location||'').includes('/runtime/media/bin/'));
  return {ok,embedded,byName};
}

function readinessEvidence(){
  const runtime=readinessRuntimeEvidence();
  const current=typeof state!=='undefined'?state.current:null;
  const project=current?.project||null;
  const assets=current?.assets||[];
  const videos=assets.filter(row=>row.kind==='video');
  const transcriptions=Object.values(current?.transcriptions||{});
  const transcript=transcriptions.find(row=>row?.status==='PASS');
  const renders=current?.renders||[];
  const vertical=renders.find(row=>row.status==='PASS'&&Number(row.width)*16===Number(row.height)*9);
  const meta=typeof socialState!=='undefined'?socialState.status:null;
  const publications=current?.publications||[];
  const published=publications.find(row=>row.status==='PUBLISHED'&&row.remote_id);
  return {runtime,project,videos,transcript,vertical,meta,published};
}

function readinessSteps(){
  const e=readinessEvidence();
  return [
    {id:'runtime',title:'Motor local',done:e.runtime.ok,detail:e.runtime.ok?(e.runtime.embedded?'Python + FFmpeg embebidos listos.':'Python + FFmpeg disponibles.'):(readinessState.runtimeError||'Verificando Python, FFmpeg y FFprobe.'),action:'runtime'},
    {id:'project',title:'Proyecto',done:Boolean(e.project),detail:e.project?e.project.name:'Crea o abre un proyecto para conservar todo junto.',action:'project'},
    {id:'video',title:'Video importado',done:e.videos.length>0,detail:e.videos.length?`${e.videos.length} video(s) gestionado(s).`:'Importa el video que quieres convertir en contenido.',action:'video'},
    {id:'transcript',title:'Transcripción',done:Boolean(e.transcript),detail:e.transcript?`${e.transcript.segments_count||0} segmentos · Whisper local.`:'Transcribe un video para que el Clipper pueda trabajar con el contenido.',action:'transcript'},
    {id:'render',title:'Reel 9:16',done:Boolean(e.vertical),detail:e.vertical?`${e.vertical.output_name||e.vertical.id} · PASS.`:'Selecciona clips y genera al menos un render vertical PASS.',action:'render'},
    {id:'meta',title:'Meta conectado',done:Boolean(e.meta?.configured),detail:e.meta?.configured?`Conexión segura · ${e.meta.credential_source||'Keychain'}.`:'Conecta Meta cuando ya tengas un render listo.',action:'meta'},
    {id:'publish',title:'Publicación real',done:Boolean(e.published),detail:e.published?`${e.published.channel} · ${e.published.remote_id}.`:'Publica una prueba con clic explícito y confirma el remote ID.',action:'publish'},
  ];
}

function readinessPanelHost(){
  if(typeof state==='undefined')return null;
  if(state.current?.project){
    const hero=document.querySelector('#project-view .project-hero');return hero?.parentElement||null;
  }
  return document.querySelector('#empty-state');
}

function ensureReadinessPanel(){
  readinessStyles();
  const host=readinessPanelHost();if(!host)return null;
  let panel=document.querySelector('#operational-readiness-panel');
  if(!panel){
    panel=document.createElement('section');panel.id='operational-readiness-panel';panel.className='panel readiness-panel';
    panel.innerHTML=`<div class="readiness-head"><div><p class="eyebrow">LISTO PARA PROBAR · WAVE 29</p><h3>Tu ruta de primera prueba</h3><p class="muted">La app valida evidencia real y te lleva al siguiente control. No publica ni activa pauta por sí sola.</p></div><span id="readiness-badge" class="count-chip">0/7</span></div><div class="readiness-progress"><span id="readiness-progress-bar"></span></div><div id="readiness-grid" class="readiness-grid"></div><div class="toolbar readiness-actions"><button id="readiness-next" class="primary readiness-next" type="button">Ir al siguiente paso</button><button id="readiness-refresh" type="button">Revisar ahora</button></div><p id="readiness-summary" class="microcopy"></p>`;
    panel.querySelector('#readiness-next').addEventListener('click',readinessPrepareNext);
    panel.querySelector('#readiness-refresh').addEventListener('click',()=>refreshOperationalReadiness(true));
  }
  if(state.current?.project){
    const hero=document.querySelector('#project-view .project-hero');if(hero&&panel.previousElementSibling!==hero)hero.insertAdjacentElement('afterend',panel);
  }else if(host.firstElementChild!==panel){host.prepend(panel)}
  return panel;
}

function renderOperationalReadiness(){
  const panel=ensureReadinessPanel();if(!panel)return;
  const steps=readinessSteps(),done=steps.filter(row=>row.done).length;
  const badge=panel.querySelector('#readiness-badge');badge.textContent=done===steps.length?'READY':`${done}/${steps.length}`;badge.classList.toggle('ok',done===steps.length);
  panel.querySelector('#readiness-progress-bar').style.width=`${Math.round(done/steps.length*100)}%`;
  const grid=panel.querySelector('#readiness-grid');grid.replaceChildren();
  steps.forEach((step,index)=>{const card=document.createElement('div');card.className=`readiness-step ${step.done?'done':'open'}`;const marker=document.createElement('span');marker.className='readiness-marker';marker.textContent=step.done?'✓':String(index+1);const title=document.createElement('strong');title.textContent=step.title;const detail=document.createElement('p');detail.textContent=step.detail;if(step.id==='runtime'&&readinessState.runtimeError)detail.classList.add('readiness-runtime-error');card.append(marker,title,detail);grid.append(card)});
  const next=steps.find(row=>!row.done);const button=panel.querySelector('#readiness-next');button.disabled=!next;button.textContent=next?`Siguiente: ${next.title}`:'Ruta básica completa';
  panel.querySelector('#readiness-summary').textContent=next?`Siguiente acción recomendada: ${next.title}.`:'Ruta básica completa. Usa UAT Meta para certificar activos, programación y pauta PAUSED con mayor profundidad.';
}

function readinessScroll(selector){const target=document.querySelector(selector);if(!target)return false;target.scrollIntoView({behavior:'smooth',block:'center'});return true}

async function readinessPrepareNext(){
  const step=readinessSteps().find(row=>!row.done);if(!step)return;
  const e=readinessEvidence();
  if(step.action==='runtime'){toast('El runtime local no está completo. Usa una build FULL MAC certificada y revisa el estado superior.');return}
  if(step.action==='project'){readinessScroll('#empty-state');document.querySelector('#start-project-name')?.focus();return}
  if(step.action==='video'){readinessScroll('#asset-form');document.querySelector('#asset-files')?.focus();toast('Importa el video. La app lo copiará al proyecto y verificará SHA-256.');return}
  if(step.action==='transcript'){
    const video=e.videos[0];if(video&&typeof previewAsset==='function'){try{await previewAsset(video.id)}catch(_){}}
    readinessScroll('#transcription-panel');toast('Pulsa “Transcribir”. Whisper trabaja localmente; este asistente no lo inicia solo.');return;
  }
  if(step.action==='render'){readinessScroll('#transcription-panel');document.querySelector('#transcription-select-clips')?.focus();toast('Elige clips y exporta uno en 9:16. El gate sólo pasa con un render PASS.');return}
  if(step.action==='meta'){readinessScroll('#meta-connect-form');document.querySelector('#meta-token-input')?.focus();toast('Conecta Meta. La credencial se valida y se guarda en Keychain, no en el proyecto.');return}
  if(step.action==='publish'){readinessScroll('#social-publication-form');toast('Prepara Facebook o Instagram y publica únicamente cuando hayas revisado cuenta, copy y render.');return}
}

async function refreshOperationalReadiness(forceRuntime=false){
  if(forceRuntime||readinessState.runtime===null){
    try{readinessState.runtime=await api('/api/runtime');readinessState.runtimeError=null}catch(err){readinessState.runtime=[];readinessState.runtimeError=String(err?.message||err||'Runtime no disponible').slice(0,220)}
  }
  renderOperationalReadiness();
}

function readinessWatch(){
  const projectName=document.querySelector('#active-project-name');if(projectName)new MutationObserver(()=>setTimeout(renderOperationalReadiness,0)).observe(projectName,{childList:true,subtree:true,characterData:true});
  clearInterval(readinessState.timer);readinessState.timer=setInterval(renderOperationalReadiness,2500);
  refreshOperationalReadiness(true);
}
window.addEventListener('beforeunload',()=>clearInterval(readinessState.timer));
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',readinessWatch,{once:true});else readinessWatch();
globalThis.renderOperationalReadiness=renderOperationalReadiness;
