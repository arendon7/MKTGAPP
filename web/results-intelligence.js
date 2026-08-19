const wave65ResultsState={companyId:null,payload:null,loading:false,generating:null,onlyAttention:false};

function wave65Styles(){
  if(document.querySelector('#wave65-results-style'))return;
  const style=document.createElement('style');style.id='wave65-results-style';style.textContent=`
  .w65-hero{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(320px,.75fr);gap:12px}.w65-hero-copy{padding:16px;border:1px solid #dcd8cf;border-radius:14px;background:#fff;display:grid;gap:8px}.w65-chain{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px}.w65-chain div{padding:9px;border:1px solid #e5e1d9;border-radius:9px;background:#faf9f6;display:grid;gap:2px}.w65-chain strong{font-size:10px}.w65-chain span{font-size:8px;color:#716d65}.w65-metrics{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px}.w65-metric{padding:11px;border:1px solid #e2ded6;border-radius:10px;background:#fff;display:grid;gap:2px}.w65-metric strong{font-size:20px}.w65-metric span{font-size:8px;color:#716d65}.w65-disclosure{padding:10px;border-radius:10px;background:#f4f1e9;font-size:9px;line-height:1.45}.w65-toolbar{display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap}.w65-list{display:grid;gap:10px}.w65-card{padding:13px;border:1px solid #dedbd2;border-radius:13px;background:#fff;display:grid;gap:10px}.w65-card.attention{border-left:4px solid #171717}.w65-head{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}.w65-head-copy{display:grid;gap:3px}.w65-head-copy h4{margin:0;font-size:14px}.w65-meta{font-size:9px;color:#706c65}.w65-evidence{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:7px}.w65-cell{padding:9px;border:1px solid #e5e1d9;border-radius:9px;display:grid;gap:3px}.w65-cell strong{font-size:10px}.w65-cell span{font-size:8px;color:#706c65}.w65-chip{display:inline-flex;width:max-content;padding:4px 7px;border-radius:999px;background:#efede7;font-size:8px}.w65-chip.observed,.w65-chip.attributed,.w65-chip.attributed_won{background:#e6efe7}.w65-next{padding:8px 10px;border-radius:9px;background:#f5f2eb;display:flex;justify-content:space-between;gap:8px;align-items:center}.w65-next strong{font-size:10px}.w65-next span{font-size:8px;color:#706c65}.w65-decision,.w65-ai{padding:10px;border:1px solid #e2ded6;border-radius:10px;display:grid;gap:6px}.w65-decision p,.w65-ai p{margin:0;font-size:9px;line-height:1.45;color:#625f58}.w65-ai ul{margin:0;padding-left:18px;font-size:9px;color:#625f58}.w65-ai li{margin:3px 0}.w65-actions{display:flex;gap:7px;flex-wrap:wrap}.w65-value{font-size:8px;color:#625f58}.w65-empty{padding:20px;border:1px dashed #d5d0c5;border-radius:11px;color:#706c65;font-size:10px}
  @media(max-width:1050px){.w65-hero{grid-template-columns:1fr}.w65-evidence{grid-template-columns:1fr 1fr}.w65-chain{grid-template-columns:1fr 1fr}}@media(max-width:680px){.w65-chain,.w65-evidence{grid-template-columns:1fr}.w65-head,.w65-next{display:grid}}
  `;document.head.append(style)
}

function wave65Company(){return typeof opsSelectedCompany==='function'?opsSelectedCompany():null}
function wave65Num(value,digits=2){const number=Number(value);if(!Number.isFinite(number))return'—';return new Intl.NumberFormat('es-CO',{maximumFractionDigits:digits}).format(number)}
function wave65Pct(value){return value===null||value===undefined?'—':`${wave65Num(value,2)}%`}
function wave65MoneyBuckets(valueByCurrency){const rows=[];for(const [currency,row] of Object.entries(valueByCurrency||{})){const won=Number(row.won_value||0),open=Number(row.open_value||0);if(won)rows.push(`${wave65Num(won,0)} ${currency} ganados`);else if(open)rows.push(`${wave65Num(open,0)} ${currency} abiertos`)}return rows.join(' · ')||'Sin valor atribuido'}
function wave65EvidenceClass(level){return String(level||'INSUFFICIENT').toLowerCase()}

