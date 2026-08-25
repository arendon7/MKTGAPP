const POST_W99_CAMPAIGN_EXECUTION_OWNER_SCHEMA='binario.marketing.campaign-execution-owner-relay.v1';

function campaignExecutionOwnerText(value){return value===null||value===undefined?'':String(value).trim()}
function campaignExecutionOwnerKind(item){return campaignExecutionOwnerText(item?.kind||item?.post_w99_action_kind).toLowerCase()}
function campaignExecutionOwnerCompany(){return typeof opsSelectedCompany==='function'?opsSelectedCompany():null}

const campaignExecutionOwnerBaseDescriptor=globalThis.contextualDeepLinkDescriptor;
if(typeof campaignExecutionOwnerBaseDescriptor==='function')globalThis.contextualDeepLinkDescriptor=function(item){
  const context=campaignExecutionOwnerBaseDescriptor.apply(this,arguments),kind=campaignExecutionOwnerKind(item),action=item?.action||item||{};
  if(context?.owner_view==='pauta'&&campaignExecutionOwnerText(action.entity_id)&&kind==='review_paid'){
    context.target_kind='PAID_DRAFT';context.target_id=campaignExecutionOwnerText(action.entity_id);context.post_w99_action_kind=kind
  }
  return context
};

const campaignExecutionOwnerBasePrepare=globalThis.contextualDeepLinkPrepareOwner;
if(typeof campaignExecutionOwnerBasePrepare==='function')globalThis.contextualDeepLinkPrepareOwner=function(context){
  if(context?.owner_view==='content'&&context?.target_kind==='MEDIA'&&context.target_id&&typeof wave49CreativeState!=='undefined'){
    wave49CreativeState.tab='pipeline';wave49CreativeState.selectedId=String(context.target_id)
  }
  return campaignExecutionOwnerBasePrepare.apply(this,arguments)
};

function campaignExecutionOwnerAnnotateCreative(){
  if(typeof wave49CreativeState==='undefined'||wave49CreativeState.tab!=='pipeline'||!wave49CreativeState.context)return;
  const rows=wave49CreativeState.context.items||[],nodes=[...document.querySelectorAll('.w49-list .w49-item')];
  if(nodes.length!==rows.length)return;
  nodes.forEach((node,index)=>{const id=rows[index]?.media?.id;if(id)node.dataset.deepMediaId=String(id)})
}
function campaignExecutionOwnerPaidRows(){return typeof wave47State!=='undefined'&&Array.isArray(wave47State.paidMedia)?[...wave47State.paidMedia].reverse():[]}
function campaignExecutionOwnerAnnotatePaid(){
  const rows=campaignExecutionOwnerPaidRows(),nodes=[...document.querySelectorAll('.wave48-plans .wave48-plan')];if(!rows.length||nodes.length!==rows.length)return;
  nodes.forEach((node,index)=>{const id=rows[index]?.id;if(id)node.dataset.deepPaidDraftId=String(id)})
}
const campaignExecutionOwnerBaseAnnotate=globalThis.contextualDeepLinkAnnotate;
if(typeof campaignExecutionOwnerBaseAnnotate==='function')globalThis.contextualDeepLinkAnnotate=function(){const value=campaignExecutionOwnerBaseAnnotate.apply(this,arguments);campaignExecutionOwnerAnnotateCreative();campaignExecutionOwnerAnnotatePaid();return value};

const campaignExecutionOwnerBaseReady=globalThis.contextualDeepLinkOwnerReady;
if(typeof campaignExecutionOwnerBaseReady==='function')globalThis.contextualDeepLinkOwnerReady=function(context){
  const company=campaignExecutionOwnerCompany();
  if(context?.owner_view==='content'&&context?.target_kind==='MEDIA'&&typeof wave49CreativeState!=='undefined'){
    if(!company?.id||!wave49CreativeState.context||String(wave49CreativeState.companyId||'')!==String(company.id))return false;
    const matches=(wave49CreativeState.context.items||[]).filter(row=>String(row?.media?.id||'')===String(context.target_id));return matches.length===1
  }
  if(context?.owner_view==='pauta'&&context?.target_kind==='PAID_DRAFT'){
    const rows=campaignExecutionOwnerPaidRows(),nodes=[...document.querySelectorAll('.wave48-plans .wave48-plan')];if(!rows.length||rows.length!==nodes.length)return false;
    return rows.filter(row=>String(row?.id||'')===String(context.target_id)).length===1
  }
  return campaignExecutionOwnerBaseReady.apply(this,arguments)
};

