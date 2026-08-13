const metaObsState={publications:new Map(),paid:new Map(),busy:new Set(),projectId:null};

function metaObsProjectId(){return state.current?.project?.id||null}
function metaObsPublished(){return (state.current?.publications||[]).filter(row=>row.status==='PUBLISHED'&&row.remote_id)}
function metaObsPaid(){return (state.current?.paid_media||[]).filter(row=>row.campaign_id||row.adset_id||row.creative_id||row.ad_id)}
function metaObsText(value,fallback='—'){return value===null||value===undefined||value===''?fallback:String(value)}
function metaObsNumber(value){const number=Number(value);return Number.isFinite(number)?number.toLocaleString():metaObsText(value)}

function ensureMetaObservabilityPanel(){
  const distribution=$('#social-distribution');if(!distribution)return null;
  let panel=$('#meta-observability');if(panel)return panel;
  panel=document.createElement('section');panel.id='meta-observability';panel.className='composer-card meta-observability-card';
  panel.innerHTML=`
    <div class="composer-head meta-observability-head">
      <div><p class="eyebrow">WAVE 24 · OBSERVABILIDAD META</p><h4>Verifica estado remoto y métricas sin modificar campañas</h4></div>
      <span id="meta-observability-safety" class="count-chip">READ ONLY</span>
    </div>
    <div class="meta-observability-toolbar">
      <p class="muted">Sólo hace lecturas GET a Meta. No cambia estado, presupuesto, targeting, copy ni creativos.</p>
      <div class="toolbar">
        <label>Ventana Ads<select id="meta-observability-period"><option value="maximum">Histórico disponible</option><option value="last_30d">Últimos 30 días</option><option value="last_14d">Últimos 14 días</option><option value="last_7d">Últimos 7 días</option><option value="today">Hoy</option><option value="yesterday">Ayer</option></select></label>
        <button id="meta-observability-refresh" type="button">Verificar recientes</button>
      </div>
    </div>
    <div class="grid-two meta-observability-grid">
      <div>
        <div class="composer-row-head"><strong>Publicaciones confirmadas</strong><span id="meta-observability-publication-count">0</span></div>
        <div id="meta-observability-publications" class="results"></div>
      </div>
      <div>
        <div class="composer-row-head"><strong>Pauta remota</strong><span id="meta-observability-paid-count">0</span></div>
        <div id="meta-observability-paid" class="results"></div>
      </div>
    </div>
    <p id="meta-observability-note" class="microcopy">Instagram muestra insights orgánicos disponibles; Facebook Reel verifica el estado oficial de procesamiento/publicación; Ads muestra estado remoto e Insights del Ad.</p>`;
  const paidList=distribution.querySelector('.paid-media-list-card');
  if(paidList)paidList.insertAdjacentElement('afterend',panel);else distribution.append(panel);
  $('#meta-observability-refresh').addEventListener('click',verifyRecentMetaObservability);
  $('#meta-observability-period').addEventListener('change',()=>{metaObsState.paid.clear();renderMetaObservability()});
  return panel;
}

function metaObsBusyKey(kind,id){return `${kind}:${id}`}
function metaObsButton(label,handler,disabled=false){const button=el('button','',label);button.type='button';button.disabled=disabled;button.addEventListener('click',handler);return button}
function metaObsMetricChip(label,value){const chip=el('span','meta-observability-metric');chip.append(el('strong','',metaObsText(value,'0')),el('small','',label));return chip}

function metaObsPublicationDetail(row,result){
  if(!result)return 'Sin verificar en esta sesión.';
  if(!result.available)return result.reason||'Meta todavía no tiene un objeto remoto verificable.';
  if(row.channel==='facebook_page'&&row.kind==='reel')return `Estado Reel: ${metaObsText(result.remote_state)}`;
  const remote=result.remote||{};return [result.remote_state,remote.media_product_type||remote.media_type,remote.timestamp||remote.created_time].filter(Boolean).join(' · ')||'Objeto remoto presente';
}

