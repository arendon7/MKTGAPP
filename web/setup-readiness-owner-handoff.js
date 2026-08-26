const POST_W99_SETUP_READINESS_OWNER_HANDOFF_SCHEMA='binario.marketing.setup-readiness-owner-handoff.v1';
const POST_W99_SETUP_READINESS_KINDS=new Set(['setup_workspace','setup_meta','setup_facebook','setup_instagram','setup_ads','setup_campaign','setup_creative','setup_crm']);
const postW99SetupReadinessOwnerHandoffState={last:null,actionId:null,humanMediaId:null};
globalThis.postW99SetupReadinessOwnerHandoffState=postW99SetupReadinessOwnerHandoffState;

function setupHandoffText(value){return value===null||value===undefined?'':String(value).trim()}
function setupHandoffCompany(){return typeof opsSelectedCompany==='function'?opsSelectedCompany():null}
function setupHandoffButtons(root,label){return root?[...root.querySelectorAll('button')].filter(button=>setupHandoffText(button.textContent)===label):[]}
function setupHandoffSupported(row){return setupHandoffText(row?.source).toUpperCase()==='SETUP'&&POST_W99_SETUP_READINESS_KINDS.has(setupHandoffText(row?.kind).toLowerCase())}
function setupHandoffExecution(){
  if(typeof controlHandoffExecutionContext==='function')return controlHandoffExecutionContext();
  if(typeof postW99ExecutionReturnState!=='undefined'&&postW99ExecutionReturnState.active)return postW99ExecutionReturnState.active;
  if(typeof executionReturnRead==='function')return executionReturnRead();
  return null;
}
function setupHandoffAction(execution){
  if(typeof controlHandoffActionRow==='function')return controlHandoffActionRow(execution);
  if(!execution?.action_id)return{state:'ACTION_CONTEXT_NOT_RESOLVED',row:null,reason:'No existe action_id del recorrido Today.'};
  const company=setupHandoffCompany();
  if(!company?.id||String(company.id)!==String(execution.company_id))return{state:'ACTION_CONTEXT_NOT_RESOLVED',row:null,reason:'La empresa activa no coincide con el recorrido Today.'};
  const plan=typeof postW99TodayState!=='undefined'?(postW99TodayState.payload?.plan||[]):[];
  const matches=plan.filter(row=>String(row?.id||'')===String(execution.action_id));
  if(matches.length!==1)return{state:'ACTION_CONTEXT_NOT_RESOLVED',row:null,reason:'La acción exacta no está disponible una sola vez en el plan Today ya cargado.'};
  return{state:'ACTION_CONTEXT_RESOLVED',row:matches[0],reason:'Action ID exacta recuperada del plan Today local.'};
}
function setupHandoffResult(state,row,meta={}){
  return{schema:POST_W99_SETUP_READINESS_OWNER_HANDOFF_SCHEMA,state,row,kind:setupHandoffText(row?.kind).toLowerCase(),nodes:[],canonical_node:null,...meta};
}
function setupHandoffSingle(nodes,row,meta){
  if(nodes.length===0)return setupHandoffResult('CONTROL_NOT_AVAILABLE',row,{...meta,explanation:`${meta.explanation} El owner no expone el control esperado.`});
  if(nodes.length>1)return setupHandoffResult('CONTROL_AMBIGUOUS',row,{...meta,explanation:`${meta.explanation} El owner expone más de un control candidato.`});
  const node=nodes[0];
  if(('disabled'in node)&&node.disabled)return setupHandoffResult('CONTROL_NOT_AVAILABLE',row,{...meta,explanation:`${meta.explanation} El control está deshabilitado.`});
  return setupHandoffResult(meta.prerequisite?'PREREQUISITE_CONTROL_RESOLVED':'CONTROL_RESOLVED',row,{...meta,nodes:[node],canonical_node:node});
}
function setupHandoffSingleForm(forms,row,meta){
  if(forms.length===0)return setupHandoffResult('CONTROL_NOT_AVAILABLE',row,{...meta,explanation:`${meta.explanation} El formulario canónico no está disponible.`});
  if(forms.length>1)return setupHandoffResult('CONTROL_AMBIGUOUS',row,{...meta,explanation:`${meta.explanation} Hay más de un formulario candidato.`});
  const form=forms[0],submits=setupHandoffButtons(form,meta.submit_label);
  if(submits.length!==1||submits[0].disabled)return setupHandoffResult(submits.length>1?'CONTROL_AMBIGUOUS':'CONTROL_NOT_AVAILABLE',row,{...meta,explanation:`${meta.explanation} El submit canónico no es único y disponible.`});
  return setupHandoffResult(meta.prerequisite?'PREREQUISITE_CONTROL_RESOLVED':'CONTROL_RESOLVED',row,{...meta,nodes:[form],canonical_node:submits[0]});
}
function setupHandoffViewReady(row){
  const expected=setupHandoffText(row?.action?.view);
  const current=setupHandoffText(typeof marketingOpsState!=='undefined'?marketingOpsState.view:'');
  if(expected==='content')return current==='content';
  return Boolean(expected)&&current===expected;
}
function setupHandoffStale(row,explanation){return setupHandoffResult('STALE_ACTION_CONTEXT',row,{control_key:null,control_label:null,control_kind:null,explanation})}
function setupHandoffLoading(row,explanation){return setupHandoffResult('OWNER_LOADING',row,{control_key:null,control_label:null,control_kind:null,explanation})}
function setupHandoffRoot(){return document.querySelector('#marketing-ops-view')}
function setupHandoffExactForms(root,submitLabel,selector='form'){
  return root?[...root.querySelectorAll(selector)].filter(form=>setupHandoffButtons(form,submitLabel).length===1):[];
}
function setupHandoffMetaConnect(row,detail){
  const root=setupHandoffRoot(),forms=setupHandoffExactForms(root,'Conectar Meta','form.marketing-ops-form');
  return setupHandoffSingleForm(forms,row,{control_key:'CONNECT_META',control_label:'Ingresar credencial + Conectar Meta',control_kind:'CONTROL_GROUP',submit_label:'Conectar Meta',prerequisite:detail!==null,explanation:detail||'La readiness Meta se resuelve únicamente desde el formulario canónico de Empresas & Meta. El adapter no envía la credencial ni dispara el submit.'});
}
function setupHandoffRefreshAssets(row,detail){
  const root=setupHandoffRoot();
  return setupHandoffSingle(setupHandoffButtons(root,'Actualizar activos'),row,{control_key:'REFRESH_META_ASSETS',control_label:'Actualizar activos',control_kind:'BUTTON',prerequisite:true,explanation:detail});
}
function setupHandoffAssociation(row,kind){
  const company=setupHandoffCompany(),metaConfigured=Boolean(typeof wave47State!=='undefined'&&wave47State.metaStatus?.configured);
  const fieldMap={setup_facebook:'facebook_page_id',setup_instagram:'instagram_id',setup_ads:'ad_account_id'};
  const field=fieldMap[kind];
  if(company?.[field])return setupHandoffStale(row,`La empresa activa ya contiene ${field}; la fila Today ya no coincide con la readiness local y no se señalará otro control.`);
  if(!metaConfigured)return setupHandoffMetaConnect(row,'Antes de asociar este activo la credencial Meta debe existir. Se señala únicamente el prerequisito canónico; después Today debe releer el estado.');
  const root=setupHandoffRoot(),forms=setupHandoffExactForms(root,'Guardar asociaciones','form.marketing-ops-form');
  if(forms.length!==1)return setupHandoffResult(forms.length>1?'CONTROL_AMBIGUOUS':'CONTROL_NOT_AVAILABLE',row,{control_key:'SAVE_META_ASSOCIATIONS',control_label:'Guardar asociaciones',control_kind:'CONTROL_GROUP',explanation:'No existe exactamente un formulario de asociaciones Meta en el owner.'});
  const form=forms[0],save=setupHandoffButtons(form,'Guardar asociaciones');
  if(save.length!==1||save[0].disabled)return setupHandoffResult(save.length>1?'CONTROL_AMBIGUOUS':'CONTROL_NOT_AVAILABLE',row,{control_key:'SAVE_META_ASSOCIATIONS',control_label:'Guardar asociaciones',control_kind:'CONTROL_GROUP',explanation:'El submit de asociaciones no es único y disponible.'});
  const pageLabels=[...form.querySelectorAll('label')].filter(label=>setupHandoffText(label.textContent).startsWith('Página de Facebook / Instagram'));
  const adLabels=[...form.querySelectorAll('label')].filter(label=>setupHandoffText(label.textContent).startsWith('Cuenta publicitaria'));
  const labels=kind==='setup_ads'?adLabels:pageLabels;
  if(labels.length!==1)return setupHandoffResult(labels.length>1?'CONTROL_AMBIGUOUS':'CONTROL_NOT_AVAILABLE',row,{control_key:'SAVE_META_ASSOCIATIONS',control_label:'Guardar asociaciones',control_kind:'CONTROL_GROUP',explanation:'El campo de asociación esperado no es único.'});
  const select=labels[0].querySelector('select');if(!select)return setupHandoffResult('CONTROL_NOT_AVAILABLE',row,{control_key:'SAVE_META_ASSOCIATIONS',control_label:'Guardar asociaciones',control_kind:'CONTROL_GROUP',explanation:'El campo de asociación esperado no contiene select.'});
  const options=[...select.options].filter(option=>setupHandoffText(option.value));
  const eligible=kind==='setup_instagram'?options.filter(option=>setupHandoffText(option.textContent).includes('@')):options;
  if(!eligible.length)return setupHandoffRefreshAssets(row,kind==='setup_instagram'?'No hay una Página con Instagram profesional visible en la lectura actual. Actualizar activos es un prerequisito humano; no se selecciona una Página por similitud.':'No hay activos elegibles visibles en la lectura actual. Actualizar activos es un prerequisito humano; el adapter no consulta Meta por sí mismo.');
  return setupHandoffResult('CONTROL_RESOLVED',row,{control_key:kind==='setup_ads'?'ASSOCIATE_AD_ACCOUNT':'ASSOCIATE_SOCIAL_ASSET',control_label:kind==='setup_ads'?'Seleccionar cuenta publicitaria + Guardar asociaciones':kind==='setup_instagram'?'Seleccionar Página con Instagram + Guardar asociaciones':'Seleccionar Página + Guardar asociaciones',control_kind:'CONTROL_GROUP',nodes:[labels[0],save[0]],canonical_node:save[0],explanation:'Los activos candidatos provienen del owner ya cargado. El adapter no cambia select.value, no preselecciona activos y no envía el formulario.'});
}
function setupHandoffWorkspace(row){
  if(typeof wave47State!=='undefined'&&wave47State.workspace?.project_id)return setupHandoffStale(row,'El owner ya reporta project_id para el workspace; la fila Today está desactualizada y no se abrirá un segundo flujo por inferencia.');
  return setupHandoffSingle(setupHandoffButtons(setupHandoffRoot(),'Abrir Video Studio'),row,{control_key:'ENSURE_COMPANY_WORKSPACE',control_label:'Abrir Video Studio',control_kind:'BUTTON',prerequisite:false,explanation:'El botón propietario crea/reutiliza el workspace únicamente cuando el usuario lo pulsa. El adapter solo lo localiza.'});
}
function setupHandoffCampaign(row){
  const company=setupHandoffCompany();
  if(typeof campaignState==='undefined'||!campaignState.loaded||campaignState.companyId!==company?.id)return setupHandoffLoading(row,'El owner de campañas todavía no terminó su lectura local; no se asume que la readiness siga pendiente.');
  if((campaignState.rows||[]).length)return setupHandoffStale(row,'El owner ya contiene al menos una campaña; setup_campaign dejó de representar el estado local actual.');
  return setupHandoffSingleForm(setupHandoffExactForms(setupHandoffRoot(),'Crear campaña','form.campaign-form'),row,{control_key:'CREATE_FIRST_CAMPAIGN',control_label:'Completar formulario + Crear campaña',control_kind:'CONTROL_GROUP',submit_label:'Crear campaña',prerequisite:false,explanation:'La readiness campaña se resuelve con el formulario canónico. Ningún campo se completa ni el submit se dispara automáticamente.'});
}
function setupHandoffCrm(row){
  const company=setupHandoffCompany();
  if(typeof crmState==='undefined'||!crmState.loaded||crmState.companyId!==company?.id)return setupHandoffLoading(row,'CRM todavía no terminó su lectura local; el adapter no interpreta una pantalla parcial como ausencia de contactos.');
  if((crmState.contacts||[]).length)return setupHandoffStale(row,'CRM ya contiene contactos; setup_crm dejó de representar el estado local actual.');
  return setupHandoffSingleForm(setupHandoffExactForms(setupHandoffRoot(),'Guardar contacto','form.crm-form'),row,{control_key:'CREATE_FIRST_CONTACT',control_label:'Completar contacto + Guardar contacto',control_kind:'CONTROL_GROUP',submit_label:'Guardar contacto',prerequisite:false,explanation:'El formulario propietario conserva toda la entrada y persistencia. El adapter no crea contactos.'});
}
function setupHandoffCreative(row){
  const company=setupHandoffCompany();
  if(typeof wave49CreativeState==='undefined'||!wave49CreativeState.context||wave49CreativeState.companyId!==company?.id)return setupHandoffLoading(row,'Creative Studio todavía no terminó su lectura local; no se elige ningún medio mientras el contexto no sea canónico.');
  const context=wave49CreativeState.context,items=context.items||[];
  if(items.some(item=>Boolean(item?.creative)))return setupHandoffStale(row,'Creative Studio ya contiene al menos una ficha creativa; setup_creative dejó de representar la readiness actual.');
  const root=setupHandoffRoot();
  if(!items.length){
    postW99SetupReadinessOwnerHandoffState.humanMediaId=null;
    if(wave49CreativeState.tab==='library')return setupHandoffSingleForm(setupHandoffExactForms(root,'Agregar a biblioteca','form.company-content-upload'),row,{control_key:'IMPORT_FIRST_CREATIVE_MEDIA',control_label:'Elegir archivo + Agregar a biblioteca',control_kind:'CONTROL_GROUP',submit_label:'Agregar a biblioteca',prerequisite:true,explanation:'Antes de crear una ficha creativa debe existir un medio. La importación sigue siendo una acción humana explícita; después debe volver al Pipeline creativo.'});
    return setupHandoffSingle(setupHandoffButtons(root,'+ Importar'),row,{control_key:'OPEN_CREATIVE_IMPORT',control_label:'+ Importar',control_kind:'NAVIGATION_BUTTON',prerequisite:true,explanation:'No hay medios todavía. Este control solo abre la importación existente; no carga archivos por sí mismo.'});
  }
  if(wave49CreativeState.tab==='library')return setupHandoffSingle(setupHandoffButtons(root,'Pipeline creativo'),row,{control_key:'RETURN_TO_CREATIVE_PIPELINE',control_label:'Pipeline creativo',control_kind:'NAVIGATION_BUTTON',prerequisite:true,explanation:'Ya existen medios. Vuelve al Pipeline para elegir explícitamente cuál recibirá la primera ficha creativa.'});
  const validIds=new Set(items.map(item=>setupHandoffText(item?.media?.id)).filter(Boolean));
  const humanId=setupHandoffText(postW99SetupReadinessOwnerHandoffState.humanMediaId);
  if(!humanId||!validIds.has(humanId)||setupHandoffText(wave49CreativeState.selectedId)!==humanId){
    postW99SetupReadinessOwnerHandoffState.humanMediaId=null;
    const lists=[...root.querySelectorAll('.w49-list')];
    return setupHandoffResult(lists.length===1?'HUMAN_SELECTION_REQUIRED':lists.length>1?'CONTROL_AMBIGUOUS':'CONTROL_NOT_AVAILABLE',row,{control_key:'SELECT_CREATIVE_MEDIA',control_label:'Elegir una pieza del Pipeline',control_kind:'HUMAN_SELECTION',nodes:lists.length===1?[lists[0]]:[],canonical_node:null,explanation:'W49 puede mostrar una selección visual por defecto, pero este handoff no la acepta como intención humana. Haz click en la pieza exacta que quieres perfilar.'});
  }
  const selected=items.filter(item=>setupHandoffText(item?.media?.id)===humanId);
  if(selected.length!==1||selected[0]?.creative)return setupHandoffResult('CONTROL_NOT_AVAILABLE',row,{control_key:'SAVE_FIRST_CREATIVE_PROFILE',control_label:'Guardar ficha creativa',control_kind:'CONTROL_GROUP',explanation:'La pieza seleccionada ya no representa una única pieza sin ficha creativa.'});
  return setupHandoffSingleForm(setupHandoffExactForms(root,'Guardar ficha creativa','form.w49-form'),row,{control_key:'SAVE_FIRST_CREATIVE_PROFILE',control_label:'Completar ficha + Guardar ficha creativa',control_kind:'CONTROL_GROUP',submit_label:'Guardar ficha creativa',prerequisite:false,explanation:'La pieza fue elegida mediante click humano en esta sesión. El adapter no acepta la selección automática de W49, no cambia campos y no guarda la ficha.'});
}
function setupHandoffResolve(){
  const execution=setupHandoffExecution();if(!execution)return null;
  const action=setupHandoffAction(execution);if(action.state!=='ACTION_CONTEXT_RESOLVED')return setupHandoffResult(action.state,null,{explanation:action.reason||'No se pudo resolver la acción Today.'});
  const row=action.row;if(!setupHandoffSupported(row))return null;
  if(!setupHandoffViewReady(row))return setupHandoffResult('OWNER_NOT_OPEN',row,{explanation:'La vista propietaria de esta readiness todavía no está abierta; no se señalará un control fuera de contexto.'});
  const kind=setupHandoffText(row.kind).toLowerCase(),company=setupHandoffCompany();
  if(kind==='setup_meta'){
    if(typeof wave47State!=='undefined'&&wave47State.metaStatus?.configured)return setupHandoffStale(row,'Meta ya aparece conectado en el owner; setup_meta está desactualizado.');
    return setupHandoffMetaConnect(row,null);
  }
  if(['setup_facebook','setup_instagram','setup_ads'].includes(kind))return setupHandoffAssociation(row,kind);
  if(kind==='setup_workspace')return setupHandoffWorkspace(row);
  if(kind==='setup_campaign')return setupHandoffCampaign(row);
  if(kind==='setup_creative')return setupHandoffCreative(row);
  if(kind==='setup_crm')return setupHandoffCrm(row);
  return null;
}
function setupHandoffPrepare(item){
  const id=setupHandoffText(item?.id);if(id!==postW99SetupReadinessOwnerHandoffState.actionId){postW99SetupReadinessOwnerHandoffState.actionId=id;postW99SetupReadinessOwnerHandoffState.humanMediaId=null}
  if(!setupHandoffSupported(item))return;
  const kind=setupHandoffText(item.kind).toLowerCase();
  if(kind==='setup_crm'&&typeof crmState!=='undefined')crmState.tab='contacts';
  if(kind==='setup_creative'&&typeof wave49CreativeState!=='undefined')wave49CreativeState.tab='pipeline';
}
function setupHandoffBindCreativeChoices(){
  const execution=setupHandoffExecution(),action=setupHandoffAction(execution||{}),row=action.row;
  if(action.state!=='ACTION_CONTEXT_RESOLVED'||!setupHandoffSupported(row)||setupHandoffText(row.kind).toLowerCase()!=='setup_creative')return;
  if(typeof wave49CreativeState==='undefined'||wave49CreativeState.tab!=='pipeline'||!wave49CreativeState.context)return;
  const items=wave49CreativeState.context.items||[],buttons=[...document.querySelectorAll('#marketing-ops-view .w49-item')];
  buttons.forEach((button,index)=>{if(button.dataset.postW99SetupCreativeChoice)return;button.dataset.postW99SetupCreativeChoice='1';button.addEventListener('click',()=>{const expected=setupHandoffText(items[index]?.media?.id),selected=setupHandoffText(wave49CreativeState.selectedId);postW99SetupReadinessOwnerHandoffState.humanMediaId=expected&&selected===expected?expected:null;setupHandoffSchedule()})});
}
function setupHandoffStyles(){
  if(document.querySelector('#post-w99-setup-readiness-owner-handoff-style'))return;const style=document.createElement('style');style.id='post-w99-setup-readiness-owner-handoff-style';style.textContent=`
.setup-readiness-owner-handoff-context{margin:0 0 12px;padding:10px 12px;border:1px solid #d8d2c8;border-radius:12px;background:#fff;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px;align-items:center}.setup-readiness-owner-handoff-copy{display:grid;gap:3px}.setup-readiness-owner-handoff-copy small{font-size:7px;letter-spacing:.09em;color:#777067}.setup-readiness-owner-handoff-copy strong{font-size:10px}.setup-readiness-owner-handoff-copy span{font-size:8px;color:#706a61}.setup-readiness-owner-handoff-chip{display:inline-flex;padding:4px 7px;border-radius:999px;background:#171717;color:#fff;font-size:7px;white-space:nowrap}.setup-readiness-owner-handoff-highlight{outline:3px dashed #171717!important;outline-offset:5px!important}.setup-readiness-owner-handoff-highlight::after{content:'SETUP · CONTROL';display:inline-flex;width:max-content;margin:5px 0 0;padding:3px 6px;border-radius:999px;background:#171717;color:#fff;font-size:7px;letter-spacing:.07em}@media(max-width:700px){.setup-readiness-owner-handoff-context{grid-template-columns:1fr}.setup-readiness-owner-handoff-chip{width:max-content}}
`;document.head.append(style)
}
function setupHandoffClear(){document.querySelector('#post-w99-setup-readiness-owner-handoff')?.remove();document.querySelectorAll('.setup-readiness-owner-handoff-highlight').forEach(node=>node.classList.remove('setup-readiness-owner-handoff-highlight'))}
function setupHandoffMessage(result){
  if(result.state==='CONTROL_RESOLVED')return{title:'Control de configuración localizado',detail:`${result.control_label}. El resaltado orienta; la decisión y el submit siguen siendo humanos.`,chip:'CONTROL EXACTO'};
  if(result.state==='PREREQUISITE_CONTROL_RESOLVED')return{title:'Prerequisito de configuración localizado',detail:`${result.control_label}. Completa este paso y deja que Today relea el estado antes del siguiente.`,chip:'PREREQUISITO'};
  if(result.state==='HUMAN_SELECTION_REQUIRED')return{title:'Elige la pieza exacta',detail:result.explanation,chip:'HUMAN CLICK'};
  if(result.state==='STALE_ACTION_CONTEXT')return{title:'La readiness ya cambió',detail:result.explanation,chip:'STALE · REFRESH'};
  if(result.state==='OWNER_LOADING')return{title:'Cargando estado propietario',detail:result.explanation,chip:'LOCAL READ'};
  if(result.state==='CONTROL_AMBIGUOUS')return{title:'Control ambiguo',detail:result.explanation,chip:'FAIL CLOSED'};
  if(result.state==='CONTROL_NOT_AVAILABLE')return{title:'Control esperado no disponible',detail:result.explanation,chip:'FAIL CLOSED'};
  return{title:'Handoff de configuración no resuelto',detail:result.explanation||'No existe evidencia suficiente para señalar un control.',chip:'FAIL CLOSED'};
}
function setupHandoffDecorate(){
  setupHandoffStyles();setupHandoffClear();setupHandoffBindCreativeChoices();const result=setupHandoffResolve();postW99SetupReadinessOwnerHandoffState.last=result;if(!result||!setupHandoffSupported(result.row))return;
  document.querySelector('#post-w99-contextual-control-handoff')?.remove();
  for(const node of result.nodes||[])if(node){node.classList.add('setup-readiness-owner-handoff-highlight')}
  const root=setupHandoffRoot();if(!root)return;const message=setupHandoffMessage(result),card=opsEl('section','setup-readiness-owner-handoff-context');card.id='post-w99-setup-readiness-owner-handoff';const copy=opsEl('div','setup-readiness-owner-handoff-copy');copy.append(opsEl('small','','PLAN DE HOY · SETUP OWNER HANDOFF'),opsEl('strong','',message.title),opsEl('span','',message.detail));card.append(copy,opsEl('span','setup-readiness-owner-handoff-chip',message.chip));const deep=root.querySelector('#post-w99-contextual-deep-link-context');if(deep)deep.insertAdjacentElement('afterend',card);else root.prepend(card)
}
function setupHandoffSchedule(){queueMicrotask(setupHandoffDecorate)}
function setupHandoffWrap(name){const base=globalThis[name];if(typeof base!=='function'||base.__postW99SetupReadinessOwnerHandoff)return;const wrapped=function(){const value=base.apply(this,arguments);setupHandoffSchedule();return value};wrapped.__postW99SetupReadinessOwnerHandoff=true;globalThis[name]=wrapped}

const setupHandoffBaseOpen=globalThis.actionCenterOpen;
if(typeof setupHandoffBaseOpen==='function')globalThis.actionCenterOpen=function(item){setupHandoffPrepare(item);const value=setupHandoffBaseOpen.apply(this,arguments);setupHandoffSchedule();return value};
['renderMarketingOps','crmRenderCurrent','campaignRenderCurrent','contentRenderCurrent'].forEach(setupHandoffWrap);
window.addEventListener('marketing-ops-refreshed',setupHandoffSchedule);window.addEventListener('pageshow',setupHandoffSchedule);setupHandoffStyles();setupHandoffSchedule();
