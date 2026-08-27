const POST_W99_CANONICAL_CHANGE_EVIDENCE_SCHEMA='binario.marketing.canonical-change-evidence.v1';
const POST_W99_CANONICAL_CHANGE_EVIDENCE_MAX_EVENTS=20;
const POST_W99_CANONICAL_CHANGE_EVIDENCE_FIELDS=[
  ['source','Fuente'],['kind','Tipo'],['rank','Prioridad canónica'],['urgency','Urgencia'],['blocking','Bloqueo'],['due_at','Fecha objetivo'],
  ['title','Título'],['detail','Detalle'],['reason_code','Código de razón'],['action_label','Acción'],['owner_view','Módulo propietario'],['owner_tab','Pestaña'],
  ['entity_id','Entity ID'],['lead_id','Lead ID'],['contact_id','Contact ID'],['opportunity_id','Opportunity ID'],['campaign_id','Campaign ID'],['media_id','Media ID'],
  ['owner_resolution_state','Resolución owner'],['owner_resolution_source_code','Código owner'],['owner_resolution_owner_view','Owner resuelto'],['owner_resolution_target_kind','Tipo de target'],['owner_resolution_target_id','Target ID'],['owner_resolution_candidate_count','Candidatos'],
  ['actionability_state','Actionability'],['owner_drift_state','Owner drift'],['requires_human_action','Requiere acción humana'],['read_only_recommendation','Recomendación read-only']
];
const POST_W99_CANONICAL_CHANGE_EVIDENCE_FIELD_NAMES=new Set(POST_W99_CANONICAL_CHANGE_EVIDENCE_FIELDS.map(([name])=>name));
const POST_W99_CANONICAL_CHANGE_EVIDENCE_RETURN_STATES=new Set(['STILL_IN_TODAY','STILL_PENDING','NO_LONGER_PENDING']);
const POST_W99_CANONICAL_CHANGE_EVIDENCE_STATES=new Set(['FIELDS_CHANGED','UNCHANGED','NO_LONGER_PRESENT']);

function canonicalChangeEvidenceText(value){return value===null||value===undefined?'':String(value).trim()}
function canonicalChangeEvidenceString(value){const text=canonicalChangeEvidenceText(value);return text||null}
function canonicalChangeEvidenceBool(value){return typeof value==='boolean'?value:null}
function canonicalChangeEvidenceNumber(value){return Number.isInteger(value)?value:null}
function canonicalChangeEvidenceScalar(value){return value===null||typeof value==='string'||typeof value==='number'||typeof value==='boolean'?value:null}
function canonicalChangeEvidenceCompany(){return typeof todayCompany==='function'?todayCompany():(typeof opsSelectedCompany==='function'?opsSelectedCompany():null)}
function canonicalChangeEvidenceKey(companyId){return `${POST_W99_CANONICAL_CHANGE_EVIDENCE_SCHEMA}:${companyId}`}
function canonicalChangeEvidenceLabel(field){return POST_W99_CANONICAL_CHANGE_EVIDENCE_FIELDS.find(([name])=>name===field)?.[1]||field}

