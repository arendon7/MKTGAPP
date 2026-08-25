const POST_W99_CONTEXTUAL_DEEP_LINK_SCHEMA='binario.marketing.contextual-deep-link.v1';
const postW99ContextualDeepLinkState={active:null,lastStatus:null};

function contextualDeepLinkText(value){return value===null||value===undefined?'':String(value)}
function contextualDeepLinkCompany(){return typeof opsSelectedCompany==='function'?opsSelectedCompany():null}
function contextualDeepLinkAction(item){return item?.action||item||{}}
function contextualDeepLinkDescriptor(item){
  const action=contextualDeepLinkAction(item),view=contextualDeepLinkText(action.view),tab=contextualDeepLinkText(action.tab),kind=contextualDeepLinkText(item?.kind).toLowerCase();
  const base={schema:POST_W99_CONTEXTUAL_DEEP_LINK_SCHEMA,owner_view:view,tab:tab||null,target_kind:'OWNER_ONLY',target_id:null,lead_id:contextualDeepLinkText(action.lead_id)||null,contact_id:contextualDeepLinkText(action.contact_id)||null,opportunity_id:contextualDeepLinkText(action.opportunity_id)||null,campaign_id:contextualDeepLinkText(action.campaign_id)||null,media_id:contextualDeepLinkText(action.media_id)||null,entity_id:contextualDeepLinkText(action.entity_id)||null,title:contextualDeepLinkText(item?.title)||contextualDeepLinkText(postW99ExecutionReturnState?.active?.title)||contextualDeepLinkText(action.label)||'Acción operativa',focused:false};
  if(view==='crm'){
    if(tab==='followups'&&base.entity_id){base.target_kind='ACTIVITY';base.target_id=base.entity_id;return base}
    if((tab==='pipeline'||base.opportunity_id)&&base.opportunity_id){base.target_kind='OPPORTUNITY';base.target_id=base.opportunity_id;return base}
    if(base.contact_id){base.target_kind='CONTACT';base.target_id=base.contact_id;return base}
    return base;
  }
  if(view==='calendar'&&base.entity_id){base.target_kind='PUBLICATION';base.target_id=base.entity_id;return base}
  if(view==='commercial-desk'&&base.lead_id){base.target_kind=base.contact_id?'HANDOFF':'LEAD';base.target_id=base.lead_id;return base}
  if(view==='campaigns'&&base.campaign_id){base.target_kind='CAMPAIGN';base.target_id=base.campaign_id;return base}
  if(view==='execution'&&base.campaign_id){base.target_kind='CAMPAIGN_EXECUTION';base.target_id=base.campaign_id;return base}
  if(view==='intelligence'&&base.campaign_id){base.target_kind='CAMPAIGN_INTELLIGENCE';base.target_id=base.campaign_id;return base}
  if(view==='content'&&base.media_id){base.target_kind='MEDIA';base.target_id=base.media_id;return base}
  return base;
}

function contextualDeepLinkClear(removeContext=true){
  document.querySelector('#post-w99-contextual-deep-link-context')?.remove();
  document.querySelectorAll('.contextual-deep-link-highlight').forEach(node=>node.classList.remove('contextual-deep-link-highlight'));
  if(removeContext){postW99ContextualDeepLinkState.active=null;postW99ContextualDeepLinkState.lastStatus=null}
}
function contextualDeepLinkStyles(){if(document.querySelector('#post-w99-contextual-deep-link-style'))return;const style=document.createElement('style');style.id='post-w99-contextual-deep-link-style';style.textContent=`
.contextual-deep-link-context{margin:0 0 12px;padding:10px 12px;border:1px solid #d8d2c8;border-radius:12px;background:#f7f4ee;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px;align-items:center}.contextual-deep-link-copy{display:grid;gap:3px;min-width:0}.contextual-deep-link-copy small{font-size:7px;letter-spacing:.09em;color:#777067}.contextual-deep-link-copy strong{font-size:10px}.contextual-deep-link-copy span{font-size:8px;color:#706a61}.contextual-deep-link-chip{display:inline-flex;padding:4px 7px;border-radius:999px;background:#171717;color:#fff;font-size:7px;white-space:nowrap}.contextual-deep-link-highlight{outline:3px solid #171717!important;outline-offset:3px!important;box-shadow:0 0 0 6px rgba(23,23,23,.08)!important}.contextual-deep-link-highlight::before{content:'PLAN DE HOY';display:inline-flex;width:max-content;margin:0 0 5px;padding:3px 6px;border-radius:999px;background:#171717;color:#fff;font-size:7px;letter-spacing:.07em}@media(max-width:700px){.contextual-deep-link-context{grid-template-columns:1fr}.contextual-deep-link-chip{width:max-content}}
`;document.head.append(style)}

