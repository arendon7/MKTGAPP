const POST_W99_EXECUTION_OWNER_RELAY_SCHEMA='binario.marketing.execution-owner-relay.v1';
const postW99ExecutionOwnerRelayState={key:null,payload:null,loading:false,error:null};

function executionOwnerRelayText(value){return value===null||value===undefined?'':String(value).trim()}
function executionOwnerRelayAction(){
  if(typeof controlHandoffExecutionContext!=='function'||typeof controlHandoffActionRow!=='function')return null;
  const execution=controlHandoffExecutionContext();if(!execution)return null;
  const resolved=controlHandoffActionRow(execution);if(resolved?.state!=='ACTION_CONTEXT_RESOLVED'||!resolved.row)return null;
  return{execution,row:resolved.row};
}
function executionOwnerRelayKind(row){return executionOwnerRelayText(row?.kind).toLowerCase()}
function executionOwnerRelayCampaignId(row){return executionOwnerRelayText(row?.action?.campaign_id)}
function executionOwnerRelayEligible(row){
  return new Set(['fix_execution','fix_publication','finish_creative','prepare_distribution','schedule_or_publish','review_paid','create_creative']).has(executionOwnerRelayKind(row))
}
function executionOwnerRelayKey(info){
  const company=typeof opsSelectedCompany==='function'?opsSelectedCompany():null;
  return company?.id&&info?.execution?.action_id&&executionOwnerRelayCampaignId(info.row)?`${company.id}:${info.execution.action_id}:${executionOwnerRelayCampaignId(info.row)}`:null
}
function executionOwnerRelayExpected(row,payload){
  const kind=executionOwnerRelayKind(row),code=executionOwnerRelayText(payload?.execution_next_action?.code).toLowerCase();
  if(kind==='fix_execution')return code==='fix_publication';
  return kind===code;
}
async function executionOwnerRelayLoad(info,force=false){
  const company=typeof opsSelectedCompany==='function'?opsSelectedCompany():null,key=executionOwnerRelayKey(info),campaignId=executionOwnerRelayCampaignId(info?.row);
  if(!company?.id||!key||!campaignId)return null;
  if(!force&&postW99ExecutionOwnerRelayState.key===key&&postW99ExecutionOwnerRelayState.payload)return postW99ExecutionOwnerRelayState.payload;
  if(postW99ExecutionOwnerRelayState.loading&&postW99ExecutionOwnerRelayState.key===key)return null;
  postW99ExecutionOwnerRelayState.key=key;postW99ExecutionOwnerRelayState.loading=true;postW99ExecutionOwnerRelayState.error=null;
  try{
    const payload=await opsApi(`/api/companies/${encodeURIComponent(company.id)}/campaigns/${encodeURIComponent(campaignId)}/execution-owner-context`);
    postW99ExecutionOwnerRelayState.payload=payload;return payload
  }catch(err){
    postW99ExecutionOwnerRelayState.payload=null;postW99ExecutionOwnerRelayState.error=err?.message||String(err);return null
  }finally{postW99ExecutionOwnerRelayState.loading=false}
}
function executionOwnerRelayCurrentTargetMatches(payload){
  const target=payload?.resolution?.target,deep=typeof postW99ContextualDeepLinkState!=='undefined'?postW99ContextualDeepLinkState.active:null;
  return Boolean(target&&deep&&executionOwnerRelayText(deep.target_kind)===executionOwnerRelayText(target.target_kind)&&executionOwnerRelayText(deep.target_id)===executionOwnerRelayText(target.target_id)&&postW99ContextualDeepLinkState.lastStatus==='FOUND_EXACT')
}
function executionOwnerRelayProof(kind,targetKind,targetId){
  const payload=postW99ExecutionOwnerRelayState.payload,info=executionOwnerRelayAction();
  if(!payload||!info||!executionOwnerRelayExpected(info.row,payload))return false;
  if(executionOwnerRelayKind(info.row)!==executionOwnerRelayText(kind).toLowerCase())return false;
  const resolution=payload.resolution||{},target=resolution.target||{};
  return resolution.state==='TARGET_RESOLVED'&&executionOwnerRelayText(target.target_kind)===executionOwnerRelayText(targetKind)&&executionOwnerRelayText(target.target_id)===executionOwnerRelayText(targetId)
}

