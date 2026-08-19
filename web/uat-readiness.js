const wave66State={companyId:null,payload:null,loading:false,queued:false};

const W66_LABELS={
  home:'Hoy','commercial-desk':'Mesa comercial',inbox:'Inbox','lead-intake':'Leads',crm:'CRM',
  campaigns:'Campañas',content:'Creative Studio',video:'Video Studio',execution:'Ejecución',
  calendar:'Calendario',publish:'Publicar',pauta:'Pauta',analytics:'Resultados',intelligence:'Resultados & IA',
  learning:'Aprendizaje','ai-copilot':'IA Copilot',ai:'IA Copilot',audiences:'Audiencias',companies:'Empresas & Meta',
  'uat-readiness':'UAT & Calidad',attribution:'Atribución','capture-bridge':'Captura web','public-gateway':'Recepción web 24/7',
  'contact-360':'Cliente 360'
};
const W66_GROUPS=[
  ['TRABAJO DIARIO',['home','commercial-desk','inbox','lead-intake','crm']],
  ['CREAR Y DISTRIBUIR',['campaigns','content','video','execution','calendar','publish','pauta']],
  ['MEDIR Y MEJORAR',['analytics','intelligence','learning','ai-copilot','ai']],
  ['CONFIGURACIÓN',['audiences','companies','uat-readiness']],
];
const W66_ADVANCED=new Set(['attribution','capture-bridge','public-gateway']);
const W66_JOURNEY=[
  ['home','Hoy'],['commercial-desk','Atender / convertir'],['crm','Pipeline'],['campaigns','Planear'],['execution','Crear / distribuir'],['intelligence','Aprender']
];
const W66_STATUS={READY:'Listo',NEEDS_DATA:'Falta caso de prueba',WAITING:'En espera',NEEDS_EVIDENCE:'Falta evidencia',OPTIONAL:'Opcional',BLOCKED:'Bloqueado'};

function wave66Styles(){
  if(document.querySelector('#wave66-uat-style'))return;
  const style=document.createElement('style');style.id='wave66-uat-style';style.textContent=`
  .w66-nav-group{display:grid;gap:4px}.w66-nav-label{padding:8px 7px 3px;font-size:7px;letter-spacing:.13em;color:#8a857c}.w66-nav-group button{width:100%;text-align:left}.w66-nav-optional{border-top:1px solid #e4e0d8;margin-top:4px;padding-top:7px}.w66-nav-optional summary{cursor:pointer;list-style:none;padding:7px;font-size:8px;color:#777269}.w66-nav-optional summary::-webkit-details-marker{display:none}.w66-nav-optional summary:after{content:'+';float:right}.w66-nav-optional[open] summary:after{content:'−'}.w66-nav-note{font-size:8px;color:#706c65;padding:6px 7px 2px;line-height:1.4}
  .w66-journey{display:flex;gap:5px;align-items:center;overflow:auto;padding:7px 0 10px;margin-bottom:3px}.w66-journey button{flex:0 0 auto;padding:6px 8px;border-radius:999px;font-size:8px;background:#f7f5f0;border:1px solid #ded9cf}.w66-journey button.current{background:#171717;color:#fff;border-color:#171717}.w66-journey .arrow{font-size:8px;color:#a39d93}.w66-journey-label{font-size:7px;letter-spacing:.1em;color:#8a857c;margin-right:2px;white-space:nowrap}
  .w66-hero{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(290px,.65fr);gap:12px}.w66-panel,.w66-card,.w66-scenario,.w66-contract{padding:14px;border:1px solid #ded9d0;border-radius:13px;background:#fff;display:grid;gap:8px}.w66-panel h3,.w66-card h4,.w66-scenario h4{margin:0}.w66-release{padding:11px;border-radius:10px;background:#f5f2eb;font-size:9px;line-height:1.5}.w66-summary{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px}.w66-metric{padding:11px;border:1px solid #e4e0d7;border-radius:10px;background:#fff;display:grid;gap:2px}.w66-metric strong{font-size:20px}.w66-metric span{font-size:8px;color:#706c65}.w66-toolbar{display:flex;align-items:flex-end;justify-content:space-between;gap:9px;flex-wrap:wrap}.w66-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}.w66-card.attention{border-left:4px solid #171717}.w66-card-head,.w66-scenario-head{display:flex;justify-content:space-between;gap:8px;align-items:flex-start}.w66-chip{display:inline-flex;width:max-content;padding:4px 7px;border-radius:999px;background:#efede7;font-size:8px;white-space:nowrap}.w66-chip.ready{background:#e5f0e6}.w66-chip.needs_data,.w66-chip.needs_evidence{background:#fff0df}.w66-chip.waiting,.w66-chip.optional{background:#f0eee8}.w66-chip.blocked{background:#171717;color:#fff}.w66-card p,.w66-scenario p{margin:0;font-size:9px;color:#666159;line-height:1.5}.w66-actions{display:flex;gap:6px;flex-wrap:wrap}.w66-scenarios{display:grid;gap:8px}.w66-scenario{grid-template-columns:minmax(0,1fr) auto;align-items:center}.w66-scenario-copy{display:grid;gap:5px}.w66-contracts{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.w66-contract strong{font-size:11px}.w66-contract span{font-size:8px;color:#706c65;line-height:1.4}.w66-empty{padding:18px;border:1px dashed #d4cfc5;border-radius:11px;color:#706c65;font-size:9px}
  @media(max-width:980px){.w66-hero,.w66-grid{grid-template-columns:1fr}.w66-contracts{grid-template-columns:1fr 1fr}}@media(max-width:640px){.w66-summary,.w66-contracts{grid-template-columns:1fr}.w66-scenario{grid-template-columns:1fr}.w66-card-head,.w66-scenario-head{display:grid}}
  `;document.head.append(style)
}

