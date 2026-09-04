const POST_W99_OPERATOR_SESSION_EVIDENCE_INTEGRATION_SCHEMA='binario.marketing.operator-session-evidence-integration.v1';
const POST_W99_OPERATOR_SESSION_EVIDENCE_STATES=new Set(['FIELDS_CHANGED','NO_WHITELISTED_CHANGE','ACTION_NOT_PRESENT_AFTER_REREAD']);
const POST_W99_OPERATOR_SESSION_EVIDENCE_FIELDS=new Set([
  'source','kind','rank','urgency','blocking','due_at','reason_code',
  'action.view','action.tab','action.entity_id','action.lead_id','action.contact_id','action.opportunity_id','action.campaign_id','action.media_id',
  'owner_resolution.state','owner_resolution.source_code','owner_resolution.owner_view','owner_resolution.target_kind','owner_resolution.target_id','owner_resolution.candidate_count',
  'owner_drift.state','owner_drift.source_code','owner_drift.owner_view','owner_drift.expected_target_kind'
]);

function operatorSessionEvidenceText(value){return value===null||value===undefined?'':String(value).trim()}
function operatorSessionEvidenceStored(event){
  const value=event?.return_evidence;if(!value||value.schema!==POST_W99_OPERATOR_SESSION_EVIDENCE_INTEGRATION_SCHEMA||!POST_W99_OPERATOR_SESSION_EVIDENCE_STATES.has(String(value.state||'')))return null;
  const fields=Array.isArray(value.changed_fields)?value.changed_fields.map(operatorSessionEvidenceText):[];
  if(fields.some(field=>!POST_W99_OPERATOR_SESSION_EVIDENCE_FIELDS.has(field))||new Set(fields).size!==fields.length)return null;
  const count=Number(value.change_count);if(!Number.isInteger(count)||count<0||count!==fields.length)return null;
  if(value.state==='FIELDS_CHANGED'&&count===0)return null;if(value.state!=='FIELDS_CHANGED'&&count!==0)return null;
  if(value.completion_claimed!==false||value.causal_change_claimed!==false||value.provider_freshness_claimed!==false)return null;
  return{...value,changed_fields:fields,change_count:count}
}
function operatorSessionEvidenceCompact(delta,companyId,actionId,checkedAt){
  const base={schema:POST_W99_OPERATOR_SESSION_EVIDENCE_INTEGRATION_SCHEMA,completion_claimed:false,causal_change_claimed:false,provider_freshness_claimed:false};
  if(!delta||!POST_W99_OPERATOR_SESSION_EVIDENCE_STATES.has(String(delta.state||'')))return null;
  if(String(delta.company_id||'')!==String(companyId)||String(delta.action_id||'')!==String(actionId)||operatorSessionEvidenceText(delta.checked_at)!==operatorSessionEvidenceText(checkedAt))return null;
  const state=String(delta.state),changes=Array.isArray(delta.changes)?delta.changes:[];
  if(state==='FIELDS_CHANGED'&&!changes.length)return null;
  if(state!=='FIELDS_CHANGED'&&changes.length)return null;
  const fields=[];
  for(const change of changes){const field=operatorSessionEvidenceText(change?.field);if(!POST_W99_OPERATOR_SESSION_EVIDENCE_FIELDS.has(field)||fields.includes(field))return null;fields.push(field)}
  return{...base,state,change_count:fields.length,changed_fields:fields,checked_at:String(checkedAt)}
}
function operatorSessionEvidenceSame(left,right){return Boolean(left&&right&&left.schema===right.schema&&left.state===right.state&&left.checked_at===right.checked_at&&left.change_count===right.change_count&&left.changed_fields.join('\u0000')===right.changed_fields.join('\u0000')&&left.completion_claimed===false&&left.causal_change_claimed===false&&left.provider_freshness_claimed===false)}
function operatorSessionEvidenceIntegrate(companyId,actionId,result){
  const base={schema:POST_W99_OPERATOR_SESSION_EVIDENCE_INTEGRATION_SCHEMA,company_id:String(companyId||''),action_id:String(actionId||''),state:'NOT_INTEGRATED'};
  if(typeof operatorSessionProgressRead!=='function'||typeof operatorSessionProgressWrite!=='function')return{...base,state:'SESSION_PROGRESS_UNAVAILABLE'};
  const checkedAt=operatorSessionEvidenceText(result?.checked_at);if(!companyId||!actionId||!result||String(result.action_id||'')!==String(actionId)||!checkedAt)return{...base,state:'RETURN_CONTEXT_MISMATCH'};
  const compact=operatorSessionEvidenceCompact(result.return_evidence_delta,companyId,actionId,checkedAt);if(!compact)return{...base,state:'DELTA_NOT_ELIGIBLE',checked_at:checkedAt};
  const session=operatorSessionProgressRead(companyId);if(!session||String(session.company_id||'')!==String(companyId)||!Array.isArray(session.events))return{...base,state:'SESSION_NOT_AVAILABLE',checked_at:checkedAt};
  const matches=session.events.map((event,index)=>({event,index})).filter(({event})=>event?.type==='RETURN_OBSERVED'&&String(event.action_id||'')===String(actionId)&&operatorSessionEvidenceText(event.checked_at)===checkedAt);
  if(matches.length!==1)return{...base,state:matches.length?'RETURN_EVENT_AMBIGUOUS':'RETURN_EVENT_NOT_FOUND',checked_at:checkedAt};
  const index=matches[0].index,event=matches[0].event,existing=operatorSessionEvidenceStored(event);
  if(operatorSessionEvidenceSame(existing,compact))return{...base,state:'ALREADY_INTEGRATED',checked_at:checkedAt,evidence:compact};
  const next={...session,events:session.events.map((row,i)=>i===index?{...row,return_evidence:compact}:row)};
  operatorSessionProgressWrite(next);
  const reread=operatorSessionProgressRead(companyId),written=(reread?.events||[]).filter(row=>row?.type==='RETURN_OBSERVED'&&String(row.action_id||'')===String(actionId)&&operatorSessionEvidenceText(row.checked_at)===checkedAt);
  if(written.length!==1||!operatorSessionEvidenceSame(operatorSessionEvidenceStored(written[0]),compact))return{...base,state:'WRITE_NOT_CONFIRMED',checked_at:checkedAt};
  return{...base,state:'INTEGRATED',checked_at:checkedAt,evidence:compact}
}
function operatorSessionEvidenceFieldLabel(field){return({source:'fuente',kind:'tipo',rank:'prioridad',urgency:'urgencia',blocking:'bloqueo',due_at:'fecha',reason_code:'razón','action.view':'owner','action.tab':'pestaña','action.entity_id':'entidad','action.lead_id':'lead','action.contact_id':'contacto','action.opportunity_id':'oportunidad','action.campaign_id':'campaña','action.media_id':'media','owner_resolution.state':'resolución owner','owner_resolution.source_code':'código owner','owner_resolution.owner_view':'owner resuelto','owner_resolution.target_kind':'tipo target','owner_resolution.target_id':'target exacto','owner_resolution.candidate_count':'candidatos','owner_drift.state':'drift','owner_drift.source_code':'código drift','owner_drift.owner_view':'owner drift','owner_drift.expected_target_kind':'target esperado'})[field]||field}
function operatorSessionEvidenceDetail(event){
  const evidence=operatorSessionEvidenceStored(event);if(!evidence)return'';
  if(evidence.state==='FIELDS_CHANGED'){const names=evidence.changed_fields.slice(0,4).map(operatorSessionEvidenceFieldLabel).join(', '),more=evidence.change_count>4?` +${evidence.change_count-4}`:'';return` Evidencia de sesión: ${evidence.change_count} campo(s) canónicos cambiaron${names?` (${names}${more})`:''}.`}
  if(evidence.state==='NO_WHITELISTED_CHANGE')return' Evidencia de sesión: sin cambios en el whitelist canónico entre apertura y relectura.';
  if(evidence.state==='ACTION_NOT_PRESENT_AFTER_REREAD')return' Evidencia de sesión: no hubo fila posterior para comparar porque esa action ID ya no apareció en la relectura.';
  return''
}

const operatorSessionEvidenceBaseDetail=globalThis.operatorSessionProgressEventDetail;if(typeof operatorSessionEvidenceBaseDetail==='function')globalThis.operatorSessionProgressEventDetail=function(event){return String(operatorSessionEvidenceBaseDetail.apply(this,arguments)||'')+operatorSessionEvidenceDetail(event)};
const operatorSessionEvidenceBaseReturn=globalThis.executionReturnBackToToday;if(typeof operatorSessionEvidenceBaseReturn==='function')globalThis.executionReturnBackToToday=async function(context){
  const value=await operatorSessionEvidenceBaseReturn.apply(this,arguments),result=typeof postW99ExecutionReturnState==='undefined'?null:postW99ExecutionReturnState.lastResult,companyId=operatorSessionEvidenceText(context?.company_id),actionId=operatorSessionEvidenceText(context?.action_id);
  if(result&&companyId&&actionId&&String(result.action_id||'')===actionId){result.session_evidence_integration=operatorSessionEvidenceIntegrate(companyId,actionId,result)}
  if(typeof operatorSessionProgressRender==='function')queueMicrotask(operatorSessionProgressRender);return value
};