function canonicalChangeEvidenceSnapshot(row){
  if(!row||!canonicalChangeEvidenceText(row.id))return null;
  const action=row.action||{},reason=row.reason||{},resolution=row.owner_resolution||{},actionability=row.actionability||{},drift=row.owner_drift||{};
  return{
    action_id:String(row.id),
    source:canonicalChangeEvidenceString(row.source),kind:canonicalChangeEvidenceString(row.kind),
    rank:canonicalChangeEvidenceNumber(row.rank),urgency:canonicalChangeEvidenceString(row.urgency),blocking:canonicalChangeEvidenceBool(row.blocking),due_at:canonicalChangeEvidenceString(row.due_at),
    title:canonicalChangeEvidenceString(row.title),detail:canonicalChangeEvidenceString(row.detail),reason_code:canonicalChangeEvidenceString(reason.code),
    action_label:canonicalChangeEvidenceString(action.label),owner_view:canonicalChangeEvidenceString(action.view),owner_tab:canonicalChangeEvidenceString(action.tab),
    entity_id:canonicalChangeEvidenceString(action.entity_id),lead_id:canonicalChangeEvidenceString(action.lead_id),contact_id:canonicalChangeEvidenceString(action.contact_id),opportunity_id:canonicalChangeEvidenceString(action.opportunity_id),campaign_id:canonicalChangeEvidenceString(action.campaign_id),media_id:canonicalChangeEvidenceString(action.media_id),
    owner_resolution_state:canonicalChangeEvidenceString(resolution.state),owner_resolution_source_code:canonicalChangeEvidenceString(resolution.source_code),owner_resolution_owner_view:canonicalChangeEvidenceString(resolution.owner_view),owner_resolution_target_kind:canonicalChangeEvidenceString(resolution.target_kind),owner_resolution_target_id:canonicalChangeEvidenceString(resolution.target_id),owner_resolution_candidate_count:canonicalChangeEvidenceScalar(resolution.candidate_count),
    actionability_state:canonicalChangeEvidenceString(actionability.state),owner_drift_state:canonicalChangeEvidenceString(drift.state),
    requires_human_action:canonicalChangeEvidenceBool(row.requires_human_action),read_only_recommendation:canonicalChangeEvidenceBool(row.read_only_recommendation)
  }
}
function canonicalChangeEvidenceValidSnapshot(snapshot){
  if(!snapshot||!canonicalChangeEvidenceText(snapshot.action_id))return false;
  for(const [field] of POST_W99_CANONICAL_CHANGE_EVIDENCE_FIELDS){const value=snapshot[field];if(value!==null&&!['string','number','boolean'].includes(typeof value))return false}
  return true
}
function canonicalChangeEvidenceDiff(before,after){
  if(!canonicalChangeEvidenceValidSnapshot(before)||!canonicalChangeEvidenceValidSnapshot(after)||String(before.action_id)!==String(after.action_id))return null;
  const changes=[];
  for(const [field,label] of POST_W99_CANONICAL_CHANGE_EVIDENCE_FIELDS){
    const left=canonicalChangeEvidenceScalar(before[field]),right=canonicalChangeEvidenceScalar(after[field]);
    if(left!==right)changes.push({field,label,before:left,after:right})
  }
  return changes
}
function canonicalChangeEvidenceBuildEvent(pending,result){
  if(!pending||!canonicalChangeEvidenceValidSnapshot(pending.snapshot)||!result||!POST_W99_CANONICAL_CHANGE_EVIDENCE_RETURN_STATES.has(String(result.state||'')))return null;
  const actionId=canonicalChangeEvidenceText(result.action_id),checkedAt=canonicalChangeEvidenceText(result.checked_at);
  if(!actionId||!checkedAt||actionId!==String(pending.action_id||'')||actionId!==String(pending.snapshot.action_id||''))return null;
  let evidenceState='NO_LONGER_PRESENT',changes=[];
  if(result.state!=='NO_LONGER_PENDING'){
    const after=canonicalChangeEvidenceSnapshot(result.current_action);if(!after||String(after.action_id)!==actionId)return null;
    const diff=canonicalChangeEvidenceDiff(pending.snapshot,after);if(diff===null)return null;
    evidenceState=diff.length?'FIELDS_CHANGED':'UNCHANGED';changes=diff
  }
  return{action_id:actionId,title:canonicalChangeEvidenceText(result.title)||canonicalChangeEvidenceText(pending.title)||actionId,checked_at:checkedAt,return_state:String(result.state),evidence_state:evidenceState,changes:changes.slice(0,POST_W99_CANONICAL_CHANGE_EVIDENCE_FIELDS.length)}
}
function canonicalChangeEvidenceValidChange(change){return Boolean(change&&POST_W99_CANONICAL_CHANGE_EVIDENCE_FIELD_NAMES.has(change.field)&&canonicalChangeEvidenceLabel(change.field)===change.label&&['string','number','boolean','object'].includes(typeof change.before)&&['string','number','boolean','object'].includes(typeof change.after)&&change.before!==change.after)}
function canonicalChangeEvidenceValidEvent(event){
  if(!event||!canonicalChangeEvidenceText(event.action_id)||!canonicalChangeEvidenceText(event.checked_at)||!POST_W99_CANONICAL_CHANGE_EVIDENCE_RETURN_STATES.has(String(event.return_state||''))||!POST_W99_CANONICAL_CHANGE_EVIDENCE_STATES.has(String(event.evidence_state||''))||!Array.isArray(event.changes))return false;
  if(event.evidence_state==='NO_LONGER_PRESENT'&&event.return_state!=='NO_LONGER_PENDING')return false;
  if(event.evidence_state==='UNCHANGED'&&event.changes.length)return false;
  if(event.evidence_state==='FIELDS_CHANGED'&&(!event.changes.length||!event.changes.every(canonicalChangeEvidenceValidChange)))return false;
  if(event.evidence_state!=='FIELDS_CHANGED'&&event.changes.some(change=>!canonicalChangeEvidenceValidChange(change)))return false;
  return true
}
function canonicalChangeEvidenceRead(companyId){
  if(!companyId)return null;
  try{
    const raw=sessionStorage.getItem(canonicalChangeEvidenceKey(companyId));if(!raw)return null;
    const value=JSON.parse(raw);if(!value||value.schema!==POST_W99_CANONICAL_CHANGE_EVIDENCE_SCHEMA||String(value.company_id)!==String(companyId)||!Array.isArray(value.events)){sessionStorage.removeItem(canonicalChangeEvidenceKey(companyId));return null}
    value.events=value.events.filter(canonicalChangeEvidenceValidEvent).slice(-POST_W99_CANONICAL_CHANGE_EVIDENCE_MAX_EVENTS);
    if(value.pending&&(!canonicalChangeEvidenceValidSnapshot(value.pending.snapshot)||String(value.pending.action_id||'')!==String(value.pending.snapshot.action_id||'')))value.pending=null;
    return value
  }catch(_err){try{sessionStorage.removeItem(canonicalChangeEvidenceKey(companyId))}catch(_ignore){}return null}
}
function canonicalChangeEvidenceWrite(value){
  if(!value?.company_id)return null;
  value.events=(value.events||[]).filter(canonicalChangeEvidenceValidEvent).slice(-POST_W99_CANONICAL_CHANGE_EVIDENCE_MAX_EVENTS);
  try{sessionStorage.setItem(canonicalChangeEvidenceKey(value.company_id),JSON.stringify(value))}catch(_err){}
  return value
}
function canonicalChangeEvidenceEnsure(companyId){return canonicalChangeEvidenceRead(companyId)||canonicalChangeEvidenceWrite({schema:POST_W99_CANONICAL_CHANGE_EVIDENCE_SCHEMA,company_id:String(companyId),events:[],pending:null})}
function canonicalChangeEvidenceCapture(row){
  const company=canonicalChangeEvidenceCompany(),snapshot=canonicalChangeEvidenceSnapshot(row);if(!company?.id||!snapshot)return;
  const value=canonicalChangeEvidenceEnsure(company.id);if(!value)return;
  value.pending={action_id:snapshot.action_id,title:canonicalChangeEvidenceText(row.title)||snapshot.action_id,opened_at:new Date().toISOString(),snapshot};canonicalChangeEvidenceWrite(value)
}
function canonicalChangeEvidenceObserveReturn(companyId,actionId,previousCheckedAt=''){
  if(typeof postW99ExecutionReturnState==='undefined'||!companyId||!actionId)return null;
  const company=canonicalChangeEvidenceCompany(),result=postW99ExecutionReturnState.lastResult,checkedAt=canonicalChangeEvidenceText(result?.checked_at);
  if(!company?.id||String(company.id)!==String(companyId)||!result||String(result.action_id)!==String(actionId)||!checkedAt||checkedAt===canonicalChangeEvidenceText(previousCheckedAt))return null;
  const value=canonicalChangeEvidenceRead(companyId),pending=value?.pending;if(!pending||String(pending.action_id)!==String(actionId))return null;
  const event=canonicalChangeEvidenceBuildEvent(pending,result);if(!event)return null;
  const duplicate=(value.events||[]).some(item=>item.action_id===event.action_id&&item.checked_at===event.checked_at);if(!duplicate)value.events.push(event);
  value.pending=null;canonicalChangeEvidenceWrite(value);return event
}
function canonicalChangeEvidenceValue(value){if(value===null)return '—';if(value===true)return 'Sí';if(value===false)return 'No';return String(value)}
function canonicalChangeEvidenceStateLabel(state){return({FIELDS_CHANGED:'Cambios observados',UNCHANGED:'Sin cambios en whitelist',NO_LONGER_PRESENT:'Ya no presente'})[state]||'Evidencia inválida'}
function canonicalChangeEvidenceEventDetail(event){
  if(event.evidence_state==='NO_LONGER_PRESENT')return 'La action ID dejó de aparecer en la cola canónica. Esto no identifica la causa ni prueba que la tarea esté completada.';
  if(event.evidence_state==='UNCHANGED')return 'Los campos certificados de esta action ID conservaron los mismos valores en la relectura. Esto no afirma que ningún otro dato del owner haya cambiado.';
  return 'Cambios observados en la representación canónica de Action Center. Se muestran como evidencia descriptiva, sin atribuir causa ni resultado de negocio.'
}
function canonicalChangeEvidenceStyles(){
  if(document.querySelector('#post-w99-canonical-change-evidence-style'))return;
  const style=document.createElement('style');style.id='post-w99-canonical-change-evidence-style';style.textContent=`
.canonical-change-evidence{border:1px solid #ddd8cf;background:#fff;border-radius:14px;padding:13px;display:grid;gap:10px}.canonical-change-evidence-head{display:flex;justify-content:space-between;align-items:flex-end;gap:10px}.canonical-change-evidence-head h3{margin:0;font-size:14px}.canonical-change-evidence-stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px}.canonical-change-evidence-stat{padding:9px;border:1px solid #e5e0d8;border-radius:9px;background:#faf9f6;display:grid;gap:2px}.canonical-change-evidence-stat strong{font-size:16px}.canonical-change-evidence-stat span{font-size:7px;color:#777168}.canonical-change-evidence-list{display:grid;gap:7px}.canonical-change-evidence-row{padding:10px;border:1px dashed #d8d2c8;border-radius:10px;display:grid;gap:6px}.canonical-change-evidence-row-head{display:flex;justify-content:space-between;gap:8px;align-items:center}.canonical-change-evidence-row-head strong{font-size:9px}.canonical-change-evidence-chip{font-size:7px;padding:4px 6px;border-radius:999px;background:#f1eee8;white-space:nowrap}.canonical-change-evidence-row p{font-size:8px;color:#706a61;margin:0;line-height:1.45}.canonical-change-evidence-diff{display:grid;gap:4px}.canonical-change-evidence-diff div{font-size:8px;padding:5px 7px;border-radius:7px;background:#f7f5f1;color:#5f5a52}.canonical-change-evidence-note{padding:9px 10px;border-radius:9px;background:#f5f2eb;color:#756f65;font-size:8px;line-height:1.45}@media(max-width:720px){.canonical-change-evidence-head{display:grid}.canonical-change-evidence-stats{grid-template-columns:1fr}.canonical-change-evidence-row-head{align-items:flex-start}}
`;document.head.append(style)
}
function canonicalChangeEvidenceStat(value,label){const node=opsEl('div','canonical-change-evidence-stat');node.append(opsEl('strong','',String(value||0)),opsEl('span','',label));return node}
function canonicalChangeEvidenceReset(companyId){try{sessionStorage.removeItem(canonicalChangeEvidenceKey(companyId))}catch(_err){}if(typeof opsToast==='function')opsToast('Se borró solo la evidencia canónica de esta sesión; ningún dato de negocio cambió.');canonicalChangeEvidenceRender()}
function canonicalChangeEvidenceRender(){
  if(typeof marketingOpsState==='undefined'||marketingOpsState.view!=='today-execution')return;
  const company=canonicalChangeEvidenceCompany(),root=document.querySelector('#marketing-ops-view');if(!company?.id||!root)return;
  root.querySelector('#post-w99-canonical-change-evidence')?.remove();const value=canonicalChangeEvidenceRead(company.id);if(!value?.events?.length)return;
  canonicalChangeEvidenceStyles();const events=value.events.slice(-5).reverse(),section=opsEl('section','canonical-change-evidence');section.id='post-w99-canonical-change-evidence';
  const head=opsEl('div','canonical-change-evidence-head'),copy=opsEl('div');copy.append(opsEl('p','eyebrow','SESIÓN · EVIDENCIA CANÓNICA'),opsEl('h3','','Qué cambió en Action Center después de volver'));const reset=opsEl('button','','Borrar evidencia de cambios');reset.type='button';reset.addEventListener('click',()=>canonicalChangeEvidenceReset(company.id));head.append(copy,reset);section.append(head);
  const count=state=>value.events.filter(event=>event.evidence_state===state).length,stats=opsEl('div','canonical-change-evidence-stats');stats.append(canonicalChangeEvidenceStat(count('FIELDS_CHANGED'),'CON CAMBIOS'),canonicalChangeEvidenceStat(count('UNCHANGED'),'SIN CAMBIOS EN WHITELIST'),canonicalChangeEvidenceStat(count('NO_LONGER_PRESENT'),'YA NO PRESENTES'));section.append(stats);
  const list=opsEl('div','canonical-change-evidence-list');for(const event of events){const row=opsEl('article','canonical-change-evidence-row'),rowHead=opsEl('div','canonical-change-evidence-row-head');rowHead.append(opsEl('strong','',event.title||event.action_id),opsEl('span','canonical-change-evidence-chip',canonicalChangeEvidenceStateLabel(event.evidence_state)));row.append(rowHead,opsEl('p','',canonicalChangeEvidenceEventDetail(event)));if(event.changes.length){const diff=opsEl('div','canonical-change-evidence-diff');event.changes.slice(0,4).forEach(change=>diff.append(opsEl('div','',`${change.label}: ${canonicalChangeEvidenceValue(change.before)} → ${canonicalChangeEvidenceValue(change.after)}`)));if(event.changes.length>4)diff.append(opsEl('div','',`+ ${event.changes.length-4} cambio(s) adicional(es) en la whitelist`));row.append(diff)}list.append(row)}section.append(list,opsEl('div','canonical-change-evidence-note','Esta evidencia compara solo campos certificados de la fila de Action Center. No prueba causalidad, ejecución correcta ni completitud; el módulo propietario sigue siendo la autoridad de negocio.'));
  const sessionPanel=root.querySelector('#post-w99-operator-session-progress'),resultCard=root.querySelector('#post-w99-execution-return-result'),hero=root.querySelector('.today-hero');if(sessionPanel)sessionPanel.insertAdjacentElement('afterend',section);else if(resultCard)resultCard.insertAdjacentElement('afterend',section);else if(hero)hero.insertAdjacentElement('afterend',section);else root.prepend(section)
}

