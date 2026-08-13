const metaDiagnosticsState={report:null,busy:false};

function ensureMetaDiagnosticsPanel(){
  const assets=$('#meta-assets');if(!assets)return null;
  let panel=$('#meta-diagnostics-panel');if(panel)return panel;
  panel=document.createElement('section');panel.id='meta-diagnostics-panel';panel.className='meta-diagnostics-panel';
  panel.innerHTML=`
    <div class="meta-diagnostics-head">
      <div><p class="eyebrow">WAVE 25 · DIAGNÓSTICO META</p><strong>¿Por qué no está listo?</strong></div>
      <span id="meta-diagnostics-badge" class="count-chip">READ ONLY</span>
    </div>
    <p class="microcopy">Comprueba token, Páginas, tareas, vínculo Instagram, permisos y cuentas Ads. No publica ni modifica campañas.</p>
    <div class="toolbar meta-diagnostics-actions"><button id="meta-diagnostics-run" type="button">Diagnosticar acceso</button><button id="meta-diagnostics-copy" type="button" disabled>Copiar diagnóstico</button></div>
    <div id="meta-diagnostics-ready" class="meta-diagnostics-ready"></div>
    <div id="meta-diagnostics-checks" class="meta-diagnostics-checks"><p class="muted">Ejecuta el diagnóstico cuando un gate UAT no avance.</p></div>`;
  assets.insertAdjacentElement('afterend',panel);
  $('#meta-diagnostics-run').addEventListener('click',runMetaDiagnostics);
  $('#meta-diagnostics-copy').addEventListener('click',copyMetaDiagnostics);
  return panel;
}

function metaDiagnosticLabel(key){return ({facebook_publish:'Facebook publicar',instagram_publish:'Instagram publicar',instagram_insights:'Instagram insights',ads_read:'Ads lectura',ads_create:'Ads crear PAUSED'})[key]||key}
function metaDiagnosticStateClass(value){return value===true?'ok':'open'}

function renderMetaDiagnostics(){
  const panel=ensureMetaDiagnosticsPanel();if(!panel)return;
  const button=$('#meta-diagnostics-run'),copy=$('#meta-diagnostics-copy'),badge=$('#meta-diagnostics-badge');
  const configured=Boolean(socialState?.status?.configured);button.disabled=metaDiagnosticsState.busy||!configured;button.textContent=metaDiagnosticsState.busy?'Diagnosticando…':'Diagnosticar acceso';
  if(!configured){badge.textContent='SIN CONEXIÓN';badge.classList.remove('ok');copy.disabled=true;return}
  const report=metaDiagnosticsState.report;if(!report){badge.textContent='READ ONLY';badge.classList.remove('ok');copy.disabled=true;return}
  badge.textContent=report.status==='PASS'?'DIAGNÓSTICO PASS':'REVISAR';badge.classList.toggle('ok',report.status==='PASS');copy.disabled=false;
  const ready=$('#meta-diagnostics-ready');ready.replaceChildren();
  for(const [key,value] of Object.entries(report.ready||{})){const chip=el('span',`meta-diagnostics-cap ${metaDiagnosticStateClass(value)}`);chip.append(el('strong','',value?'✓':'!'),el('span','',metaDiagnosticLabel(key)));ready.append(chip)}
  const checks=$('#meta-diagnostics-checks');checks.replaceChildren();
  for(const row of report.checks||[]){const item=el('div',`meta-diagnostics-check state-${String(row.state||'WARN').toLowerCase()}`);const head=el('div','meta-diagnostics-check-head');head.append(el('strong','',row.title||row.id),el('span','count-chip',row.state||'WARN'));item.append(head,el('p','',row.detail||''));if(row.action)item.append(el('p','microcopy',`Qué hacer: ${row.action}`));checks.append(item)}
  if(!(report.checks||[]).length)checks.append(el('p','muted','Meta no devolvió checks diagnósticos.'));
}

async function runMetaDiagnostics(){
  if(metaDiagnosticsState.busy)return;if(!socialState?.status?.configured){toast('Conecta Meta antes de diagnosticar');return}
  metaDiagnosticsState.busy=true;renderMetaDiagnostics();
  try{metaDiagnosticsState.report=await api('/api/meta/diagnostics');renderMetaDiagnostics();toast(metaDiagnosticsState.report.status==='PASS'?'Diagnóstico Meta completo':'Diagnóstico Meta: hay pasos por revisar')}catch(err){metaDiagnosticsState.report=null;toast(`Diagnóstico Meta: ${err.message}`)}finally{metaDiagnosticsState.busy=false;renderMetaDiagnostics()}
}

