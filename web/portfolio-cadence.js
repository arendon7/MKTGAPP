const postW99CadenceState={open:false,payload:null,loading:false};

function cadenceStyles(){
  if(document.querySelector('#post-w99-cadence-style'))return;
  const s=document.createElement('style');
  s.id='post-w99-cadence-style';
  s.textContent=`.cadence-trigger{border:1px solid #d9d4ca;background:#fff;border-radius:10px;padding:8px 10px;font-size:9px;color:#5e5a53;cursor:pointer}.cadence-overlay{position:fixed;inset:0;background:rgba(20,19,17,.46);z-index:9996;display:grid;place-items:center;padding:18px}.cadence-dialog{width:min(1080px,100%);max-height:90vh;overflow:hidden;background:#fff;border:1px solid #d8d3c9;border-radius:16px;box-shadow:0 24px 80px rgba(0,0,0,.22);display:grid;grid-template-rows:auto auto auto minmax(0,1fr)}.cadence-head{padding:15px 17px;border-bottom:1px solid #e7e3dc;display:flex;justify-content:space-between;gap:12px;align-items:center}.cadence-head h2{font-size:15px;margin:0}.cadence-head p{font-size:8px;color:#777168;margin:3px 0 0}.cadence-close{border:0;background:#f2efe9;border-radius:8px;padding:6px 9px;cursor:pointer}.cadence-summary{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:8px;padding:12px 16px;border-bottom:1px solid #e7e3dc}.cadence-kpi{background:#faf9f6;border:1px solid #ece8e0;border-radius:10px;padding:9px}.cadence-kpi strong{display:block;font-size:15px}.cadence-kpi span{font-size:8px;color:#777168}.cadence-scope{font-size:8px;color:#6f695f;padding:9px 16px;background:#faf9f6;border-bottom:1px solid #e7e3dc}.cadence-body{overflow:auto;padding:12px 16px 18px;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.cadence-section{min-width:0}.cadence-section h3{margin:0 0 7px;font-size:11px}.cadence-note{font-size:8px;color:#817b72;background:#faf9f6;border-radius:8px;padding:8px;margin-bottom:8px}.cadence-item{border:1px solid #e8e4dc;border-radius:11px;padding:9px;margin-bottom:7px}.cadence-item-head{display:flex;justify-content:space-between;gap:8px;align-items:start}.cadence-item h4{font-size:9px;margin:0}.cadence-sub{font-size:8px;color:#777168;margin-top:2px}.cadence-state{font-size:7px;background:#f2efe9;border-radius:999px;padding:4px 6px;white-space:nowrap}.cadence-anomaly{border-style:dashed}.cadence-item button{margin-top:7px;border:1px solid #d8d2c8;background:#fff;border-radius:8px;padding:6px 8px;font-size:8px;cursor:pointer}.cadence-hidden{display:none!important}@media(max-width:900px){.cadence-summary{grid-template-columns:repeat(2,minmax(0,1fr))}.cadence-body{grid-template-columns:1fr}.cadence-overlay{padding:7px}.cadence-dialog{max-height:95vh}}`;
  document.head.append(s);
}

function cadenceEnsureTrigger(){
  cadenceStyles();
  const top=document.querySelector('.marketing-ops-top');
  if(!top||top.querySelector('[data-post-w99-cadence-trigger]'))return;
  const b=opsEl('button','cadence-trigger','Cadencia');
  b.type='button';
  b.dataset.postW99CadenceTrigger='1';
  b.title='Semántica temporal del portfolio';
  b.addEventListener('click',cadenceOpen);
  const portfolio=top.querySelector('[data-post-w99-portfolio-trigger]');
  if(portfolio)portfolio.insertAdjacentElement('afterend',b);else top.append(b);
}

