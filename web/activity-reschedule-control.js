const POST_W99_ACTIVITY_RESCHEDULE_SCHEMA='binario.marketing.activity-reschedule-control.v2';
const postW99ActivityRescheduleBridgeState={refreshing:false,lastOwner:null};

function activityRescheduleText(value){return value===null||value===undefined?'':String(value).trim()}
function activityRescheduleRows(){
  if(typeof crmState==='undefined')return [];
  return [...(crmState.activities||[])].sort((a,b)=>typeof crmActivityKey==='function'?crmActivityKey(a).localeCompare(crmActivityKey(b)):String(a.id||'').localeCompare(String(b.id||'')))
}
function activityRescheduleExactRow(activityId){
  const matches=activityRescheduleRows().filter(row=>String(row.id||'')===String(activityId||''));
  return matches.length===1?matches[0]:null
}
function activityRescheduleWave45Ready(){return typeof followupRescheduleOpen==='function'}
function activityRescheduleStyles(){
  if(document.querySelector('#post-w99-activity-reschedule-style'))return;
  const style=document.createElement('style');style.id='post-w99-activity-reschedule-style';style.textContent=`
.crm-activity-owner-actions{display:flex;gap:5px;align-items:center;justify-content:flex-end;flex-wrap:wrap}.crm-activity-owner-actions button{font-size:8px!important;padding:5px 7px!important}.crm-followup .followup-reschedule-inline{grid-column:1/-1}.crm-activity-owner-gap{font-size:7px;color:#806d54}@media(max-width:700px){.crm-activity-owner-actions{justify-content:flex-start}}
`;document.head.append(style)
}
function activityRescheduleCanonicalItem(activity){
  return{entity:'crm_activity',entityId:String(activity.id),companyId:String(crmState?.companyId||'')}
}
function activityRescheduleOpenCanonical(activity,rowNode){
  if(!activity||activity.completed_at||!rowNode||!activityRescheduleWave45Ready())return;
  const exact=activityRescheduleExactRow(activity.id);if(!exact||exact.completed_at)return;
  postW99ActivityRescheduleBridgeState.lastOwner={schema:POST_W99_ACTIVITY_RESCHEDULE_SCHEMA,activity_id:String(activity.id),mutation_owner:'WAVE45_FOLLOWUP_RESCHEDULE',opened_at:new Date().toISOString()};
  followupRescheduleOpen(activityRescheduleCanonicalItem(exact),rowNode)
}
function activityRescheduleDecorate(){
  activityRescheduleStyles();
  if(typeof marketingOpsState==='undefined'||marketingOpsState.view!=='crm'||typeof crmState==='undefined'||crmState.tab!=='followups'||!crmState.loaded)return;
  const rows=activityRescheduleRows(),nodes=[...document.querySelectorAll('.crm-followup')];
  nodes.forEach((item,index)=>{
    const activity=rows[index];if(!activity?.id)return;
    item.dataset.postW99ActivityId=String(activity.id);
    if(activity.completed_at)return;
    const complete=[...item.querySelectorAll('button')].find(button=>activityRescheduleText(button.textContent)==='Completar');
    if(!complete)return;
    let group=item.querySelector('.crm-activity-owner-actions');
    if(!group){group=opsEl('div','crm-activity-owner-actions');group.dataset.postW99ActivityOwnerActions='1';complete.replaceWith(group);group.append(complete)}
    if(group.querySelector('button[data-post-w99-activity-reschedule-trigger]'))return;
    if(!activityRescheduleWave45Ready()){
      const gap=opsEl('span','crm-activity-owner-gap','Reprogramación Wave 45 no disponible');gap.dataset.postW99ActivityRescheduleGap='1';group.append(gap);return
    }
    const trigger=opsEl('button','','Reprogramar');trigger.type='button';trigger.dataset.postW99ActivityRescheduleTrigger='1';trigger.dataset.activityId=String(activity.id);
    trigger.addEventListener('click',()=>activityRescheduleOpenCanonical(activity,item));group.append(trigger)
  })
}