function metaDiagnosticsText(){
  const report=metaDiagnosticsState.report;if(!report)return 'BINARIO Marketing · Meta diagnostics · sin ejecutar';
  const lines=['BINARIO Marketing · Wave 25 Meta diagnostics',`Resultado: ${report.status}`,`Graph: ${report.graph_version||'—'}`,`Credencial: ${report.credential_source||'—'}`,'','Capacidades:'];
  for(const [key,value] of Object.entries(report.ready||{}))lines.push(`- ${value?'PASS':'BLOCKED'} · ${metaDiagnosticLabel(key)}`);
  lines.push('','Checks:');for(const row of report.checks||[])lines.push(`- ${row.state} · ${row.title}: ${row.detail}${row.action?` · Qué hacer: ${row.action}`:''}`);
  const missing=report.permissions?.missing||{};lines.push('','Permisos faltantes por flujo:');for(const [key,values] of Object.entries(missing))lines.push(`- ${metaDiagnosticLabel(key)}: ${values.length?values.join(', '):'ninguno detectado'}`);
  lines.push('','Security: reporte sin token; diagnóstico de sólo lectura; sin mutaciones Meta.');return lines.join('\n');
}
async function copyMetaDiagnostics(){try{await navigator.clipboard.writeText(metaDiagnosticsText());toast('Diagnóstico Meta copiado')}catch(err){toast('No se pudo copiar el diagnóstico')}}

function metaDiagnosticsWatch(){ensureMetaDiagnosticsPanel();const target=$('#meta-status-badge');if(target)new MutationObserver(()=>renderMetaDiagnostics()).observe(target,{childList:true,characterData:true,subtree:true});renderMetaDiagnostics()}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',metaDiagnosticsWatch,{once:true});else metaDiagnosticsWatch();
globalThis.renderMetaDiagnostics=renderMetaDiagnostics;

// Wave 26: user-triggered remote evidence for the existing six-gate Meta UAT.
const metaRemoteUatState={projectId:null,publication:null,paid:null,busy:false,errors:[],timer:null};
const metaRemoteBaseSteps=typeof metaUatSteps==='function'?metaUatSteps:null;
const metaRemoteBaseReport=typeof metaUatReport==='function'?metaUatReport:null;