function cadenceShell(){
  let o=document.querySelector('#post-w99-cadence');
  if(o)return o;
  o=opsEl('div','cadence-overlay cadence-hidden');
  o.id='post-w99-cadence';
  o.innerHTML='<section class="cadence-dialog" role="dialog" aria-modal="true" aria-label="Portfolio Cadence"><header class="cadence-head"><div><h2>Portfolio Cadence</h2><p>Deadlines explícitos separados de antigüedad observada, anomalías temporales y trabajo sin agenda</p></div><button class="cadence-close" type="button">Cerrar</button></header><div class="cadence-summary"></div><div class="cadence-scope"></div><div class="cadence-body"></div></section>';
  document.body.append(o);
  o.querySelector('.cadence-close').addEventListener('click',cadenceClose);
  o.addEventListener('mousedown',e=>{if(e.target===o)cadenceClose()});
  return o;
}

async function cadenceOpen(){
  postW99CadenceState.open=true;
  cadenceShell().classList.remove('cadence-hidden');
  await cadenceLoad();
}
function cadenceClose(){
  postW99CadenceState.open=false;
  document.querySelector('#post-w99-cadence')?.classList.add('cadence-hidden');
}
async function cadenceLoad(){
  postW99CadenceState.loading=true;
  cadenceRender();
  try{postW99CadenceState.payload=await opsApi('/api/portfolio-cadence')}
  catch(err){postW99CadenceState.payload=null;opsToast(err.message)}
  finally{postW99CadenceState.loading=false;cadenceRender()}
}

function cadenceResolvedItem(item){
  if(item?.action)return item;
  const queue=postW99CadenceState.payload?.queue||[];
  return queue.find(row=>(item?.portfolio_id&&row.portfolio_id===item.portfolio_id)||(item?.id&&row.id===item.id))||item;
}
async function cadenceNavigate(item){
  const target=cadenceResolvedItem(item);
  const companyId=target?.company?.id;
  if(!companyId){opsToast('La acción no tiene empresa asociada.');return}
  if(typeof portfolioNavigate==='function'){
    await portfolioNavigate(companyId,target.action||{view:'home'});
    cadenceClose();
    return;
  }
  if(typeof marketingOpsState==='undefined'){opsToast('Contexto de empresa no disponible.');return}
  marketingOpsState.selectedCompanyId=companyId;
  try{localStorage.setItem('marketingOpsCompany',companyId)}catch(_err){}
  if(typeof fillCompanyFilter==='function')fillCompanyFilter();
  if(typeof globalThis.refreshMarketingOps==='function')await globalThis.refreshMarketingOps(false);
  cadenceClose();
  if(typeof opsShowView==='function')opsShowView(target?.action?.view||'home');
}

function cadenceAt(timing){
  if(!timing?.at)return 'Sin fecha explícita';
  const d=new Date(timing.at);
  return Number.isNaN(d.getTime())?String(timing.at):d.toLocaleString();
}
function cadenceTimingMeta(timing){
  const pieces=[timing?.kind||'SIN SEMÁNTICA'];
  if(timing?.timestamp_quality&&timing.timestamp_quality!=='NOT_APPLICABLE')pieces.push(timing.timestamp_quality);
  if(timing?.age_hours!==null&&timing?.age_hours!==undefined&&Number.isFinite(Number(timing.age_hours)))pieces.push(`${Number(timing.age_hours).toLocaleString()} h`);
  return pieces.join(' · ');
}
function cadenceSection(title,items,explanation){
  const section=opsEl('section','cadence-section');
  section.append(opsEl('h3','',`${title} · ${items.length}`),opsEl('div','cadence-note',explanation));
  if(!items.length){section.append(opsEl('div','cadence-note','Sin elementos en esta categoría.'));return section}
  items.slice(0,20).forEach(item=>{
    const timing=item.timing||{},company=item.company||{};
    const card=opsEl('article',`cadence-item${timing.temporal_anomaly?' cadence-anomaly':''}`);
    const head=opsEl('div','cadence-item-head'),left=opsEl('div');
    left.append(
      opsEl('h4','',item.title||'Acción'),
      opsEl('div','cadence-sub',`${company.name||'Empresa'} · ${item.source||''} · ${cadenceAt(timing)}`),
      opsEl('div','cadence-sub',cadenceTimingMeta(timing))
    );
    head.append(left,opsEl('span','cadence-state',timing.state||timing.kind||''));
    card.append(head,opsEl('div','cadence-sub',timing.explanation||''));
    const resolved=cadenceResolvedItem(item);
    const b=opsEl('button','',resolved?.action?.label||'Abrir');
    b.type='button';
    b.addEventListener('click',()=>cadenceNavigate(item));
    card.append(b);
    section.append(card);
  });
  return section;
}
function cadenceAnomalySection(items){
  return cadenceSection(
    'Anomalías temporales',
    items,
    'Timestamps futuros, inválidos o faltantes se muestran como anomalías; nunca se coercionan a edad cero ni crean un deadline.'
  );
}

