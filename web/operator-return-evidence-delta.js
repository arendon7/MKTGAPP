const POST_W99_OPERATOR_RETURN_EVIDENCE_DELTA_SCHEMA='binario.marketing.operator-return-evidence-delta.v1';
const POST_W99_OPERATOR_RETURN_EVIDENCE_SNAPSHOT_SCHEMA='binario.marketing.operator-return-evidence-snapshot.v1';
const POST_W99_OPERATOR_RETURN_EVIDENCE_FIELDS=[
  'source','kind','rank','urgency','blocking','due_at','reason_code',
  'action.view','action.tab','action.entity_id','action.lead_id','action.contact_id','action.opportunity_id','action.campaign_id','action.media_id',
  'owner_resolution.state','owner_resolution.source_code','owner_resolution.owner_view','owner_resolution.target_kind','owner_resolution.target_id','owner_resolution.candidate_count',
  'owner_drift.state','owner_drift.source_code','owner_drift.owner_view','owner_drift.expected_target_kind'
];

function operatorReturnEvidenceText(value){return value===null||value===undefined?'':String(value).trim()}
function operatorReturnEvidenceCompany(){return typeof todayCompany==='function'?todayCompany():(typeof opsSelectedCompany==='function'?opsSelectedCompany():null)}
function operatorReturnEvidenceSnapshotKey(companyId){return `${POST_W99_OPERATOR_RETURN_EVIDENCE_SNAPSHOT_SCHEMA}:${companyId}`}
function operatorReturnEvidenceScalar(value){if(value===null||value===undefined)return null;if(typeof value==='boolean')return value;if(typeof value==='number')return Number.isFinite(value)?value:null;const text=String(value).trim();return text||null}
function operatorReturnEvidenceCount(value){if(typeof value==='boolean'||value===null||value===undefined)return null;if(Number.isInteger(value))return value;if(typeof value==='string'&&/^-?\d+$/.test(value.trim()))return Number(value.trim());return null}
function operatorReturnEvidenceProjection(row){
  if(!row||!operatorReturnEvidenceText(row.id))return null;
  const action=row.action||{},resolution=row.owner_resolution||{},drift=row.owner_drift||{};
  return{
    action_id:operatorReturnEvidenceText(row.id),
    source:operatorReturnEvidenceText(row.source)||null,
    kind:operatorReturnEvidenceText(row.kind)||null,
    rank:operatorReturnEvidenceScalar(row.rank),
    urgency:operatorReturnEvidenceText(row.urgency).toUpperCase()||null,
    blocking:typeof row.blocking==='boolean'?row.blocking:null,
    due_at:operatorReturnEvidenceScalar(row.due_at),
    reason_code:operatorReturnEvidenceText(row.reason?.code)||null,
    action:{
      view:operatorReturnEvidenceText(action.view)||null,
      tab:operatorReturnEvidenceText(action.tab)||null,
      entity_id:operatorReturnEvidenceText(action.entity_id)||null,
      lead_id:operatorReturnEvidenceText(action.lead_id)||null,
      contact_id:operatorReturnEvidenceText(action.contact_id)||null,
      opportunity_id:operatorReturnEvidenceText(action.opportunity_id)||null,
      campaign_id:operatorReturnEvidenceText(action.campaign_id)||null,
      media_id:operatorReturnEvidenceText(action.media_id)||null
    },
    owner_resolution:{
      state:operatorReturnEvidenceText(resolution.state).toUpperCase()||null,
      source_code:operatorReturnEvidenceText(resolution.source_code).toUpperCase()||null,
      owner_view:operatorReturnEvidenceText(resolution.owner_view)||null,
      target_kind:operatorReturnEvidenceText(resolution.target_kind).toUpperCase()||null,
      target_id:operatorReturnEvidenceText(resolution.target_id)||null,
      candidate_count:operatorReturnEvidenceCount(resolution.candidate_count)
    },
    owner_drift:{
      state:operatorReturnEvidenceText(drift.state).toUpperCase()||null,
      source_code:operatorReturnEvidenceText(drift.source_code).toUpperCase()||null,
      owner_view:operatorReturnEvidenceText(drift.owner_view)||null,
      expected_target_kind:operatorReturnEvidenceText(drift.expected_target_kind).toUpperCase()||null
    }
  }
}
function operatorReturnEvidenceAt(object,path){return path.split('.').reduce((value,key)=>value&&typeof value==='object'?value[key]:undefined,object)}
function operatorReturnEvidenceEqual(left,right){return left===right||(left===null&&right===undefined)||(left===undefined&&right===null)}
function operatorReturnEvidenceDiff(before,after){
  const changes=[];for(const path of POST_W99_OPERATOR_RETURN_EVIDENCE_FIELDS){const previous=operatorReturnEvidenceAt(before,path),current=operatorReturnEvidenceAt(after,path);if(!operatorReturnEvidenceEqual(previous,current))changes.push({field:path,before:previous??null,after:current??null})}return changes
}
function operatorReturnEvidenceWrite(companyId,row){
  const snapshot=operatorReturnEvidenceProjection(row);if(!companyId||!snapshot||!snapshot.action?.view)return null;
  const value={schema:POST_W99_OPERATOR_RETURN_EVIDENCE_SNAPSHOT_SCHEMA,company_id:String(companyId),action_id:snapshot.action_id,opened_at:new Date().toISOString(),snapshot};
  try{sessionStorage.setItem(operatorReturnEvidenceSnapshotKey(companyId),JSON.stringify(value))}catch(_err){}
  return value
}
function operatorReturnEvidenceRead(companyId,actionId){
  if(!companyId||!actionId)return null;try{const raw=sessionStorage.getItem(operatorReturnEvidenceSnapshotKey(companyId));if(!raw)return null;const value=JSON.parse(raw);if(!value||value.schema!==POST_W99_OPERATOR_RETURN_EVIDENCE_SNAPSHOT_SCHEMA||String(value.company_id)!==String(companyId)||String(value.action_id)!==String(actionId)||!value.snapshot||String(value.snapshot.action_id)!==String(actionId))return null;return value}catch(_err){return null}
}
function operatorReturnEvidenceClear(companyId,actionId){
  const value=operatorReturnEvidenceRead(companyId,actionId);if(!value)return;try{sessionStorage.removeItem(operatorReturnEvidenceSnapshotKey(companyId))}catch(_err){}
}
function operatorReturnEvidenceResolve(snapshotEnvelope,result,companyId,actionId){
  const base={schema:POST_W99_OPERATOR_RETURN_EVIDENCE_DELTA_SCHEMA,company_id:String(companyId||''),action_id:String(actionId||''),completion_claimed:false,causal_change_claimed:false,provider_freshness_claimed:false};
  if(!snapshotEnvelope)return{...base,state:'NO_OPEN_SNAPSHOT',changes:[]};
  if(String(snapshotEnvelope.company_id)!==String(companyId)||String(snapshotEnvelope.action_id)!==String(actionId))return{...base,state:'SNAPSHOT_SCOPE_MISMATCH',changes:[]};
  if(!result||String(result.action_id)!==String(actionId)||!operatorReturnEvidenceText(result.checked_at))return{...base,state:'RETURN_CONTEXT_MISMATCH',changes:[]};
  if(result.state==='NO_LONGER_PENDING')return{...base,state:'ACTION_NOT_PRESENT_AFTER_REREAD',checked_at:String(result.checked_at),opened_at:String(snapshotEnvelope.opened_at||''),before:snapshotEnvelope.snapshot,after:null,changes:[]};
  if(!['STILL_IN_TODAY','STILL_PENDING'].includes(String(result.state||'')))return{...base,state:'RETURN_STATE_UNSUPPORTED',checked_at:String(result.checked_at),changes:[]};
  const current=result.current_action,after=operatorReturnEvidenceProjection(current);if(!after||String(after.action_id)!==String(actionId))return{...base,state:'CURRENT_ACTION_SHAPE_INVALID',checked_at:String(result.checked_at),changes:[]};
  const changes=operatorReturnEvidenceDiff(snapshotEnvelope.snapshot,after);
  return{...base,state:changes.length?'FIELDS_CHANGED':'NO_WHITELISTED_CHANGE',checked_at:String(result.checked_at),opened_at:String(snapshotEnvelope.opened_at||''),observed_return_state:String(result.state),before:snapshotEnvelope.snapshot,after,changes}
}

