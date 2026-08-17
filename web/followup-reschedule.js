const followupRescheduleState={busy:new Set()};

function followupRescheduleStyles(){
  if(document.querySelector('#followup-reschedule-wave45-style'))return;
  const style=document.createElement('style');style.id='followup-reschedule-wave45-style';style.textContent=`
  .followup-reschedule-inline{grid-column:2/-1;display:flex;align-items:end;gap:8px;flex-wrap:wrap;margin-top:8px;padding:10px;border:1px solid #d9d5cc;border-radius:10px;background:#faf9f6}.followup-reschedule-inline label{display:grid;gap:4px;font-size:9px;color:#706c65}.followup-reschedule-inline input{min-height:34px}.followup-reschedule-inline .hint{width:100%;font-size:9px;color:#706c65}@media(max-width:700px){.followup-reschedule-inline{grid-column:1}}
  `;document.head.append(style)
}

function followupLocalValue(date){
  const pad=value=>String(value).padStart(2,'0');
  return`${date.getFullYear()}-${pad(date.getMonth()+1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function followupDefaultValue(){
  const date=new Date();date.setDate(date.getDate()+1);date.setHours(9,0,0,0);return followupLocalValue(date)
}

function followupCloseEditor(rowNode){rowNode?.querySelector('.followup-reschedule-inline')?.remove()}

async function followupRescheduleSave(item,rowNode,input,save){
  if(followupRescheduleState.busy.has(item.entityId))return;
  const date=new Date(input.value);
  if(!input.value||Number.isNaN(date.getTime())){opsToast('Selecciona una fecha válida');return}
  if(date.getTime()<=Date.now()){opsToast('La nueva fecha debe quedar en el futuro');return}
  followupRescheduleState.busy.add(item.entityId);rowNode?.classList.add('busy');save.disabled=true;
  try{
    await opsApi(`/api/companies/${encodeURIComponent(item.companyId)}/activities/${encodeURIComponent(item.entityId)}/reschedule`,{method:'POST',body:{due_at:date.toISOString()}});
    if(typeof crmState!=='undefined')crmState.loaded=false;
    opsToast('Seguimiento reprogramado');
    await refreshMarketingOps(true);
    if(marketingOpsState.view==='home')renderMarketingOps()
  }catch(err){opsToast(err.message)}finally{followupRescheduleState.busy.delete(item.entityId);rowNode?.classList.remove('busy');save.disabled=false}
}

function followupRescheduleOpen(item,rowNode){
  if(item.entity!=='crm_activity'||!rowNode)return;
  const existing=rowNode.querySelector('.followup-reschedule-inline');if(existing){existing.remove();return}
  document.querySelectorAll('.followup-reschedule-inline').forEach(node=>node.remove());
  const editor=opsEl('div','followup-reschedule-inline');
  const label=opsEl('label','','Nueva fecha y hora');const input=document.createElement('input');input.type='datetime-local';input.value=followupDefaultValue();input.min=followupLocalValue(new Date(Date.now()+60000));label.append(input);
  const save=opsEl('button','primary','Guardar fecha');save.type='button';save.addEventListener('click',()=>followupRescheduleSave(item,rowNode,input,save));
  const cancel=opsEl('button','','Cancelar');cancel.type='button';cancel.addEventListener('click',()=>followupCloseEditor(rowNode));
  editor.append(label,save,cancel,opsEl('span','hint','Solo cambia la fecha del seguimiento local. No envía mensajes, correos ni respuestas.'));
  rowNode.append(editor);input.focus()
}

const wave44DailyActionButtons=dailyActionButtons;
dailyActionButtons=function(item,rowNode){
  const actions=wave44DailyActionButtons(item,rowNode);
  if(item.entity==='crm_activity'){
    const reschedule=opsEl('button','','Reprogramar');reschedule.type='button';reschedule.addEventListener('click',()=>followupRescheduleOpen(item,rowNode));
    const complete=[...actions.querySelectorAll('button')].find(button=>button.textContent==='Completar');
    if(complete)actions.insertBefore(reschedule,complete);else actions.append(reschedule)
  }
  return actions
};

followupRescheduleStyles();if(marketingOpsState.view==='home')renderMarketingOps();