function cadenceRender(){
  const shell=cadenceShell(),summary=shell.querySelector('.cadence-summary'),scope=shell.querySelector('.cadence-scope'),body=shell.querySelector('.cadence-body');
  summary.replaceChildren();body.replaceChildren();
  if(postW99CadenceState.loading){scope.textContent='Leyendo únicamente estado local…';body.append(opsEl('div','cadence-note','Normalizando semántica temporal del portfolio…'));return}
  const p=postW99CadenceState.payload;
  if(!p){scope.textContent='Sin lectura disponible.';body.append(opsEl('div','cadence-note','No hay lectura de cadencia disponible.'));return}
  const s=p.summary||{};
  [
    ['Incidentes',s.blocked_incidents||0],
    ['Vencidos',s.overdue_deadlines||0],
    ['Hoy',s.today_deadlines||0],
    ['Leads',s.received_leads||0],
    ['Sin agenda',s.unscheduled||0],
    ['Sin fecha',s.undated||0],
    ['Anomalías',s.temporal_anomalies||0],
  ].forEach(([label,value])=>{
    const card=opsEl('div','cadence-kpi');
    card.append(opsEl('strong','',String(value)),opsEl('span','',label));
    summary.append(card);
  });
  const sc=p.scope||{};
  scope.textContent=sc.parent_queue_truncated
    ?`Alcance parcial: Portfolio Control Tower reporta ${sc.parent_queue_total||0} acciones y expone ${sc.projected_queue_total||0}. Cadence no inventa las faltantes.`
    :`Alcance completo del queue expuesto por Portfolio Control Tower: ${sc.projected_queue_total||0} acción(es). El orden no se modifica.`;
  const b=p.buckets||{};
  body.append(
    cadenceSection('Incidentes bloqueantes',b.blocked_incidents||[],'Fecha de incidente, no nuevo deadline.'),
    cadenceSection('Vencimientos reales',b.overdue_deadlines||[],'Solo elementos que la fuente operativa ya declaró vencidos.'),
    cadenceSection('Para hoy',b.today_deadlines||[],'Solo deadlines que la fuente operativa ya clasificó para hoy.'),
    cadenceSection('Leads recibidos',b.received_leads||[],'received_at sirve para medir antigüedad observacional; nunca se convierte en vencimiento.'),
    cadenceSection('Pendiente de agenda',b.unscheduled||[],'Requiere programación humana; no se inventa una fecha.'),
    cadenceSection('Acciones sin fecha',b.undated||[],'Trabajo válido sin semántica temporal suficiente para construir un deadline.'),
    cadenceSection('Otras fechas observadas',b.other_observed||[],'Hay una marca temporal, pero no autoridad semántica para llamarla deadline.'),
    cadenceAnomalySection(p.temporal_anomalies||[])
  );
}

window.addEventListener('keydown',e=>{if(e.key==='Escape'&&postW99CadenceState.open)cadenceClose()});
const postW99CadenceBaseRender=globalThis.renderMarketingOps;
globalThis.renderMarketingOps=function(){postW99CadenceBaseRender();cadenceEnsureTrigger()};
window.addEventListener('marketing-ops-refreshed',()=>{cadenceEnsureTrigger();if(postW99CadenceState.open)cadenceLoad()});
cadenceEnsureTrigger();
