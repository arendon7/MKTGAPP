function dailyOpsEnsureStyles(){
  if(document.querySelector('#daily-ops-wave43-style'))return;
  const style=document.createElement('style');style.id='daily-ops-wave43-style';style.textContent=`
  .daily-focus{display:grid;gap:10px;margin-top:14px}.daily-focus-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-end}.daily-focus-list{display:grid;gap:7px}.daily-focus-item{display:grid;grid-template-columns:92px minmax(0,1fr) auto;gap:10px;align-items:center;padding:11px 12px;border:1px solid #dfdbd2;border-radius:12px;background:#fff}.daily-focus-item.high{border-left:4px solid #171717}.daily-focus-item .daily-type{font-size:9px;text-transform:uppercase;letter-spacing:.08em;color:#706c65}.daily-focus-item p{margin:2px 0 0;font-size:10px;color:#706c65}.daily-focus-item button{min-height:32px}.daily-focus-zero{padding:14px;border:1px dashed #cfcbc2;border-radius:12px;color:#706c65;background:#faf9f6}.daily-summary{display:flex;gap:6px;flex-wrap:wrap}.daily-summary span{padding:5px 8px;border-radius:999px;background:#efede7;font-size:9px}@media(max-width:700px){.daily-focus-item{grid-template-columns:1fr}.daily-focus-head{align-items:flex-start;flex-direction:column}}
  `;document.head.append(style)
}
function dailyCompanyName(id){return marketingOpsState.companies.find(row=>row.id===id)?.name||'Empresa'}
function dailyToday(value){if(!value)return false;const date=new Date(value),now=new Date();return !Number.isNaN(date.getTime())&&date.getFullYear()===now.getFullYear()&&date.getMonth()===now.getMonth()&&date.getDate()===now.getDate()}
function dailyBeforeNow(value){if(!value)return false;const date=new Date(value);return !Number.isNaN(date.getTime())&&date.getTime()<Date.now()}
function dailyItems(){
  const items=[];
  for(const row of marketingOpsState.calendar||[]){
    if(row.status==='FAILED')items.push({priority:0,type:'Publicación',title:`Error · ${dailyCompanyName(row.company_id)}`,detail:row.message||row.error||'Publicación con error',date:row.scheduled_for||row.updated_at,view:'calendar'});
    else if(row.status==='QUEUED'&&dailyBeforeNow(row.scheduled_for))items.push({priority:1,type:'Publicación',title:`Programación vencida · ${dailyCompanyName(row.company_id)}`,detail:row.message||'Revisar programación',date:row.scheduled_for,view:'calendar'});
    else if(row.status==='QUEUED'&&dailyToday(row.scheduled_for))items.push({priority:3,type:'Publicación hoy',title:dailyCompanyName(row.company_id),detail:row.message||'Publicación programada',date:row.scheduled_for,view:'calendar'});
  }
  const next=marketingOpsState.dashboard?.crm?.next_activities||[];
  for(const row of next){
    if(!row.due_at)continue;const overdue=dailyBeforeNow(row.due_at);if(overdue||dailyToday(row.due_at))items.push({priority:overdue?2:4,type:overdue?'CRM vencido':'CRM hoy',title:dailyCompanyName(row.company_id),detail:row.summary||'Seguimiento pendiente',date:row.due_at,view:'crm'});
  }
  return items.sort((a,b)=>a.priority-b.priority||String(a.date||'').localeCompare(String(b.date||''))).slice(0,12)
}
function dailyFocus(root){
  dailyOpsEnsureStyles();const data=marketingOpsState.dashboard||{},summary=data.summary||{},crm=data.crm||{},items=dailyItems();const section=opsEl('section','marketing-ops-section daily-focus');const head=opsEl('div','daily-focus-head');const copy=opsEl('div','');copy.append(opsEl('p','eyebrow','HOY · PRIORIDADES'),opsEl('h3','','Qué necesita tu atención'),opsEl('p','muted','Ordenado por urgencia con datos locales. Meta sólo se consulta cuando tú actualizas la Bandeja.'));const badges=opsEl('div','daily-summary');badges.append(opsEl('span','',`${summary.failed||0} publicaciones con error`),opsEl('span','',`${data.overdue||0} programaciones vencidas`),opsEl('span','',`${crm.overdue_activities||0} seguimientos CRM vencidos`));head.append(copy,badges);section.append(head);const list=opsEl('div','daily-focus-list');
  if(!items.length)list.append(opsEl('div','daily-focus-zero','No hay tareas críticas ni vencidas para este filtro. Puedes revisar el Calendario o continuar con tus próximos seguimientos.'));
  for(const item of items){const row=opsEl('div',`daily-focus-item ${item.priority<=2?'high':''}`);row.append(opsEl('span','daily-type',item.type));const body=opsEl('div','');body.append(opsEl('strong','',item.title),opsEl('p','',item.detail),opsEl('p','',opsDate(item.date)));const button=opsEl('button','','Revisar');button.type='button';button.addEventListener('click',()=>opsShowView(item.view));row.append(body,button);list.append(row)}section.append(list);root.append(section)
}

renderOpsHome=function(root){
  const data=marketingOpsState.dashboard||{summary:{}};const summary=data.summary||{},crm=data.crm||{};
  const grid=opsEl('div','marketing-ops-grid');grid.append(opsMetric('HOY',data.scheduled_today||0,'publicaciones programadas'),opsMetric('SEGUIMIENTOS',crm.pending_activities||0,'pendientes en CRM'),opsMetric('BORRADORES',summary.draft||0,'pendientes de revisar'),opsMetric('REQUIEREN ATENCIÓN',(summary.failed||0)+(data.overdue||0)+(crm.overdue_activities||0),'errores o vencidos'));root.append(grid);
  const actions=opsEl('div','marketing-ops-actions');[['+ Programar publicación','publish'],['Ver calendario','calendar'],['Abrir CRM','crm'],['Bandeja','inbox']].forEach(([label,view])=>{const button=opsEl('button',view==='publish'?'primary':'',label);button.type='button';button.addEventListener('click',()=>opsShowView(view));actions.append(button)});root.append(actions);
  dailyFocus(root);
  const section=opsEl('section','marketing-ops-section');const head=opsEl('div','marketing-ops-section-head');const copy=opsEl('div','');copy.append(opsEl('p','eyebrow','DESPUÉS'),opsEl('h3','','Próximas publicaciones'));head.append(copy,opsEl('span','marketing-ops-badge',`${(data.upcoming||[]).length} visibles`));section.append(head);const list=opsEl('div','marketing-ops-list');for(const row of data.upcoming||[]){const item=opsEl('div','marketing-ops-row');const left=opsEl('div','');left.append(opsEl('strong','',row.company_name||'Empresa'),opsEl('p','',row.message||'(sin copy)'));const middle=opsEl('div','');middle.append(opsEl('span','status',opsStatusLabel(row.status)),opsEl('p','',opsDate(row.scheduled_for)));const right=opsEl('span','marketing-ops-badge',row.channel==='instagram'?'Instagram':'Facebook');item.append(left,middle,right);list.append(item)}if(!(data.upcoming||[]).length)list.append(opsEmpty(marketingOpsState.companies.length?'No hay publicaciones futuras programadas.':'Crea tu primera empresa para empezar.'));section.append(list);root.append(section)
};

dailyOpsEnsureStyles();if(marketingOpsState.view==='home')renderMarketingOps();