function campaignExecutionOwnerByDataset(selector,key,value){const matches=[...document.querySelectorAll(selector)].filter(node=>String(node.dataset[key]||'')===String(value||''));return matches.length===1?matches[0]:null}
const campaignExecutionOwnerBaseFindTarget=globalThis.contextualDeepLinkFindTarget;
if(typeof campaignExecutionOwnerBaseFindTarget==='function')globalThis.contextualDeepLinkFindTarget=function(context){
  if(context?.target_kind==='MEDIA'&&context?.owner_view==='content'){
    const exact=campaignExecutionOwnerByDataset('.w49-item[data-deep-media-id]','deepMediaId',context.target_id);if(exact)return exact
  }
  if(context?.target_kind==='PAID_DRAFT')return campaignExecutionOwnerByDataset('.wave48-plan[data-deep-paid-draft-id]','deepPaidDraftId',context.target_id);
  return campaignExecutionOwnerBaseFindTarget.apply(this,arguments)
};

function campaignExecutionOwnerMeta(key,label,controlKind,kind,targetKind,explanation){return{schema:POST_W99_CAMPAIGN_EXECUTION_OWNER_SCHEMA,control_key:key,control_label:label,control_kind:controlKind,action_kind:kind,target_kind:targetKind,explanation}}
function campaignExecutionOwnerPublicationControl(row,targetInfo){
  const kind=campaignExecutionOwnerKind(row),deep=targetInfo?.context||{};if(!['fix_execution','schedule_or_publish','calendar'].includes(kind)||String(deep.target_kind||'').toUpperCase()!=='PUBLICATION')return null;
  const selected=typeof editorialState!=='undefined'&&String(editorialState.selectedId||'')===String(deep.target_id||''),panels=selected?[...document.querySelectorAll('#marketing-ops-view .editorial-panel')]:[];
  const label=kind==='fix_execution'?'Corregir publicación fallida':kind==='schedule_or_publish'?'Programar o gestionar borrador':'Revisar publicación programada';
  return controlHandoffSingle(panels,campaignExecutionOwnerMeta('W42_EXACT_PUBLICATION_OWNER',label,'CONTROL_GROUP',kind,'PUBLICATION','El relay resolvió un publication_id único. Wave 42 conserva copy, fecha, reemplazo/cancelación y toda mutación exige acción humana explícita.'))
}
function campaignExecutionOwnerMediaControl(row,targetInfo){
  const kind=campaignExecutionOwnerKind(row),deep=targetInfo?.context||{};if(!['finish_creative','prepare_distribution'].includes(kind)||String(deep.target_kind||'').toUpperCase()!=='MEDIA')return null;
  const selected=typeof wave49CreativeState!=='undefined'&&String(wave49CreativeState.selectedId||'')===String(deep.target_id||''),item=selected&&typeof wave49SelectedItem==='function'?wave49SelectedItem():null;
  if(!item||String(item?.media?.id||'')!==String(deep.target_id||''))return controlHandoffOwnerGap(kind,'MEDIA','Creative Studio no confirma el media_id exacto seleccionado. No se elige otra pieza.');
  if(kind==='finish_creative'){
    const forms=[...document.querySelectorAll('.w49-editor form.w49-form')];return controlHandoffSingle(forms,campaignExecutionOwnerMeta('W49_FINISH_CREATIVE','Completar ficha creativa','CONTROL_GROUP',kind,'MEDIA','El formulario W49 pertenece al media_id exacto. Guardar sigue siendo submit humano y conserva la autoridad canónica del Creative Studio.'))
  }
  const groups=[...document.querySelectorAll('.w49-editor > .w49-actions')];return controlHandoffSingle(groups,campaignExecutionOwnerMeta('W49_PREPARE_DISTRIBUTION','Elegir distribución del creativo exacto','CONTROL_GROUP',kind,'MEDIA','W49 ofrece los canales canónicos de distribución de la pieza exacta. El relay no elige Facebook, Instagram ni Pauta y no ejecuta ningún envío.'))
}
function campaignExecutionOwnerCampaignControl(row,targetInfo){
  const kind=campaignExecutionOwnerKind(row),deep=targetInfo?.context||{};if(kind!=='define_channels'||String(deep.target_kind||'').toUpperCase()!=='CAMPAIGN')return null;
  const selected=typeof campaignState!=='undefined'&&String(campaignState.selectedId||'')===String(deep.target_id||''),forms=selected?[...document.querySelectorAll('.campaign-form')]:[];
  return controlHandoffSingle(forms,campaignExecutionOwnerMeta('W35_DEFINE_CHANNELS','Definir canales de la campaña','CONTROL_GROUP',kind,'CAMPAIGN','La campaña exacta ya está seleccionada en W35. El usuario conserva canales, estado y submit; el relay no modifica el plan.'))
}
function campaignExecutionOwnerPaidControl(row,targetInfo){
  const kind=campaignExecutionOwnerKind(row),deep=targetInfo?.context||{};if(kind!=='review_paid'||String(deep.target_kind||'').toUpperCase()!=='PAID_DRAFT')return null;
  const target=targetInfo?.node;if(!target)return null;
  return controlHandoffSingle([target],campaignExecutionOwnerMeta('W48_REVIEW_PAID_DRAFT','Revisar plan de pauta exacto','CONTROL_GROUP',kind,'PAID_DRAFT','La card corresponde al draft_id exacto. Crear en Meta permanece PAUSED y exige confirmación humana; cancelar también exige confirmación. El relay no ejecuta ninguna opción.'))
}
const campaignExecutionOwnerBaseResolve=globalThis.controlHandoffResolveControl;
if(typeof campaignExecutionOwnerBaseResolve==='function')globalThis.controlHandoffResolveControl=function(row,targetInfo){
  const targetKind=campaignExecutionOwnerText(targetInfo?.context?.target_kind).toUpperCase(),kind=campaignExecutionOwnerKind(row);let resolved=null;
  if(targetKind==='PUBLICATION')resolved=campaignExecutionOwnerPublicationControl(row,targetInfo);
  else if(targetKind==='MEDIA')resolved=campaignExecutionOwnerMediaControl(row,targetInfo);
  else if(targetKind==='CAMPAIGN')resolved=campaignExecutionOwnerCampaignControl(row,targetInfo);
  else if(targetKind==='PAID_DRAFT')resolved=campaignExecutionOwnerPaidControl(row,targetInfo);
  else if(targetKind==='CAMPAIGN_EXECUTION'&&kind==='fix_execution'){
    const resolution=row?.owner_resolution||{};if(['AMBIGUOUS_TARGET','NO_TARGET'].includes(String(resolution.state||''))){return controlHandoffOwnerGap(kind,'CAMPAIGN_EXECUTION',resolution.reason||'W64 no puede demostrar un owner final único. Se mantiene la campaña de ejecución sin elegir una publicación.')}
  }
  if(resolved)return resolved;return campaignExecutionOwnerBaseResolve.apply(this,arguments)
};

