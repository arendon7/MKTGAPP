const POST_W99_ACTIVITY_RESCHEDULE_SCHEMA='binario.marketing.activity-reschedule-control.v1';
const postW99ActivityRescheduleState={openId:null,busy:false,lastMutation:null};

function activityRescheduleText(value){return value===null||value===undefined?'':String(value).trim()}
function activityRescheduleCompany(){return typeof opsSelectedCompany==='function'?opsSelectedCompany():null}
function activityRescheduleRows(){
  if(typeof crmState==='undefined')return [];
  return [...(crmState.activities||[])].sort((a,b)=>typeof crmActivityKey==='function'?crmActivityKey(a).localeCompare(crmActivityKey(b)):String(a.id||'').localeCompare(String(b.id||'')))
}
function activityRescheduleExactRow(activityId){const matches=activityRescheduleRows().filter(row=>String(row.id||'')===String(activityId||''));return matches.length===1?matches[0]:null}
function activityRescheduleLocalInput(value){
  if(!value)return '';
  const parsed=new Date(value);if(Number.isNaN(parsed.getTime()))return '';
  const shifted=new Date(parsed.getTime()-parsed.getTimezoneOffset()*60000);
  return shifted.toISOString().slice(0,16)
}
function activityRescheduleStyles(){
  if(document.querySelector('#post-w99-activity-reschedule-style'))return;
  const style=document.createElement('style');style.id='post-w99-activity-reschedule-style';style.textContent=`
.crm-activity-owner-actions{display:flex;gap:5px;align-items:center;justify-content:flex-end;flex-wrap:wrap}.crm-activity-owner-actions button{font-size:8px!important;padding:5px 7px!important}.crm-activity-reschedule-panel{grid-column:1/-1;padding:9px;border:1px solid #cec8bd;border-radius:10px;background:#faf8f3;display:grid;gap:7px}.crm-activity-reschedule-form{display:grid;grid-template-columns:minmax(180px,1fr) auto;gap:7px;align-items:end}.crm-activity-reschedule-form label{display:grid;gap:3px;font-size:7px;color:#716d65}.crm-activity-reschedule-form input{width:100%;box-sizing:border-box;font-size:8px!important;margin:0!important}.crm-activity-reschedule-form button{font-size:8px!important}.crm-activity-reschedule-note{grid-column:1/-1;font-size:7px;color:#716d65;line-height:1.45}.crm-activity-reschedule-status{font-size:7px;color:#716d65}@media(max-width:700px){.crm-activity-owner-actions{justify-content:flex-start}.crm-activity-reschedule-form{grid-template-columns:1fr}}
`;document.head.append(style)
}
async function activityRescheduleRefreshOwner(){
  if(typeof wave63State!=='undefined')wave63State.data=null;
  if(typeof crmRefresh==='function')await crmRefresh(true);
  if(typeof wave63Load==='function')await wave63Load(true);
  if(typeof refreshMarketingOps==='function')await refreshMarketingOps(false);
  if(typeof crmState!=='undefined')crmState.tab='followups';
  if(typeof marketingOpsState!=='undefined'&&marketingOpsState.view==='crm'&&typeof crmRenderCurrent==='function')crmRenderCurrent()
}
function activityRescheduleForm(activity){
  const form=opsEl('form','crm-activity-reschedule-form');form.dataset.activityId=String(activity.id);
  const due=document.createElement('input');due.type='datetime-local';due.required=true;due.value=activityRescheduleLocalInput(activity.due_at);
  const label=opsEl('label','','Nueva fecha / hora');label.append(due);
  const submit=opsEl('button','primary','Guardar nueva fecha');submit.type='submit';
  const note=opsEl('div','crm-activity-reschedule-note','Este submit modifica únicamente due_at de la actividad existente. No cambia resumen, tipo, contacto, oportunidad ni estado de completitud; tampoco crea una actividad nueva.');
  form.append(label,submit,note);
  form.addEventListener('submit',async event=>{
    event.preventDefault();if(postW99ActivityRescheduleState.busy)return;
    const company=activityRescheduleCompany();if(!company?.id||String(company.id)!==String(crmState?.companyId||'')){opsToast('La empresa CRM activa no coincide');return}
    const dueAt=due.value?(typeof crmLocalIso==='function'?crmLocalIso(due.value):null):null;if(!dueAt){opsToast('Selecciona una fecha válida');return}
    const exact=activityRescheduleExactRow(activity.id);if(!exact||exact.completed_at){opsToast('La actividad pendiente exacta ya no está disponible');return}
    postW99ActivityRescheduleState.busy=true;submit.disabled=true;
    try{
      await opsApi(`/api/companies/${encodeURIComponent(company.id)}/activities/${encodeURIComponent(activity.id)}`,{method:'PATCH',body:{due_at:dueAt}});
      postW99ActivityRescheduleState.lastMutation={kind:'RESCHEDULE_ACTIVITY',activity_id:activity.id,due_at:dueAt};postW99ActivityRescheduleState.openId=null;opsToast('Seguimiento reprogramado');await activityRescheduleRefreshOwner()
    }catch(err){opsToast(err.message)}finally{postW99ActivityRescheduleState.busy=false;if(submit.isConnected)submit.disabled=false}
  });
  return form
}
function activityReschedulePanel(activity){
  const panel=opsEl('div','crm-activity-reschedule-panel');panel.dataset.activityId=String(activity.id);panel.append(opsEl('strong','','Reprogramar actividad existente'),activityRescheduleForm(activity),opsEl('div','crm-activity-reschedule-status',`Schema ${POST_W99_ACTIVITY_RESCHEDULE_SCHEMA} · actividad ${String(activity.id).slice(0,16)}… · submit humano requerido.`));return panel
}
function activityRescheduleDecorate(){
  activityRescheduleStyles();if(typeof marketingOpsState==='undefined'||marketingOpsState.view!=='crm'||typeof crmState==='undefined'||crmState.tab!=='followups'||!crmState.loaded)return;
  const rows=activityRescheduleRows(),nodes=[...document.querySelectorAll('.crm-followup')];
  if(postW99ActivityRescheduleState.openId&&!rows.some(row=>String(row.id)===String(postW99ActivityRescheduleState.openId)&&!row.completed_at))postW99ActivityRescheduleState.openId=null;
  nodes.forEach((item,index)=>{
    const activity=rows[index];if(!activity?.id)return;item.dataset.postW99ActivityId=String(activity.id);if(activity.completed_at)return;
    let group=item.querySelector('.crm-activity-owner-actions');
    if(!group){
      const complete=[...item.querySelectorAll('button')].find(button=>activityRescheduleText(button.textContent)==='Completar');
      if(!complete)return;
      group=opsEl('div','crm-activity-owner-actions');group.dataset.postW99ActivityOwnerActions='1';complete.replaceWith(group);group.append(complete)
    }
    let trigger=group.querySelector('button[data-post-w99-activity-reschedule-trigger]');
    if(!trigger){trigger=opsEl('button','','Reprogramar');trigger.type='button';trigger.dataset.postW99ActivityRescheduleTrigger='1';trigger.dataset.activityId=String(activity.id);trigger.addEventListener('click',()=>{postW99ActivityRescheduleState.openId=String(postW99ActivityRescheduleState.openId||'')===String(activity.id)?null:String(activity.id);if(typeof crmRenderCurrent==='function')crmRenderCurrent()});group.append(trigger)}
    if(String(postW99ActivityRescheduleState.openId||'')===String(activity.id)&&!item.querySelector('.crm-activity-reschedule-panel'))item.append(activityReschedulePanel(activity))
  })
}