function renderMetaObsPublication(row,root){
  const result=metaObsState.publications.get(row.id),busy=metaObsState.busy.has(metaObsBusyKey('publication',row.id));
  const item=el('div','result-item meta-observability-item');
  const head=el('div','meta-observability-item-head');
  const copy=el('div','');copy.append(el('strong','',`${row.channel==='instagram'?'Instagram':'Facebook'} · ${row.kind}`),el('p','',`Meta ${row.remote_id}`));
  const button=metaObsButton(busy?'Verificando…':'Verificar',()=>verifyMetaPublication(row.id),busy||!socialState.status?.configured);head.append(copy,button);item.append(head,el('p','muted',metaObsPublicationDetail(row,result)));
  const insights=result?.insights||{};const metricNames=['reach','views','likes','comments','shares','saved','total_interactions'];const present=metricNames.filter(name=>insights[name]!==undefined);
  if(present.length){const metrics=el('div','meta-observability-metrics');for(const name of present)metrics.append(metaObsMetricChip(name.replaceAll('_',' '),metaObsNumber(insights[name])));item.append(metrics)}
  if(result?.metric_errors&&Object.keys(result.metric_errors).length)item.append(el('p','microcopy',`${Object.keys(result.metric_errors).length} métrica(s) no disponibles para este tipo de medio.`));
  root.append(item);
}

function metaObsObjectLine(label,row){if(!row)return `${label}: sin ID remoto`;return `${label}: ${metaObsText(row.observed_state||row.status||row.effective_status)} · ${metaObsText(row.id)}`}
function renderMetaObsPaid(row,root){
  const result=metaObsState.paid.get(row.id),busy=metaObsState.busy.has(metaObsBusyKey('paid',row.id));
  const item=el('div','result-item meta-observability-item');const head=el('div','meta-observability-item-head');
  const copy=el('div','');copy.append(el('strong','',row.campaign_name||'Pauta Meta'),el('p','',`${row.status} · ${row.ad_id?`Ad ${row.ad_id}`:'estructura parcial'}`));
  head.append(copy,metaObsButton(busy?'Verificando…':'Estado + métricas',()=>verifyMetaPaid(row.id),busy||!socialState.status?.configured));item.append(head);
  if(!result){item.append(el('p','muted','Sin verificar en esta sesión.'));root.append(item);return}
  if(!result.available){item.append(el('p','muted',result.reason||'Sin objetos remotos.'));root.append(item);return}
  const safety=result.safety||{};const safetyText=safety.explicit_active_detected?'ALERTA: Meta reportó un objeto configurado ACTIVE.':safety.configured_paused===true?'Campaign, Ad Set y Ad confirmados PAUSED.':'Estado remoto leído; revisa la jerarquía.';
  item.append(el('p',safety.explicit_active_detected?'meta-observability-alert':'muted',safetyText));
  const objects=result.objects||{};const lines=el('div','meta-observability-object-lines');lines.append(el('span','',metaObsObjectLine('Campaign',objects.campaign)),el('span','',metaObsObjectLine('Ad Set',objects.adset)),el('span','',metaObsObjectLine('Creative',objects.creative)),el('span','',metaObsObjectLine('Ad',objects.ad)));item.append(lines);
  const insights=result.insights||{};const metrics=el('div','meta-observability-metrics');for(const [label,key] of [['Impresiones','impressions'],['Alcance','reach'],['Clics','clicks'],['Gasto','spend'],['CTR','ctr'],['CPM','cpm']]){if(insights[key]!==undefined)metrics.append(metaObsMetricChip(label,metaObsNumber(insights[key])))}if(metrics.childElementCount)item.append(metrics);
  root.append(item);
}