function executionOwnerRelayStyles(){
  if(document.querySelector('#post-w99-execution-owner-relay-style'))return;
  const style=document.createElement('style');style.id='post-w99-execution-owner-relay-style';style.textContent=`
.execution-owner-relay{margin:0 0 12px;padding:10px 12px;border:1px solid #d8d2c8;border-radius:12px;background:#fbfaf7;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px;align-items:center}.execution-owner-relay-copy{display:grid;gap:3px}.execution-owner-relay-copy small{font-size:7px;letter-spacing:.09em;color:#777067}.execution-owner-relay-copy strong{font-size:10px}.execution-owner-relay-copy span{font-size:8px;color:#706a61}.execution-owner-relay-actions{display:flex;gap:6px;align-items:center;flex-wrap:wrap}.execution-owner-relay-chip{display:inline-flex;padding:4px 7px;border-radius:999px;background:#efede7;font-size:7px;white-space:nowrap}@media(max-width:700px){.execution-owner-relay{grid-template-columns:1fr}.execution-owner-relay-actions{justify-content:flex-start}}
`;document.head.append(style)
}
function executionOwnerRelayTargetLabel(target){
  return({PUBLICATION:'publicación',PAID_MEDIA:'pauta',MEDIA:'creativo',CAMPAIGN:'campaña'})[target?.target_kind]||'owner'
}
function executionOwnerRelayFinalContext(info,payload){
  const target=payload?.resolution?.target;if(!target)return null;
  return{
    schema:'binario.marketing.contextual-deep-link.v1',
    owner_view:target.view,
    tab:null,
    target_kind:target.target_kind,
    target_id:target.target_id,
    lead_id:null,contact_id:null,opportunity_id:null,
    campaign_id:target.campaign_id||executionOwnerRelayCampaignId(info.row)||null,
    media_id:target.media_id||null,
    entity_id:target.publication_id||null,
    paid_media_id:target.paid_media_id||null,
    title:info.row?.title||info.row?.action?.label||'Acción operativa',
    focused:false
  }
}
function executionOwnerRelayOpen(info,payload){
  const context=executionOwnerRelayFinalContext(info,payload);if(!context)return;
  if(typeof contextualDeepLinkClear==='function')contextualDeepLinkClear(false);
  postW99ContextualDeepLinkState.active=context;postW99ContextualDeepLinkState.lastStatus=null;
  if(context.target_kind==='PUBLICATION'&&typeof editorialState!=='undefined')editorialState.selectedId=context.target_id;
  if(context.target_kind==='CAMPAIGN'&&typeof campaignState!=='undefined')campaignState.selectedId=context.target_id;
  if(context.target_kind==='MEDIA'&&typeof wave49CreativeState!=='undefined'){wave49CreativeState.selectedId=context.target_id;wave49CreativeState.tab='pipeline'}
  if(context.owner_view==='content'){
    if(typeof opsShowLegacy==='function')opsShowLegacy();
    if(typeof contentRenderCurrent==='function')contentRenderCurrent()
  }else if(typeof opsShowView==='function')opsShowView(context.owner_view);
  if(typeof contextualDeepLinkSchedule==='function')contextualDeepLinkSchedule();
  if(typeof controlHandoffSchedule==='function')controlHandoffSchedule();
  executionOwnerRelaySchedule()
}
function executionOwnerRelayMessage(info,payload){
  if(postW99ExecutionOwnerRelayState.error)return{title:'No se pudo revalidar el owner final',detail:postW99ExecutionOwnerRelayState.error,chip:'FAIL CLOSED'};
  if(!payload)return{title:'Revalidando owner final',detail:'Se consulta únicamente estado local para comprobar identidad exacta.',chip:'LOCAL READ'};
  if(!executionOwnerRelayExpected(info.row,payload))return{title:'La acción de ejecución cambió',detail:`Today conserva ${executionOwnerRelayKind(info.row).toUpperCase()}, pero W64 ahora reporta ${payload.execution_next_action?.code||'otra acción'}. No se continuará con contexto envejecido.`,chip:'STALE'};
  const resolution=payload.resolution||{};
  if(resolution.state==='TARGET_RESOLVED'){
    const same=executionOwnerRelayCurrentTargetMatches(payload),label=executionOwnerRelayTargetLabel(resolution.target);
    return{title:same?'Owner final exacto revalidado':`Owner final exacto disponible · ${label}`,detail:resolution.reason,chip:same?'EXACTO':'2º SALTO',canOpen:!same}
  }
  if(resolution.state==='TARGET_AMBIGUOUS')return{title:'Owner final ambiguo',detail:`${resolution.reason} Candidatos: ${resolution.candidate_count}.`,chip:'AMBIGUO'};
  if(resolution.state==='TARGET_NOT_AVAILABLE')return{title:'Owner final no disponible',detail:resolution.reason,chip:'NO DISPONIBLE'};
  return{title:'Navegación de owner solamente',detail:resolution.reason,chip:'OWNER ONLY'}
}
function executionOwnerRelayDecorate(){
  executionOwnerRelayStyles();document.querySelector('#post-w99-execution-owner-relay')?.remove();
  const info=executionOwnerRelayAction();if(!info||!executionOwnerRelayEligible(info.row))return;
  const key=executionOwnerRelayKey(info),payload=postW99ExecutionOwnerRelayState.key===key?postW99ExecutionOwnerRelayState.payload:null;
  if(!payload&&!postW99ExecutionOwnerRelayState.loading){executionOwnerRelayLoad(info).then(executionOwnerRelaySchedule)}
  const root=document.querySelector('#marketing-ops-view');if(!root)return;
  const message=executionOwnerRelayMessage(info,payload),card=opsEl('section','execution-owner-relay');card.id='post-w99-execution-owner-relay';
  const copy=opsEl('div','execution-owner-relay-copy');copy.append(opsEl('small','','PLAN DE HOY · OWNER RELAY'),opsEl('strong','',message.title),opsEl('span','',message.detail));
  const actions=opsEl('div','execution-owner-relay-actions');actions.append(opsEl('span','execution-owner-relay-chip',message.chip));
  if(message.canOpen&&payload?.resolution?.target){const button=opsEl('button','primary',`Abrir ${executionOwnerRelayTargetLabel(payload.resolution.target)} exacta`);button.type='button';button.addEventListener('click',()=>executionOwnerRelayOpen(info,payload));actions.append(button)}
  card.append(copy,actions);
  const handoff=root.querySelector('#post-w99-contextual-control-handoff'),deep=root.querySelector('#post-w99-contextual-deep-link-context');
  if(handoff)handoff.insertAdjacentElement('afterend',card);else if(deep)deep.insertAdjacentElement('afterend',card);else root.prepend(card)
}
function executionOwnerRelaySchedule(){queueMicrotask(executionOwnerRelayDecorate)}

