const POST_W99_CAMPAIGN_EXECUTION_CANDIDATE_SELECTOR_SCHEMA='binario.marketing.campaign-execution-candidate-selector.v1';
const postW99CampaignExecutionCandidateSelectorState={active:null};

function candidateSelectorText(value){return value===null||value===undefined?'':String(value).trim()}
function candidateSelectorCompany(){return typeof opsSelectedCompany==='function'?opsSelectedCompany():null}
function candidateSelectorResolution(item){const value=item?.owner_resolution;return value&&String(value.state||'')==='AMBIGUOUS_TARGET'?value:null}
function candidateSelectorSupportedTarget(kind){return ['PUBLICATION','PAID_DRAFT'].includes(String(kind||'').toUpperCase())}
function candidateSelectorValidation(item){
  const resolution=candidateSelectorResolution(item);if(!resolution)return null;
  const ownerView=candidateSelectorText(resolution.owner_view),targetKind=candidateSelectorText(resolution.target_kind).toUpperCase(),candidates=Array.isArray(resolution.candidates)?resolution.candidates:[],ids=candidates.map(row=>candidateSelectorText(row?.id)),unique=new Set(ids);
  let reason=null;
  if(!ownerView)reason='El resolver no declaró owner_view.';
  else if(!candidateSelectorSupportedTarget(targetKind))reason='El tipo de target ambiguo no pertenece al contrato seleccionable actual.';
  else if(candidates.length<2)reason='AMBIGUOUS_TARGET requiere al menos dos candidatos.';
  else if(ids.some(id=>!id))reason='Existe un candidato sin ID canónico.';
  else if(unique.size!==ids.length)reason='La lista contiene IDs duplicados y no representa opciones distintas.';
  else if(Number(resolution.candidate_count)!==candidates.length)reason='candidate_count no coincide con la lista visible.';
  return{resolution,ownerView,targetKind,candidates,valid:!reason,reason};
}
function candidateSelectorStyles(){if(document.querySelector('#post-w99-campaign-execution-candidate-selector-style'))return;const style=document.createElement('style');style.id='post-w99-campaign-execution-candidate-selector-style';style.textContent=`
.candidate-selector-backdrop{position:fixed;inset:0;z-index:10120;background:rgba(18,17,15,.56);display:grid;place-items:center;padding:18px}.candidate-selector-dialog{width:min(780px,100%);max-height:min(760px,calc(100vh - 36px));overflow:auto;border:1px solid #d8d2c8;border-radius:16px;background:#fff;box-shadow:0 28px 80px rgba(0,0,0,.3);padding:16px;display:grid;gap:12px}.candidate-selector-head{display:grid;gap:5px}.candidate-selector-head h3{margin:0;font-size:18px}.candidate-selector-head p{margin:0;font-size:9px;color:#706a61;line-height:1.5}.candidate-selector-list{display:grid;gap:8px}.candidate-selector-option{border:1px solid #ded9d0;border-radius:11px;background:#fbfaf7;padding:11px;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px;align-items:center}.candidate-selector-copy{display:grid;gap:4px;min-width:0}.candidate-selector-copy strong{font-size:10px}.candidate-selector-copy span{font-size:8px;color:#706a61}.candidate-selector-id{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:7px!important;word-break:break-all;color:#8a8379!important}.candidate-selector-meta{display:flex;gap:5px;flex-wrap:wrap}.candidate-selector-chip{display:inline-flex;padding:3px 6px;border-radius:999px;background:#efebe4;font-size:7px;color:#615b52}.candidate-selector-actions{display:flex;justify-content:flex-end;gap:7px;flex-wrap:wrap}.candidate-selector-safety{padding:9px 10px;border-radius:9px;background:#f5f2eb;color:#746e65;font-size:8px;line-height:1.45}.candidate-selector-error{padding:11px;border:1px solid #cfc7bb;border-radius:10px;background:#f8f5ef;font-size:9px;color:#5f594f}.candidate-selector-option button{white-space:nowrap}@media(max-width:700px){.candidate-selector-option{grid-template-columns:1fr}.candidate-selector-actions{justify-content:flex-start}}
`;document.head.append(style)}
function candidateSelectorClose(){document.querySelector('#post-w99-campaign-execution-candidate-selector')?.remove();postW99CampaignExecutionCandidateSelectorState.active=null}
function candidateSelectorFromToday(item){
  if(typeof marketingOpsState==='undefined'||marketingOpsState?.view!=='today-execution')return false;
  const active=typeof postW99ExecutionReturnState!=='undefined'?postW99ExecutionReturnState.active:null;
  return Boolean(active?.action_id&&String(active.action_id)===String(item?.id||''));
}
function candidateSelectorCandidateTitle(validation,candidate,index){
  if(validation.targetKind==='PUBLICATION')return `Publicación ${candidateSelectorText(candidate?.channel)||index+1}`;
  if(validation.targetKind==='PAID_DRAFT')return candidateSelectorText(candidate?.campaign_name)||`Plan de pauta ${index+1}`;
  return `Candidato ${index+1}`;
}
function candidateSelectorCandidateMeta(_validation,candidate){
  const values=[];
  for(const [key,label] of [['status','Estado'],['scheduled_for','Fecha'],['channel','Canal']]){const value=candidateSelectorText(candidate?.[key]);if(value)values.push([label,value])}
  return values;
}
function candidateSelectorExactItem(item,validation,candidate){
  const targetId=candidateSelectorText(candidate?.id);if(!validation?.valid||!targetId||!validation.candidates.some(row=>candidateSelectorText(row?.id)===targetId))return null;
  const action={...(item?.action||{})};action.view=validation.ownerView;action.tab=null;
  if(validation.targetKind==='PUBLICATION'){action.entity_id=targetId;action.label='Abrir publicación elegida'}
  else if(validation.targetKind==='PAID_DRAFT'){action.entity_id=targetId;action.label='Abrir plan de pauta elegido'}
  else return null;
  return{...item,action,explicit_owner_selection:{schema:POST_W99_CAMPAIGN_EXECUTION_CANDIDATE_SELECTOR_SCHEMA,source_resolution_state:'AMBIGUOUS_TARGET',owner_view:validation.ownerView,target_kind:validation.targetKind,target_id:targetId,selected_by:'HUMAN_CLICK',persisted:false,selected_at:new Date().toISOString()}};
}
const candidateSelectorBaseOpen=globalThis.actionCenterOpen;
function candidateSelectorChoose(candidate){
  const active=postW99CampaignExecutionCandidateSelectorState.active;if(!active?.validation?.valid)return;
  const company=candidateSelectorCompany();if(!company?.id||String(company.id)!==String(active.companyId||'')){candidateSelectorClose();if(typeof opsToast==='function')opsToast('La empresa cambió; vuelve a abrir la acción desde el estado actual.');return}
  const exact=candidateSelectorExactItem(active.item,active.validation,candidate);if(!exact)return;
  const fromToday=Boolean(active.fromToday);candidateSelectorClose();
  if(fromToday&&typeof executionReturnCapture==='function')executionReturnCapture(exact);
  if(typeof candidateSelectorBaseOpen==='function')return candidateSelectorBaseOpen(exact);
  const view=exact?.action?.view;if(view&&typeof opsShowView==='function')return opsShowView(view)
}
function candidateSelectorRender(item,validation,fromToday){
  candidateSelectorStyles();candidateSelectorClose();const company=candidateSelectorCompany();
  postW99CampaignExecutionCandidateSelectorState.active={item,validation,fromToday,companyId:company?.id||null};
  const backdrop=opsEl('div','candidate-selector-backdrop');backdrop.id='post-w99-campaign-execution-candidate-selector';backdrop.setAttribute('role','dialog');backdrop.setAttribute('aria-modal','true');backdrop.setAttribute('aria-label','Elegir destino exacto');
  const dialog=opsEl('section','candidate-selector-dialog'),head=opsEl('div','candidate-selector-head');head.append(opsEl('p','eyebrow','PLAN DE HOY · ELECCIÓN EXPLÍCITA'),opsEl('h3','',item?.title||'Elige el registro exacto'),opsEl('p','',validation?.resolution?.reason||'El estado local contiene más de un candidato canónico y no se elegirá ninguno automáticamente.'));dialog.append(head);
  if(validation?.valid){const list=opsEl('div','candidate-selector-list');validation.candidates.forEach((candidate,index)=>{const option=opsEl('article','candidate-selector-option'),copy=opsEl('div','candidate-selector-copy');copy.append(opsEl('strong','',candidateSelectorCandidateTitle(validation,candidate,index)),opsEl('span','candidate-selector-id',candidateSelectorText(candidate?.id)));const meta=opsEl('div','candidate-selector-meta');candidateSelectorCandidateMeta(validation,candidate).forEach(([label,value])=>meta.append(opsEl('span','candidate-selector-chip',`${label}: ${value}`)));if(meta.childNodes.length)copy.append(meta);const choose=opsEl('button','primary','Elegir este registro');choose.type='button';choose.addEventListener('click',()=>candidateSelectorChoose(candidate));option.append(copy,choose);list.append(option)});dialog.append(list,opsEl('div','candidate-selector-safety','Los candidatos conservan el orden de la lectura local; este orden no expresa prioridad ni recomendación. Elegir solo fija el ID de navegación para esta apertura. No completa, publica, programa, crea pauta ni modifica el objeto.'))}else dialog.append(opsEl('div','candidate-selector-error',`Selección bloqueada: ${validation?.reason||'el contrato ambiguo no es válido.'} No se abrió ningún owner alternativo.`));
  const actions=opsEl('div','candidate-selector-actions'),cancel=opsEl('button','','Cancelar sin abrir');cancel.type='button';cancel.addEventListener('click',candidateSelectorClose);actions.append(cancel);dialog.append(actions);backdrop.append(dialog);document.body.append(backdrop)
}
if(typeof candidateSelectorBaseOpen==='function')globalThis.actionCenterOpen=function(item){
  const validation=candidateSelectorValidation(item);if(!validation)return candidateSelectorBaseOpen.apply(this,arguments);
  const fromToday=candidateSelectorFromToday(item);if(fromToday&&typeof executionReturnForget==='function')executionReturnForget();candidateSelectorRender(item,validation,fromToday);return undefined
};
window.addEventListener('keydown',event=>{if(event.key==='Escape'&&postW99CampaignExecutionCandidateSelectorState.active)candidateSelectorClose()});
window.addEventListener('marketing-ops-refreshed',candidateSelectorClose);window.addEventListener('pagehide',candidateSelectorClose);
