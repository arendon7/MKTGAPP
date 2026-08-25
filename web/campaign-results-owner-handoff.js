const POST_W99_CAMPAIGN_RESULTS_OWNER_SCHEMA='binario.marketing.campaign-results-owner-handoff.v1';
const POST_W99_CAMPAIGN_RESULTS_TARGET_KIND='CAMPAIGN_RESULTS';
const POST_W99_CAMPAIGN_RESULTS_KINDS=new Set(['capture_results','review_coverage','record_decision','review_results']);
const postW99CampaignResultsOwnerState={companyId:null,campaignId:null,payload:null,loading:false,preparedDecisionId:null};

function campaignResultsOwnerText(value){return value===null||value===undefined?'':String(value).trim()}
function campaignResultsOwnerCompany(){return typeof opsSelectedCompany==='function'?opsSelectedCompany():null}
function campaignResultsOwnerActionKind(item){return campaignResultsOwnerText(item?.kind||item?.post_w99_action_kind).toLowerCase()}
function campaignResultsOwnerMatches(context){return context?.target_kind===POST_W99_CAMPAIGN_RESULTS_TARGET_KIND&&Boolean(context.target_id)}
function campaignResultsOwnerPayloadMatches(context){const company=campaignResultsOwnerCompany();return Boolean(company?.id&&postW99CampaignResultsOwnerState.payload&&String(postW99CampaignResultsOwnerState.companyId)===String(company.id)&&String(postW99CampaignResultsOwnerState.campaignId)===String(context?.target_id))}

async function campaignResultsOwnerLoad(context){
  const company=campaignResultsOwnerCompany(),campaignId=campaignResultsOwnerText(context?.target_id);if(!company?.id||!campaignId)return null;
  if(campaignResultsOwnerPayloadMatches(context))return postW99CampaignResultsOwnerState.payload;
  if(postW99CampaignResultsOwnerState.loading&&String(postW99CampaignResultsOwnerState.companyId)===String(company.id)&&String(postW99CampaignResultsOwnerState.campaignId)===campaignId)return null;
  postW99CampaignResultsOwnerState.loading=true;postW99CampaignResultsOwnerState.companyId=company.id;postW99CampaignResultsOwnerState.campaignId=campaignId;postW99CampaignResultsOwnerState.payload=null;postW99CampaignResultsOwnerState.preparedDecisionId=null;
  try{postW99CampaignResultsOwnerState.payload=await opsApi(`/api/companies/${encodeURIComponent(company.id)}/campaigns/${encodeURIComponent(campaignId)}/results-owner-context`);return postW99CampaignResultsOwnerState.payload}
  catch(err){opsToast(err.message);return null}
  finally{postW99CampaignResultsOwnerState.loading=false;campaignResultsOwnerSchedule()}
}
function campaignResultsOwnerEnsureLearning(context){
  const company=campaignResultsOwnerCompany();if(!company?.id||typeof wave52LearningState==='undefined')return false;
  wave52LearningState.view='learning';
  if(wave52LearningState.data&&String(wave52LearningState.companyId||'')===String(company.id))return true;
  if(typeof wave52Load==='function'&&!wave52LearningState.loading)wave52Load(false).then(campaignResultsOwnerSchedule);
  return false
}

const campaignResultsOwnerBaseDescriptor=globalThis.contextualDeepLinkDescriptor;
if(typeof campaignResultsOwnerBaseDescriptor==='function')globalThis.contextualDeepLinkDescriptor=function(item){
  const context=campaignResultsOwnerBaseDescriptor.apply(this,arguments),kind=campaignResultsOwnerActionKind(item);
  if(context?.owner_view==='analytics'&&context.campaign_id&&POST_W99_CAMPAIGN_RESULTS_KINDS.has(kind)){
    context.target_kind=POST_W99_CAMPAIGN_RESULTS_TARGET_KIND;context.target_id=context.campaign_id;context.post_w99_action_kind=kind
  }
  return context
};
const campaignResultsOwnerBasePrepare=globalThis.contextualDeepLinkPrepareOwner;
if(typeof campaignResultsOwnerBasePrepare==='function')globalThis.contextualDeepLinkPrepareOwner=function(context){
  if(campaignResultsOwnerMatches(context)&&typeof wave52LearningState!=='undefined')wave52LearningState.view='learning';
  return campaignResultsOwnerBasePrepare.apply(this,arguments)
};
const campaignResultsOwnerBaseReady=globalThis.contextualDeepLinkOwnerReady;
if(typeof campaignResultsOwnerBaseReady==='function')globalThis.contextualDeepLinkOwnerReady=function(context){
  if(campaignResultsOwnerMatches(context)){
    const company=campaignResultsOwnerCompany();if(!company?.id)return false;
    if(!campaignResultsOwnerPayloadMatches(context)){campaignResultsOwnerLoad(context);return false}
    if(!campaignResultsOwnerEnsureLearning(context))return false;
    return true
  }
  return campaignResultsOwnerBaseReady.apply(this,arguments)
};

