const POST_W99_CAMPAIGN_EXECUTION_OWNER_DRIFT_SCHEMA='binario.marketing.campaign-execution-owner-drift.v1';
function ownerDriftText(value){return value===null||value===undefined?'':String(value).trim()}
function ownerDriftMetadata(item){
  const drift=item?.owner_drift;if(!drift||drift.schema!==POST_W99_CAMPAIGN_EXECUTION_OWNER_DRIFT_SCHEMA)return null;
  const sourceCode=ownerDriftText(drift.source_code).toUpperCase(),ownerView=ownerDriftText(drift.owner_view),expected=ownerDriftText(drift.expected_target_kind).toUpperCase(),campaignId=ownerDriftText(drift.campaign_id),recovery=drift.recovery||{};
  const rules={FIX_PUBLICATION:['calendar','PUBLICATION'],SCHEDULE_OR_PUBLISH:['calendar','PUBLICATION'],REVIEW_PAID:['pauta','PAID_DRAFT'],FINISH_CREATIVE:['content','MEDIA'],PREPARE_DISTRIBUTION:['content','MEDIA']},rule=rules[sourceCode];
  if(!rule||drift.state!=='CANONICAL_TARGET_NOT_PRESENT'||ownerView!==rule[0]||expected!==rule[1]||!campaignId)return null;
  if(drift.target_selected!==false||drift.replacement_inferred!==false)return null;
  if(recovery.mode!=='OPEN_OWNER_AND_REVIEW_CURRENT_STATE'||ownerDriftText(recovery.view)!==ownerView||recovery.requires_human_review!==true)return null;
  return drift
}
const ownerDriftBaseOpen=globalThis.actionCenterOpen;
if(typeof ownerDriftBaseOpen==='function')globalThis.actionCenterOpen=function(item){
  const drift=ownerDriftMetadata(item);
  if(drift&&typeof opsToast==='function')opsToast('El objeto esperado ya no está en el estado canónico. Abrimos el módulo propietario para revisar el estado actual; no se eligió un reemplazo.');
  return ownerDriftBaseOpen.apply(this,arguments)
};
const ownerDriftBaseResolve=globalThis.controlHandoffResolve;
if(typeof ownerDriftBaseResolve==='function')globalThis.controlHandoffResolve=function(){
  const baseResult=ownerDriftBaseResolve.apply(this,arguments);
  if(baseResult?.state!=='TARGET_NOT_EXACT')return baseResult;
  if(typeof controlHandoffExecutionContext!=='function'||typeof controlHandoffActionRow!=='function')return baseResult;
  const execution=controlHandoffExecutionContext();if(!execution)return baseResult;
  const action=controlHandoffActionRow(execution);if(action?.state!=='ACTION_CONTEXT_RESOLVED'||!action.row)return baseResult;
  const drift=ownerDriftMetadata(action.row);if(!drift)return baseResult;
  return{schema:baseResult.schema||'binario.marketing.contextual-control-handoff.v1',state:'OWNER_STATE_DRIFT',execution,row:action.row,target:null,control:null,owner_drift:drift,explanation:`${ownerDriftText(drift.reason)||'El objeto esperado ya no está presente en el estado canónico.'} Revisa el módulo propietario y vuelve a Hoy; no se seleccionó otro registro.`}
};
const ownerDriftBaseMessage=globalThis.controlHandoffMessage;
if(typeof ownerDriftBaseMessage==='function')globalThis.controlHandoffMessage=function(result){
  if(result?.state==='OWNER_STATE_DRIFT')return{title:'Estado canónico cambió',detail:result.explanation,chip:'REVISAR OWNER'};
  return ownerDriftBaseMessage.apply(this,arguments)
};
if(typeof controlHandoffSchedule==='function')controlHandoffSchedule();