function wave65EnsureNav(){
  const nav=document.querySelector('.marketing-ops-nav');if(!nav)return;
  let button=nav.querySelector('[data-ops-view="intelligence"]');
  if(!button){button=opsEl('button','','Resultados & IA');button.type='button';button.dataset.opsView='intelligence';button.innerHTML='Resultados & IA <small>W65</small>';button.addEventListener('click',()=>opsShowView('intelligence'));const execution=nav.querySelector('[data-ops-view="execution"]');if(execution)execution.insertAdjacentElement('afterend',button);else nav.append(button)}
  button.classList.toggle('active',marketingOpsState.view==='intelligence')
}

async function wave65Load(force=false){
  const company=wave65Company();if(!company){wave65ResultsState.companyId=null;wave65ResultsState.payload=null;return null}
  if(wave65ResultsState.loading)return wave65ResultsState.payload;
  if(!force&&wave65ResultsState.companyId===company.id&&wave65ResultsState.payload)return wave65ResultsState.payload;
  wave65ResultsState.loading=true;
  try{const payload=await opsApi(`/api/companies/${encodeURIComponent(company.id)}/results-intelligence`);wave65ResultsState.companyId=company.id;wave65ResultsState.payload=payload;return payload}catch(err){opsToast(err.message);return null}finally{wave65ResultsState.loading=false}
}

function wave65Go(view,row){
  if(view==='campaigns'){if(typeof campaignState!=='undefined')campaignState.selectedId=row.campaign.id;opsShowView('campaigns');return}
  opsShowView(view)
}

async function wave65Analyze(row){
  const company=wave65Company(),payload=wave65ResultsState.payload;if(!company||!payload||wave65ResultsState.generating)return;
  if(!row.evidence?.has_signal){opsToast('Primero captura evidencia observada o atribuida para esta campaña');return}
  if(!payload.ai?.configured){opsToast('Configura provider y modelo de IA en Hoy');opsShowView('home');return}
  if(!confirm(`Se enviará contexto marketing sanitizado a ${payload.ai.provider} para analizar esta campaña. La IA no publicará, activará pauta ni ejecutará decisiones. ¿Continuar?`))return;
  wave65ResultsState.generating=row.campaign.id;wave65Render();
  try{
    await opsApi(`/api/companies/${encodeURIComponent(company.id)}/ai/generate`,{method:'POST',body:{task:'CAMPAIGN',campaign_id:row.campaign.id,instruction:'Analiza los resultados observados y la atribución disponible. Distingue explícitamente evidencia observada, atribución parcial y límites de cobertura. Propón próximos pasos, pero no afirmes causalidad no demostrada ni ejecutes acciones.'}});
    await wave65Load(true);opsToast('Análisis IA guardado como recomendación, sin ejecutar cambios')
  }catch(err){opsToast(err.message)}
  finally{wave65ResultsState.generating=null;wave65Render()}
}

function wave65MetricCell(label,value,copy){const node=opsEl('div','w65-cell');node.append(opsEl('span','',label),opsEl('strong','',value),opsEl('span','',copy));return node}

function wave65AIBlock(row){
  const box=opsEl('div','w65-ai'),session=row.latest_ai;
  box.append(opsEl('strong','',session?'Último análisis IA':'IA opcional'));
  if(!session){box.append(opsEl('p','',row.evidence?.has_signal?'Puedes pedir una interpretación adicional. La evidencia determinística permanece separada y es la fuente de verdad.':'La IA se habilita cuando exista evidencia observada o atribuida.'));return box}
  box.append(opsEl('p','',session.summary||'Análisis guardado sin resumen.'));
  if((session.diagnosis||[]).length){const list=document.createElement('ul');for(const item of session.diagnosis.slice(0,3))list.append(opsEl('li','',item));box.append(list)}
  if((session.recommendations||[]).length){const list=document.createElement('ul');for(const rec of session.recommendations.slice(0,3)){list.append(opsEl('li','',`${rec.priority||'—'} · ${rec.title||'Recomendación'}${rec.next_step?` · ${rec.next_step}`:''}`))}box.append(list)}
  box.append(opsEl('span','w65-value',`${session.provider} · ${session.model} · contexto ${String(session.context_sha256||'').slice(0,12)}… · ${opsDate(session.created_at)}`));return box
}