function renderMetaObservability(){
  const panel=ensureMetaObservabilityPanel();if(!panel||!state.current?.project)return;
  const projectId=metaObsProjectId();if(metaObsState.projectId!==projectId){metaObsState.projectId=projectId;metaObsState.publications.clear();metaObsState.paid.clear();metaObsState.busy.clear()}
  const publications=metaObsPublished(),paid=metaObsPaid();$('#meta-observability-publication-count').textContent=String(publications.length);$('#meta-observability-paid-count').textContent=String(paid.length);
  const publicationRoot=$('#meta-observability-publications');publicationRoot.replaceChildren();for(const row of [...publications].reverse())renderMetaObsPublication(row,publicationRoot);if(!publications.length)publicationRoot.append(el('p','muted','Todavía no hay publicaciones PUBLISHED con remote_id.'));
  const paidRoot=$('#meta-observability-paid');paidRoot.replaceChildren();for(const row of [...paid].reverse())renderMetaObsPaid(row,paidRoot);if(!paid.length)paidRoot.append(el('p','muted','Todavía no hay estructura de pauta remota.'));
  const paidResults=[...metaObsState.paid.values()];const active=paidResults.some(result=>result?.safety?.explicit_active_detected);const allPaused=paidResults.length>0&&paidResults.every(result=>result?.safety?.configured_paused===true&&!result?.safety?.explicit_active_detected);const badge=$('#meta-observability-safety');badge.textContent=active?'ALERTA ACTIVE':allPaused?'PAUSED CONFIRMADO':'READ ONLY';badge.classList.toggle('ok',allPaused);badge.classList.toggle('meta-observability-danger',active);
}

async function verifyMetaPublication(publicationId){
  const projectId=metaObsProjectId();if(!projectId)return;const key=metaObsBusyKey('publication',publicationId);metaObsState.busy.add(key);renderMetaObservability();
  try{const result=await api(`/api/projects/${encodeURIComponent(projectId)}/publications/${encodeURIComponent(publicationId)}/observability`);metaObsState.publications.set(publicationId,result);toast('Estado de publicación verificado en Meta')}catch(err){toast(`Meta: ${err.message}`)}finally{metaObsState.busy.delete(key);renderMetaObservability()}
}
async function verifyMetaPaid(draftId){
  const projectId=metaObsProjectId();if(!projectId)return;const key=metaObsBusyKey('paid',draftId);metaObsState.busy.add(key);renderMetaObservability();
  try{const preset=$('#meta-observability-period')?.value||'maximum';const result=await api(`/api/projects/${encodeURIComponent(projectId)}/paid-media/${encodeURIComponent(draftId)}/observability?date_preset=${encodeURIComponent(preset)}`);metaObsState.paid.set(draftId,result);if(result?.safety?.explicit_active_detected)toast('ALERTA: Meta reportó un objeto ACTIVE');else toast('Estado de pauta verificado en Meta')}catch(err){toast(`Meta: ${err.message}`)}finally{metaObsState.busy.delete(key);renderMetaObservability()}
}
async function verifyRecentMetaObservability(){
  if(!socialState.status?.configured){toast('Conecta Meta antes de verificar estado remoto');return}
  const tasks=[...metaObsPublished().slice(-5).map(row=>['publication',row.id]),...metaObsPaid().slice(-5).map(row=>['paid',row.id])];if(!tasks.length){toast('No hay objetos remotos para verificar');return}
  for(const [kind,id] of tasks){if(kind==='publication')await verifyMetaPublication(id);else await verifyMetaPaid(id)}
}

function metaObsWatch(){const title=$('#active-project-name');if(title)new MutationObserver(()=>setTimeout(renderMetaObservability,0)).observe(title,{childList:true,characterData:true,subtree:true});setInterval(()=>{if(metaObsProjectId())renderMetaObservability()},3000);setTimeout(renderMetaObservability,0)}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',metaObsWatch,{once:true});else metaObsWatch();
globalThis.renderMetaObservability=renderMetaObservability;
