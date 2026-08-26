const POST_W99_CAMPAIGN_MEDIA_CANDIDATE_SELECTION_SCHEMA='binario.marketing.campaign-media-candidate-selection-handoff.v1';
const postW99CampaignMediaCandidateSelectionState={active:null};

function mediaCandidateSelectionText(value){return value===null||value===undefined?'':String(value).trim()}
function mediaCandidateSelectionCompany(){return typeof opsSelectedCompany==='function'?opsSelectedCompany():null}
function mediaCandidateSelectionResolution(item){
  const value=item?.owner_resolution,kind=mediaCandidateSelectionText(value?.target_kind).toUpperCase(),state=mediaCandidateSelectionText(value?.state).toUpperCase(),code=mediaCandidateSelectionText(value?.source_code).toUpperCase();
  if(state!=='AMBIGUOUS_TARGET'||kind!=='MEDIA'||!['FINISH_CREATIVE','PREPARE_DISTRIBUTION'].includes(code))return null;
  return value
}
function mediaCandidateSelectionValidation(item){
  const resolution=mediaCandidateSelectionResolution(item);if(!resolution)return null;
  const ownerView=mediaCandidateSelectionText(resolution.owner_view),sourceCode=mediaCandidateSelectionText(resolution.source_code).toUpperCase(),candidates=Array.isArray(resolution.candidates)?resolution.candidates:[],ids=candidates.map(row=>mediaCandidateSelectionText(row?.id)),unique=new Set(ids);
  let reason=null;
  if(ownerView!=='content')reason='La ambigüedad MEDIA no declara Creative Studio como owner exacto.';
  else if(!['FINISH_CREATIVE','PREPARE_DISTRIBUTION'].includes(sourceCode))reason='El código W64 no pertenece al contrato MEDIA seleccionable.';
  else if(candidates.length<2)reason='AMBIGUOUS_TARGET MEDIA requiere al menos dos candidatos.';
  else if(ids.some(id=>!id))reason='Existe un creativo candidato sin media_id canónico.';
  else if(unique.size!==ids.length)reason='La lista MEDIA contiene IDs duplicados y no representa opciones distintas.';
  else if(Number(resolution.candidate_count)!==candidates.length)reason='candidate_count no coincide con los creativos visibles.';
  return{resolution,ownerView,sourceCode,candidates,valid:!reason,reason}
}
function mediaCandidateSelectionFromToday(item){
  if(typeof marketingOpsState==='undefined'||marketingOpsState?.view!=='today-execution')return false;
  const active=typeof postW99ExecutionReturnState!=='undefined'?postW99ExecutionReturnState.active:null;
  return Boolean(active?.action_id&&String(active.action_id)===String(item?.id||''))
}
function mediaCandidateSelectionStyles(){if(document.querySelector('#post-w99-campaign-media-candidate-selection-style'))return;const style=document.createElement('style');style.id='post-w99-campaign-media-candidate-selection-style';style.textContent=`
.media-candidate-selection-backdrop{position:fixed;inset:0;z-index:10140;background:rgba(18,17,15,.58);display:grid;place-items:center;padding:18px}.media-candidate-selection-dialog{width:min(780px,100%);max-height:min(760px,calc(100vh - 36px));overflow:auto;border:1px solid #d8d2c8;border-radius:16px;background:#fff;box-shadow:0 28px 80px rgba(0,0,0,.3);padding:16px;display:grid;gap:12px}.media-candidate-selection-head{display:grid;gap:5px}.media-candidate-selection-head h3{margin:0;font-size:18px}.media-candidate-selection-head p{margin:0;font-size:9px;color:#706a61;line-height:1.5}.media-candidate-selection-list{display:grid;gap:8px}.media-candidate-selection-option{border:1px solid #ded9d0;border-radius:11px;background:#fbfaf7;padding:11px;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px;align-items:center}.media-candidate-selection-copy{display:grid;gap:4px;min-width:0}.media-candidate-selection-copy strong{font-size:10px}.media-candidate-selection-copy span{font-size:8px;color:#706a61}.media-candidate-selection-id{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:7px!important;word-break:break-all;color:#8a8379!important}.media-candidate-selection-meta{display:flex;gap:5px;flex-wrap:wrap}.media-candidate-selection-chip{display:inline-flex;padding:3px 6px;border-radius:999px;background:#efebe4;font-size:7px;color:#615b52}.media-candidate-selection-actions{display:flex;justify-content:flex-end;gap:7px;flex-wrap:wrap}.media-candidate-selection-safety{padding:9px 10px;border-radius:9px;background:#f5f2eb;color:#746e65;font-size:8px;line-height:1.45}.media-candidate-selection-error{padding:11px;border:1px solid #cfc7bb;border-radius:10px;background:#f8f5ef;font-size:9px;color:#5f594f}@media(max-width:700px){.media-candidate-selection-option{grid-template-columns:1fr}.media-candidate-selection-actions{justify-content:flex-start}}
`;document.head.append(style)}
function mediaCandidateSelectionClose(){document.querySelector('#post-w99-campaign-media-candidate-selection')?.remove();postW99CampaignMediaCandidateSelectionState.active=null}
function mediaCandidateSelectionTitle(validation,candidate,index){return mediaCandidateSelectionText(candidate?.name)||`Creativo ${index+1}`}
function mediaCandidateSelectionMeta(candidate){const values=[];for(const [key,label] of [['stage','Estado'],['kind','Tipo']]){const value=mediaCandidateSelectionText(candidate?.[key]);if(value)values.push([label,value])}return values}
function mediaCandidateSelectionExactItem(item,validation,candidate){
  const targetId=mediaCandidateSelectionText(candidate?.id);if(!validation?.valid||!targetId||!validation.candidates.some(row=>mediaCandidateSelectionText(row?.id)===targetId))return null;
  const sourceResolution={...(item?.owner_resolution||{})},action={...(item?.action||{})};action.view='content';action.tab=null;action.media_id=targetId;action.entity_id=null;action.label=validation.sourceCode==='FINISH_CREATIVE'?'Abrir creativo elegido':'Abrir creativo para distribución';
  const navigationResolution={...sourceResolution,state:'EXACT_TARGET',target_id:targetId,candidate_count:1,candidates:[{...candidate}],reason:'Una persona eligió explícitamente este media_id entre candidatos canónicos. Esta exactitud existe solo para la navegación actual y no cambia la resolución backend.',navigation_only:true,selected_by:'HUMAN_CLICK',persisted:false,source_resolution_state:'AMBIGUOUS_TARGET'};
  return{...item,action,source_owner_resolution:sourceResolution,owner_resolution:navigationResolution,explicit_media_selection:{schema:POST_W99_CAMPAIGN_MEDIA_CANDIDATE_SELECTION_SCHEMA,source_resolution_state:'AMBIGUOUS_TARGET',source_code:validation.sourceCode,owner_view:'content',target_kind:'MEDIA',target_id:targetId,selected_by:'HUMAN_CLICK',persisted:false,priority_inferred:false,recommendation_made:false,selected_at:new Date().toISOString()}}
}
const mediaCandidateSelectionBaseOpen=globalThis.actionCenterOpen;
function mediaCandidateSelectionChoose(candidate){
  const active=postW99CampaignMediaCandidateSelectionState.active;if(!active?.validation?.valid)return;
  const company=mediaCandidateSelectionCompany();if(!company?.id||String(company.id)!==String(active.companyId||'')){mediaCandidateSelectionClose();if(typeof opsToast==='function')opsToast('La empresa cambió; vuelve a abrir la acción desde el estado actual.');return}
  const exact=mediaCandidateSelectionExactItem(active.item,active.validation,candidate);if(!exact)return;
  const fromToday=Boolean(active.fromToday);mediaCandidateSelectionClose();
  if(fromToday&&typeof executionReturnCapture==='function')executionReturnCapture(exact);
  if(typeof mediaCandidateSelectionBaseOpen==='function')return mediaCandidateSelectionBaseOpen(exact);
  if(typeof opsShowView==='function')return opsShowView('content')
}
function mediaCandidateSelectionRender(item,validation,fromToday){
  mediaCandidateSelectionStyles();mediaCandidateSelectionClose();const company=mediaCandidateSelectionCompany();postW99CampaignMediaCandidateSelectionState.active={item,validation,fromToday,companyId:company?.id||null};
  const backdrop=opsEl('div','media-candidate-selection-backdrop');backdrop.id='post-w99-campaign-media-candidate-selection';backdrop.setAttribute('role','dialog');backdrop.setAttribute('aria-modal','true');backdrop.setAttribute('aria-label','Elegir creativo exacto');
  const dialog=opsEl('section','media-candidate-selection-dialog'),head=opsEl('div','media-candidate-selection-head'),title=validation?.sourceCode==='FINISH_CREATIVE'?'¿Qué creativo quieres completar?':'¿Qué creativo quieres preparar para distribución?';head.append(opsEl('p','eyebrow','PLAN DE HOY · ELIGE EL CREATIVO'),opsEl('h3','',title),opsEl('p','',validation?.resolution?.reason||'Hay varios creativos canónicos elegibles y el sistema no elegirá uno por posición.'));dialog.append(head);
  if(validation?.valid){const list=opsEl('div','media-candidate-selection-list');validation.candidates.forEach((candidate,index)=>{const option=opsEl('article','media-candidate-selection-option'),copy=opsEl('div','media-candidate-selection-copy');copy.append(opsEl('strong','',mediaCandidateSelectionTitle(validation,candidate,index)),opsEl('span','media-candidate-selection-id',mediaCandidateSelectionText(candidate?.id)));const meta=opsEl('div','media-candidate-selection-meta');mediaCandidateSelectionMeta(candidate).forEach(([label,value])=>meta.append(opsEl('span','media-candidate-selection-chip',`${label}: ${value}`)));if(meta.childNodes.length)copy.append(meta);const choose=opsEl('button','primary','Elegir este creativo');choose.type='button';choose.addEventListener('click',()=>mediaCandidateSelectionChoose(candidate));option.append(copy,choose);list.append(option)});dialog.append(list,opsEl('div','media-candidate-selection-safety','Los creativos se muestran en el orden recibido del estado canónico. Ese orden no es ranking ni recomendación. El click solo fija el media_id para esta apertura; no completa la pieza, no cambia su estado, no publica y no crea distribución.'))}else dialog.append(opsEl('div','media-candidate-selection-error',`Selección bloqueada: ${validation?.reason||'el contrato MEDIA ambiguo no es válido.'}`));
  const actions=opsEl('div','media-candidate-selection-actions'),cancel=opsEl('button','','Cancelar sin abrir');cancel.type='button';cancel.addEventListener('click',mediaCandidateSelectionClose);actions.append(cancel);dialog.append(actions);backdrop.append(dialog);document.body.append(backdrop)
}
if(typeof mediaCandidateSelectionBaseOpen==='function')globalThis.actionCenterOpen=function(item){
  const validation=mediaCandidateSelectionValidation(item);if(!validation)return mediaCandidateSelectionBaseOpen.apply(this,arguments);
  const fromToday=mediaCandidateSelectionFromToday(item);if(fromToday&&typeof executionReturnForget==='function')executionReturnForget();mediaCandidateSelectionRender(item,validation,fromToday);return undefined
};
window.addEventListener('keydown',event=>{if(event.key==='Escape'&&postW99CampaignMediaCandidateSelectionState.active)mediaCandidateSelectionClose()});
window.addEventListener('marketing-ops-refreshed',mediaCandidateSelectionClose);window.addEventListener('pagehide',mediaCandidateSelectionClose);
