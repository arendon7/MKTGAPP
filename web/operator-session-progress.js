const POST_W99_OPERATOR_SESSION_PROGRESS_SCHEMA='binario.marketing.operator-session-progress.v1';
const POST_W99_OPERATOR_SESSION_PROGRESS_MAX_EVENTS=40;
const postW99OperatorSessionProgressState={lastRecordedReturn:null};

function operatorSessionProgressText(value){return value===null||value===undefined?'':String(value).trim()}
function operatorSessionProgressCompany(){return typeof todayCompany==='function'?todayCompany():(typeof opsSelectedCompany==='function'?opsSelectedCompany():null)}
function operatorSessionProgressKey(companyId){return `${POST_W99_OPERATOR_SESSION_PROGRESS_SCHEMA}:${companyId}`}
function operatorSessionProgressAllowedReturnState(value){return ['STILL_IN_TODAY','STILL_PENDING','NO_LONGER_PENDING'].includes(String(value||''))}
function operatorSessionProgressValidEvent(event){
  if(!event||!['ACTION_OPENED','RETURN_OBSERVED'].includes(event.type)||!operatorSessionProgressText(event.action_id))return false;
  if(event.type==='ACTION_OPENED')return Boolean(operatorSessionProgressText(event.observed_at));
  return Boolean(operatorSessionProgressAllowedReturnState(event.observed_state)&&operatorSessionProgressText(event.checked_at))
}
function operatorSessionProgressRead(companyId){
  if(!companyId)return null;
  try{
    const raw=sessionStorage.getItem(operatorSessionProgressKey(companyId));if(!raw)return null;
    const value=JSON.parse(raw);
    if(!value||value.schema!==POST_W99_OPERATOR_SESSION_PROGRESS_SCHEMA||String(value.company_id)!==String(companyId)||!Array.isArray(value.events)){sessionStorage.removeItem(operatorSessionProgressKey(companyId));return null}
    value.events=value.events.filter(operatorSessionProgressValidEvent).slice(-POST_W99_OPERATOR_SESSION_PROGRESS_MAX_EVENTS);
    return value
  }catch(_err){try{sessionStorage.removeItem(operatorSessionProgressKey(companyId))}catch(_ignore){}return null}
}
function operatorSessionProgressWrite(value){
  if(!value?.company_id)return null;
  value.events=(value.events||[]).filter(operatorSessionProgressValidEvent).slice(-POST_W99_OPERATOR_SESSION_PROGRESS_MAX_EVENTS);
  try{sessionStorage.setItem(operatorSessionProgressKey(value.company_id),JSON.stringify(value))}catch(_err){}
  return value
}
function operatorSessionProgressInitialPlan(){return typeof postW99TodayState!=='undefined'?(postW99TodayState.payload?.plan||[]):[]}
function operatorSessionProgressEnsure(companyId){
  let value=operatorSessionProgressRead(companyId);if(value)return value;
  const plan=operatorSessionProgressInitialPlan();
  value={schema:POST_W99_OPERATOR_SESSION_PROGRESS_SCHEMA,company_id:String(companyId),started_at:new Date().toISOString(),initial_plan_count:plan.length,initial_action_ids:plan.map(row=>operatorSessionProgressText(row?.id)).filter(Boolean),events:[]};
  return operatorSessionProgressWrite(value)
}
function operatorSessionProgressAppend(companyId,event){const value=operatorSessionProgressEnsure(companyId);if(!value||!operatorSessionProgressValidEvent(event))return null;value.events.push(event);return operatorSessionProgressWrite(value)}
function operatorSessionProgressRecordOpen(row){
  const company=operatorSessionProgressCompany(),actionId=operatorSessionProgressText(row?.id);if(!company?.id||!actionId)return;
  operatorSessionProgressAppend(company.id,{type:'ACTION_OPENED',action_id:actionId,title:operatorSessionProgressText(row?.title)||'Acción del plan',source:operatorSessionProgressText(row?.source)||'OTHER',urgency:operatorSessionProgressText(row?.urgency)||'LOW',sequence:Number(row?.operator?.sequence||0)||null,observed_at:new Date().toISOString()})
}
function operatorSessionProgressRecordReturn(companyId,actionId,previousCheckedAt=''){
  if(typeof postW99ExecutionReturnState==='undefined'||!companyId||!actionId)return;
  const company=operatorSessionProgressCompany(),result=postW99ExecutionReturnState.lastResult,checkedAt=operatorSessionProgressText(result?.checked_at);
  if(!company?.id||String(company.id)!==String(companyId)||!result||String(result.action_id)!==String(actionId)||!checkedAt||checkedAt===operatorSessionProgressText(previousCheckedAt)||!operatorSessionProgressAllowedReturnState(result.state))return;
  const fingerprint=`${companyId}:${actionId}:${checkedAt}`;if(postW99OperatorSessionProgressState.lastRecordedReturn===fingerprint)return;
  const current=operatorSessionProgressRead(companyId),already=(current?.events||[]).some(event=>event.type==='RETURN_OBSERVED'&&event.action_id===String(actionId)&&event.checked_at===checkedAt);
  if(!already)operatorSessionProgressAppend(companyId,{type:'RETURN_OBSERVED',action_id:String(actionId),title:operatorSessionProgressText(result.title)||'Acción observada',observed_state:String(result.state),checked_at:checkedAt,today_sequence:result.today_sequence??null,canonical_position:result.canonical_position??null,next_action_id:operatorSessionProgressText(result.next_action?.id)||null});
  postW99OperatorSessionProgressState.lastRecordedReturn=fingerprint
}
function operatorSessionProgressLatestReturns(value){const latest=new Map();for(const event of value?.events||[]){if(event.type==='RETURN_OBSERVED')latest.set(event.action_id,event)}return [...latest.values()]}
function operatorSessionProgressSummary(value){
  const opened=new Set((value?.events||[]).filter(event=>event.type==='ACTION_OPENED').map(event=>event.action_id));
  const latest=operatorSessionProgressLatestReturns(value),count=state=>latest.filter(event=>event.observed_state===state).length;
  return{opened:opened.size,observed:latest.length,still_today:count('STILL_IN_TODAY'),still_pending:count('STILL_PENDING'),no_longer_pending:count('NO_LONGER_PENDING')}
}
function operatorSessionProgressStateLabel(state){return({STILL_IN_TODAY:'Sigue en foco',STILL_PENDING:'Pendiente fuera de foco',NO_LONGER_PENDING:'Ya no está en cola'})[state]||'Estado no válido'}
function operatorSessionProgressEventDetail(event){if(event.observed_state==='STILL_IN_TODAY')return event.today_sequence?`Ahora está en la posición ${event.today_sequence} de Hoy.`:'Action Center todavía la mantiene dentro del foco diario.';if(event.observed_state==='STILL_PENDING')return event.canonical_position?`Sigue en Action Center, posición ${event.canonical_position}, fuera del foco de cinco.`:'Sigue en Action Center fuera del foco diario.';if(event.observed_state==='NO_LONGER_PENDING')return 'La action ID ya no apareció en la cola al releer el estado local. Esto no prueba por sí solo que esté completada.';return 'Observación descartada por contrato fail-closed.'}
function operatorSessionProgressStyles(){
  if(document.querySelector('#post-w99-operator-session-progress-style'))return;
  const style=document.createElement('style');style.id='post-w99-operator-session-progress-style';style.textContent=`
.operator-session-progress{border:1px solid #dedad2;background:#fff;border-radius:14px;padding:13px;display:grid;gap:10px}.operator-session-progress-head{display:flex;justify-content:space-between;align-items:flex-end;gap:10px}.operator-session-progress-head h3{margin:0;font-size:14px}.operator-session-progress-stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:7px}.operator-session-progress-stat{padding:9px;border:1px solid #e5e0d8;border-radius:9px;background:#faf9f6;display:grid;gap:2px}.operator-session-progress-stat strong{font-size:16px}.operator-session-progress-stat span{font-size:7px;color:#777168}.operator-session-progress-list{display:grid;gap:6px}.operator-session-progress-row{padding:9px 10px;border:1px dashed #d8d2c8;border-radius:9px;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:9px;align-items:center}.operator-session-progress-copy{display:grid;gap:3px}.operator-session-progress-copy strong{font-size:9px}.operator-session-progress-copy p{font-size:8px;color:#706a61;margin:0}.operator-session-progress-chip{font-size:7px;padding:4px 6px;border-radius:999px;background:#f1eee8;white-space:nowrap}.operator-session-progress-note{padding:9px 10px;border-radius:9px;background:#f5f2eb;color:#756f65;font-size:8px;line-height:1.45}@media(max-width:720px){.operator-session-progress-head{display:grid}.operator-session-progress-stats{grid-template-columns:1fr 1fr}.operator-session-progress-row{grid-template-columns:1fr}.operator-session-progress-chip{width:max-content}}
`;document.head.append(style)
}
function operatorSessionProgressStat(value,label){const node=opsEl('div','operator-session-progress-stat');node.append(opsEl('strong','',String(value||0)),opsEl('span','',label));return node}
function operatorSessionProgressReset(companyId){try{sessionStorage.removeItem(operatorSessionProgressKey(companyId))}catch(_err){}postW99OperatorSessionProgressState.lastRecordedReturn=null;if(typeof opsToast==='function')opsToast('Se borró solo el historial local de esta sesión; ninguna tarea ni dato de negocio cambió.');operatorSessionProgressRender()}
function operatorSessionProgressRender(){
  if(typeof marketingOpsState==='undefined'||marketingOpsState.view!=='today-execution')return;
  const company=operatorSessionProgressCompany(),root=document.querySelector('#marketing-ops-view');if(!company?.id||!root)return;
  root.querySelector('#post-w99-operator-session-progress')?.remove();const value=operatorSessionProgressRead(company.id);if(!value)return;
  operatorSessionProgressStyles();const summary=operatorSessionProgressSummary(value),section=opsEl('section','operator-session-progress');section.id='post-w99-operator-session-progress';
  const head=opsEl('div','operator-session-progress-head'),copy=opsEl('div');copy.append(opsEl('p','eyebrow','SESIÓN · CAMBIOS OBSERVADOS'),opsEl('h3','','Qué ha cambiado mientras ejecutas el plan'));const reset=opsEl('button','','Reiniciar registro de sesión');reset.type='button';reset.addEventListener('click',()=>operatorSessionProgressReset(company.id));head.append(copy,reset);section.append(head);
  const stats=opsEl('div','operator-session-progress-stats');stats.append(operatorSessionProgressStat(summary.opened,'ACCIONES ABIERTAS'),operatorSessionProgressStat(summary.still_today,'SIGUEN EN FOCO'),operatorSessionProgressStat(summary.still_pending,'PENDIENTES FUERA DE FOCO'),operatorSessionProgressStat(summary.no_longer_pending,'YA NO EN COLA'));section.append(stats);
  const returns=operatorSessionProgressLatestReturns(value).slice(-5).reverse(),list=opsEl('div','operator-session-progress-list');if(!returns.length)list.append(opsEl('div','operator-session-progress-note','Aún no hay regresos observados. Abre una acción desde Hoy, trabaja en su módulo propietario y usa “Volver y releer plan”.'));
  for(const event of returns){const row=opsEl('article','operator-session-progress-row'),eventCopy=opsEl('div','operator-session-progress-copy');eventCopy.append(opsEl('strong','',event.title||event.action_id),opsEl('p','',operatorSessionProgressEventDetail(event)));row.append(eventCopy,opsEl('span','operator-session-progress-chip',operatorSessionProgressStateLabel(event.observed_state)));list.append(row)}section.append(list,opsEl('div','operator-session-progress-note','Este panel no es un contador de tareas completadas. “Ya no está en cola” significa únicamente que esa action ID no apareció en la relectura canónica; el owner sigue siendo la única autoridad de negocio.'));
  const resultCard=root.querySelector('#post-w99-execution-return-result'),hero=root.querySelector('.today-hero');if(resultCard)resultCard.insertAdjacentElement('afterend',section);else if(hero)hero.insertAdjacentElement('afterend',section);else root.prepend(section)
}

