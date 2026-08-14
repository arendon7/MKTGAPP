const analyticsState={companyKey:undefined,local:null,remote:null,loading:false,remoteLoading:false};

function analyticsEnsureStyles(){
  if(document.querySelector('#analytics-wave38-style'))return;
  const style=document.createElement('style');style.id='analytics-wave38-style';style.textContent=`
  .analytics-grid{display:grid;grid-template-columns:repeat(4,minmax(130px,1fr));gap:10px}.analytics-split{display:grid;grid-template-columns:minmax(320px,1fr) minmax(380px,1.35fr);gap:12px}.analytics-channel-grid{display:grid;grid-template-columns:repeat(2,minmax(180px,1fr));gap:8px}.analytics-channel{border:1px solid #dedbd2;border-radius:11px;background:#fff;padding:11px;display:grid;gap:5px}.analytics-channel strong{font-size:12px}.analytics-channel span{font-size:10px;color:#706c64}.analytics-list{display:grid;gap:7px}.analytics-row{border:1px solid #e1ddd4;border-radius:10px;padding:9px 10px;background:#fff;display:grid;grid-template-columns:minmax(0,1.5fr) minmax(110px,.55fr) minmax(100px,.45fr);gap:10px;align-items:center}.analytics-row p{margin:2px 0 0;font-size:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.analytics-row small{color:#77736b}.analytics-metrics{display:flex;gap:6px;flex-wrap:wrap}.analytics-chip{font-size:9px;padding:3px 7px;border-radius:999px;background:#efede7}.analytics-top{display:grid;gap:7px}.analytics-top-card{border:1px solid #dedbd2;border-radius:10px;padding:10px;background:#fff;display:grid;gap:5px}.analytics-top-card-head{display:flex;align-items:flex-start;justify-content:space-between;gap:8px}.analytics-note{padding:10px;border:1px solid #dedbd2;background:#f7f4ed;border-radius:10px;font-size:10px;line-height:1.45}.analytics-error{padding:8px;border:1px solid #d8c9c9;background:#fbf4f4;border-radius:8px;font-size:9px}.analytics-actions{display:flex;gap:8px;flex-wrap:wrap;align-items:center}.analytics-company-table{display:grid;gap:6px}.analytics-company-row{display:grid;grid-template-columns:minmax(140px,1fr) repeat(3,minmax(70px,.4fr));gap:8px;padding:8px 0;border-bottom:1px solid #eeeae1;font-size:10px}.analytics-company-row.header{font-weight:700;color:#6c685f}.analytics-company-row:last-child{border-bottom:0}
  @media(max-width:1050px){.analytics-grid{grid-template-columns:repeat(2,1fr)}.analytics-split{grid-template-columns:1fr}}@media(max-width:700px){.analytics-grid,.analytics-channel-grid{grid-template-columns:1fr}.analytics-row{grid-template-columns:1fr}.analytics-company-row{grid-template-columns:1fr 1fr}.analytics-company-row.header{display:none}}
  `;document.head.append(style)
}

function analyticsEnsureNav(){
  const nav=document.querySelector('.marketing-ops-nav');if(!nav||nav.querySelector('[data-ops-view="analytics"]'))return;
  const button=opsEl('button','','Analítica');button.type='button';button.dataset.opsView='analytics';button.innerHTML='Analítica <small>W38</small>';button.addEventListener('click',()=>opsShowView('analytics'));
  const calendar=nav.querySelector('[data-ops-view="calendar"]');if(calendar?.nextSibling)nav.insertBefore(button,calendar.nextSibling);else nav.append(button)
}

function analyticsCompanyId(){return marketingOpsState.selectedCompanyId||null}
function analyticsCompanyKey(){return analyticsCompanyId()||'__all__'}
function analyticsNumber(value){const number=Number(value||0);return Number.isFinite(number)?new Intl.NumberFormat('es-CO',{maximumFractionDigits:1}).format(number):'0'}
function analyticsChannelLabel(value){return value==='instagram'?'Instagram':value==='facebook_page'?'Facebook':value}
function analyticsKindLabel(value){return ({text:'Texto',link:'Enlace',image:'Imagen',reel:'Reel',video:'Video'})[value]||value}
function analyticsTrim(text,limit=110){const value=String(text||'').trim();return value.length>limit?`${value.slice(0,limit-1)}…`:value||'(sin copy)'}

async function analyticsLoadLocal(force=false){
  const key=analyticsCompanyKey();
  if(analyticsState.loading)return;
  if(!force&&analyticsState.local&&analyticsState.companyKey===key)return;
  analyticsState.loading=true;
  analyticsState.companyKey=key;
  analyticsState.remote=null;
  try{
    const companyId=analyticsCompanyId();
    analyticsState.local=await opsApi(`/api/analytics/social${companyId?`?company_id=${encodeURIComponent(companyId)}`:''}`)
  }catch(err){analyticsState.local=null;opsToast(err.message)}finally{analyticsState.loading=false}
}