function operatorReturnEvidenceLabel(field){return({source:'Fuente',kind:'Tipo de acción',rank:'Prioridad canónica',urgency:'Urgencia',blocking:'Bloqueo',due_at:'Fecha',reason_code:'Razón','action.view':'Módulo owner','action.tab':'Pestaña','action.entity_id':'Entidad','action.lead_id':'Lead','action.contact_id':'Contacto','action.opportunity_id':'Oportunidad','action.campaign_id':'Campaña','action.media_id':'Media','owner_resolution.state':'Resolución owner','owner_resolution.source_code':'Código owner','owner_resolution.owner_view':'Owner resuelto','owner_resolution.target_kind':'Tipo de target','owner_resolution.target_id':'Target exacto','owner_resolution.candidate_count':'Candidatos','owner_drift.state':'Estado de drift','owner_drift.source_code':'Código de drift','owner_drift.owner_view':'Owner de drift','owner_drift.expected_target_kind':'Target esperado'})[field]||field}
function operatorReturnEvidenceDisplay(value){if(value===null||value===undefined||value==='')return '—';if(value===true)return 'Sí';if(value===false)return 'No';return String(value)}
function operatorReturnEvidenceStyles(){
  if(document.querySelector('#post-w99-operator-return-evidence-delta-style'))return;
  const style=document.createElement('style');style.id='post-w99-operator-return-evidence-delta-style';style.textContent=`
.operator-return-evidence{border:1px solid #d9d3c9;border-radius:12px;background:#fff;padding:11px 13px;display:grid;gap:9px}.operator-return-evidence-copy{display:grid;gap:4px}.operator-return-evidence-copy strong{font-size:10px}.operator-return-evidence-copy p{font-size:8px;color:#706a61;margin:0;line-height:1.45}.operator-return-evidence-list{display:grid;gap:5px}.operator-return-evidence-row{display:grid;grid-template-columns:minmax(120px,.8fr) minmax(0,1fr) auto minmax(0,1fr);gap:7px;align-items:center;padding:7px 8px;border:1px dashed #ded8cf;border-radius:8px;font-size:8px}.operator-return-evidence-row strong{font-size:8px}.operator-return-evidence-arrow{color:#9a9388}.operator-return-evidence-note{font-size:7px;color:#827a70;line-height:1.45}@media(max-width:720px){.operator-return-evidence-row{grid-template-columns:1fr}.operator-return-evidence-arrow{display:none}}
`;document.head.append(style)
}
function operatorReturnEvidenceCopy(delta){
  if(delta.state==='FIELDS_CHANGED')return{title:'Cambios canónicos observados al volver',detail:`La misma action ID sigue pendiente, pero ${delta.changes.length} campo(s) del projection whitelist cambiaron entre la apertura y la relectura.`};
  if(delta.state==='NO_WHITELISTED_CHANGE')return{title:'Sin cambios en los campos canónicos observados',detail:'La misma action ID sigue pendiente y el projection whitelist permanece igual. La posición de la cola puede cambiar por separado y no se interpreta como estado de negocio.'};
  if(delta.state==='ACTION_NOT_PRESENT_AFTER_REREAD')return{title:'La action ID ya no está disponible para comparar',detail:'La relectura canónica no devolvió esa action ID. No hay fila posterior sobre la cual calcular un delta y esto no demuestra que la acción haya sido completada.'};
  return null
}
function operatorReturnEvidenceRender(){
  if(typeof marketingOpsState==='undefined'||marketingOpsState.view!=='today-execution')return;
  const root=document.querySelector('#marketing-ops-view');if(!root)return;root.querySelector('#post-w99-operator-return-evidence-delta')?.remove();
  const result=typeof postW99ExecutionReturnState==='undefined'?null:postW99ExecutionReturnState.lastResult,delta=result?.return_evidence_delta,company=operatorReturnEvidenceCompany();if(!delta||!company?.id||String(delta.company_id)!==String(company.id))return;
  const copyInfo=operatorReturnEvidenceCopy(delta);if(!copyInfo)return;operatorReturnEvidenceStyles();const section=opsEl('section','operator-return-evidence');section.id='post-w99-operator-return-evidence-delta';section.dataset.deltaState=delta.state;
  const copy=opsEl('div','operator-return-evidence-copy');copy.append(opsEl('span','eyebrow','REGRESO · EVIDENCIA ANTES / DESPUÉS'),opsEl('strong','',copyInfo.title),opsEl('p','',copyInfo.detail));section.append(copy);
  if(delta.state==='FIELDS_CHANGED'){const list=opsEl('div','operator-return-evidence-list');for(const change of delta.changes.slice(0,12)){const row=opsEl('div','operator-return-evidence-row');row.append(opsEl('strong','',operatorReturnEvidenceLabel(change.field)),opsEl('span','',operatorReturnEvidenceDisplay(change.before)),opsEl('span','operator-return-evidence-arrow','→'),opsEl('span','',operatorReturnEvidenceDisplay(change.after)));list.append(row)}section.append(list)}
  section.append(opsEl('div','operator-return-evidence-note','Comparación directa de campos locales whitelisted. No atribuye causalidad al trabajo realizado, no afirma completion y no declara frescura de providers.'));
  const returnCard=root.querySelector('#post-w99-execution-return-result'),progress=root.querySelector('#post-w99-operator-session-progress');if(returnCard)returnCard.insertAdjacentElement('afterend',section);else if(progress)progress.insertAdjacentElement('beforebegin',section);else root.prepend(section);
  if(returnCard){for(const button of returnCard.querySelectorAll('button')){if(operatorReturnEvidenceText(button.textContent)==='Cerrar mensaje'&&!button.dataset.postW99ReturnEvidenceDismiss){button.dataset.postW99ReturnEvidenceDismiss='1';button.addEventListener('click',()=>section.remove())}}}
}