function executionOwnerRelayInstallAnnotations(){
  const paidSummary=globalThis.wave48PlanSummary;
  if(typeof paidSummary==='function'&&!paidSummary.__postW99ExecutionOwnerRelay){
    const wrapped=function(row){const card=paidSummary.apply(this,arguments);if(card&&row?.id)card.dataset.executionPaidMediaId=String(row.id);return card};
    wrapped.__postW99ExecutionOwnerRelay=true;globalThis.wave48PlanSummary=wrapped
  }
  const itemCard=globalThis.wave49ItemCard;
  if(typeof itemCard==='function'&&!itemCard.__postW99ExecutionOwnerRelay){
    const wrapped=function(row){const card=itemCard.apply(this,arguments);const id=row?.media?.id;if(card&&id)card.dataset.executionMediaId=String(id);return card};
    wrapped.__postW99ExecutionOwnerRelay=true;globalThis.wave49ItemCard=wrapped
  }
  const paidRender=globalThis.wave48RenderPlans;
  if(typeof paidRender==='function'&&!paidRender.__postW99ExecutionOwnerRelay){
    const wrapped=async function(){const value=await paidRender.apply(this,arguments);if(typeof contextualDeepLinkSchedule==='function')contextualDeepLinkSchedule();executionOwnerRelaySchedule();return value};
    wrapped.__postW99ExecutionOwnerRelay=true;globalThis.wave48RenderPlans=wrapped
  }
}

const executionOwnerRelayBaseFindTarget=globalThis.contextualDeepLinkFindTarget;
if(typeof executionOwnerRelayBaseFindTarget==='function'){
  globalThis.contextualDeepLinkFindTarget=function(context){
    const found=executionOwnerRelayBaseFindTarget(context);if(found)return found;
    if(context?.target_kind==='PAID_MEDIA')return[...document.querySelectorAll('[data-execution-paid-media-id]')].find(node=>node.dataset.executionPaidMediaId===String(context.target_id))||null;
    if(context?.target_kind==='MEDIA')return[...document.querySelectorAll('[data-execution-media-id]')].find(node=>node.dataset.executionMediaId===String(context.target_id))||null;
    return null
  }
}