function activityRescheduleMeta(controlKey,controlLabel,controlKind,kind,explanation){return{control_key:controlKey,control_label:controlLabel,control_kind:controlKind,action_kind:kind,target_kind:'ACTIVITY',explanation}}
function activityRescheduleResolveActivity(row,targetInfo){
  const target=targetInfo?.node,deep=targetInfo?.context||{},kind=activityRescheduleText(row?.kind).toLowerCase();if(!target||String(deep.target_kind||'').toUpperCase()!=='ACTIVITY')return null;
  const exact=activityRescheduleExactRow(deep.target_id);if(!exact||exact.completed_at)return typeof controlHandoffOwnerGap==='function'?controlHandoffOwnerGap(kind,'ACTIVITY','La actividad exacta ya no existe como seguimiento pendiente en la lectura CRM actual. No se selecciona otra actividad.'):null;
  const rescheduleKinds=['crm_unscheduled','pipeline_unscheduled_followup'];
  const decisionKinds=['crm_overdue','crm_today','pipeline_overdue_followup','pipeline_due_soon'];
  if(rescheduleKinds.includes(kind)){
    const panel=target.querySelector('.crm-activity-reschedule-panel');if(panel){const forms=[...panel.querySelectorAll('form.crm-activity-reschedule-form')];return controlHandoffSingle(forms,activityRescheduleMeta('RESCHEDULE_EXISTING_ACTIVITY','Definir fecha del seguimiento existente','CONTROL_GROUP',kind,'La actividad exacta permanece intacta salvo due_at; guardar requiere submit humano explícito.'))}
    const triggers=[...target.querySelectorAll('button[data-post-w99-activity-reschedule-trigger]')];return controlHandoffSingle(triggers,activityRescheduleMeta('OPEN_ACTIVITY_RESCHEDULE','Reprogramar seguimiento existente','BUTTON',kind,'Abre el editor estrecho de due_at para esta actividad exacta; no guarda nada al abrir.'))
  }
  if(decisionKinds.includes(kind)){
    const groups=[...target.querySelectorAll('.crm-activity-owner-actions')].filter(group=>group.querySelectorAll('button').length===2&&[...group.querySelectorAll('button')].some(button=>activityRescheduleText(button.textContent)==='Completar')&&group.querySelectorAll('button[data-post-w99-activity-reschedule-trigger]').length===1);
    return controlHandoffSingle(groups,activityRescheduleMeta('RESOLVE_EXISTING_ACTIVITY','Completar o reprogramar seguimiento','CONTROL_GROUP',kind,'La actividad existe y tiene fecha. El owner ofrece las dos decisiones humanas válidas: completar si ya ocurrió o reprogramar due_at si sigue pendiente. Ninguna se ejecuta automáticamente.'))
  }
  return null
}
const activityRescheduleBaseResolveControl=globalThis.controlHandoffResolveControl;
if(typeof activityRescheduleBaseResolveControl==='function')globalThis.controlHandoffResolveControl=function(row,targetInfo){
  if(String(targetInfo?.context?.target_kind||'').toUpperCase()==='ACTIVITY'){
    const resolved=activityRescheduleResolveActivity(row,targetInfo);if(resolved)return resolved
  }
  return activityRescheduleBaseResolveControl.apply(this,arguments)
};

function activityRescheduleSchedule(){queueMicrotask(()=>{activityRescheduleDecorate();if(typeof contextualDeepLinkSchedule==='function')contextualDeepLinkSchedule();if(typeof controlHandoffSchedule==='function')controlHandoffSchedule()})}
function activityRescheduleWrap(name){const base=globalThis[name];if(typeof base!=='function'||base.__postW99ActivityReschedule)return;const wrapped=function(){const value=base.apply(this,arguments);activityRescheduleDecorate();if(typeof contextualDeepLinkSchedule==='function')contextualDeepLinkSchedule();if(typeof controlHandoffSchedule==='function')controlHandoffSchedule();return value};wrapped.__postW99ActivityReschedule=true;globalThis[name]=wrapped}
['crmRenderCurrent','renderMarketingOps'].forEach(activityRescheduleWrap);
window.addEventListener('marketing-ops-refreshed',activityRescheduleSchedule);window.addEventListener('pageshow',activityRescheduleSchedule);activityRescheduleStyles();activityRescheduleSchedule();