const operatorReturnEvidenceBaseTodayOpen=globalThis.todayOpen;if(typeof operatorReturnEvidenceBaseTodayOpen==='function')globalThis.todayOpen=function(row){const company=operatorReturnEvidenceCompany();if(company?.id)operatorReturnEvidenceWrite(company.id,row);return operatorReturnEvidenceBaseTodayOpen.apply(this,arguments)};
const operatorReturnEvidenceBaseReturn=globalThis.executionReturnBackToToday;if(typeof operatorReturnEvidenceBaseReturn==='function')globalThis.executionReturnBackToToday=async function(context){
  const companyId=operatorReturnEvidenceText(context?.company_id),actionId=operatorReturnEvidenceText(context?.action_id),snapshot=operatorReturnEvidenceRead(companyId,actionId),previousCheckedAt=operatorReturnEvidenceText(typeof postW99ExecutionReturnState==='undefined'?null:postW99ExecutionReturnState.lastResult?.checked_at);
  const value=await operatorReturnEvidenceBaseReturn.apply(this,arguments),result=typeof postW99ExecutionReturnState==='undefined'?null:postW99ExecutionReturnState.lastResult,checkedAt=operatorReturnEvidenceText(result?.checked_at);
  if(result&&String(result.action_id||'')===actionId&&checkedAt&&checkedAt!==previousCheckedAt){result.return_evidence_delta=operatorReturnEvidenceResolve(snapshot,result,companyId,actionId);operatorReturnEvidenceClear(companyId,actionId)}
  queueMicrotask(operatorReturnEvidenceRender);return value
};
const operatorReturnEvidenceBaseRender=globalThis.renderMarketingOps;if(typeof operatorReturnEvidenceBaseRender==='function')globalThis.renderMarketingOps=function(){const value=operatorReturnEvidenceBaseRender.apply(this,arguments);operatorReturnEvidenceRender();return value};
window.addEventListener('marketing-ops-refreshed',operatorReturnEvidenceRender);window.addEventListener('pageshow',operatorReturnEvidenceRender);queueMicrotask(operatorReturnEvidenceRender);