function contextualDeepLinkPrepareOwner(context){
  if(!context)return;
  try{
    if(context.owner_view==='crm'&&typeof crmState!=='undefined'){
      if(context.target_kind==='ACTIVITY')crmState.tab='followups';
      else if(context.target_kind==='OPPORTUNITY')crmState.tab='pipeline';
      else if(context.target_kind==='CONTACT')crmState.tab='contacts';
    }
    if(context.owner_view==='calendar'&&context.target_kind==='PUBLICATION'&&typeof editorialState!=='undefined')editorialState.selectedId=context.target_id;
    if(context.owner_view==='campaigns'&&context.target_kind==='CAMPAIGN'&&typeof campaignState!=='undefined')campaignState.selectedId=context.target_id;
    if(context.owner_view==='execution'&&typeof wave64ExecutionState!=='undefined')wave64ExecutionState.onlyAction=false;
    if(context.owner_view==='intelligence'&&typeof wave65ResultsState!=='undefined')wave65ResultsState.onlyAttention=false;
  }catch(_err){}
}

function contextualDeepLinkAssign(nodes,rows,key,datasetKey){
  const list=[...nodes];list.forEach((node,index)=>{const value=rows[index]?.[key];if(value!==undefined&&value!==null&&value!=='')node.dataset[datasetKey]=String(value)})
}
function contextualDeepLinkAnnotateCrm(){
  if(typeof crmState==='undefined')return;
  contextualDeepLinkAssign(document.querySelectorAll('.crm-contact'),crmState.contacts||[],'id','deepContactId');
  const stages=typeof crmStages!=='undefined'?crmStages:[],columns=[...document.querySelectorAll('.crm-pipeline .crm-column')];
  stages.forEach(([stage],index)=>{const rows=(crmState.opportunities||[]).filter(row=>row.stage===stage);contextualDeepLinkAssign(columns[index]?.querySelectorAll('.crm-opportunity')||[],rows,'id','deepOpportunityId')});
  const activities=[...(crmState.activities||[])].sort((a,b)=>typeof crmActivityKey==='function'?crmActivityKey(a).localeCompare(crmActivityKey(b)):0);contextualDeepLinkAssign(document.querySelectorAll('.crm-followup'),activities,'id','deepActivityId');
}
function contextualDeepLinkAnnotateCalendar(){const rows=[...(marketingOpsState?.calendar||[])].sort((a,b)=>String(a.scheduled_for||a.created_at).localeCompare(String(b.scheduled_for||b.created_at)));contextualDeepLinkAssign(document.querySelectorAll('.marketing-ops-calendar-row'),rows,'id','deepPublicationId')}
function contextualDeepLinkAnnotateCampaigns(){if(typeof campaignState==='undefined')return;contextualDeepLinkAssign(document.querySelectorAll('.campaign-card'),campaignState.rows||[],'id','deepCampaignId')}
function contextualDeepLinkAnnotateCommercial(){
  if(typeof wave61State==='undefined'||!wave61State.data)return;const lanes=[...document.querySelectorAll('.w61-board .w61-lane')],data=wave61State.data;
  contextualDeepLinkAssign(lanes[1]?.querySelectorAll('.w61-list > .w61-row')||[],(data.lead_queue||[]).slice(0,8),'lead_id','deepLeadId');
  const handoffs=(data.handoffs||[]).slice(0,8).filter(row=>row.handoff_state!=='CLOSED'),nodes=[...(lanes[2]?.querySelectorAll('.w61-list > .w61-row')||[])];nodes.forEach((node,index)=>{const row=handoffs[index];if(!row)return;if(row.lead_id)node.dataset.deepHandoffLeadId=String(row.lead_id);if(row.contact_id)node.dataset.deepHandoffContactId=String(row.contact_id);if(row.opportunity_id)node.dataset.deepHandoffOpportunityId=String(row.opportunity_id)})
}
function contextualDeepLinkAnnotateExecution(){if(typeof wave64ExecutionState==='undefined')return;const rows=(wave64ExecutionState.payload?.campaigns||[]).filter(row=>!wave64ExecutionState.onlyAction||row.requires_action);const nodes=[...document.querySelectorAll('.w64-card')];nodes.forEach((node,index)=>{const id=rows[index]?.campaign?.id;if(id)node.dataset.deepExecutionCampaignId=String(id)})}
function contextualDeepLinkAnnotateIntelligence(){if(typeof wave65ResultsState==='undefined')return;const rows=(wave65ResultsState.payload?.campaigns||[]).filter(row=>!wave65ResultsState.onlyAttention||row.requires_attention);const nodes=[...document.querySelectorAll('.w65-card')];nodes.forEach((node,index)=>{const id=rows[index]?.campaign?.id;if(id)node.dataset.deepIntelligenceCampaignId=String(id)})}
function contextualDeepLinkAnnotateContent(){if(typeof companyContentState==='undefined')return;contextualDeepLinkAssign(document.querySelectorAll('.company-content-card'),companyContentState.media||[],'id','deepMediaId')}
function contextualDeepLinkAnnotate(){contextualDeepLinkAnnotateCrm();contextualDeepLinkAnnotateCalendar();contextualDeepLinkAnnotateCampaigns();contextualDeepLinkAnnotateCommercial();contextualDeepLinkAnnotateExecution();contextualDeepLinkAnnotateIntelligence();contextualDeepLinkAnnotateContent()}