function wave65DecisionBlock(row){
  const box=opsEl('div','w65-decision'),decision=row.decision;
  box.append(opsEl('strong','',decision?`Decisión humana · ${decision.action}`:'Decisión humana pendiente'));
  box.append(opsEl('p','',decision?(decision.rationale||'Decisión registrada sin razonamiento visible.'):'Cuando haya evidencia suficiente, registra SCALE, ITERATE, HOLD o RETIRE desde Resultados. Esa decisión documenta criterio; no ejecuta cambios.'));
  return box
}

function wave65Card(row){
  const card=opsEl('article',`w65-card ${row.requires_attention?'attention':''}`),head=opsEl('div','w65-head'),copy=opsEl('div','w65-head-copy');
  copy.append(opsEl('p','eyebrow',row.campaign.objective||'CAMPAÑA'),opsEl('h4','',row.campaign.name),opsEl('span','w65-meta',`${row.campaign.status} · ${(row.campaign.channels||[]).join(' · ')||'sin canales'}`));
  head.append(copy,opsEl('span',`w65-chip ${wave65EvidenceClass(row.evidence.level)}`,row.evidence.label));card.append(head,opsEl('div','w65-disclosure',row.evidence.summary));
  const metrics=row.evidence.metrics||{},evidence=opsEl('div','w65-evidence');
  evidence.append(
    wave65MetricCell('ORG. INTERACTION RATE',wave65Pct(metrics.organic_interaction_rate),`${row.evidence.organic_observations} observaciones`),
    wave65MetricCell('PAID CTR',wave65Pct(metrics.paid_ctr),`${wave65Num(metrics.clicks||0,0)} clicks`),
    wave65MetricCell('ATRIBUCIÓN CRM',wave65Num(row.attribution.attributed_opportunities,0),`${row.attribution.attributed_won} ganadas · LAST_CAPTURED_TOUCH`),
    wave65MetricCell('VALOR ATRIBUIDO',wave65MoneyBuckets(row.attribution.value_by_currency),'sin conversión de moneda')
  );card.append(evidence);
  const next=opsEl('div','w65-next'),nextCopy=opsEl('div','');nextCopy.append(opsEl('strong','',`Siguiente: ${row.next_action.label}`),opsEl('span','',row.next_action.code));const go=opsEl('button','primary','Ir');go.type='button';go.addEventListener('click',()=>wave65Go(row.next_action.view,row));next.append(nextCopy,go);card.append(next,wave65DecisionBlock(row),wave65AIBlock(row));
  const actions=opsEl('div','w65-actions'),execution=opsEl('button','','Ejecución'),results=opsEl('button','','Resultados'),campaign=opsEl('button','','Campaña');execution.type=results.type=campaign.type='button';execution.addEventListener('click',()=>wave65Go('execution',row));results.addEventListener('click',()=>wave65Go('analytics',row));campaign.addEventListener('click',()=>wave65Go('campaigns',row));actions.append(execution,results,campaign);
  const ai=opsEl('button',row.evidence.has_signal&&wave65ResultsState.payload?.ai?.configured?'primary':'',wave65ResultsState.generating===row.campaign.id?'Analizando…':row.evidence.has_signal?'Analizar con IA':'IA requiere evidencia');ai.type='button';ai.disabled=wave65ResultsState.generating===row.campaign.id||!row.evidence.has_signal;ai.addEventListener('click',()=>wave65Analyze(row));actions.append(ai);card.append(actions);return card
}