const canonicalChangeEvidenceBaseTodayOpen=globalThis.todayOpen;if(typeof canonicalChangeEvidenceBaseTodayOpen==='function')globalThis.todayOpen=function(row){canonicalChangeEvidenceCapture(row);return canonicalChangeEvidenceBaseTodayOpen.apply(this,arguments)};
const canonicalChangeEvidenceBaseReturn=globalThis.executionReturnBackToToday;if(typeof canonicalChangeEvidenceBaseReturn==='function')globalThis.executionReturnBackToToday=async function(context){const companyId=canonicalChangeEvidenceText(context?.company_id),actionId=canonicalChangeEvidenceText(context?.action_id),previousCheckedAt=canonicalChangeEvidenceText(typeof postW99ExecutionReturnState==='undefined'?null:postW99ExecutionReturnState.lastResult?.checked_at),value=await canonicalChangeEvidenceBaseReturn.apply(this,arguments);canonicalChangeEvidenceObserveReturn(companyId,actionId,previousCheckedAt);queueMicrotask(canonicalChangeEvidenceRender);return value};
const canonicalChangeEvidenceBaseRender=globalThis.renderMarketingOps;if(typeof canonicalChangeEvidenceBaseRender==='function')globalThis.renderMarketingOps=function(){const value=canonicalChangeEvidenceBaseRender.apply(this,arguments);canonicalChangeEvidenceRender();return value};
if(typeof window!=='undefined'){window.addEventListener('marketing-ops-refreshed',canonicalChangeEvidenceRender);window.addEventListener('pageshow',canonicalChangeEvidenceRender);queueMicrotask(canonicalChangeEvidenceRender)}