function metaRemoteProjectId(){return state.current?.project?.id||null}
function metaRemoteFacebookReel(){return [...(state.current?.publications||[])].reverse().find(row=>row.channel==='facebook_page'&&row.kind==='reel'&&row.status==='PUBLISHED'&&row.remote_id)||null}
function metaRemotePaidDraft(){return [...(state.current?.paid_media||[])].reverse().find(row=>row.status==='REMOTE_PAUSED'&&row.campaign_id&&row.adset_id&&row.creative_id&&row.ad_id)||null}
function metaRemoteSafeMessage(value){return String(value||'Error Meta').replace(/Bearer\s+\S+/gi,'Bearer [credencial oculta]').replace(/access_token=[^&\s]+/gi,'access_token=[credencial oculta]').replace(/\bEA[A-Za-z0-9_-]{20,}\b/g,'[credencial oculta]').slice(0,700)}
function metaRemoteExplainError(value){
  const message=metaRemoteSafeMessage(value),text=message.toLowerCase();
  if(/\b190\b/.test(text)||text.includes('access token')||text.includes('oauth'))return {category:'TOKEN',title:'Token vencido o no utilizable',action:'Reconecta Meta con un token vigente de la app correcta.',message};
  if(text.includes('permission')||text.includes('permissions')||text.includes('not authorized')||/\b(?:10|200)\b/.test(text))return {category:'PERMISSION',title:'Permiso insuficiente',action:'Ejecuta Diagnóstico Meta y corrige el permiso o rol exacto que aparezca bloqueado.',message};
  if(text.includes('unsupported get request')||text.includes('does not exist')||text.includes('cannot be loaded')||text.includes('object'))return {category:'ASSET_ACCESS',title:'Activo no accesible',action:'Confirma que la Página, Instagram o cuenta Ads pertenece al acceso conectado y vuelve a descubrir activos.',message};
  if(text.includes('rate')||text.includes('too many')||text.includes('temporar')||text.includes('timeout')||text.includes('unavailable'))return {category:'TRANSIENT',title:'Meta temporalmente no disponible',action:'Conserva el estado local y vuelve a verificar; no recrees objetos remotos mientras exista un ID guardado.',message};
  if(text.includes('invalid parameter')||text.includes('invalid')||/\b100\b/.test(text))return {category:'VALIDATION',title:'Dato rechazado por Meta',action:'Revisa el campo indicado antes de repetir la operación.',message};
  return {category:'PROVIDER',title:'Respuesta de Meta no clasificada',action:'Copia este reporte diagnóstico para revisar el bloqueo sin compartir credenciales.',message};
}
function metaRemoteSafeProviderUrl(value){
  try{const url=new URL(String(value||''));const host=url.hostname.toLowerCase();const allowed=host==='facebook.com'||host.endsWith('.facebook.com')||host==='instagram.com'||host.endsWith('.instagram.com');return url.protocol==='https:'&&allowed?url.href:null}catch(_err){return null}
}
function metaRemotePublicationUrl(result){const remote=result?.remote||{};return metaRemoteSafeProviderUrl(remote.permalink||remote.permalink_url||'')}
function metaRemoteReelPassed(result){
  if(!result?.available)return false;const remoteState=String(result.remote_state||'').toUpperCase();const publishing=String(result.remote?.status?.publishing_phase?.status||'').toUpperCase();
  return ['READY','PUBLISHED','COMPLETE','COMPLETED'].includes(remoteState)||['PUBLISHED','COMPLETE','COMPLETED'].includes(publishing);
}
function metaRemotePaidPassed(result){return Boolean(result?.available&&result?.safety?.configured_paused===true&&!result?.safety?.explicit_active_detected)}
function metaRemoteSyncProject(){const projectId=metaRemoteProjectId();if(projectId===metaRemoteUatState.projectId)return;metaRemoteUatState.projectId=projectId;metaRemoteUatState.publication=null;metaRemoteUatState.paid=null;metaRemoteUatState.errors=[]}

function metaRemotePatchedSteps(){
  const steps=metaRemoteBaseSteps?metaRemoteBaseSteps():[];const reel=metaRemoteFacebookReel(),paid=metaRemotePaidDraft();const reelResult=metaRemoteUatState.publication?.id===reel?.id?metaRemoteUatState.publication.result:null;const paidResult=metaRemoteUatState.paid?.id===paid?.id?metaRemoteUatState.paid.result:null;
  return steps.map(step=>{
    if(step.id==='reel'){
      if(!reel)return {...step,done:false,detail:'Publica un Reel de prueba; después Wave 26 confirmará el estado remoto con Meta.'};
      if(!reelResult)return {...step,done:false,detail:`Local PUBLISHED · ${reel.remote_id}. Falta readback remoto GET.`};
      const done=metaRemoteReelPassed(reelResult);return {...step,done,detail:done?`Local PUBLISHED + Meta ${String(reelResult.remote_state||'READY').toUpperCase()} · ${reel.remote_id}.`:`Local PUBLISHED · Meta ${String(reelResult.remote_state||'procesando').toUpperCase()}; vuelve a verificar.`};
    }
    if(step.id==='paid'){
      if(!paid)return {...step,done:false,detail:'Crea Campaign → AdSet → Creative → Ad en PAUSED; luego Wave 26 confirmará los estados remotos.'};
      if(!paidResult)return {...step,done:false,detail:`IDs remotos guardados · Ad ${paid.ad_id}. Falta readback remoto GET.`};
      if(paidResult?.safety?.explicit_active_detected)return {...step,done:false,detail:'ALERTA: Meta reportó al menos un objeto configurado ACTIVE. No se considera UAT PASS.'};
      const done=metaRemotePaidPassed(paidResult);return {...step,done,detail:done?`Local REMOTE_PAUSED + Meta PAUSED confirmado · Campaign ${paid.campaign_id} · Ad ${paid.ad_id}.`:'Meta respondió, pero la jerarquía todavía no está confirmada completamente en PAUSED.'};
    }
    return step;
  });
}
if(metaRemoteBaseSteps)metaUatSteps=metaRemotePatchedSteps;