async function analyticsRefreshMeta(){
  const companyId=analyticsCompanyId();if(!companyId){opsToast('Selecciona una empresa para consultar Meta');return}
  if(analyticsState.remoteLoading)return;
  analyticsState.remoteLoading=true;analyticsRenderCurrent();
  try{
    analyticsState.remote=await opsApi(`/api/analytics/social/meta?company_id=${encodeURIComponent(companyId)}&limit=12`);
    opsToast(analyticsState.remote.configured?'Analítica Meta actualizada':'Meta no está conectado')
  }catch(err){analyticsState.remote=null;opsToast(err.message)}finally{analyticsState.remoteLoading=false;analyticsRenderCurrent()}
}

function analyticsMetricCard(title,value,copy){return opsMetric(title,analyticsNumber(value),copy)}

function analyticsLocalSummary(root,data){
  const summary=data.summary||{},grid=opsEl('div','analytics-grid');
  grid.append(
    analyticsMetricCard('PUBLICACIONES',summary.total||0,'histórico del filtro'),
    analyticsMetricCard('PROGRAMADAS',summary.queued||0,'pendientes en la cola'),
    analyticsMetricCard('PUBLICADAS',summary.published||0,`${summary.published_with_remote_id||0} con ID remoto`),
    analyticsMetricCard('REQUIEREN ATENCIÓN',summary.failed||0,'fallidas para revisar')
  );root.append(grid);
  const channels=opsEl('div','analytics-channel-grid');
  const facebook=opsEl('article','analytics-channel');facebook.append(opsEl('strong','','Facebook'),opsEl('span','',`${data.channels?.facebook_page||0} publicaciones registradas`));
  const instagram=opsEl('article','analytics-channel');instagram.append(opsEl('strong','','Instagram'),opsEl('span','',`${data.channels?.instagram||0} publicaciones registradas`));
  channels.append(facebook,instagram);root.append(channels)
}

function analyticsCompanies(root,data){
  if(analyticsCompanyId()||!(data.by_company||[]).length)return;
  const section=opsEl('section','marketing-ops-section'),head=opsEl('div','marketing-ops-section-head'),copy=opsEl('div','');copy.append(opsEl('p','eyebrow','MULTIEMPRESA'),opsEl('h3','','Vista comparativa'));head.append(copy);section.append(head);
  const table=opsEl('div','analytics-company-table');const header=opsEl('div','analytics-company-row header');['Empresa','Total','Publicadas','Errores'].forEach(label=>header.append(opsEl('span','',label)));table.append(header);
  for(const row of data.by_company||[]){const line=opsEl('div','analytics-company-row');line.append(opsEl('strong','',row.company_name),opsEl('span','',row.total||0),opsEl('span','',row.statuses?.PUBLISHED||0),opsEl('span','',row.statuses?.FAILED||0));table.append(line)}section.append(table);root.append(section)
}

function analyticsRecent(root,data){
  const section=opsEl('section','marketing-ops-section'),head=opsEl('div','marketing-ops-section-head'),copy=opsEl('div','');copy.append(opsEl('p','eyebrow','ACTIVIDAD SOCIAL'),opsEl('h3','','Publicaciones recientes'));head.append(copy);section.append(head);const list=opsEl('div','analytics-list');
  for(const row of (data.recent||[]).slice(0,12)){const item=opsEl('article','analytics-row'),left=opsEl('div','');left.append(opsEl('strong','',row.company_name||'Empresa'),opsEl('p','',analyticsTrim(row.message)));const middle=opsEl('div','');middle.append(opsEl('span','analytics-chip',`${analyticsChannelLabel(row.channel)} · ${analyticsKindLabel(row.kind)}`),opsEl('p','',opsDate(row.updated_at)));const right=opsEl('span','status',opsStatusLabel(row.status));item.append(left,middle,right);list.append(item)}
  if(!(data.recent||[]).length)list.append(opsEmpty('Aún no hay publicaciones en este filtro.'));section.append(list);root.append(section)
}

