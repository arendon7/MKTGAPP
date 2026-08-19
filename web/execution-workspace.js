const wave64ExecutionState={companyId:null,payload:null,loading:false,onlyAction:false};
const W64_STEP_LABELS={READY:'Listo',ACTIVE:'Activo',NEEDS_ACTION:'Falta',OPTIONAL:'Opcional',WAITING:'Espera',NOT_REQUIRED:'No aplica'};
const W64_OBJECTIVES={AWARENESS:'Reconocimiento',ENGAGEMENT:'Interacción',LEADS:'Leads',SALES:'Ventas',RETENTION:'Retención',OTHER:'Otro'};

function wave64Styles(){
  if(document.querySelector('#wave64-execution-style'))return;
  const style=document.createElement('style');style.id='wave64-execution-style';style.textContent=`
  .w64-hero{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(320px,.75fr);gap:12px}.w64-hero-copy{padding:16px;border:1px solid #dcd8cf;border-radius:14px;background:#fff;display:grid;gap:8px}.w64-flow{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:6px}.w64-flow div{padding:9px;border:1px solid #e5e1d9;border-radius:9px;background:#faf9f6;display:grid;gap:2px}.w64-flow strong{font-size:10px}.w64-flow span{font-size:8px;color:#716d65}.w64-metrics{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px}.w64-metric{padding:11px;border:1px solid #e2ded6;border-radius:10px;background:#fff;display:grid;gap:2px}.w64-metric strong{font-size:20px}.w64-metric span{font-size:8px;color:#716d65}.w64-toolbar{display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap}.w64-list{display:grid;gap:10px}.w64-card{padding:13px;border:1px solid #dedbd2;border-radius:13px;background:#fff;display:grid;gap:10px}.w64-card.attention{border-left:4px solid #171717}.w64-head{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}.w64-head-copy{display:grid;gap:3px;min-width:0}.w64-head-copy h4{margin:0;font-size:14px}.w64-meta{font-size:9px;color:#706c65}.w64-next{padding:8px 10px;border-radius:9px;background:#f5f2eb;display:flex;align-items:center;justify-content:space-between;gap:8px}.w64-next strong{font-size:10px}.w64-next span{font-size:9px;color:#625f58}.w64-steps{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:6px}.w64-step{padding:8px;border:1px solid #e5e1d9;border-radius:9px;display:grid;gap:3px}.w64-step strong{font-size:9px}.w64-step span{font-size:8px;color:#716d65}.w64-step em{font-size:8px;font-style:normal}.w64-step.ready,.w64-step.active{background:#eef4ee}.w64-step.needs_action{background:#f6efe8}.w64-columns{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px}.w64-column{padding:9px;border:1px solid #e5e1d9;border-radius:9px;display:grid;gap:3px}.w64-column strong{font-size:10px}.w64-column span{font-size:8px;color:#706c65}.w64-actions{display:flex;gap:7px;flex-wrap:wrap}.w64-empty{padding:20px;border:1px dashed #d5d0c5;border-radius:11px;color:#706c65;font-size:10px}
  @media(max-width:1050px){.w64-hero{grid-template-columns:1fr}.w64-steps{grid-template-columns:1fr 1fr 1fr}.w64-columns{grid-template-columns:1fr}}@media(max-width:680px){.w64-flow,.w64-steps{grid-template-columns:1fr}.w64-head,.w64-next{display:grid}}
  `;document.head.append(style)
}

function wave64Company(){return typeof opsSelectedCompany==='function'?opsSelectedCompany():null}
function wave64StatusLabel(value){return W64_STEP_LABELS[value]||value}
function wave64Objective(value){return W64_OBJECTIVES[value]||value||'—'}
function wave64Counts(counts){return Object.entries(counts||{}).filter(([,value])=>value).map(([key,value])=>`${value} ${key.toLowerCase()}`).join(' · ')||'0'}

function wave64EnsureNav(){
  const nav=document.querySelector('.marketing-ops-nav');if(!nav)return;
  let button=nav.querySelector('[data-ops-view="execution"]');
  if(!button){button=opsEl('button','','Ejecución');button.type='button';button.dataset.opsView='execution';button.innerHTML='Ejecución <small>W64</small>';button.addEventListener('click',()=>opsShowView('execution'));const campaigns=nav.querySelector('[data-ops-view="campaigns"]');if(campaigns)campaigns.insertAdjacentElement('afterend',button);else nav.append(button)}
  button.classList.toggle('active',marketingOpsState.view==='execution')
}