function wave66Company(){return typeof opsSelectedCompany==='function'?opsSelectedCompany():null}
function wave66Group(label,buttons){const group=opsEl('div','w66-nav-group');group.dataset.w66Group=label;group.append(opsEl('div','w66-nav-label',label));buttons.forEach(button=>group.append(button));return group}
function wave66Label(button,view){const label=W66_LABELS[view];if(!label)return;button.replaceChildren(document.createTextNode(label))}

function wave66EnsureUATNavButton(){
  const nav=document.querySelector('.marketing-ops-nav');if(!nav)return null;
  let button=nav.querySelector('[data-ops-view="uat-readiness"]');
  if(!button){button=opsEl('button','','UAT & Calidad');button.type='button';button.dataset.opsView='uat-readiness';button.addEventListener('click',()=>opsShowView('uat-readiness'));nav.append(button)}
  return button
}

function wave66RebuildNavigation(){
  const nav=document.querySelector('.marketing-ops-nav');if(!nav)return;wave66EnsureUATNavButton();
  const buttons=[...nav.querySelectorAll('button[data-ops-view]')],unique=new Map();
  for(const button of buttons){const view=button.dataset.opsView;if(view&&!unique.has(view))unique.set(view,button)}
  for(const [view,button] of unique)wave66Label(button,view);
  nav.replaceChildren();const used=new Set();
  for(const [label,views] of W66_GROUPS){const rows=[];for(const view of views){const button=unique.get(view);if(button){rows.push(button);used.add(view)}}if(rows.length)nav.append(wave66Group(label,rows))}
  const advanced=[],other=[];for(const [view,button] of unique){if(used.has(view))continue;(W66_ADVANCED.has(view)?advanced:other).push(button)}
  if(other.length)nav.append(wave66Group('MÁS HERRAMIENTAS',other));
  if(advanced.length){const details=document.createElement('details');details.className='w66-nav-optional';const summary=document.createElement('summary');summary.textContent='Avanzado · opcional';details.append(summary,opsEl('div','w66-nav-note','Atribución avanzada y recepción web 24/7 permanecen fuera del camino crítico del producto local.'),wave66Group('INTEGRACIONES',advanced));nav.append(details)}
  const current=marketingOpsState?.view;nav.querySelectorAll('button[data-ops-view]').forEach(button=>button.classList.toggle('active',button.dataset.opsView===current))
}

function wave66Go(view,tab=null){
  if(view==='crm'&&tab){try{crmState.tab=tab}catch(_err){}}
  opsShowView(view)
}

function wave66JourneyStrip(){
  const root=document.querySelector('#marketing-ops-view'),company=wave66Company();if(!root||!company||marketingOpsState?.view==='uat-readiness')return;
  root.querySelector('.w66-journey')?.remove();
  const current=marketingOpsState?.view,strip=opsEl('nav','w66-journey');strip.setAttribute('aria-label','Recorrido operativo');strip.append(opsEl('span','w66-journey-label','FLUJO'));
  W66_JOURNEY.forEach(([view,label],index)=>{const button=opsEl('button',view===current?'current':'',label);button.type='button';button.addEventListener('click',()=>wave66Go(view,view==='crm'?'pipeline':null));strip.append(button);if(index<W66_JOURNEY.length-1)strip.append(opsEl('span','arrow','→'))});
  root.prepend(strip)
}

