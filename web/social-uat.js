const metaUatState={timer:null,lastProjectId:null};

function ensureMetaUatStyles(){
  if($('#meta-uat-style'))return;
  const style=document.createElement('style');style.id='meta-uat-style';style.textContent=`
    .meta-uat-panel{margin:14px 0 18px;background:#fff}
    .meta-uat-progress{height:7px;margin:12px 0 14px;border-radius:999px;background:#e8e6df;overflow:hidden}
    .meta-uat-progress span{display:block;width:0;height:100%;background:#171717;transition:width .2s ease}
    .meta-uat-steps{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-bottom:12px}
    .meta-uat-step{display:grid;grid-template-columns:28px minmax(0,1fr);gap:8px;align-items:flex-start;padding:10px;border:1px solid #e4e1d8;border-radius:12px;background:#fff}
    .meta-uat-step.done{background:#f2f1eb}
    .meta-uat-marker{display:inline-flex;align-items:center;justify-content:center;width:24px;height:24px;border-radius:50%;background:#dedbd2;color:#5e5a52;font-size:10px;font-weight:900}
    .meta-uat-step.done .meta-uat-marker{background:#171717;color:#fff}
    .meta-uat-copy strong{display:block;font-size:11px}
    .meta-uat-copy p{margin-top:3px;color:#77756d;font-size:9px;line-height:1.4;overflow-wrap:anywhere}
    .meta-uat-actions{margin:0 0 8px}
    @media(max-width:980px){.meta-uat-steps{grid-template-columns:repeat(2,minmax(0,1fr))}}
    @media(max-width:640px){.meta-uat-steps{grid-template-columns:1fr}.meta-uat-actions button{width:100%}}
  `;document.head.append(style);
}

function metaUatEligibleReels(){
  if(typeof socialEligibleReels==='function')return socialEligibleReels();
  return (state.current?.renders||[]).filter(row=>row.status==='PASS'&&Number(row.width)*16===Number(row.height)*9&&Number(row.width)>=540&&Number(row.height)>=960&&(Number(row.end)-Number(row.start))>=4&&(Number(row.end)-Number(row.start))<=60);
}

function metaUatEvidence(){
  const status=typeof socialState!=='undefined'?socialState.status:null;
  const pages=typeof socialState!=='undefined'?(socialState.pages||[]):[];
  const adAccounts=typeof socialState!=='undefined'?(socialState.adAccounts||[]):[];
  const renders=metaUatEligibleReels();
  const publications=state.current?.publications||[];
  const paid=state.current?.paid_media||[];
  const reel=publications.find(row=>row.channel==='facebook_page'&&row.kind==='reel'&&row.status==='PUBLISHED'&&row.remote_id);
  const scheduled=publications.find(row=>row.scheduled_for&&['QUEUED','PUBLISHING','PUBLISHED'].includes(row.status));
  const remotePaid=paid.find(row=>row.status==='REMOTE_PAUSED'&&row.campaign_id&&row.adset_id&&row.creative_id&&row.ad_id);
  return {status,pages,adAccounts,renders,reel,scheduled,remotePaid};
}

function metaUatSteps(){
  const e=metaUatEvidence();
  return [
    {id:'connection',title:'Conectar Meta',done:Boolean(e.status?.configured),detail:e.status?.configured?`Conectado mediante ${e.status.credential_source||'credencial segura'}.`:'Conecta la cuenta de Meta desde Keychain.',action:'connection'},
    {id:'assets',title:'Detectar activos',done:e.pages.length>0&&e.adAccounts.length>0,detail:`${e.pages.length} Página(s) · ${e.adAccounts.length} cuenta(s) Ads.`,action:'assets'},
    {id:'render',title:'Tener Reel 9:16 listo',done:e.renders.length>0,detail:e.renders.length?`${e.renders[0].output_name||e.renders[0].id} · ${e.renders[0].width}×${e.renders[0].height}.`:'Necesitas un render PASS 9:16 de 4–60 s.',action:'render'},
    {id:'reel',title:'Publicar Reel de prueba',done:Boolean(e.reel),detail:e.reel?`Confirmado por Meta · ${e.reel.remote_id}.`:'Prepara el Reel; la publicación requiere tu clic explícito.',action:'reel'},
    {id:'schedule',title:'Programar una publicación',done:Boolean(e.scheduled),detail:e.scheduled?`${e.scheduled.status} · ${e.scheduled.scheduled_for}.`:'Programa una publicación futura y confirma que queda en cola.',action:'schedule'},
    {id:'paid',title:'Crear pauta completa PAUSED',done:Boolean(e.remotePaid),detail:e.remotePaid?`Campaign ${e.remotePaid.campaign_id} · AdSet ${e.remotePaid.adset_id} · Creative ${e.remotePaid.creative_id} · Ad ${e.remotePaid.ad_id}.`:'Crea Campaign → AdSet → Creative → Ad sin activación.',action:'paid'},
  ];
}