function ensureMetaRemoteUatStyles(){
  if($('#meta-remote-uat-style'))return;const style=document.createElement('style');style.id='meta-remote-uat-style';style.textContent=`
    .meta-remote-uat{margin:10px 0 16px;padding:12px;border:1px solid #dedbd2;border-radius:14px;background:#faf9f5}
    .meta-remote-uat-head{display:flex;align-items:flex-start;justify-content:space-between;gap:10px}.meta-remote-uat-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:10px 0}.meta-remote-gate{padding:9px;border:1px solid #e4e1d8;border-radius:10px;background:#fff}.meta-remote-gate strong,.meta-remote-gate span{display:block}.meta-remote-gate span{margin-top:3px;color:#77756d;font-size:10px;line-height:1.4}.meta-remote-error{margin-top:8px;padding:8px;border-left:3px solid #171717;background:#fff}.meta-remote-error strong{font-size:10px}.meta-remote-error p{margin:3px 0;font-size:9px;overflow-wrap:anywhere}@media(max-width:640px){.meta-remote-uat-grid{grid-template-columns:1fr}.meta-remote-uat .toolbar button{width:100%}}
  `;document.head.append(style);
}
function metaRemoteGate(title,status,detail){const item=el('div','meta-remote-gate');item.append(el('strong','',`${status} · ${title}`),el('span','',detail));return item}
function renderMetaRemoteUat(){
  metaRemoteSyncProject();const uat=$('#meta-uat-panel');if(!uat)return;ensureMetaRemoteUatStyles();let panel=$('#meta-remote-uat');if(!panel){panel=document.createElement('section');panel.id='meta-remote-uat';panel.className='meta-remote-uat';panel.innerHTML=`<div class="meta-remote-uat-head"><div><p class="eyebrow">WAVE 26 · UAT REMOTO META</p><strong>Local PASS no basta: confirma el proveedor</strong></div><span id="meta-remote-uat-badge" class="count-chip">READ ONLY</span></div><p class="microcopy">Sólo consulta los IDs ya creados. No publica, no activa campañas y no recrea objetos cuando Meta falla.</p><div id="meta-remote-uat-grid" class="meta-remote-uat-grid"></div><div class="toolbar"><button id="meta-remote-uat-verify" type="button">Verificar gates remotos</button><button id="meta-remote-uat-open" type="button" disabled>Abrir publicación en Meta</button></div><div id="meta-remote-uat-errors"></div>`;uat.insertAdjacentElement('afterend',panel);$('#meta-remote-uat-verify').addEventListener('click',verifyMetaRemoteUat);$('#meta-remote-uat-open').addEventListener('click',openMetaRemotePublication)}
  const reel=metaRemoteFacebookReel(),paid=metaRemotePaidDraft(),reelResult=metaRemoteUatState.publication?.id===reel?.id?metaRemoteUatState.publication.result:null,paidResult=metaRemoteUatState.paid?.id===paid?.id?metaRemoteUatState.paid.result:null;const reelPass=metaRemoteReelPassed(reelResult),paidPass=metaRemotePaidPassed(paidResult);const grid=$('#meta-remote-uat-grid');grid.replaceChildren();
  grid.append(metaRemoteGate('Facebook Reel',reelPass?'META PASS':reel?'LOCAL PASS':'PENDIENTE',reelPass?`Meta ${String(reelResult.remote_state||'READY').toUpperCase()} · ${reel.remote_id}`:reelResult?`Meta ${String(reelResult.remote_state||'procesando').toUpperCase()}`:reel?`Meta ID ${reel.remote_id} · falta verificar`:'Sin Reel PUBLISHED con remote_id'));
  const paidStatus=paidResult?.safety?.explicit_active_detected?'ALERTA ACTIVE':paidPass?'META PAUSED':paid?'LOCAL PASS':'PENDIENTE';grid.append(metaRemoteGate('Pauta',paidStatus,paidPass?`Campaign ${paid.campaign_id} · Ad ${paid.ad_id}`:paidResult?.safety?.explicit_active_detected?'Se detectó estado configurado ACTIVE; revisar en Meta.':paid?`Ad ${paid.ad_id} · falta verificar PAUSED`:'Sin jerarquía REMOTE_PAUSED completa'));
  const badge=$('#meta-remote-uat-badge');badge.textContent=reelPass&&paidPass?'REMOTE PASS':paidResult?.safety?.explicit_active_detected?'ALERTA ACTIVE':'READ ONLY';badge.classList.toggle('ok',reelPass&&paidPass);
  const button=$('#meta-remote-uat-verify');button.disabled=metaRemoteUatState.busy||!socialState?.status?.configured;button.textContent=metaRemoteUatState.busy?'Verificando…':'Verificar gates remotos';const url=metaRemotePublicationUrl(reelResult);$('#meta-remote-uat-open').disabled=!url;
  const errors=$('#meta-remote-uat-errors');errors.replaceChildren();for(const row of metaRemoteUatState.errors){const item=el('div','meta-remote-error');item.append(el('strong','',`${row.category} · ${row.title}`),el('p','',row.message),el('p','microcopy',`Qué hacer: ${row.action}`));errors.append(item)}
}
async function metaRemoteRead(path,kind,id){try{const result=await api(path);if(kind==='publication')metaRemoteUatState.publication={id,result};else metaRemoteUatState.paid={id,result};if(typeof metaObsState!=='undefined'){if(kind==='publication')metaObsState.publications.set(id,result);else metaObsState.paid.set(id,result)}return result}catch(err){metaRemoteUatState.errors.push(metaRemoteExplainError(err.message));return null}}
async function verifyMetaRemoteUat(){
  if(metaRemoteUatState.busy)return;if(!socialState?.status?.configured){toast('Conecta Meta antes de verificar evidencia remota');return}metaRemoteSyncProject();const projectId=metaRemoteProjectId(),reel=metaRemoteFacebookReel(),paid=metaRemotePaidDraft();if(!projectId)return;if(!reel&&!paid){toast('Primero completa los objetos locales del UAT');return}metaRemoteUatState.busy=true;metaRemoteUatState.errors=[];renderMetaRemoteUat();
  try{if(reel)await metaRemoteRead(`/api/projects/${encodeURIComponent(projectId)}/publications/${encodeURIComponent(reel.id)}/observability`,'publication',reel.id);if(paid)await metaRemoteRead(`/api/projects/${encodeURIComponent(projectId)}/paid-media/${encodeURIComponent(paid.id)}/observability?date_preset=maximum`,'paid',paid.id);if(typeof renderMetaObservability==='function')renderMetaObservability();if(typeof renderMetaUat==='function')renderMetaUat();toast(metaRemoteUatState.errors.length?'Meta verificado con bloqueos diagnosticados':'Evidencia remota Meta actualizada')}finally{metaRemoteUatState.busy=false;renderMetaRemoteUat()}
}
function openMetaRemotePublication(){const url=metaRemotePublicationUrl(metaRemoteUatState.publication?.result);if(!url){toast('Meta no devolvió un permalink HTTPS permitido');return}const anchor=document.createElement('a');anchor.href=url;anchor.target='_blank';anchor.rel='noopener noreferrer';document.body.append(anchor);anchor.click();anchor.remove()}
function metaRemoteUatReport(){
  const steps=metaRemotePatchedSteps(),project=state.current?.project||{};const lines=['BINARIO Marketing · Wave 26 Meta UAT remoto',`Proyecto: ${project.name||project.id||'—'} (${project.id||'—'})`,`Fecha: ${new Date().toISOString()}`,`Resultado: ${steps.every(step=>step.done)?'PASS':'INCOMPLETE'}`,'',...steps.map((step,index)=>`${index+1}. ${step.done?'PASS':'OPEN'} · ${step.title} · ${step.detail}`)];
  if(metaRemoteUatState.errors.length){lines.push('','Errores Meta normalizados:');for(const row of metaRemoteUatState.errors)lines.push(`- ${row.category} · ${row.title} · ${row.message} · Qué hacer: ${row.action}`)}lines.push('','Safety: readback GET; sin activación; sin recreación automática; URLs externas sólo HTTPS facebook.com/instagram.com; reporte con credenciales ocultas.');return lines.join('\n');
}
if(metaRemoteBaseReport)metaUatReport=metaRemoteUatReport;
function metaRemoteWatch(){clearInterval(metaRemoteUatState.timer);metaRemoteUatState.timer=setInterval(()=>{if(metaRemoteProjectId())renderMetaRemoteUat()},2500);renderMetaRemoteUat()}
window.addEventListener('beforeunload',()=>clearInterval(metaRemoteUatState.timer));
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',metaRemoteWatch,{once:true});else metaRemoteWatch();
globalThis.renderMetaRemoteUat=renderMetaRemoteUat;