const executionOwnerRelayBaseResolveControl=globalThis.controlHandoffResolveControl;
if(typeof executionOwnerRelayBaseResolveControl==='function'){
  globalThis.controlHandoffResolveControl=function(row,targetInfo){
    const target=targetInfo?.node,deep=targetInfo?.context||{},kind=executionOwnerRelayKind(row),targetKind=executionOwnerRelayText(deep.target_kind).toUpperCase(),targetId=executionOwnerRelayText(deep.target_id);
    const meta=(controlKey,controlLabel,controlKind,explanation)=>({control_key:controlKey,control_label:controlLabel,control_kind:controlKind,action_kind:kind,target_kind:targetKind,explanation});
    if(targetKind==='PUBLICATION'&&['fix_execution','fix_publication','schedule_or_publish'].includes(kind)&&executionOwnerRelayProof(kind,targetKind,targetId)){
      const selected=typeof editorialState!=='undefined'&&String(editorialState.selectedId||'')===targetId,panels=selected?[...document.querySelectorAll('#marketing-ops-view .editorial-panel')]:[];
      return controlHandoffSingle(panels,meta('MANAGE_EXECUTION_PUBLICATION','Gestionar publicación exacta','CONTROL_GROUP','El relay probó un único publication ID causal. El panel conserva Guardar nueva versión y Cancelar publicación como decisiones humanas explícitas.'))
    }
    if(targetKind==='PAID_MEDIA'&&kind==='review_paid'&&executionOwnerRelayProof(kind,targetKind,targetId)){
      const groups=[...target.querySelectorAll('.wave48-actions')].filter(group=>[...group.querySelectorAll('button')].some(button=>['Crear en Meta · PAUSED','Cancelar borrador'].includes(controlHandoffText(button.textContent))));
      return controlHandoffSingle(groups,meta('REVIEW_EXACT_PAID_DRAFT','Revisar borrador de pauta exacto','CONTROL_GROUP','El borrador exacto conserva la elección humana entre crear la jerarquía remota en PAUSED o cancelar el borrador. El relay no dispara ninguna de las dos.'))
    }
    if(targetKind==='MEDIA'&&kind==='finish_creative'&&executionOwnerRelayProof(kind,targetKind,targetId)){
      const selected=typeof wave49CreativeState!=='undefined'&&String(wave49CreativeState.selectedId||'')===targetId,forms=selected?[...document.querySelectorAll('#marketing-ops-view .w49-editor form.w49-form')]:[];
      return controlHandoffSingleGroup(forms,text=>text==='Guardar ficha creativa',meta('FINISH_EXACT_CREATIVE','Editar estado + Guardar ficha creativa','CONTROL_GROUP','El media exacto está seleccionado. El operador conserva la decisión de cambiar Estado —por ejemplo a Lista— y el submit final; el relay no marca READY automáticamente.'))
    }
    if(targetKind==='MEDIA'&&kind==='prepare_distribution'&&executionOwnerRelayProof(kind,targetKind,targetId)){
      const selected=typeof wave49CreativeState!=='undefined'&&String(wave49CreativeState.selectedId||'')===targetId;
      const groups=selected?[...document.querySelectorAll('#marketing-ops-view .w49-editor .w49-actions')].filter(group=>[...group.querySelectorAll('button')].some(button=>['Preparar Facebook','Preparar Instagram','Enviar a Pauta'].includes(controlHandoffText(button.textContent)))):[];
      return controlHandoffSingle(groups,meta('CHOOSE_EXACT_DISTRIBUTION_OWNER','Elegir canal de distribución','CONTROL_GROUP','El creativo exacto está listo; Facebook, Instagram y Pauta siguen siendo alternativas humanas separadas. No se preselecciona canal.'))
    }
    return executionOwnerRelayBaseResolveControl.apply(this,arguments)
  }
}

function executionOwnerRelayWrap(name){
  const base=globalThis[name];if(typeof base!=='function'||base.__postW99ExecutionOwnerRelayRender)return;
  const wrapped=function(){const value=base.apply(this,arguments);executionOwnerRelayInstallAnnotations();executionOwnerRelaySchedule();return value};
  wrapped.__postW99ExecutionOwnerRelayRender=true;globalThis[name]=wrapped
}
['renderMarketingOps','wave64Render','wave65Render','contentRenderCurrent'].forEach(executionOwnerRelayWrap);
window.addEventListener('marketing-ops-refreshed',()=>{postW99ExecutionOwnerRelayState.key=null;postW99ExecutionOwnerRelayState.payload=null;postW99ExecutionOwnerRelayState.error=null;executionOwnerRelaySchedule()});
window.addEventListener('pageshow',executionOwnerRelaySchedule);
executionOwnerRelayStyles();executionOwnerRelayInstallAnnotations();executionOwnerRelaySchedule();
