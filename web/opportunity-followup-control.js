const POST_W99_OPPORTUNITY_FOLLOWUP_CONTROL_SCHEMA='binario.marketing.opportunity-followup-control.v1';
const postW99OpportunityFollowupControlState={openId:null,busy:false,lastMutation:null};

function opportunityControlText(value){return value===null||value===undefined?'':String(value).trim()}
function opportunityControlCompany(){return typeof opsSelectedCompany==='function'?opsSelectedCompany():null}
function opportunityControlLocalInput(value){
  if(!value)return '';
  const parsed=new Date(value);if(Number.isNaN(parsed.getTime()))return '';
  const shifted=new Date(parsed.getTime()-parsed.getTimezoneOffset()*60000);
  return shifted.toISOString().slice(0,16)
}
function opportunityControlWave63Row(opportunityId){
  if(typeof wave63State==='undefined'||!wave63State.data||!opportunityId)return null;
  const matches=[];for(const lane of wave63State.data.lanes||[])for(const row of lane.opportunities||[])if(String(row.id||'')===String(opportunityId))matches.push(row);
  return matches.length===1?matches[0]:null
}
function opportunityControlPendingActivities(opportunityId){
  if(typeof crmState==='undefined')return [];
  return (crmState.activities||[]).filter(row=>String(row.opportunity_id||'')===String(opportunityId)&&!row.completed_at)
}
function opportunityControlAnnotateWave63(){
  if(typeof wave63State==='undefined'||!wave63State.data)return [];
  const lanes=[...document.querySelectorAll('.w63-board .w63-lane')],mapped=[];
  (wave63State.data.lanes||[]).forEach((lane,index)=>{
    const rows=(lane.opportunities||[]).filter(row=>!wave63State.attentionOnly||row.attention?.requires_attention),cards=[...(lanes[index]?.querySelectorAll('.w63-card')||[])];
    cards.forEach((card,rowIndex)=>{const row=rows[rowIndex];if(!row?.id)return;card.dataset.deepOpportunityId=String(row.id);card.dataset.postW99OpportunityId=String(row.id);mapped.push({card,row})})
  });
  return mapped
}

const opportunityControlBaseAnnotateCrm=globalThis.contextualDeepLinkAnnotateCrm;
if(typeof opportunityControlBaseAnnotateCrm==='function')globalThis.contextualDeepLinkAnnotateCrm=function(){const value=opportunityControlBaseAnnotateCrm.apply(this,arguments);opportunityControlAnnotateWave63();return value};
const opportunityControlBaseOwnerReady=globalThis.contextualDeepLinkOwnerReady;
if(typeof opportunityControlBaseOwnerReady==='function')globalThis.contextualDeepLinkOwnerReady=function(context){
  if(context?.owner_view==='crm'&&context?.target_kind==='OPPORTUNITY'&&typeof wave63State!=='undefined'){
    const company=opportunityControlCompany();if(!company?.id||!wave63State.data||String(wave63State.companyId||'')!==String(company.id))return false;
  }
  return opportunityControlBaseOwnerReady.apply(this,arguments)
};