const operatorSessionProgressBaseTodayOpen=globalThis.todayOpen;if(typeof operatorSessionProgressBaseTodayOpen==='function')globalThis.todayOpen=function(row){operatorSessionProgressRecordOpen(row);return operatorSessionProgressBaseTodayOpen.apply(this,arguments)};
const operatorSessionProgressBaseReturn=globalThis.executionReturnBackToToday;if(typeof operatorSessionProgressBaseReturn==='function')globalThis.executionReturnBackToToday=async function(context){const companyId=operatorSessionProgressText(context?.company_id),actionId=operatorSessionProgressText(context?.action_id),previousCheckedAt=operatorSessionProgressText(typeof postW99ExecutionReturnState==='undefined'?null:postW99ExecutionReturnState.lastResult?.checked_at),value=await operatorSessionProgressBaseReturn.apply(this,arguments);operatorSessionProgressRecordReturn(companyId,actionId,previousCheckedAt);queueMicrotask(operatorSessionProgressRender);return value};
const operatorSessionProgressBaseRender=globalThis.renderMarketingOps;if(typeof operatorSessionProgressBaseRender==='function')globalThis.renderMarketingOps=function(){const value=operatorSessionProgressBaseRender.apply(this,arguments);operatorSessionProgressRender();return value};
window.addEventListener('marketing-ops-refreshed',operatorSessionProgressRender);window.addEventListener('pageshow',operatorSessionProgressRender);queueMicrotask(operatorSessionProgressRender);
