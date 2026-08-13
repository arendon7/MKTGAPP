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