function wave65Render(){
  if(marketingOpsState.view!=='intelligence')return;wave65EnsureNav();wave65Styles();const root=document.querySelector('#marketing-ops-view');if(!root)return;root.replaceChildren();document.querySelector('#marketing-ops-eyebrow').textContent='RESULTADOS & IA · W65';document.querySelector('#marketing-ops-title').textContent='Resultados, aprendizaje y recomendación';document.querySelector('#marketing-ops-subtitle').textContent='Evidencia determinística primero. IA opcional después. Ninguna recomendación ejecuta cambios por sí sola.';document.querySelectorAll('[data-ops-view]').forEach(button=>button.classList.toggle('active',button.dataset.opsView==='intelligence'));
  const company=wave65Company();if(!company){root.append(opsEmpty('Selecciona una empresa para revisar resultados y aprendizaje.'));return}
  const payload=wave65ResultsState.payload;if(!payload||wave65ResultsState.companyId!==company.id){root.append(opsEmpty('Cargando resultados locales…'));wave65Load(true).then(wave65Render);return}
  const summary=payload.summary||{},hero=opsEl('div','w65-hero'),copy=opsEl('section','w65-hero-copy');copy.append(opsEl('p','eyebrow','RESULTS & INTELLIGENCE WORKSPACE'),opsEl('h3','',`Cerrar el ciclo · ${company.name}`),opsEl('p','muted','La app separa ejecución, evidencia observada, atribución parcial, decisión humana y recomendación IA para no confundir correlación con causalidad.'));
  const chain=opsEl('div','w65-chain');[['1 · Ejecutar','W64'],['2 · Observar','Snapshot W52'],['3 · Decidir','SCALE / ITERATE / HOLD / RETIRE'],['4 · Interpretar','IA opcional y explícita']].forEach(([a,b])=>{const node=opsEl('div','');node.append(opsEl('strong','',a),opsEl('span','',b));chain.append(node)});copy.append(chain);
  const snapshot=payload.latest_snapshot?`${payload.latest_snapshot.date_preset} · ${opsDate(payload.latest_snapshot.created_at)}`:'Sin snapshot';copy.append(opsEl('div','w65-disclosure',`Última evidencia: ${snapshot}. Cobertura de oportunidades atribuibles: ${wave65Pct(payload.attribution_coverage?.opportunity_percent||0)}. El modelo CRM es LAST_CAPTURED_TOUCH y no supone cobertura total.`));
  const metrics=opsEl('div','w65-metrics');[[summary.with_observed_evidence||0,'CON EVIDENCIA OBSERVADA'],[summary.with_attributed_opportunities||0,'CON OPORTUNIDAD ATRIBUIDA'],[summary.with_human_decision||0,'CON DECISIÓN HUMANA'],[summary.with_ai_analysis||0,'CON ANÁLISIS IA']].forEach(([value,label])=>{const node=opsEl('div','w65-metric');node.append(opsEl('strong','',String(value)),opsEl('span','',label));metrics.append(node)});hero.append(copy,metrics);root.append(hero);
  const section=opsEl('section','marketing-ops-section'),toolbar=opsEl('div','w65-toolbar'),toolbarCopy=opsEl('div','');toolbarCopy.append(opsEl('p','eyebrow','CAMPAÑAS'),opsEl('h3','','De evidencia a decisión'));const controls=opsEl('div','marketing-ops-actions'),filter=opsEl('button',wave65ResultsState.onlyAttention?'primary':'','Solo requieren atención');filter.type='button';filter.addEventListener('click',()=>{wave65ResultsState.onlyAttention=!wave65ResultsState.onlyAttention;wave65Render()});const refresh=opsEl('button','','Actualizar local');refresh.type='button';refresh.addEventListener('click',async()=>{await wave65Load(true);wave65Render()});controls.append(filter,refresh);toolbar.append(toolbarCopy,controls);section.append(toolbar);
  const rows=(payload.campaigns||[]).filter(row=>!wave65ResultsState.onlyAttention||row.requires_attention),list=opsEl('div','w65-list');for(const row of rows)list.append(wave65Card(row));if(!rows.length)list.append(opsEl('div','w65-empty',payload.campaigns?.length?'No hay campañas que requieran atención con este filtro.':'Aún no hay campañas para interpretar.'));section.append(list);root.append(section)
}

const wave65BaseRender=globalThis.renderMarketingOps;
globalThis.renderMarketingOps=function(){wave65EnsureNav();if(marketingOpsState.view==='intelligence'){wave65Render();return}wave65BaseRender();wave65EnsureNav()};

if(typeof wave47EnsureNavigation==='function'){
  const wave65BaseNav=wave47EnsureNavigation;
  wave47EnsureNavigation=function(){wave65BaseNav();wave65EnsureNav()}
}

window.addEventListener('marketing-ops-refreshed',()=>{if(marketingOpsState.view==='intelligence')wave65Load(true).then(wave65Render)});
wave65EnsureNav();