function contextualDeepLinkOwnerReady(context){
  const company=contextualDeepLinkCompany();if(!context||!company?.id)return false;
  if(context.owner_view==='crm')return typeof crmState!=='undefined'&&crmState.loaded&&crmState.companyId===company.id;
  if(context.owner_view==='campaigns')return typeof campaignState!=='undefined'&&campaignState.loaded&&campaignState.companyId===company.id;
  if(context.owner_view==='commercial-desk')return typeof wave61State!=='undefined'&&wave61State.data&&wave61State.companyId===company.id;
  if(context.owner_view==='execution')return typeof wave64ExecutionState!=='undefined'&&wave64ExecutionState.payload&&wave64ExecutionState.companyId===company.id;
  if(context.owner_view==='intelligence')return typeof wave65ResultsState!=='undefined'&&wave65ResultsState.payload&&wave65ResultsState.companyId===company.id;
  if(context.owner_view==='content')return typeof companyContentState!=='undefined'&&companyContentState.loaded&&companyContentState.companyId===company.id;
  return true;
}
function contextualDeepLinkFindByDataset(key,value){if(!value)return null;return [...document.querySelectorAll(`[data-${key}]`)].find(node=>node.dataset[key.replace(/-([a-z])/g,(_m,c)=>c.toUpperCase())]===String(value))||null}
function contextualDeepLinkFindTarget(context){
  if(!context?.target_id)return null;
  if(context.target_kind==='ACTIVITY')return contextualDeepLinkFindByDataset('deep-activity-id',context.target_id);
  if(context.target_kind==='OPPORTUNITY')return contextualDeepLinkFindByDataset('deep-opportunity-id',context.target_id);
  if(context.target_kind==='CONTACT')return contextualDeepLinkFindByDataset('deep-contact-id',context.target_id);
  if(context.target_kind==='PUBLICATION')return contextualDeepLinkFindByDataset('deep-publication-id',context.target_id);
  if(context.target_kind==='LEAD')return contextualDeepLinkFindByDataset('deep-lead-id',context.target_id);
  if(context.target_kind==='HANDOFF'){
    const candidates=[...document.querySelectorAll('[data-deep-handoff-lead-id]')].filter(node=>node.dataset.deepHandoffLeadId===String(context.target_id));
    return candidates.find(node=>(!context.contact_id||node.dataset.deepHandoffContactId===String(context.contact_id))&&(!context.opportunity_id||node.dataset.deepHandoffOpportunityId===String(context.opportunity_id)))||candidates[0]||null;
  }
  if(context.target_kind==='CAMPAIGN')return contextualDeepLinkFindByDataset('deep-campaign-id',context.target_id);
  if(context.target_kind==='CAMPAIGN_EXECUTION')return contextualDeepLinkFindByDataset('deep-execution-campaign-id',context.target_id);
  if(context.target_kind==='CAMPAIGN_INTELLIGENCE')return contextualDeepLinkFindByDataset('deep-intelligence-campaign-id',context.target_id);
  if(context.target_kind==='MEDIA')return contextualDeepLinkFindByDataset('deep-media-id',context.target_id);
  return null;
}
function contextualDeepLinkViewMatches(context){if(!context)return false;const view=contextualDeepLinkText(marketingOpsState?.view);if(context.owner_view==='content')return view==='content';return view===context.owner_view}
function contextualDeepLinkRenderContext(context,status){
  const root=document.querySelector('#marketing-ops-view');if(!root)return;root.querySelector('#post-w99-contextual-deep-link-context')?.remove();
  const card=opsEl('section','contextual-deep-link-context');card.id='post-w99-contextual-deep-link-context';const copy=opsEl('div','contextual-deep-link-copy');let strong='Módulo abierto',detail='No hay un identificador suficientemente específico para afirmar un registro exacto.',chip='OWNER ONLY';
  if(status==='FOUND_EXACT'){strong='Registro exacto localizado';detail=`${context.title} · ${context.target_kind} ${String(context.target_id).slice(0,12)}${String(context.target_id).length>12?'…':''}. El resaltado es navegación, no estado de negocio.`;chip='EXACT TARGET'}
  else if(status==='TARGET_NOT_FOUND'){strong='El módulo abrió, pero el registro no está visible';detail='El identificador exacto no apareció en la lectura local actual. No se eligió otro registro por similitud y no se infirió que la tarea estuviera completada.';chip='NOT FOUND'}
  else if(status==='LOADING'){strong='Localizando el registro exacto';detail='El módulo propietario todavía está cargando su lectura local. No se ejecutará ninguna acción durante la localización.';chip='LOCAL READ'}
  copy.append(opsEl('small','','PLAN DE HOY · CONTEXTO DE NAVEGACIÓN'),opsEl('strong','',strong),opsEl('span','',detail));card.append(copy,opsEl('span','contextual-deep-link-chip',chip));root.prepend(card)
}
function contextualDeepLinkDecorate(){
  contextualDeepLinkStyles();document.querySelectorAll('.contextual-deep-link-highlight').forEach(node=>node.classList.remove('contextual-deep-link-highlight'));const context=postW99ContextualDeepLinkState.active;if(!context||!contextualDeepLinkViewMatches(context)){document.querySelector('#post-w99-contextual-deep-link-context')?.remove();return}
  contextualDeepLinkAnnotate();if(context.target_kind==='OWNER_ONLY'){postW99ContextualDeepLinkState.lastStatus='OWNER_ONLY';contextualDeepLinkRenderContext(context,'OWNER_ONLY');return}
  if(!contextualDeepLinkOwnerReady(context)){postW99ContextualDeepLinkState.lastStatus='LOADING';contextualDeepLinkRenderContext(context,'LOADING');return}
  const target=contextualDeepLinkFindTarget(context);if(!target){postW99ContextualDeepLinkState.lastStatus='TARGET_NOT_FOUND';contextualDeepLinkRenderContext(context,'TARGET_NOT_FOUND');return}
  target.classList.add('contextual-deep-link-highlight');postW99ContextualDeepLinkState.lastStatus='FOUND_EXACT';contextualDeepLinkRenderContext(context,'FOUND_EXACT');if(!context.focused){context.focused=true;try{target.scrollIntoView({block:'center',behavior:'smooth'})}catch(_err){target.scrollIntoView()}}
}
function contextualDeepLinkSchedule(){queueMicrotask(contextualDeepLinkDecorate)}