function wave66QueuePolish(){
  if(wave66State.queued)return;wave66State.queued=true;
  queueMicrotask(()=>{wave66State.queued=false;wave66Styles();wave66RebuildNavigation();wave66JourneyStrip()})
}

async function wave66Load(force=false){
  const company=wave66Company();if(!company){wave66State.companyId=null;wave66State.payload=null;return null}
  if(wave66State.loading)return wave66State.payload;
  if(!force&&wave66State.companyId===company.id&&wave66State.payload)return wave66State.payload;
  wave66State.loading=true;
  try{const payload=await opsApi(`/api/companies/${encodeURIComponent(company.id)}/uat-readiness`);wave66State.companyId=company.id;wave66State.payload=payload;return payload}catch(err){wave66State.payload=null;opsToast(err.message);return null}finally{wave66State.loading=false}
}

function wave66StatusClass(status){return String(status||'WAITING').toLowerCase()}
function wave66StatusChip(status){return opsEl('span',`w66-chip ${wave66StatusClass(status)}`,W66_STATUS[status]||status)}
function wave66Metric(value,label){const node=opsEl('div','w66-metric');node.append(opsEl('strong','',String(value??0)),opsEl('span','',label));return node}
function wave66Contract(title,value,detail){const node=opsEl('div','w66-contract');node.append(opsEl('strong','',value),opsEl('span','',title),opsEl('span','',detail));return node}

function wave66JourneyCard(row){
  const card=opsEl('article',`w66-card ${row.required&&row.status!=='READY'?'attention':''}`),head=opsEl('div','w66-card-head'),copy=opsEl('div','');copy.append(opsEl('p','eyebrow',row.code),opsEl('h4','',row.label));head.append(copy,wave66StatusChip(row.status));card.append(head,opsEl('p','',row.detail));
  if(row.metric!==null&&row.metric!==undefined)card.append(opsEl('span','w66-chip',`${row.metric} registro(s)/señal(es)`));
  const actions=opsEl('div','w66-actions'),open=opsEl('button',row.status==='READY'?'primary':'','Abrir tramo');open.type='button';open.addEventListener('click',()=>wave66Go(row.view,row.tab));actions.append(open);if(!row.required)actions.append(opsEl('span','w66-chip optional','No bloquea core'));card.append(actions);return card
}

function wave66Scenario(row){
  const item=opsEl('article','w66-scenario'),copy=opsEl('div','w66-scenario-copy'),head=opsEl('div','w66-scenario-head'),title=opsEl('div','');title.append(opsEl('p','eyebrow',row.id),opsEl('h4','',row.label));head.append(title,wave66StatusChip(row.status));copy.append(head,opsEl('p','',`Precondición: ${row.precondition}`),opsEl('p','',`Esperado: ${row.expected}`));const button=opsEl('button',row.status==='READY'?'primary':'','Abrir');button.type='button';button.addEventListener('click',()=>wave66Go(row.view,row.tab));item.append(copy,button);return item
}