function ensureMetaUatPanel(){
  const distribution=$('#social-distribution');if(!distribution)return null;ensureMetaUatStyles();
  let panel=$('#meta-uat-panel');if(panel)return panel;
  panel=document.createElement('section');panel.id='meta-uat-panel';panel.className='composer-card meta-uat-panel';
  panel.innerHTML=`
    <div class="composer-head">
      <div><p class="eyebrow">UAT META · PRUEBA GUIADA</p><h4>Verifica publicación, programación y pauta sin adivinar el flujo</h4></div>
      <span id="meta-uat-badge" class="count-chip">0/6</span>
    </div>
    <p class="muted">Este asistente no publica ni activa pauta automáticamente. Sólo prepara el siguiente paso y valida evidencia real guardada por la app.</p>
    <div id="meta-uat-progress" class="meta-uat-progress" aria-label="Progreso UAT"><span></span></div>
    <div id="meta-uat-steps" class="meta-uat-steps"></div>
    <div class="toolbar meta-uat-actions"><button id="meta-uat-next" class="primary" type="button">Preparar siguiente paso</button><button id="meta-uat-refresh" type="button">Revisar ahora</button><button id="meta-uat-copy" type="button">Copiar reporte UAT</button></div>
    <p id="meta-uat-summary" class="microcopy"></p>`;
  const intro=distribution.querySelector(':scope > .muted');
  if(intro)intro.insertAdjacentElement('afterend',panel);else distribution.prepend(panel);
  $('#meta-uat-next').addEventListener('click',prepareNextMetaUatStep);
  $('#meta-uat-refresh').addEventListener('click',()=>{if(typeof refreshMetaConnection==='function')refreshMetaConnection();if(typeof refreshSocialProject==='function')refreshSocialProject();setTimeout(renderMetaUat,150)});
  $('#meta-uat-copy').addEventListener('click',copyMetaUatReport);
  return panel;
}

function renderMetaUat(){
  const panel=ensureMetaUatPanel();if(!panel||!state.current?.project)return;
  const steps=metaUatSteps(),done=steps.filter(step=>step.done).length;
  $('#meta-uat-badge').textContent=done===steps.length?'UAT PASS':`${done}/${steps.length}`;
  $('#meta-uat-badge').classList.toggle('ok',done===steps.length);
  const progress=$('#meta-uat-progress span');if(progress)progress.style.width=`${Math.round(done/steps.length*100)}%`;
  const root=$('#meta-uat-steps');root.replaceChildren();
  steps.forEach((step,index)=>{
    const row=el('div',`meta-uat-step ${step.done?'done':'open'}`);
    const marker=el('span','meta-uat-marker',step.done?'✓':String(index+1));
    const copy=el('div','meta-uat-copy');copy.append(el('strong','',step.title),el('p','',step.detail));
    row.append(marker,copy);root.append(row);
  });
  const next=steps.find(step=>!step.done),button=$('#meta-uat-next');
  button.disabled=!next;button.textContent=next?`Preparar: ${next.title}`:'UAT completo';
  $('#meta-uat-summary').textContent=done===steps.length?'Wave 23 UAT completo para este proyecto: publicación real, programación y pauta remota PAUSED verificadas.':`Faltan ${steps.length-done} gate(s). Instagram local no forma parte de este UAT hasta certificar su ingest binario.`;
}

function metaUatScroll(selector){const target=$(selector);if(!target)return false;target.scrollIntoView({behavior:'smooth',block:'center'});return true}
function metaUatSet(select,value){if(!select)return;select.value=value;select.dispatchEvent(new Event('change',{bubbles:true}))}