function campaignResultsOwnerStyles(){
  if(document.querySelector('#post-w99-campaign-results-owner-style'))return;
  const style=document.createElement('style');style.id='post-w99-campaign-results-owner-style';style.textContent=`
.campaign-results-owner-context{margin:0 0 12px;padding:12px;border:1px solid #d5d0c6;border-radius:12px;background:#fff;display:grid;gap:9px}.campaign-results-owner-head{display:flex;justify-content:space-between;align-items:flex-start;gap:10px}.campaign-results-owner-copy{display:grid;gap:3px}.campaign-results-owner-copy small{font-size:7px;letter-spacing:.09em;color:#777067}.campaign-results-owner-copy strong{font-size:11px}.campaign-results-owner-copy span{font-size:8px;color:#706a61}.campaign-results-owner-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px}.campaign-results-owner-cell{padding:7px;border:1px solid #e5e0d7;border-radius:8px;display:grid;gap:2px}.campaign-results-owner-cell small{font-size:7px;color:#777067}.campaign-results-owner-cell strong{font-size:8px}.campaign-results-owner-actions{display:flex;gap:6px;flex-wrap:wrap}.campaign-results-owner-actions button{font-size:8px!important}.campaign-results-owner-context.contextual-deep-link-highlight::before{content:'CAMPAÑA · RESULTADOS'}@media(max-width:760px){.campaign-results-owner-grid{grid-template-columns:1fr 1fr}.campaign-results-owner-head{display:grid}}
`;document.head.append(style)
}
function campaignResultsOwnerCell(label,value){const node=opsEl('div','campaign-results-owner-cell');node.append(opsEl('small','',label),opsEl('strong','',value||'—'));return node}
function campaignResultsOwnerExactPayload(context){return campaignResultsOwnerPayloadMatches(context)?postW99CampaignResultsOwnerState.payload:null}
function campaignResultsOwnerPrepareDecision(campaignId){
  const payload=postW99CampaignResultsOwnerState.payload,form=document.querySelector('.w52-decision-form');if(!payload||!form||String(payload.campaign?.id||'')!==String(campaignId)){opsToast('El formulario canónico de decisión no está disponible para esta campaña');return}
  const selects=[...form.querySelectorAll('select')],kind=selects[0],entity=selects[1],rows=wave52LearningState?.data?.campaigns||[];if(!kind||!entity||!rows.some(row=>String(row.id||'')===String(campaignId))){opsToast('La campaña exacta no está disponible en el snapshot actual');return}
  kind.value='CAMPAIGN';entity.replaceChildren();for(const row of rows){const option=opsEl('option','',row.name||row.id);option.value=row.id;entity.append(option)}entity.value=String(campaignId);entity.disabled=false;
  const submit=form.querySelector('button[type="submit"]');if(submit)submit.disabled=false;form.dataset.postW99PreparedCampaignId=String(campaignId);postW99CampaignResultsOwnerState.preparedDecisionId=String(campaignId);
  try{form.scrollIntoView({block:'center',behavior:'smooth'})}catch(_err){form.scrollIntoView()}const rationale=form.querySelector('textarea');if(rationale)rationale.focus();if(typeof controlHandoffSchedule==='function')controlHandoffSchedule()
}
function campaignResultsOwnerEnsureContext(){
  campaignResultsOwnerStyles();const context=typeof postW99ContextualDeepLinkState!=='undefined'?postW99ContextualDeepLinkState.active:null,root=document.querySelector('#marketing-ops-view');root?.querySelector('#post-w99-campaign-results-owner-context')?.remove();if(!root||!campaignResultsOwnerMatches(context)||marketingOpsState?.view!=='analytics')return null;
  const payload=campaignResultsOwnerExactPayload(context);if(!payload)return null;const campaign=payload.campaign||{},learning=payload.learning||{},intel=payload.intelligence||{},evidence=intel.evidence||{},attribution=intel.attribution||{},kind=campaignResultsOwnerText(context.post_w99_action_kind).toLowerCase();
  const card=opsEl('section','campaign-results-owner-context');card.id='post-w99-campaign-results-owner-context';card.dataset.deepResultsCampaignId=String(campaign.id);const head=opsEl('div','campaign-results-owner-head'),copy=opsEl('div','campaign-results-owner-copy');copy.append(opsEl('small','','RESULTADOS · CAMPAÑA EXACTA'),opsEl('strong','',campaign.name||campaign.id),opsEl('span','',`${campaign.objective||'—'} · ${campaign.status||'—'} · ${(campaign.channels||[]).join(' · ')||'sin canales'}`));head.append(copy,opsEl('span','status',evidence.label||'Contexto local'));card.append(head);
  const snapshot=learning.latest_snapshot,decision=intel.decision,grid=opsEl('div','campaign-results-owner-grid');grid.append(campaignResultsOwnerCell('SNAPSHOT',snapshot?`${snapshot.date_preset||'—'} · ${opsDate(snapshot.created_at)}`:'Sin snapshot'),campaignResultsOwnerCell('EVIDENCIA',evidence.summary||evidence.level||'Insuficiente'),campaignResultsOwnerCell('ATRIBUCIÓN',`${Number(attribution.attributed_opportunities||0)} oportunidad(es)`),campaignResultsOwnerCell('DECISIÓN',decision?.action||'Pendiente'));card.append(grid);
  if(kind==='record_decision'){const actions=opsEl('div','campaign-results-owner-actions'),prepare=opsEl('button','','Preparar decisión para esta campaña');prepare.type='button';prepare.dataset.postW99ResultsDecisionPrepare='1';prepare.dataset.campaignId=String(campaign.id);prepare.disabled=!Boolean(payload.controls?.record_decision?.available);prepare.addEventListener('click',()=>campaignResultsOwnerPrepareDecision(campaign.id));actions.append(prepare);card.append(actions)}
  const tabs=root.querySelector('.w52-tabs');if(tabs)tabs.insertAdjacentElement('afterend',card);else root.prepend(card);return card
}
const campaignResultsOwnerBaseAnnotate=globalThis.contextualDeepLinkAnnotate;
if(typeof campaignResultsOwnerBaseAnnotate==='function')globalThis.contextualDeepLinkAnnotate=function(){const value=campaignResultsOwnerBaseAnnotate.apply(this,arguments);campaignResultsOwnerEnsureContext();return value};
const campaignResultsOwnerBaseFindTarget=globalThis.contextualDeepLinkFindTarget;
if(typeof campaignResultsOwnerBaseFindTarget==='function')globalThis.contextualDeepLinkFindTarget=function(context){
  if(campaignResultsOwnerMatches(context)){const matches=[...document.querySelectorAll('[data-deep-results-campaign-id]')].filter(node=>String(node.dataset.deepResultsCampaignId||'')===String(context.target_id));return matches.length===1?matches[0]:null}
  return campaignResultsOwnerBaseFindTarget.apply(this,arguments)
};