function campaignExecutionOwnerSchedule(){queueMicrotask(()=>{campaignExecutionOwnerAnnotateCreative();campaignExecutionOwnerAnnotatePaid();if(typeof contextualDeepLinkSchedule==='function')contextualDeepLinkSchedule();if(typeof controlHandoffSchedule==='function')controlHandoffSchedule()})}
function campaignExecutionOwnerWrap(name){const base=globalThis[name];if(typeof base!=='function'||base.__postW99CampaignExecutionOwner)return;const wrapped=function(){const value=base.apply(this,arguments);campaignExecutionOwnerSchedule();return value};wrapped.__postW99CampaignExecutionOwner=true;globalThis[name]=wrapped}
['renderMarketingOps','contentRenderCurrent','campaignRenderCurrent','wave64Render'].forEach(campaignExecutionOwnerWrap);
const campaignExecutionOwnerBasePaidPlans=globalThis.wave48RenderPlans;
if(typeof campaignExecutionOwnerBasePaidPlans==='function')globalThis.wave48RenderPlans=async function(){const value=await campaignExecutionOwnerBasePaidPlans.apply(this,arguments);campaignExecutionOwnerSchedule();return value};
window.addEventListener('marketing-ops-refreshed',campaignExecutionOwnerSchedule);window.addEventListener('pageshow',campaignExecutionOwnerSchedule);campaignExecutionOwnerSchedule();
