const wave60State={companyId:null,data:null,loading:false};

function wave60Company(){return typeof wave47Company==='function'?wave47Company():(typeof opsSelectedCompany==='function'?opsSelectedCompany():null)}
function wave60Styles(){
  if(document.querySelector('#wave60-workdesk-style'))return;
  const style=document.createElement('style');style.id='wave60-workdesk-style';style.textContent=`
  .w60-shell{display:grid;gap:12px;margin-top:12px}.w60-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-end}.w60-actions{display:flex;gap:7px;flex-wrap:wrap}.w60-grid{display:grid;grid-template-columns:minmax(0,1.4fr) repeat(3,minmax(150px,.7fr));gap:9px}.w60-next,.w60-status,.w60-section,.w60-focus-strip{border:1px solid #dedad1;border-radius:13px;background:#fff}.w60-next{padding:15px;display:grid;gap:8px}.w60-next strong{font-size:18px;line-height:1.15}.w60-next p{margin:0}.w60-status{padding:12px;display:grid;gap:5px}.w60-status strong{font-size:21px}.w60-status span{font-size:8px;color:#716d65;line-height:1.35}.w60-status button{margin-top:4px}.w60-section{padding:13px;display:grid;gap:9px}.w60-queue{display:grid;gap:6px}.w60-row{display:grid;grid-template-columns:84px minmax(0,1fr) auto;gap:10px;align-items:center;padding:10px;border:1px solid #e7e3db;border-radius:10px;background:#fbfaf7}.w60-row.urgent{border-left:4px solid #171717}.w60-kind{font-size:8px;text-transform:uppercase;letter-spacing:.07em;color:#716d65}.w60-row strong{font-size:10px}.w60-row p{margin:2px 0 0;font-size:9px;color:#716d65;line-height:1.4}.w60-empty{padding:12px;border:1px dashed #d5d0c7;border-radius:10px;color:#716d65;font-size:9px}.w60-focus-strip{padding:11px 12px;margin-bottom:12px;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;align-items:center}.w60-focus-copy{display:flex;gap:12px;align-items:center;flex-wrap:wrap}.w60-focus-copy strong{font-size:11px}.w60-chips{display:flex;gap:5px;flex-wrap:wrap}.w60-chip{padding:4px 7px;border-radius:999px;background:#efede7;font-size:8px}.w60-chip.hot{background:#171717;color:#fff}.w60-inbox-cache{display:grid;gap:6px}.w60-cache-line{display:flex;justify-content:space-between;gap:8px;padding:7px 0;border-bottom:1px solid #eeeae2;font-size:9px}.w60-cache-line:last-child{border-bottom:0}.w60-note{font-size:8px;color:#716d65;line-height:1.45}.w60-loading{padding:13px;border:1px dashed #d5d0c7;border-radius:11px;color:#716d65;font-size:9px}
  @media(max-width:1050px){.w60-grid{grid-template-columns:1fr 1fr}.w60-next{grid-column:1/-1}}@media(max-width:720px){.w60-grid{grid-template-columns:1fr}.w60-next{grid-column:auto}.w60-row{grid-template-columns:1fr}.w60-focus-strip{grid-template-columns:1fr}.w60-head{align-items:flex-start;flex-direction:column}}
  `;document.head.append(style)
}
function wave60Date(value){return value?opsDate(value):'Sin fecha'}
function wave60Kind(kind){return ({publication_failed:'Publicación',publication_overdue:'Publicación',publication_today:'Publicación hoy',crm_overdue:'CRM vencido',crm_today:'CRM hoy',crm_unscheduled:'CRM sin fecha'})[kind]||kind||'Tarea'}
function wave60OpenCrmTab(tab='followups'){
  try{crmState.tab=tab}catch(_err){}
  opsShowView('crm');
}
function wave60OpenItem(item){
  if(!item?.view)return;
  if(item.view==='crm'){
    try{crmState.tab=item.tab||'followups';if(item.contact_id)crmState.selectedContactId=item.contact_id}catch(_err){}
  }
  opsShowView(item.view)
}
async function wave60Load(force=false){
  const company=wave60Company();if(!company){wave60State.companyId=null;wave60State.data=null;return null}
  if(wave60State.loading)return wave60State.data;
  if(!force&&wave60State.companyId===company.id&&wave60State.data)return wave60State.data;
  wave60State.loading=true;
  try{wave60State.data=await opsApi(`/api/companies/${encodeURIComponent(company.id)}/workdesk`);wave60State.companyId=company.id;return wave60State.data}
  catch(err){wave60State.data=null;opsToast(err.message);return null}
  finally{wave60State.loading=false}
}
function wave60EnsureData(){
  const company=wave60Company();if(!company)return;
  if(wave60State.companyId===company.id&&wave60State.data)return;
  if(wave60State.loading)return;
  wave60Load(true).then(()=>{if(['home','crm'].includes(marketingOpsState?.view))renderMarketingOps()})
}
function wave60InboxCache(){
  const company=wave60Company();if(!company||typeof inboxState==='undefined')return null;
  if(inboxState.companyKey!==company.id||!inboxState.data)return null;
  const data=inboxState.data,summary=data.summary||{};let messages=0,matched=0;
  for(const conversation of data.conversations||[]){for(const message of conversation.messages||[]){messages+=1;if(message.crm_contact?.id)matched+=1}}
  const comments=(data.comments||[]).length;for(const comment of data.comments||[]){if(comment.crm_contact?.id)matched+=1}
  return {configured:Boolean(data.configured),conversations:Number(summary.conversations||0),comments:Number(summary.comments||comments),crmMatches:Number(summary.crm_matches||0),interactions:messages+comments,matchedInteractions:matched,unmatchedInteractions:Math.max(0,messages+comments-matched)}
}
function wave60ExplicitInboxRefresh(){
  opsShowView('inbox');
  setTimeout(()=>{if(typeof inboxRefresh==='function')inboxRefresh()},0)
}
function wave60StatusCard(title,value,copy,buttonLabel,action){
  const card=opsEl('div','w60-status');card.append(opsEl('span','',title),opsEl('strong','',String(value)),opsEl('span','',copy));if(buttonLabel&&action){const b=opsEl('button','','');b.type='button';b.textContent=buttonLabel;b.addEventListener('click',action);card.append(b)}return card
}
function wave60Queue(root,data,limit=8){
  const section=opsEl('section','w60-section'),head=opsEl('div','w60-head'),copy=opsEl('div','');copy.append(opsEl('p','eyebrow','COLA OPERATIVA'),opsEl('h3','','Qué hacer a continuación'),opsEl('p','muted','Una sola cola cruza publicaciones y seguimientos CRM locales, ordenada por urgencia.'));const openCrm=opsEl('button','','Ver todos los seguimientos');openCrm.type='button';openCrm.addEventListener('click',()=>wave60OpenCrmTab('followups'));head.append(copy,openCrm);section.append(head);const list=opsEl('div','w60-queue');const rows=(data.queue||[]).slice(0,limit);for(const item of rows){const row=opsEl('div',`w60-row ${Number(item.priority)<=2?'urgent':''}`),body=opsEl('div','');row.append(opsEl('span','w60-kind',wave60Kind(item.kind)));body.append(opsEl('strong','',item.title),opsEl('p','',item.detail));if(item.due_at)body.append(opsEl('p','',wave60Date(item.due_at)));const action=opsEl('button',Number(item.priority)<=2?'primary':'','Abrir');action.type='button';action.addEventListener('click',()=>wave60OpenItem(item));row.append(body,action);list.append(row)}if(!rows.length)list.append(opsEl('div','w60-empty','No hay publicaciones fallidas/vencidas ni seguimientos pendientes para priorizar.'));section.append(list);root.append(section)
}
function wave60Home(){
  if(marketingOpsState?.view!=='home')return;wave60Styles();const root=document.querySelector('#marketing-ops-view');if(!root||root.querySelector('#wave60-workdesk'))return;const company=wave60Company();if(!company)return;wave60EnsureData();const data=wave60State.companyId===company.id?wave60State.data:null;const shell=opsEl('div','w60-shell');shell.id='wave60-workdesk';
  if(!data){shell.append(opsEl('div','w60-loading','Preparando mesa de trabajo local…'));const anchor=root.querySelector('.w59-journey');if(anchor)anchor.insertAdjacentElement('afterend',shell);else root.prepend(shell);return}
  const head=opsEl('div','w60-head'),copy=opsEl('div','');copy.append(opsEl('p','eyebrow','MESA DE TRABAJO · W60'),opsEl('h3','',`Atención diaria · ${company.name}`),opsEl('p','muted','Prioriza conversaciones, seguimientos y publicaciones desde el estado local. Inbox solo consulta Meta cuando tú lo ordenas.'));const actions=opsEl('div','w60-actions'),refresh=opsEl('button','','Actualizar estado local');refresh.type='button';refresh.addEventListener('click',async()=>{await wave60Load(true);renderMarketingOps()});actions.append(refresh);head.append(copy,actions);shell.append(head);
  const cache=wave60InboxCache(),grid=opsEl('div','w60-grid'),next=opsEl('div','w60-next');next.append(opsEl('span','w60-kind','SIGUIENTE ACCIÓN'));if(data.next_action){next.append(opsEl('strong','',data.next_action.title),opsEl('p','muted',data.next_action.detail));const b=opsEl('button','primary','Resolver ahora');b.type='button';b.addEventListener('click',()=>wave60OpenItem(data.next_action));next.append(b)}else{next.append(opsEl('strong','','Operación al día'),opsEl('p','muted','No hay elementos críticos en la cola local. Puedes revisar Inbox o avanzar campañas y creativos.'))}grid.append(next);
  grid.append(wave60StatusCard('INBOX',cache?cache.interactions:'—',cache?`${cache.unmatchedInteractions} interacciones sin vínculo CRM · caché de la última consulta`:'Aún no consultado en esta sesión','Actualizar Inbox',wave60ExplicitInboxRefresh),wave60StatusCard('CRM',data.crm?.overdue||0,`${data.crm?.today||0} hoy · ${data.crm?.unscheduled||0} sin fecha`,'Abrir seguimientos',()=>wave60OpenCrmTab('followups')),wave60StatusCard('PUBLICACIONES',(data.publications?.failed||0)+(data.publications?.overdue||0),`${data.publications?.today||0} previstas hoy`,'Abrir calendario',()=>opsShowView('calendar')));shell.append(grid);wave60Queue(shell,data,7);
  const anchor=root.querySelector('.w59-journey');if(anchor)anchor.insertAdjacentElement('afterend',shell);else root.prepend(shell)
}
function wave60InboxStrip(){
  if(marketingOpsState?.view!=='inbox')return;wave60Styles();const root=document.querySelector('#marketing-ops-view');if(!root||root.querySelector('#wave60-inbox-focus'))return;const cache=wave60InboxCache(),strip=opsEl('section','w60-focus-strip');strip.id='wave60-inbox-focus';const copy=opsEl('div','w60-focus-copy');copy.append(opsEl('strong','',cache?'Triage de la última consulta':'Inbox pendiente de consulta'));const chips=opsEl('div','w60-chips');if(cache){chips.append(opsEl('span','w60-chip',`${cache.interactions} interacciones`),opsEl('span','w60-chip',`${cache.crmMatches} contactos CRM`),opsEl('span',cache.unmatchedInteractions?'w60-chip hot':'w60-chip',`${cache.unmatchedInteractions} sin vínculo CRM`))}else chips.append(opsEl('span','w60-chip','Sin caché Meta en esta sesión'));copy.append(chips);const actions=opsEl('div','w60-actions'),crm=opsEl('button','','Seguimientos CRM');crm.type='button';crm.addEventListener('click',()=>wave60OpenCrmTab('followups'));actions.append(crm);if(!cache){const refresh=opsEl('button','primary','Actualizar Inbox');refresh.type='button';refresh.addEventListener('click',()=>{if(typeof inboxRefresh==='function')inboxRefresh()});actions.append(refresh)}strip.append(copy,actions);const first=root.firstElementChild;if(first)first.insertAdjacentElement('afterend',strip);else root.append(strip)
}
function wave60CrmStrip(){
  if(marketingOpsState?.view!=='crm')return;wave60Styles();const root=document.querySelector('#marketing-ops-view');if(!root||root.querySelector('#wave60-crm-focus'))return;const company=wave60Company();if(!company)return;wave60EnsureData();const data=wave60State.companyId===company.id?wave60State.data:null;if(!data)return;const strip=opsEl('section','w60-focus-strip');strip.id='wave60-crm-focus';const copy=opsEl('div','w60-focus-copy');copy.append(opsEl('strong','','Foco comercial'));const chips=opsEl('div','w60-chips');chips.append(opsEl('span',data.crm.overdue?'w60-chip hot':'w60-chip',`${data.crm.overdue} vencidos`),opsEl('span','w60-chip',`${data.crm.today} hoy`),opsEl('span','w60-chip',`${data.crm.unscheduled} sin fecha`),opsEl('span','w60-chip',`${data.crm.open_opportunities} oportunidades abiertas`));copy.append(chips);const actions=opsEl('div','w60-actions'),follow=opsEl('button',crmState?.tab==='followups'?'primary':'','Seguimientos'),pipeline=opsEl('button',crmState?.tab==='pipeline'?'primary':'','Pipeline');follow.type=pipeline.type='button';follow.addEventListener('click',()=>{crmState.tab='followups';crmRenderCurrent()});pipeline.addEventListener('click',()=>{crmState.tab='pipeline';crmRenderCurrent()});actions.append(follow,pipeline);strip.append(copy,actions);root.prepend(strip)
}
function wave60Enhance(){wave60Styles();wave60Home();wave60InboxStrip();wave60CrmStrip()}
function wave60QueueEnhance(){queueMicrotask(wave60Enhance)}

const wave60BaseRenderMarketingOps=globalThis.renderMarketingOps;
if(typeof wave60BaseRenderMarketingOps==='function')globalThis.renderMarketingOps=function(){const result=wave60BaseRenderMarketingOps();wave60QueueEnhance();return result};
window.addEventListener('marketing-company-change',()=>{wave60State.companyId=null;wave60State.data=null;wave60QueueEnhance()});
wave60Enhance();
