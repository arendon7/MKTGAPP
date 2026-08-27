const POST_W99_OPERATOR_CURRENT_PRIORITY_CONTINUITY_SCHEMA='binario.marketing.operator-current-priority-continuity.v1';

function operatorCurrentPriorityText(value){return value===null||value===undefined?'':String(value).trim()}
function operatorCurrentPriorityCompany(){return typeof todayCompany==='function'?todayCompany():(typeof opsSelectedCompany==='function'?opsSelectedCompany():null)}
function operatorCurrentPriorityLatestReturn(companyId){
  if(!companyId||typeof operatorSessionProgressRead!=='function')return null;
  const value=operatorSessionProgressRead(companyId);if(!value||String(value.company_id)!==String(companyId)||!Array.isArray(value.events))return null;
  const returns=value.events.filter(event=>event?.type==='RETURN_OBSERVED'&&operatorCurrentPriorityText(event.action_id)&&operatorCurrentPriorityText(event.checked_at));
  return returns.length?returns[returns.length-1]:null
}
function operatorCurrentPriorityTodayPayload(companyId){
  if(typeof postW99TodayState==='undefined')return null;
  const payload=postW99TodayState.payload;if(!payload||String(payload.company?.id||'')!==String(companyId))return null;
  return payload
}
function operatorCurrentPriorityResolve(){
  const company=operatorCurrentPriorityCompany();if(!company?.id)return{schema:POST_W99_OPERATOR_CURRENT_PRIORITY_CONTINUITY_SCHEMA,state:'NO_COMPANY',executable:false};
  const companyId=String(company.id),event=operatorCurrentPriorityLatestReturn(companyId);if(!event)return{schema:POST_W99_OPERATOR_CURRENT_PRIORITY_CONTINUITY_SCHEMA,state:'NO_RETURN_EVIDENCE',company_id:companyId,executable:false};
  if(event.observed_state!=='NO_LONGER_PENDING')return{schema:POST_W99_OPERATOR_CURRENT_PRIORITY_CONTINUITY_SCHEMA,state:'NO_HANDOFF_REQUIRED',company_id:companyId,from_action_id:String(event.action_id),checked_at:String(event.checked_at),executable:false};
  const payload=operatorCurrentPriorityTodayPayload(companyId);if(!payload)return{schema:POST_W99_OPERATOR_CURRENT_PRIORITY_CONTINUITY_SCHEMA,state:'TODAY_NOT_READY',company_id:companyId,from_action_id:String(event.action_id),checked_at:String(event.checked_at),executable:false};
  const plan=Array.isArray(payload.plan)?payload.plan:[],primary=payload.primary_action||null,nextId=operatorCurrentPriorityText(event.next_action_id);
  if(!nextId){
    if(!primary&&plan.length===0)return{schema:POST_W99_OPERATOR_CURRENT_PRIORITY_CONTINUITY_SCHEMA,state:'PLAN_CLEAR_AFTER_RETURN',company_id:companyId,from_action_id:String(event.action_id),checked_at:String(event.checked_at),executable:false};
    return{schema:POST_W99_OPERATOR_CURRENT_PRIORITY_CONTINUITY_SCHEMA,state:'RETURN_PRIORITY_MISSING',company_id:companyId,from_action_id:String(event.action_id),checked_at:String(event.checked_at),executable:false}
  }
  const matches=plan.filter(row=>operatorCurrentPriorityText(row?.id)===nextId);
  if(matches.length>1)return{schema:POST_W99_OPERATOR_CURRENT_PRIORITY_CONTINUITY_SCHEMA,state:'CURRENT_PLAN_AMBIGUOUS',company_id:companyId,from_action_id:String(event.action_id),observed_priority_id:nextId,checked_at:String(event.checked_at),executable:false};
  if(matches.length===0)return{schema:POST_W99_OPERATOR_CURRENT_PRIORITY_CONTINUITY_SCHEMA,state:'OBSERVED_PRIORITY_NO_LONGER_IN_TODAY',company_id:companyId,from_action_id:String(event.action_id),observed_priority_id:nextId,checked_at:String(event.checked_at),executable:false};
  const candidate=matches[0],primaryId=operatorCurrentPriorityText(primary?.id),statusId=operatorCurrentPriorityText(payload.status?.primary_action_id),firstId=operatorCurrentPriorityText(plan[0]?.id);
  if(primaryId!==nextId||statusId!==nextId||firstId!==nextId)return{schema:POST_W99_OPERATOR_CURRENT_PRIORITY_CONTINUITY_SCHEMA,state:'OBSERVED_PRIORITY_NO_LONGER_PRIMARY',company_id:companyId,from_action_id:String(event.action_id),observed_priority_id:nextId,current_primary_id:primaryId||null,checked_at:String(event.checked_at),executable:false};
  if(operatorCurrentPriorityText(candidate?.action?.view)===''||Number(candidate?.operator?.sequence||0)!==1)return{schema:POST_W99_OPERATOR_CURRENT_PRIORITY_CONTINUITY_SCHEMA,state:'CURRENT_PRIORITY_SHAPE_INVALID',company_id:companyId,from_action_id:String(event.action_id),observed_priority_id:nextId,checked_at:String(event.checked_at),executable:false};
  return{schema:POST_W99_OPERATOR_CURRENT_PRIORITY_CONTINUITY_SCHEMA,state:'CURRENT_PRIORITY_CONFIRMED',company_id:companyId,from_action_id:String(event.action_id),current_priority_id:nextId,checked_at:String(event.checked_at),candidate,executable:true,causal_successor_claimed:false}
}
function operatorCurrentPriorityStyles(){
  if(document.querySelector('#post-w99-operator-current-priority-continuity-style'))return;
  const style=document.createElement('style');style.id='post-w99-operator-current-priority-continuity-style';style.textContent=`
.operator-current-priority{border:1px solid #d8d2c8;border-radius:12px;background:#faf8f3;padding:11px 13px;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;align-items:center}.operator-current-priority-copy{display:grid;gap:4px}.operator-current-priority-copy strong{font-size:10px}.operator-current-priority-copy p{font-size:8px;color:#706a61;margin:0;line-height:1.45}.operator-current-priority-actions{display:flex;gap:6px;flex-wrap:wrap}.operator-current-priority-note{font-size:7px;color:#837c72}@media(max-width:720px){.operator-current-priority{grid-template-columns:1fr}}
`;document.head.append(style)
}
function operatorCurrentPriorityCopy(result){
  if(result.state==='CURRENT_PRIORITY_CONFIRMED')return{title:'La prioridad observada al volver sigue siendo la prioridad actual',detail:'La misma action ID que Today marcó como primaria durante esa relectura continúa hoy en la posición 1. Puedes abrirla explícitamente; esto no afirma que sea la sucesora causal de la acción anterior.'};
  if(result.state==='PLAN_CLEAR_AFTER_RETURN')return{title:'La relectura no dejó una prioridad siguiente y el plan actual sigue vacío',detail:'No hay una acción que este handoff pueda abrir. Esto tampoco convierte la acción anterior en completada: solo describe la cola canónica actual.'};
  if(result.state==='OBSERVED_PRIORITY_NO_LONGER_PRIMARY')return{title:'La prioridad observada en ese regreso ya no es la prioridad principal',detail:'Today cambió desde aquella relectura. Este panel no abrirá una prioridad histórica como si siguiera vigente; usa el plan actual.'};
  if(result.state==='OBSERVED_PRIORITY_NO_LONGER_IN_TODAY')return{title:'La prioridad observada en ese regreso ya no está en el foco actual',detail:'La action ID registrada entonces no aparece en el plan visible actual. No se infiere por qué cambió ni se selecciona un reemplazo.'};
  if(result.state==='RETURN_PRIORITY_MISSING'||result.state==='CURRENT_PLAN_AMBIGUOUS'||result.state==='CURRENT_PRIORITY_SHAPE_INVALID')return{title:'No se puede demostrar continuidad exacta de prioridad',detail:'La evidencia disponible no cumple identidad, cardinalidad o forma suficiente. El handoff falla cerrado y no abre ninguna acción.'};
  return null
}
function operatorCurrentPriorityRender(){
  if(typeof marketingOpsState==='undefined'||marketingOpsState.view!=='today-execution')return;
  const root=document.querySelector('#marketing-ops-view');if(!root)return;root.querySelector('#post-w99-operator-current-priority-continuity')?.remove();
  const result=operatorCurrentPriorityResolve(),copyInfo=operatorCurrentPriorityCopy(result);if(!copyInfo)return;
  operatorCurrentPriorityStyles();const section=opsEl('section','operator-current-priority');section.id='post-w99-operator-current-priority-continuity';section.dataset.continuityState=result.state;
  const copy=opsEl('div','operator-current-priority-copy');copy.append(opsEl('span','eyebrow','SESIÓN · CONTINUIDAD DE PRIORIDAD'),opsEl('strong','',copyInfo.title),opsEl('p','',copyInfo.detail),opsEl('span','operator-current-priority-note','La prioridad mostrada proviene de Action Center/Today. No se atribuye causalidad, completion ni repriorización a esta capa.'));section.append(copy);
  if(result.state==='CURRENT_PRIORITY_CONFIRMED'&&result.executable===true&&result.candidate){const actions=opsEl('div','operator-current-priority-actions'),open=opsEl('button','primary','Abrir prioridad actual');open.type='button';open.addEventListener('click',()=>{const fresh=operatorCurrentPriorityResolve();if(fresh.state!=='CURRENT_PRIORITY_CONFIRMED'||fresh.current_priority_id!==result.current_priority_id||!fresh.candidate){if(typeof opsToast==='function')opsToast('La prioridad cambió; relee el plan antes de abrirla.');operatorCurrentPriorityRender();return}if(typeof todayOpen==='function')todayOpen(fresh.candidate)});actions.append(open);section.append(actions)}
  const progress=root.querySelector('#post-w99-operator-session-progress'),returnCard=root.querySelector('#post-w99-execution-return-result');if(progress)progress.insertAdjacentElement('afterend',section);else if(returnCard)returnCard.insertAdjacentElement('afterend',section);else root.prepend(section)
}

const operatorCurrentPriorityBaseReturn=globalThis.executionReturnBackToToday;if(typeof operatorCurrentPriorityBaseReturn==='function')globalThis.executionReturnBackToToday=async function(){const value=await operatorCurrentPriorityBaseReturn.apply(this,arguments);queueMicrotask(operatorCurrentPriorityRender);return value};
const operatorCurrentPriorityBaseReset=globalThis.operatorSessionProgressReset;if(typeof operatorCurrentPriorityBaseReset==='function')globalThis.operatorSessionProgressReset=function(){const value=operatorCurrentPriorityBaseReset.apply(this,arguments);queueMicrotask(operatorCurrentPriorityRender);return value};
const operatorCurrentPriorityBaseRender=globalThis.renderMarketingOps;if(typeof operatorCurrentPriorityBaseRender==='function')globalThis.renderMarketingOps=function(){const value=operatorCurrentPriorityBaseRender.apply(this,arguments);operatorCurrentPriorityRender();return value};
window.addEventListener('marketing-ops-refreshed',operatorCurrentPriorityRender);window.addEventListener('pageshow',operatorCurrentPriorityRender);queueMicrotask(operatorCurrentPriorityRender);