function campaignResultsOwnerMeta(key,label,controlKind,kind,explanation,targetKind=POST_W99_CAMPAIGN_RESULTS_TARGET_KIND){return{control_key:key,control_label:label,control_kind:controlKind,action_kind:kind,target_kind:targetKind,explanation}}
function campaignResultsOwnerResolve(row,targetInfo){
  const target=targetInfo?.node,context=targetInfo?.context||{},kind=campaignResultsOwnerText(row?.kind).toLowerCase();if(!target||String(context.target_kind||'')!==POST_W99_CAMPAIGN_RESULTS_TARGET_KIND)return null;
  if(kind==='capture_results'){
    const buttons=[...document.querySelectorAll('.w52-head .w52-actions button')].filter(button=>{const text=campaignResultsOwnerText(button.textContent);return text==='Actualizar resultados desde Meta'||text==='Consultando Meta…'});
    return controlHandoffSingle(buttons,campaignResultsOwnerMeta('W52_REFRESH_RESULTS','Actualizar resultados desde Meta','BUTTON',kind,'Control canónico W52. El click humano abre confirmación y solo entonces consulta providers para guardar un snapshot local; este handoff no ejecuta la lectura.'))
  }
  if(kind==='record_decision'){
    const campaignId=String(context.target_id||''),form=document.querySelector('.w52-decision-form');if(String(postW99CampaignResultsOwnerState.preparedDecisionId||'')===campaignId&&form?.dataset.postW99PreparedCampaignId===campaignId){return controlHandoffSingleGroup([form],text=>text==='Registrar decisión local',campaignResultsOwnerMeta('W52_SUBMIT_CAMPAIGN_DECISION','Completar razonamiento + registrar decisión','CONTROL_GROUP',kind,'El formulario W52 quedó preparado por click humano para la campaña exacta. Solo se resuelve cuando existe un único Registrar decisión local habilitado; el usuario conserva decisión, razonamiento y submit final.'))}
    const buttons=[...target.querySelectorAll('button[data-post-w99-results-decision-prepare]')];return controlHandoffSingle(buttons,campaignResultsOwnerMeta('PREPARE_W52_CAMPAIGN_DECISION','Preparar decisión para esta campaña','BUTTON',kind,'Este botón solo prepara el formulario canónico W52 con el campaign_id exacto. No registra ni ejecuta una decisión.'))
  }
  if(kind==='review_coverage')return controlHandoffSingle([target],campaignResultsOwnerMeta('REVIEW_EXACT_CAMPAIGN_COVERAGE','Revisar cobertura de la campaña exacta','READ_ONLY_SURFACE',kind,'La superficie reúne snapshot, evidencia y atribución locales de la campaña exacta. Revisarla no consulta providers ni cambia estado.'));
  if(kind==='review_results')return controlHandoffSingle([target],campaignResultsOwnerMeta('REVIEW_EXACT_CAMPAIGN_RESULTS','Revisar resultados de la campaña exacta','READ_ONLY_SURFACE',kind,'La superficie exacta conserva evidencia, atribución y decisión humana sin inferir causalidad ni ejecutar recomendaciones.'));
  return null
}
const campaignResultsOwnerBaseResolveControl=globalThis.controlHandoffResolveControl;
if(typeof campaignResultsOwnerBaseResolveControl==='function')globalThis.controlHandoffResolveControl=function(row,targetInfo){
  const kind=campaignResultsOwnerText(row?.kind).toLowerCase(),targetKind=campaignResultsOwnerText(targetInfo?.context?.target_kind).toUpperCase();
  if(targetKind===POST_W99_CAMPAIGN_RESULTS_TARGET_KIND){const resolved=campaignResultsOwnerResolve(row,targetInfo);if(resolved)return resolved}
  if(targetKind==='CAMPAIGN_INTELLIGENCE'&&kind==='optional_ai'){
    const target=targetInfo?.node,buttons=target?[...target.querySelectorAll('.w65-actions button')].filter(button=>{const text=campaignResultsOwnerText(button.textContent);return text==='Analizar con IA'||text==='Analizando…'}):[];
    return controlHandoffSingle(buttons,campaignResultsOwnerMeta('W65_OPTIONAL_AI','Analizar con IA','BUTTON',kind,'Control canónico W65. El usuario debe confirmar explícitamente el envío de contexto sanitizado; la IA no obtiene autoridad de ejecución.','CAMPAIGN_INTELLIGENCE'))
  }
  return campaignResultsOwnerBaseResolveControl.apply(this,arguments)
};

function campaignResultsOwnerSchedule(){queueMicrotask(()=>{campaignResultsOwnerEnsureContext();if(typeof contextualDeepLinkSchedule==='function')contextualDeepLinkSchedule();if(typeof controlHandoffSchedule==='function')controlHandoffSchedule()})}
function campaignResultsOwnerWrap(name){const base=globalThis[name];if(typeof base!=='function'||base.__postW99CampaignResultsOwner)return;const wrapped=function(){const value=base.apply(this,arguments);campaignResultsOwnerSchedule();return value};wrapped.__postW99CampaignResultsOwner=true;globalThis[name]=wrapped}
['renderMarketingOps','wave52RenderAnalytics','wave65Render'].forEach(campaignResultsOwnerWrap);
window.addEventListener('marketing-ops-refreshed',campaignResultsOwnerSchedule);window.addEventListener('pageshow',campaignResultsOwnerSchedule);campaignResultsOwnerStyles();campaignResultsOwnerSchedule();