function opportunityControlStyles(){
  if(document.querySelector('#post-w99-opportunity-followup-control-style'))return;
  const style=document.createElement('style');style.id='post-w99-opportunity-followup-control-style';style.textContent=`
.crm-opportunity-followup-trigger{font-size:8px!important;padding:5px 7px!important}.crm-opportunity-followup-control{margin-top:2px;padding:9px;border:1px solid #cec8bd;border-radius:10px;background:#faf8f3;display:grid;gap:9px}.crm-opportunity-followup-control-head{display:grid;gap:3px}.crm-opportunity-followup-control-head strong{font-size:9px!important}.crm-opportunity-followup-control-head span{font-size:7px;color:#716d65}.crm-opportunity-control-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}.crm-opportunity-control-section{padding:8px;border:1px solid #ded9cf;border-radius:9px;background:#fff;display:grid;gap:7px}.crm-opportunity-control-section h4{margin:0;font-size:8px}.crm-opportunity-control-form{display:grid;gap:6px}.crm-opportunity-control-form label{display:grid;gap:3px;font-size:7px;color:#716d65}.crm-opportunity-control-form input,.crm-opportunity-control-form select,.crm-opportunity-control-form textarea{width:100%;box-sizing:border-box;font-size:8px!important;margin:0!important}.crm-opportunity-control-form textarea{min-height:54px}.crm-opportunity-control-form button{font-size:8px!important}.crm-opportunity-control-note{padding:6px 7px;border:1px dashed #d7d1c6;border-radius:8px;font-size:7px;color:#716d65}.crm-opportunity-control-status{font-size:7px;color:#716d65;line-height:1.4}@media(max-width:850px){.crm-opportunity-control-grid{grid-template-columns:1fr}}
`;document.head.append(style)
}
function opportunityControlLabel(text,input){const label=opsEl('label','',text);label.append(input);return label}
function opportunityControlKindSelect(){const select=document.createElement('select');(typeof crmKinds!=='undefined'?crmKinds:[]).forEach(([value,label])=>{const option=opsEl('option','',label);option.value=value;select.append(option)});return select}
async function opportunityControlRefreshOwner(){
  if(typeof wave63State!=='undefined')wave63State.data=null;
  if(typeof crmRefresh==='function')await crmRefresh(true);
  if(typeof wave63Load==='function')await wave63Load(true);
  if(typeof refreshMarketingOps==='function')await refreshMarketingOps(false);
  if(typeof crmState!=='undefined')crmState.tab='pipeline';
  if(typeof marketingOpsState!=='undefined'&&marketingOpsState.view==='crm'&&typeof crmRenderCurrent==='function')crmRenderCurrent()
}
function opportunityControlNextActionForm(row){
  const form=opsEl('form','crm-opportunity-control-form crm-opportunity-next-action-form');form.dataset.opportunityId=String(row.id);
  const action=document.createElement('input');action.value=opportunityControlText(row.next_action);action.placeholder='Ej. Enviar propuesta revisada';action.required=true;
  const at=document.createElement('input');at.type='datetime-local';at.value=opportunityControlLocalInput(row.next_action_at);
  const note=opsEl('div','crm-opportunity-control-note','Guardar aquí modifica únicamente next_action / next_action_at de esta oportunidad. No cambia etapa ni crea una actividad CRM.');
  const submit=opsEl('button','primary','Guardar próxima acción');submit.type='submit';
  form.append(opportunityControlLabel('Próxima acción',action),opportunityControlLabel('Fecha / hora (opcional)',at),note,submit);
  form.addEventListener('submit',async event=>{
    event.preventDefault();if(postW99OpportunityFollowupControlState.busy)return;const company=opportunityControlCompany();if(!company?.id||String(company.id)!==String(crmState?.companyId||'')){opsToast('La empresa CRM activa no coincide');return}
    const nextAction=opportunityControlText(action.value);if(!nextAction){opsToast('Escribe la próxima acción');return}const nextActionAt=at.value?(typeof crmLocalIso==='function'?crmLocalIso(at.value):null):null;if(at.value&&!nextActionAt){opsToast('Fecha inválida');return}
    postW99OpportunityFollowupControlState.busy=true;submit.disabled=true;
    try{await opsApi(`/api/companies/${encodeURIComponent(company.id)}/opportunities/${encodeURIComponent(row.id)}`,{method:'PATCH',body:{next_action:nextAction,next_action_at:nextActionAt}});postW99OpportunityFollowupControlState.lastMutation={kind:'NEXT_ACTION',opportunity_id:row.id};opsToast('Próxima acción guardada');await opportunityControlRefreshOwner()}
    catch(err){opsToast(err.message)}finally{postW99OpportunityFollowupControlState.busy=false;if(submit.isConnected)submit.disabled=false}
  });return form
}
function opportunityControlFollowupForm(row){
  const form=opsEl('form','crm-opportunity-control-form crm-opportunity-followup-form');form.dataset.opportunityId=String(row.id);
  const kind=opportunityControlKindSelect(),due=document.createElement('input'),summary=document.createElement('textarea');due.type='datetime-local';summary.required=true;summary.placeholder='Ej. Llamar para confirmar recepción de propuesta';
  const note=opsEl('div','crm-opportunity-control-note','Programar seguimiento crea una actividad CRM ligada a esta oportunidad. No envía WhatsApp, email ni llamada y no cambia next_action automáticamente.');
  const submit=opsEl('button','primary','Programar seguimiento');submit.type='submit';form.append(opportunityControlLabel('Tipo',kind),opportunityControlLabel('Fecha / hora (opcional)',due),opportunityControlLabel('Detalle',summary),note,submit);
  form.addEventListener('submit',async event=>{
    event.preventDefault();if(postW99OpportunityFollowupControlState.busy)return;const company=opportunityControlCompany();if(!company?.id||String(company.id)!==String(crmState?.companyId||'')){opsToast('La empresa CRM activa no coincide');return}
    const detail=opportunityControlText(summary.value);if(!detail){opsToast('Escribe el detalle del seguimiento');return}const dueAt=due.value?(typeof crmLocalIso==='function'?crmLocalIso(due.value):null):null;if(due.value&&!dueAt){opsToast('Fecha inválida');return}
    postW99OpportunityFollowupControlState.busy=true;submit.disabled=true;
    try{await opsApi(`/api/companies/${encodeURIComponent(company.id)}/activities`,{method:'POST',body:{contact_id:null,opportunity_id:row.id,kind:kind.value,summary:detail,due_at:dueAt}});postW99OpportunityFollowupControlState.lastMutation={kind:'FOLLOWUP',opportunity_id:row.id};opsToast('Seguimiento programado');await opportunityControlRefreshOwner()}
    catch(err){opsToast(err.message)}finally{postW99OpportunityFollowupControlState.busy=false;if(submit.isConnected)submit.disabled=false}
  });return form
}
function opportunityControlPanel(row){
  const panel=opsEl('div','crm-opportunity-followup-control');panel.dataset.opportunityId=String(row.id);
  const head=opsEl('div','crm-opportunity-followup-control-head'),pending=opportunityControlPendingActivities(row.id),overdue=pending.filter(item=>typeof crmIsOverdue==='function'&&crmIsOverdue(item));head.append(opsEl('strong','','Control de seguimiento de la oportunidad'),opsEl('span','',`${pending.length} actividad(es) pendiente(s)${overdue.length?` · ${overdue.length} vencida(s)`:''}. Las actividades existentes se completan desde la pestaña Seguimientos.`));panel.append(head);
  const grid=opsEl('div','crm-opportunity-control-grid'),next=opsEl('section','crm-opportunity-control-section'),follow=opsEl('section','crm-opportunity-control-section');next.append(opsEl('h4','','PRÓXIMA ACCIÓN'),opportunityControlNextActionForm(row));follow.append(opsEl('h4','','NUEVA ACTIVIDAD CRM'),opportunityControlFollowupForm(row));grid.append(next,follow);panel.append(grid);
  panel.append(opsEl('div','crm-opportunity-control-status',`Schema ${POST_W99_OPPORTUNITY_FOLLOWUP_CONTROL_SCHEMA} · Mutaciones solo por submit humano explícito sobre APIs CRM existentes.`));return panel
}
function opportunityControlDecorate(){
  opportunityControlStyles();if(typeof marketingOpsState==='undefined'||marketingOpsState.view!=='crm'||typeof crmState==='undefined'||crmState.tab!=='pipeline')return;
  const mapped=opportunityControlAnnotateWave63();if(postW99OpportunityFollowupControlState.openId&&!mapped.some(item=>String(item.row.id)===String(postW99OpportunityFollowupControlState.openId)))postW99OpportunityFollowupControlState.openId=null;
  mapped.forEach(({card,row})=>{
    if(['WON','LOST'].includes(String(row.stage||'')))return;
    let actions=card.querySelector('.w63-card-actions');if(!actions){actions=opsEl('div','w63-card-actions');card.append(actions)}
    let trigger=actions.querySelector('[data-post-w99-opportunity-followup-trigger]');if(!trigger){trigger=opsEl('button','crm-opportunity-followup-trigger','Gestionar seguimiento');trigger.type='button';trigger.dataset.postW99OpportunityFollowupTrigger='1';trigger.dataset.opportunityId=String(row.id);trigger.addEventListener('click',()=>{postW99OpportunityFollowupControlState.openId=String(postW99OpportunityFollowupControlState.openId||'')===String(row.id)?null:String(row.id);if(typeof crmRenderCurrent==='function')crmRenderCurrent()});actions.append(trigger)}
    if(String(postW99OpportunityFollowupControlState.openId||'')===String(row.id)&&!card.querySelector('.crm-opportunity-followup-control'))card.append(opportunityControlPanel(row))
  })
}