function prepareNextMetaUatStep(){
  const step=metaUatSteps().find(item=>!item.done);if(!step)return;
  if(step.action==='connection'){
    metaUatScroll('#meta-connect-form');$('#meta-token-input')?.focus();toast('Pega el token y pulsa “Conectar Meta”. La app lo valida antes de guardarlo en Keychain.');return;
  }
  if(step.action==='assets'){
    metaUatScroll('#meta-assets');if(typeof refreshMetaConnection==='function')refreshMetaConnection();toast('Revisando Páginas, Instagram vinculado y cuentas Ads disponibles.');return;
  }
  if(step.action==='render'){
    metaUatScroll('#render-list');toast('Genera o exporta un render vertical 9:16, PASS y de 4–60 segundos.');return;
  }
  if(step.action==='reel'){
    metaUatSet($('#social-channel'),'facebook_page');if(typeof setSocialKinds==='function')setSocialKinds();metaUatSet($('#social-kind'),'reel');if(typeof renderSocialFieldVisibility==='function')renderSocialFieldVisibility();
    const reel=metaUatEligibleReels()[0];if(reel)$('#social-render-id').value=reel.id;
    if(!$('#social-message').value.trim())$('#social-message').value='[UAT] Prueba de publicación desde BINARIO Marketing';
    metaUatScroll('#social-publication-form');toast('Reel preparado. Revisa cuenta, copy y render; “Publicar ahora” sigue requiriendo tu clic.');return;
  }
  if(step.action==='schedule'){
    metaUatSet($('#social-channel'),'facebook_page');if(typeof setSocialKinds==='function')setSocialKinds();metaUatSet($('#social-kind'),'text');
    const when=new Date(Date.now()+10*60*1000);const local=new Date(when.getTime()-when.getTimezoneOffset()*60000).toISOString().slice(0,16);$('#social-scheduled-for').value=local;
    if(!$('#social-message').value.trim())$('#social-message').value='[UAT] Publicación programada desde BINARIO Marketing';
    metaUatScroll('#social-publication-form');toast('Programación preparada a +10 min. Revisa y pulsa “Guardar / programar”.');return;
  }
  if(step.action==='paid'){
    const e=metaUatEvidence();if(e.adAccounts[0])$('#meta-ad-account').value=e.adAccounts[0].id;if(e.pages[0])$('#meta-paid-page').value=e.pages[0].id;
    const suffix=new Date().toISOString().slice(0,10);if(!$('#meta-campaign-name').value.trim())$('#meta-campaign-name').value=`UAT BINARIO ${suffix}`;if(!$('#meta-adset-name').value.trim())$('#meta-adset-name').value='UAT Colombia';if(!$('#meta-creative-name').value.trim())$('#meta-creative-name').value='UAT Creative';if(!$('#meta-ad-name').value.trim())$('#meta-ad-name').value='UAT Ad';
    metaUatScroll('#meta-campaign-form');toast('Pauta preparada. Completa URL destino, imagen pública y copy; “Crear campaña pausada completa” no activa gasto.');
  }
}

function metaUatReport(){
  const steps=metaUatSteps(),project=state.current?.project||{};return [
    'BINARIO Marketing · Wave 23 Meta UAT',
    `Proyecto: ${project.name||project.id||'—'} (${project.id||'—'})`,
    `Fecha: ${new Date().toISOString()}`,
    `Resultado: ${steps.every(step=>step.done)?'PASS':'INCOMPLETE'}`,
    '',
    ...steps.map((step,index)=>`${index+1}. ${step.done?'PASS':'OPEN'} · ${step.title} · ${step.detail}`),
    '',
    'Safety: sin activación de pauta; sin token en reporte; acciones externas requieren clic explícito.',
  ].join('\n');
}
async function copyMetaUatReport(){try{await navigator.clipboard.writeText(metaUatReport());toast('Reporte UAT copiado')}catch(err){toast('No se pudo copiar el reporte UAT')}}

function metaUatWatch(){
  const title=$('#active-project-name');if(title)new MutationObserver(()=>setTimeout(renderMetaUat,0)).observe(title,{childList:true,characterData:true,subtree:true});
  clearInterval(metaUatState.timer);metaUatState.timer=setInterval(()=>{if(socialProjectId())renderMetaUat()},2500);setTimeout(renderMetaUat,0);
}
window.addEventListener('beforeunload',()=>clearInterval(metaUatState.timer));
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',metaUatWatch,{once:true});else metaUatWatch();
globalThis.renderMetaUat=renderMetaUat;

(function loadMetaObservabilityExtension(){
  if(!document.querySelector('link[data-meta-observability]')){const link=document.createElement('link');link.rel='stylesheet';link.href='/meta-observability.css';link.dataset.metaObservability='1';document.head.append(link)}
  if(!document.querySelector('script[data-meta-observability]')){const script=document.createElement('script');script.src='/meta-observability.js';script.defer=true;script.dataset.metaObservability='1';document.head.append(script)}
})();