async function wave64Load(force=false){
  const company=wave64Company();if(!company){wave64ExecutionState.companyId=null;wave64ExecutionState.payload=null;return null}
  if(wave64ExecutionState.loading)return wave64ExecutionState.payload;
  if(!force&&wave64ExecutionState.payload&&wave64ExecutionState.companyId===company.id)return wave64ExecutionState.payload;
  wave64ExecutionState.loading=true;
  try{const payload=await opsApi(`/api/companies/${encodeURIComponent(company.id)}/execution-workspace`);wave64ExecutionState.companyId=company.id;wave64ExecutionState.payload=payload;return payload}catch(err){opsToast(err.message);return null}finally{wave64ExecutionState.loading=false}
}

function wave64Go(view,row,mediaId=null){
  if(view==='campaigns'){
    if(typeof campaignState!=='undefined')campaignState.selectedId=row.campaign.id;
    opsShowView('campaigns');return;
  }
  if(view==='content'){
    if(mediaId&&typeof wave49CreativeState!=='undefined')wave49CreativeState.selectedId=mediaId;
    if(typeof opsShowLegacy==='function')opsShowLegacy();
    if(typeof contentRenderCurrent==='function')contentRenderCurrent();
    return;
  }
  opsShowView(view);
}

function wave64ActionButton(label,view,row,mediaId=null,primary=false){
  const button=opsEl('button',primary?'primary':'',label);button.type='button';button.addEventListener('click',()=>wave64Go(view,row,mediaId));return button
}

function wave64Card(row){
  const card=opsEl('article',`w64-card ${row.requires_action?'attention':''}`),head=opsEl('div','w64-head'),copy=opsEl('div','w64-head-copy');copy.append(opsEl('p','eyebrow',wave64Objective(row.campaign.objective)),opsEl('h4','',row.campaign.name),opsEl('span','w64-meta',`${row.campaign.status} · ${(row.campaign.channels||[]).join(' · ')||'sin canales'} · ${row.campaign.audience_contacts} contactos`));head.append(copy,opsEl('span','status',row.requires_action?'Requiere acción':'En curso'));card.append(head);
  const next=opsEl('div','w64-next'),nextCopy=opsEl('div','');nextCopy.append(opsEl('strong','',`Siguiente: ${row.next_action.label}`),opsEl('span','',row.next_action.code));next.append(nextCopy,wave64ActionButton('Ir',row.next_action.view,row,row.next_action.media_id||null,true));card.append(next);
  const steps=opsEl('div','w64-steps');for(const step of row.steps||[]){const node=opsEl('div',`w64-step ${String(step.state||'').toLowerCase()}`);node.append(opsEl('strong','',step.label),opsEl('em','',wave64StatusLabel(step.state)),opsEl('span','',step.detail));steps.append(node)}card.append(steps);
  const columns=opsEl('div','w64-columns');const creative=opsEl('div','w64-column');creative.append(opsEl('strong','',`Creativos · ${row.creative.ready}/${row.creative.total} listos`),opsEl('span','',wave64Counts(row.creative.counts)));const organic=opsEl('div','w64-column');organic.append(opsEl('strong','',`Orgánico · ${row.organic.publications}`),opsEl('span','',wave64Counts(row.organic.counts)));const paid=opsEl('div','w64-column');paid.append(opsEl('strong','',`Pauta · ${row.paid.plans}`),opsEl('span','',row.paid.plans?wave64Counts(row.paid.counts):'Sin plan de pauta'));columns.append(creative,organic,paid);card.append(columns);
  if((row.planned_only_channels||[]).length)card.append(opsEl('div','marketing-ops-note',`Canales todavía planificados, no ejecutables desde este gate: ${row.planned_only_channels.join(', ')}.`));
  const actions=opsEl('div','w64-actions');actions.append(wave64ActionButton('Campaña','campaigns',row));const firstMedia=row.creative.items?.[0]?.media_id||null;actions.append(wave64ActionButton('Creative Studio','content',row,firstMedia),wave64ActionButton('Calendario','calendar',row),wave64ActionButton('Pauta','pauta',row),wave64ActionButton('Resultados','analytics',row));card.append(actions);return card
}