function wave66Render(){
  if(marketingOpsState.view!=='uat-readiness')return;wave66Styles();wave66RebuildNavigation();const root=document.querySelector('#marketing-ops-view');if(!root)return;root.replaceChildren();
  document.querySelector('#marketing-ops-eyebrow').textContent='PRODUCT UAT · W66';document.querySelector('#marketing-ops-title').textContent='UAT & Calidad del producto';document.querySelector('#marketing-ops-subtitle').textContent='Recorre el producto de extremo a extremo sin confundir ausencia de datos con fallo de superficie ni UAT manual con release de producción.';document.querySelectorAll('[data-ops-view]').forEach(button=>button.classList.toggle('active',button.dataset.opsView==='uat-readiness'));
  const company=wave66Company();if(!company){root.append(opsEl('div','w66-empty','Selecciona o crea una empresa. La UAT se evalúa siempre dentro de un contexto empresarial explícito.'));return}
  const payload=wave66State.payload;if(!payload||wave66State.companyId!==company.id){root.append(opsEl('div','w66-empty','Componiendo readiness local de Hoy, comercial, pipeline, ejecución y resultados…'));wave66Load(true).then(wave66Render);return}
  const summary=payload.summary||{},hero=opsEl('div','w66-hero'),main=opsEl('section','w66-panel');main.append(opsEl('p','eyebrow','MANUAL UAT READINESS'),opsEl('h3','',`${company.name} · recorrido preparado`),opsEl('p','muted','El diagnóstico es local y de solo lectura. “Falta caso de prueba” significa que la superficie existe pero necesita datos controlados para recorrer ese escenario; no se genera evidencia falsa automáticamente.'));
  main.append(opsEl('div','w66-release',`Estado de release: ${payload.release_boundary.version} · RELEASE_READY=${payload.release_boundary.release_ready} · UAT física registrada=${payload.release_boundary.physical_uat_recorded}. W66 prepara y endurece el recorrido; no certifica por sí sola el Mac físico ni producción.`));
  const metrics=opsEl('div','w66-summary');metrics.append(wave66Metric(summary.ready_steps,'TRAMOS REQUERIDOS LISTOS'),wave66Metric(summary.scenario_gaps,'TRAMOS QUE NECESITAN DATOS'),wave66Metric((payload.evidence?.pipeline_summary||{}).requires_attention||0,'CASOS CRM CON ATENCIÓN'),wave66Metric((payload.evidence?.results_summary||{}).with_human_decision||0,'CAMPAÑAS CON DECISIÓN'));hero.append(main,metrics);root.append(hero);
  const journeySection=opsEl('section','marketing-ops-section'),toolbar=opsEl('div','w66-toolbar'),copy=opsEl('div','');copy.append(opsEl('p','eyebrow','RECORRIDO CRÍTICO'),opsEl('h3','','De empresa a aprendizaje'));const refresh=opsEl('button','','Actualizar diagnóstico local');refresh.type='button';refresh.addEventListener('click',async()=>{await wave66Load(true);wave66Render()});toolbar.append(copy,refresh);journeySection.append(toolbar);const grid=opsEl('div','w66-grid');for(const row of payload.journey||[])grid.append(wave66JourneyCard(row));journeySection.append(grid);root.append(journeySection);
  const scenarioSection=opsEl('section','marketing-ops-section');scenarioSection.append(opsEl('p','eyebrow','ESCENARIOS MANUALES'),opsEl('h3','','Checklist navegable para tu Mac'));const scenarios=opsEl('div','w66-scenarios');for(const row of payload.manual_scenarios||[])scenarios.append(wave66Scenario(row));scenarioSection.append(scenarios);root.append(scenarioSection);
  const contractSection=opsEl('section','marketing-ops-section');contractSection.append(opsEl('p','eyebrow','CONTRATOS PRESERVADOS'),opsEl('h3','','Lo que W66 no puede debilitar'));const contracts=opsEl('div','w66-contracts');contracts.append(wave66Contract('WORKFLOWS',`${payload.contracts.workflow_count} canónicos`,payload.contracts.canonical_workflows_only?'ci.yml · full-mac-app.yml · persistent-release.yml':'Revisar drift de workflows'),wave66Contract('RUNTIME','Loopback local',payload.contracts.loopback_default?'127.0.0.1 por defecto':'Revisar bind'),wave66Contract('CLOUD',payload.contracts.cloud_required?'Requerido':'Opcional','El core local no depende de Supabase/Vercel'),wave66Contract('PROVIDERS',payload.safety.provider_read_performed?'Lectura detectada':'Sin lectura al abrir','El diagnóstico no consulta Meta'),wave66Contract('AUTOMATIZACIÓN',payload.safety.automatic_publish?'Publicación automática':'Sin ejecución automática','No mensajes, stages, publicación ni activación de pauta'),wave66Contract('PRODUCCIÓN',payload.summary.production_ready?'Ready':'Bloqueada','Firma distribución, notarización y UAT física siguen fuera de W66'));contractSection.append(contracts);root.append(contractSection)
}

const wave66BaseRender=globalThis.renderMarketingOps;
if(typeof wave66BaseRender==='function')globalThis.renderMarketingOps=function(){if(marketingOpsState.view==='uat-readiness'){wave66Render();wave66QueuePolish();return}const result=wave66BaseRender();wave66QueuePolish();return result};
const wave66BaseShowView=globalThis.opsShowView;
if(typeof wave66BaseShowView==='function')globalThis.opsShowView=function(view){const result=wave66BaseShowView(view);wave66QueuePolish();return result};
window.addEventListener('marketing-company-change',()=>{wave66State.payload=null;wave66State.companyId=null;wave66QueuePolish();if(marketingOpsState.view==='uat-readiness')wave66Render()});
window.addEventListener('marketing-ops-refreshed',()=>{if(marketingOpsState.view==='uat-readiness'){wave66State.payload=null;wave66Load(true).then(wave66Render)}else wave66QueuePolish()});
wave66Styles();wave66QueuePolish();