async function activityRescheduleRefreshAfterWave45(){
  if(postW99ActivityRescheduleBridgeState.refreshing)return;
  if(typeof marketingOpsState==='undefined'||marketingOpsState.view!=='crm'||typeof crmState==='undefined'||crmState.tab!=='followups'||crmState.loaded!==false)return;
  if(typeof crmRefresh!=='function'||typeof crmRenderCurrent!=='function')return;
  postW99ActivityRescheduleBridgeState.refreshing=true;
  try{await crmRefresh(true);crmState.tab='followups';crmRenderCurrent()}finally{postW99ActivityRescheduleBridgeState.refreshing=false}
}

function activityRescheduleMeta(controlKey,controlLabel,controlKind,kind,explanation){return{control_key:controlKey,control_label:controlLabel,control_kind:controlKind,action_kind:kind,target_kind:'ACTIVITY',explanation}}
function activityRescheduleResolveActivity(row,targetInfo){
  const target=targetInfo?.node,deep=targetInfo?.context||{},kind=activityRescheduleText(row?.kind).toLowerCase();
  if(!target||String(deep.target_kind||'').toUpperCase()!=='ACTIVITY')return null;
  const exact=activityRescheduleExactRow(deep.target_id);
  if(!exact||exact.completed_at)return typeof controlHandoffOwnerGap==='function'?controlHandoffOwnerGap(kind,'ACTIVITY','La actividad exacta ya no existe como seguimiento pendiente. No se selecciona otra actividad.'):null;
  if(!activityRescheduleWave45Ready())return typeof controlHandoffOwnerGap==='function'?controlHandoffOwnerGap(kind,'ACTIVITY','La autoridad canónica Wave 45 de reprogramación no está cargada. No se crea una mutación alternativa.'):null;
  const rescheduleKinds=['crm_unscheduled','pipeline_unscheduled_followup'];
  const decisionKinds=['crm_overdue','crm_today','pipeline_overdue_followup','pipeline_due_soon'];
  if(rescheduleKinds.includes(kind)){
    const editors=[...target.querySelectorAll('.followup-reschedule-inline')];
    if(editors.length)return controlHandoffSingle(editors,activityRescheduleMeta('WAVE45_RESCHEDULE_EDITOR','Definir nueva fecha del seguimiento','CONTROL_GROUP',kind,'Editor canónico de Wave 45 sobre la actividad exacta. Guardar conserva su validación de fecha futura y su POST /reschedule.'));
    const triggers=[...target.querySelectorAll('button[data-post-w99-activity-reschedule-trigger]')];
    return controlHandoffSingle(triggers,activityRescheduleMeta('OPEN_WAVE45_RESCHEDULE','Reprogramar seguimiento existente','BUTTON',kind,'Abre el editor Wave 45 de la actividad exacta; abrirlo no modifica estado.'))
  }
  if(decisionKinds.includes(kind)){
    const groups=[...target.querySelectorAll('.crm-activity-owner-actions')].filter(group=>[...group.querySelectorAll('button')].some(button=>activityRescheduleText(button.textContent)==='Completar')&&group.querySelectorAll('button[data-post-w99-activity-reschedule-trigger]').length===1);
    return controlHandoffSingle(groups,activityRescheduleMeta('RESOLVE_EXISTING_ACTIVITY','Completar o reprogramar seguimiento','CONTROL_GROUP',kind,'El owner ofrece las dos decisiones humanas canónicas: completar si ocurrió o abrir Wave 45 para mover due_at si sigue pendiente. Ninguna se ejecuta automáticamente.'))
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

function activityRescheduleSchedule(){queueMicrotask(()=>{activityRescheduleDecorate();activityRescheduleRefreshAfterWave45();if(typeof contextualDeepLinkSchedule==='function')contextualDeepLinkSchedule();if(typeof controlHandoffSchedule==='function')controlHandoffSchedule()})}
function activityRescheduleWrap(name){const base=globalThis[name];if(typeof base!=='function'||base.__postW99ActivityReschedule)return;const wrapped=function(){const value=base.apply(this,arguments);activityRescheduleDecorate();if(typeof contextualDeepLinkSchedule==='function')contextualDeepLinkSchedule();if(typeof controlHandoffSchedule==='function')controlHandoffSchedule();return value};wrapped.__postW99ActivityReschedule=true;globalThis[name]=wrapped}
['crmRenderCurrent','renderMarketingOps'].forEach(activityRescheduleWrap);
window.addEventListener('marketing-ops-refreshed',activityRescheduleSchedule);window.addEventListener('pageshow',activityRescheduleSchedule);activityRescheduleStyles();activityRescheduleSchedule();