function analyticsRemote(root,local){
  const section=opsEl('section','marketing-ops-section'),head=opsEl('div','marketing-ops-section-head'),copy=opsEl('div','');copy.append(opsEl('p','eyebrow','META · READ ONLY'),opsEl('h3','','Rendimiento remoto'),opsEl('p','muted','La consulta a Meta sólo ocurre cuando pulsas Actualizar. No publica, no modifica campañas y no activa pauta.'));head.append(copy);
  const actions=opsEl('div','analytics-actions'),refresh=opsEl('button','primary',analyticsState.remoteLoading?'Consultando Meta…':'Actualizar desde Meta');refresh.type='button';refresh.disabled=analyticsState.remoteLoading||!analyticsCompanyId();refresh.addEventListener('click',analyticsRefreshMeta);actions.append(refresh);head.append(actions);section.append(head);
  if(!analyticsCompanyId()){section.append(opsEl('div','analytics-note','Selecciona una empresa arriba para consultar sus publicaciones remotas. La vista “Todas las empresas” permanece completamente local.'));root.append(section);return}
  if(!local.meta?.configured){section.append(opsEl('div','analytics-note','Meta no está conectado. Puedes seguir usando el histórico local; conecta la cuenta desde Empresas cuando quieras consultar rendimiento remoto.'));root.append(section);return}
  const remote=analyticsState.remote;if(!remote){section.append(opsEl('div','analytics-note','Pulsa “Actualizar desde Meta” para leer las publicaciones remotas recientes. No hacemos polling automático para evitar llamadas innecesarias y mantener el control explícito.'));root.append(section);return}
  const coverage=remote.coverage||{},metrics=remote.totals||{},grid=opsEl('div','analytics-grid');grid.append(analyticsMetricCard('ALCANCE',metrics.reach||0,`${coverage.measured||0} piezas con métricas`),analyticsMetricCard('VISTAS',metrics.views||0,'Instagram medido'),analyticsMetricCard('INTERACCIONES',metrics.total_interactions||0,'métrica agregada disponible'),analyticsMetricCard('OBSERVADAS',coverage.observed||0,`${coverage.errors||0} errores de lectura`));section.append(grid);
  const note=opsEl('div','analytics-note',`Cobertura: ${coverage.requested||0} de ${coverage.eligible||0} publicaciones remotas elegibles revisadas. Facebook se verifica por presencia/estado con el readback actual; Wave 38 no inventa métricas orgánicas que el backend certificado todavía no lee.`);section.append(note);
  if((remote.top_content||[]).length){const top=opsEl('div','analytics-top');top.append(opsEl('h4','','Contenido con mejor señal disponible'));for(const row of remote.top_content){const card=opsEl('article','analytics-top-card'),cardHead=opsEl('div','analytics-top-card-head'),left=opsEl('div','');left.append(opsEl('strong','',analyticsTrim(row.message,90)),opsEl('small','',`${analyticsChannelLabel(row.channel)} · ${analyticsKindLabel(row.kind)}`));cardHead.append(left,opsEl('span','status',row.remote_state||'PRESENT'));card.append(cardHead);const chips=opsEl('div','analytics-metrics');for(const key of ['total_interactions','views','reach','likes','comments','shares','saved']){if(row.metrics?.[key]!==undefined)chips.append(opsEl('span','analytics-chip',`${key.replaceAll('_',' ')}: ${analyticsNumber(row.metrics[key])}`))}card.append(chips);top.append(card)}section.append(top)}
  const failed=(remote.observations||[]).filter(row=>row.provider_error);if(failed.length){const errors=opsEl('div','');failed.forEach(row=>errors.append(opsEl('div','analytics-error',`${analyticsTrim(row.message,70)} · ${row.provider_error}`)));section.append(errors)}root.append(section)
}

function analyticsRenderCurrent(){
  if(marketingOpsState.view!=='analytics')return;analyticsEnsureNav();analyticsEnsureStyles();const root=document.querySelector('#marketing-ops-view');if(!root)return;root.replaceChildren();document.querySelector('#marketing-ops-eyebrow').textContent='ANALÍTICA';document.querySelector('#marketing-ops-title').textContent='Rendimiento de redes';document.querySelector('#marketing-ops-subtitle').textContent='Qué publicaste, qué salió bien y qué requiere atención, por empresa.';document.querySelectorAll('[data-ops-view]').forEach(button=>button.classList.toggle('active',button.dataset.opsView==='analytics'));
  const key=analyticsCompanyKey();if(!analyticsState.local||analyticsState.companyKey!==key){root.append(opsEmpty('Cargando analítica local…'));analyticsLoadLocal(true).then(analyticsRenderCurrent);return}
  analyticsLocalSummary(root,analyticsState.local);analyticsCompanies(root,analyticsState.local);analyticsRemote(root,analyticsState.local);analyticsRecent(root,analyticsState.local)
}

const analyticsBaseRender=globalThis.renderMarketingOps;
globalThis.renderMarketingOps=function(){analyticsEnsureNav();if(marketingOpsState.view==='analytics'){analyticsRenderCurrent();return}analyticsBaseRender()};

const analyticsBaseHome=globalThis.renderOpsHome;
if(typeof analyticsBaseHome==='function')globalThis.renderOpsHome=function(root){analyticsBaseHome(root);const section=opsEl('section','marketing-ops-section'),head=opsEl('div','marketing-ops-section-head'),copy=opsEl('div','');copy.append(opsEl('p','eyebrow','ANALÍTICA'),opsEl('h3','','Rendimiento de redes'),opsEl('p','muted','Convierte el readback técnico de Meta en una vista operativa por empresa.'));const open=opsEl('button','','Abrir analítica');open.type='button';open.addEventListener('click',()=>opsShowView('analytics'));head.append(copy,open);section.append(head);root.append(section)};

analyticsEnsureStyles();analyticsEnsureNav();