function wave64Render(){
  if(marketingOpsState.view!=='execution')return;wave64EnsureNav();wave64Styles();const root=document.querySelector('#marketing-ops-view');if(!root)return;root.replaceChildren();document.querySelector('#marketing-ops-eyebrow').textContent='EJECUCIÓN · W64';document.querySelector('#marketing-ops-title').textContent='Centro de ejecución de campañas';document.querySelector('#marketing-ops-subtitle').textContent='De campaña a creativo, calendario, pauta y resultados sin duplicar acciones ni automatizar providers.';document.querySelectorAll('[data-ops-view]').forEach(button=>button.classList.toggle('active',button.dataset.opsView==='execution'));
  const company=wave64Company();if(!company){root.append(opsEmpty('Selecciona una empresa para ver su ejecución de campañas.'));return}
  const payload=wave64ExecutionState.payload;if(!payload||wave64ExecutionState.companyId!==company.id){root.append(opsEmpty('Cargando ejecución local…'));wave64Load(true).then(wave64Render);return}
  const summary=payload.summary||{},hero=opsEl('div','w64-hero'),copy=opsEl('section','w64-hero-copy');copy.append(opsEl('p','eyebrow','EXECUTION WORKSPACE'),opsEl('h3','',`De plan a distribución · ${company.name}`),opsEl('p','muted','Una sola lectura operativa. Cada botón abre el módulo canónico que conserva la mutación explícita.'));const flow=opsEl('div','w64-flow');[['1 · Plan','Campaña + canales'],['2 · Crear','Creative Studio'],['3 · Orgánico','Calendario'],['4 · Pauta','Siempre PAUSED'],['5 · Aprender','Resultados']].forEach(([a,b])=>{const node=opsEl('div','');node.append(opsEl('strong','',a),opsEl('span','',b));flow.append(node)});copy.append(flow);const metrics=opsEl('div','w64-metrics');[[summary.active_campaigns||0,'CAMPAÑAS ACTIVAS'],[summary.requires_action||0,'REQUIEREN ACCIÓN'],[summary.ready_creatives||0,'CREATIVOS LISTOS'],[(summary.queued_publications||0)+(summary.paid_remote_paused||0),'DISTRIBUCIÓN PREPARADA']].forEach(([value,label])=>{const metric=opsEl('div','w64-metric');metric.append(opsEl('strong','',String(value)),opsEl('span','',label));metrics.append(metric)});hero.append(copy,metrics);root.append(hero);
  const section=opsEl('section','marketing-ops-section'),toolbar=opsEl('div','w64-toolbar'),toolbarCopy=opsEl('div','');toolbarCopy.append(opsEl('p','eyebrow','CAMPAÑAS'),opsEl('h3','','Estado de ejecución'));const controls=opsEl('div','marketing-ops-actions'),filter=opsEl('button',wave64ExecutionState.onlyAction?'primary':'','Solo requieren acción');filter.type='button';filter.addEventListener('click',()=>{wave64ExecutionState.onlyAction=!wave64ExecutionState.onlyAction;wave64Render()});const refresh=opsEl('button','','Actualizar');refresh.type='button';refresh.addEventListener('click',async()=>{await wave64Load(true);wave64Render()});controls.append(filter,refresh);toolbar.append(toolbarCopy,controls);section.append(toolbar);const list=opsEl('div','w64-list'),rows=(payload.campaigns||[]).filter(row=>!wave64ExecutionState.onlyAction||row.requires_action);rows.forEach(row=>list.append(wave64Card(row)));if(!rows.length)list.append(opsEl('div','w64-empty',payload.campaigns?.length?'No hay campañas que requieran acción con este filtro.':'Crea una campaña para empezar a coordinar ejecución.'));section.append(list);root.append(section)
}

const wave64BaseRender=globalThis.renderMarketingOps;
globalThis.renderMarketingOps=function(){wave64EnsureNav();if(marketingOpsState.view==='execution'){wave64Render();return}wave64BaseRender();wave64EnsureNav()};

if(typeof wave47EnsureNavigation==='function'){
  const wave64BaseNav=wave47EnsureNavigation;
  wave47EnsureNavigation=function(){wave64BaseNav();wave64EnsureNav()};
}

window.addEventListener('marketing-ops-refreshed',()=>{if(marketingOpsState.view==='execution')wave64Load(true).then(wave64Render)});
wave64EnsureNav();