const contextualDeepLinkBaseOpen=globalThis.actionCenterOpen;
if(typeof contextualDeepLinkBaseOpen==='function')globalThis.actionCenterOpen=function(item){const context=contextualDeepLinkDescriptor(item);postW99ContextualDeepLinkState.active=context;postW99ContextualDeepLinkState.lastStatus=null;contextualDeepLinkPrepareOwner(context);const value=contextualDeepLinkBaseOpen.apply(this,arguments);contextualDeepLinkSchedule();return value};

function contextualDeepLinkWrapRender(name){const base=globalThis[name];if(typeof base!=='function'||base.__postW99ContextualDeepLink)return;const wrapped=function(){const value=base.apply(this,arguments);contextualDeepLinkSchedule();return value};wrapped.__postW99ContextualDeepLink=true;globalThis[name]=wrapped}
['renderMarketingOps','crmRenderCurrent','campaignRenderCurrent','wave61Render','wave64Render','wave65Render','contentRenderCurrent'].forEach(contextualDeepLinkWrapRender);

const contextualDeepLinkBaseShowView=globalThis.opsShowView;
if(typeof contextualDeepLinkBaseShowView==='function')globalThis.opsShowView=function(view){const active=postW99ContextualDeepLinkState.active;if(active&&String(view)!==String(active.owner_view))contextualDeepLinkClear(true);const value=contextualDeepLinkBaseShowView.apply(this,arguments);contextualDeepLinkSchedule();return value};
const contextualDeepLinkBaseShowLegacy=globalThis.opsShowLegacy;
if(typeof contextualDeepLinkBaseShowLegacy==='function')globalThis.opsShowLegacy=function(){const active=postW99ContextualDeepLinkState.active;if(active&&active.owner_view!=='content')contextualDeepLinkClear(true);const value=contextualDeepLinkBaseShowLegacy.apply(this,arguments);contextualDeepLinkSchedule();return value};
const contextualDeepLinkBaseForget=globalThis.executionReturnForget;
if(typeof contextualDeepLinkBaseForget==='function')globalThis.executionReturnForget=function(){contextualDeepLinkClear(true);return contextualDeepLinkBaseForget.apply(this,arguments)};

contextualDeepLinkStyles();contextualDeepLinkSchedule();