function opportunityControlPipelineMeta(controlKey,controlLabel,controlKind,kind,explanation){return{control_key:controlKey,control_label:controlLabel,control_kind:controlKind,action_kind:kind,target_kind:'OPPORTUNITY',explanation}}
function opportunityControlPipelineGap(kind,explanation){return typeof controlHandoffOwnerGap==='function'?controlHandoffOwnerGap(kind,'OPPORTUNITY',explanation):null}
function opportunityControlResolvePipeline(row,targetInfo){
  const target=targetInfo?.node,deep=targetInfo?.context||{},kind=opportunityControlText(row?.kind).toLowerCase();if(!target||!kind.startsWith('pipeline_')||String(deep.target_kind||'').toUpperCase()!=='OPPORTUNITY')return null;
  const pipelineRow=opportunityControlWave63Row(deep.target_id);if(!pipelineRow)return opportunityControlPipelineGap(kind,'El target DOM existe pero la proyección Wave 63 no contiene exactamente una oportunidad con ese ID. No se elige otra por título o posición.');
  let route=null;
  if(['pipeline_overdue_next_action','pipeline_unscheduled_next_action'].includes(kind))route='NEXT_ACTION';
  else if(kind==='pipeline_no_followup')route='CHOICE';
  else if(['pipeline_overdue_followup','pipeline_unscheduled_followup'].includes(kind))return opportunityControlPipelineGap(kind,'La alerta corresponde a una actividad CRM ya existente. Este control no crea una actividad sustituta ni edita silenciosamente la existente; el owner de actividades conserva esa responsabilidad.');
  else if(kind==='pipeline_due_soon'){
    const due=opportunityControlText(row?.due_at),nextMatch=Boolean(due)&&opportunityControlText(pipelineRow.next_action_at)===due,activityMatches=opportunityControlPendingActivities(pipelineRow.id).filter(item=>opportunityControlText(item.due_at)===due);
    if(nextMatch&&activityMatches.length===0)route='NEXT_ACTION';
    else return opportunityControlPipelineGap(kind,'Vence pronto no puede atribuirse de forma única a next_action: existe o puede existir una actividad CRM con la misma fecha. No se adivina cuál control corresponde.')
  }else return null;
  const panel=target.querySelector('.crm-opportunity-followup-control');
  if(panel){
    if(route==='CHOICE')return controlHandoffSingle([panel],opportunityControlPipelineMeta('CHOOSE_OPPORTUNITY_NEXT_STEP','Elegir próxima acción o nueva actividad','CONTROL_GROUP',kind,'La oportunidad no tiene siguiente paso. El owner expone ambas alternativas sin preseleccionar ninguna.'));
    const forms=[...panel.querySelectorAll('form.crm-opportunity-next-action-form')];return controlHandoffSingle(forms,opportunityControlPipelineMeta('EDIT_OPPORTUNITY_NEXT_ACTION','Editar próxima acción y fecha','CONTROL_GROUP',kind,'El formulario actualiza exclusivamente next_action / next_action_at de la oportunidad exacta. El submit sigue siendo humano.'))
  }
  const triggers=[...target.querySelectorAll('button[data-post-w99-opportunity-followup-trigger]')];return controlHandoffSingle(triggers,opportunityControlPipelineMeta('OPEN_OPPORTUNITY_FOLLOWUP_CONTROL','Gestionar seguimiento','BUTTON',kind,'Abre el control de la oportunidad exacta; no guarda, programa ni completa nada por sí mismo.'))
}
const opportunityControlBaseResolveControl=globalThis.controlHandoffResolveControl;
if(typeof opportunityControlBaseResolveControl==='function')globalThis.controlHandoffResolveControl=function(row,targetInfo){
  const kind=opportunityControlText(row?.kind).toLowerCase(),targetKind=opportunityControlText(targetInfo?.context?.target_kind).toUpperCase();
  if(targetKind==='OPPORTUNITY'&&kind.startsWith('pipeline_')){const resolved=opportunityControlResolvePipeline(row,targetInfo);if(resolved)return resolved}
  return opportunityControlBaseResolveControl.apply(this,arguments)
};

function opportunityControlSchedule(){queueMicrotask(()=>{opportunityControlDecorate();if(typeof contextualDeepLinkSchedule==='function')contextualDeepLinkSchedule();if(typeof controlHandoffSchedule==='function')controlHandoffSchedule()})}
function opportunityControlWrap(name){const base=globalThis[name];if(typeof base!=='function'||base.__postW99OpportunityFollowupControl)return;const wrapped=function(){const value=base.apply(this,arguments);opportunityControlDecorate();if(typeof contextualDeepLinkSchedule==='function')contextualDeepLinkSchedule();if(typeof controlHandoffSchedule==='function')controlHandoffSchedule();return value};wrapped.__postW99OpportunityFollowupControl=true;globalThis[name]=wrapped}
['wave63Draw','crmRenderCurrent','renderMarketingOps'].forEach(opportunityControlWrap);
window.addEventListener('marketing-ops-refreshed',opportunityControlSchedule);window.addEventListener('pageshow',opportunityControlSchedule);opportunityControlStyles();opportunityControlSchedule();
