const dailyActionState={busy:new Set()};

function dailyActionEnsureStyles(){
  if(document.querySelector('#daily-actions-wave44-style'))return;
  const style=document.createElement('style');style.id='daily-actions-wave44-style';style.textContent=`
  .daily-action-buttons{display:flex;gap:6px;justify-content:flex-end;flex-wrap:wrap}.daily-action-buttons button{min-height:32px}.daily-action-note{margin-top:9px;padding:9px 11px;border-radius:10px;background:#f4f2ed;color:#706c65;font-size:9px}.daily-focus-item.busy{opacity:.65;pointer-events:none}@media(max-width:700px){.daily-action-buttons{justify-content:flex-start}}
  `;document.head.append(style)
}

function dailyActionItems(){
  const items=[];
  for(const row of marketingOpsState.calendar||[]){
    const common={entity:'publication',entityId:row.id,companyId:row.company_id,companyName:row.company_name||dailyCompanyName(row.company_id),date:row.scheduled_for||row.updated_at,view:'calendar'};
    if(row.status==='FAILED')items.push({...common,priority:0,type:'Publicación',title:`Error · ${common.companyName}`,detail:row.message||row.error||'Publicación con error'});
    else if(row.status==='QUEUED'&&dailyBeforeNow(row.scheduled_for))items.push({...common,priority:1,type:'Publicación',title:`Programación vencida · ${common.companyName}`,detail:row.message||'Revisar programación'});
    else if(row.status==='QUEUED'&&dailyToday(row.scheduled_for))items.push({...common,priority:3,type:'Publicación hoy',title:common.companyName,detail:row.message||'Publicación programada'});
  }
  const next=marketingOpsState.dashboard?.crm?.next_activities||[];
  for(const row of next){
    if(!row.due_at||row.completed_at)continue;
    const overdue=dailyBeforeNow(row.due_at);
    if(overdue||dailyToday(row.due_at))items.push({priority:overdue?2:4,type:overdue?'CRM vencido':'CRM hoy',title:dailyCompanyName(row.company_id),detail:row.summary||'Seguimiento pendiente',date:row.due_at,view:'crm',entity:'crm_activity',entityId:row.id,companyId:row.company_id});
  }
  return items.sort((a,b)=>a.priority-b.priority||String(a.date||'').localeCompare(String(b.date||''))).slice(0,12)
}

function dailyActionOpenPublication(item){
  const row=(marketingOpsState.calendar||[]).find(value=>value.id===item.entityId&&value.company_id===item.companyId);
  if(!row){opsToast('La publicación cambió. Actualiza prioridades.');return}
  if(typeof editorialState==='undefined'){opsToast('Gestión editorial todavía no está disponible.');return}
  editorialState.selectedId=row.id;
  opsShowView('calendar')
}

function dailyActionOpenCrm(){
  if(typeof crmState!=='undefined')crmState.tab='followups';
  opsShowView('crm')
}

async function dailyActionCompleteActivity(item,rowNode){
  if(item.entity!=='crm_activity'||dailyActionState.busy.has(item.entityId))return;
  if(!window.confirm(`Marcar como completado este seguimiento de ${item.title}?`))return;
  dailyActionState.busy.add(item.entityId);rowNode?.classList.add('busy');
  try{
    await opsApi(`/api/companies/${encodeURIComponent(item.companyId)}/activities/${encodeURIComponent(item.entityId)}/complete`,{method:'POST'});
    if(typeof crmState!=='undefined')crmState.loaded=false;
    await refreshMarketingOps(true);
    opsToast('Seguimiento completado');
    if(marketingOpsState.view==='home')renderMarketingOps()
  }catch(err){opsToast(err.message)}finally{dailyActionState.busy.delete(item.entityId);rowNode?.classList.remove('busy')}
}

function dailyActionButtons(item,rowNode){
  const actions=opsEl('div','daily-action-buttons');
  if(item.entity==='crm_activity'){
    const open=opsEl('button','','Abrir');open.type='button';open.addEventListener('click',()=>dailyActionOpenCrm());
    const complete=opsEl('button','primary','Completar');complete.type='button';complete.addEventListener('click',()=>dailyActionCompleteActivity(item,rowNode));
    actions.append(open,complete);return actions
  }
  const manage=opsEl('button','','Gestionar');manage.type='button';manage.addEventListener('click',()=>dailyActionOpenPublication(item));actions.append(manage);return actions
}

dailyFocus=function(root){
  dailyActionEnsureStyles();const data=marketingOpsState.dashboard||{},summary=data.summary||{},crm=data.crm||{},items=dailyActionItems();const section=opsEl('section','marketing-ops-section daily-focus');const head=opsEl('div','daily-focus-head');const copy=opsEl('div','');copy.append(opsEl('p','eyebrow','HOY · PRIORIDADES'),opsEl('h3','','Qué necesita tu atención'),opsEl('p','muted','Resuelve seguimientos locales o abre la publicación exacta. Ninguna acción publica, reintenta ni responde automáticamente.'));const badges=opsEl('div','daily-summary');badges.append(opsEl('span','',`${summary.failed||0} publicaciones con error`),opsEl('span','',`${data.overdue||0} programaciones vencidas`),opsEl('span','',`${crm.overdue_activities||0} seguimientos CRM vencidos`));head.append(copy,badges);section.append(head);const list=opsEl('div','daily-focus-list');
  if(!items.length)list.append(opsEl('div','daily-focus-zero','No hay tareas críticas ni vencidas para este filtro. Puedes revisar el Calendario o continuar con tus próximos seguimientos.'));
  for(const item of items){const row=opsEl('div',`daily-focus-item ${item.priority<=2?'high':''}`);row.dataset.entity=item.entity;row.dataset.entityId=item.entityId;row.append(opsEl('span','daily-type',item.type));const body=opsEl('div','');body.append(opsEl('strong','',item.title),opsEl('p','',item.detail),opsEl('p','',opsDate(item.date)));row.append(body,dailyActionButtons(item,row));list.append(row)}section.append(list);section.append(opsEl('div','daily-action-note','Completar modifica únicamente el CRM local tras confirmación. Gestionar abre la publicación seleccionada en el calendario editorial; cualquier cambio posterior sigue usando sus confirmaciones y reglas existentes.'));root.append(section)
};

dailyActionEnsureStyles();if(marketingOpsState.view==='home')renderMarketingOps();
