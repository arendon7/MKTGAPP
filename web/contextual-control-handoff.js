const POST_W99_CONTROL_HANDOFF_SCHEMA='binario.marketing.contextual-control-handoff.v1';
const postW99ControlHandoffState={last:null};

function controlHandoffText(value){return value===null||value===undefined?'':String(value).trim()}
function controlHandoffExecutionContext(){
  if(typeof postW99ExecutionReturnState!=='undefined'&&postW99ExecutionReturnState.active)return postW99ExecutionReturnState.active;
  if(typeof executionReturnRead==='function')return executionReturnRead();
  return null;
}
function controlHandoffCompany(){return typeof opsSelectedCompany==='function'?opsSelectedCompany():null}
function controlHandoffActionRow(execution){
  if(!execution?.action_id)return{state:'ACTION_CONTEXT_NOT_RESOLVED',row:null,reason:'No existe action_id del recorrido Today.'};
  const company=controlHandoffCompany();
  if(!company?.id||String(company.id)!==String(execution.company_id))return{state:'ACTION_CONTEXT_NOT_RESOLVED',row:null,reason:'La empresa activa no coincide con el recorrido Today.'};
  const plan=typeof postW99TodayState!=='undefined'?(postW99TodayState.payload?.plan||[]):[];
  const matches=plan.filter(row=>String(row?.id||'')===String(execution.action_id));
  if(matches.length!==1)return{state:'ACTION_CONTEXT_NOT_RESOLVED',row:null,reason:'La acción exacta no está disponible una sola vez en el plan Today ya cargado.'};
  return{state:'ACTION_CONTEXT_RESOLVED',row:matches[0],reason:'Action ID exacta recuperada del plan Today local.'};
}
function controlHandoffExactTarget(){
  const deep=typeof postW99ContextualDeepLinkState!=='undefined'?postW99ContextualDeepLinkState.active:null;
  const status=typeof postW99ContextualDeepLinkState!=='undefined'?postW99ContextualDeepLinkState.lastStatus:null;
  if(!deep||status!=='FOUND_EXACT')return{state:'TARGET_NOT_EXACT',context:deep,node:null,reason:'Contextual Deep Linking no ha confirmado FOUND_EXACT.'};
  const nodes=[...document.querySelectorAll('.contextual-deep-link-highlight')];
  if(nodes.length!==1)return{state:'TARGET_NOT_EXACT',context:deep,node:null,reason:'El DOM no contiene exactamente un target resaltado por ID canónico.'};
  return{state:'TARGET_EXACT',context:deep,node:nodes[0],reason:'Target exacto confirmado por Contextual Deep Linking.'};
}
function controlHandoffButton(target,predicate){return target?[...target.querySelectorAll('button')].filter(button=>predicate(controlHandoffText(button.textContent),button)):[]}
function controlHandoffSingle(nodes,meta){
  if(nodes.length===0)return{state:'CONTROL_NOT_AVAILABLE',node:null,...meta};
  if(nodes.length>1)return{state:'CONTROL_AMBIGUOUS',node:null,...meta};
  const node=nodes[0];
  if(('disabled'in node)&&node.disabled)return{state:'CONTROL_NOT_AVAILABLE',node:null,...meta,explanation:`${meta.explanation} El control está deshabilitado en el owner.`};
  return{state:'CONTROL_RESOLVED',node,...meta};
}
function controlHandoffSingleGroup(groups,controlPredicate,meta){
  if(groups.length===0)return{state:'CONTROL_NOT_AVAILABLE',node:null,...meta};
  if(groups.length>1)return{state:'CONTROL_AMBIGUOUS',node:null,...meta};
  const group=groups[0],controls=controlHandoffButton(group,controlPredicate);
  if(controls.length===0)return{state:'CONTROL_NOT_AVAILABLE',node:null,...meta,explanation:`${meta.explanation} El submit canónico no está disponible en el grupo.`};
  if(controls.length>1)return{state:'CONTROL_AMBIGUOUS',node:null,...meta,explanation:`${meta.explanation} El grupo expone más de un submit candidato.`};
  if(controls[0].disabled)return{state:'CONTROL_NOT_AVAILABLE',node:null,...meta,explanation:`${meta.explanation} El submit canónico está deshabilitado en el owner.`};
  return{state:'CONTROL_RESOLVED',node:group,canonical_node:controls[0],...meta};
}
function controlHandoffOwnerGap(kind,targetKind,explanation){
  return{state:'OWNER_CONTROL_GAP',node:null,control_key:null,control_label:null,control_kind:null,action_kind:kind,target_kind:targetKind,explanation};
}
function controlHandoffResolveControl(row,targetInfo){
  const target=targetInfo.node,deep=targetInfo.context||{},kind=controlHandoffText(row?.kind).toLowerCase(),targetKind=controlHandoffText(deep.target_kind).toUpperCase();
  const meta=(controlKey,controlLabel,controlKind,explanation)=>({control_key:controlKey,control_label:controlLabel,control_kind:controlKind,action_kind:kind,target_kind:targetKind,explanation});

  if(targetKind==='ACTIVITY'&&['crm_overdue','crm_today'].includes(kind)){
    return controlHandoffSingle(controlHandoffButton(target,text=>text==='Completar'),meta('COMPLETE_ACTIVITY','Completar seguimiento','BUTTON','Control existente en CRM. Resaltarlo no significa que deba completarse: la decisión sigue siendo humana.'));
  }
  if(targetKind==='ACTIVITY'&&kind==='crm_unscheduled'){
    return controlHandoffOwnerGap(kind,targetKind,'El seguimiento exacto está visible en CRM, pero esa card no expone Reprogramar. Ese control existe hoy en el Workdesk/Home y no se sustituye por Completar ni se cruza a otro owner de forma implícita.');
  }
  if(targetKind==='PUBLICATION'&&['publication_failed','publication_overdue','publication_today'].includes(kind)){
    const selectedMatches=typeof editorialState!=='undefined'&&String(editorialState.selectedId||'')===String(deep.target_id||'');
    const panels=selectedMatches?[...document.querySelectorAll('#marketing-ops-view .editorial-panel')]:[];
    return controlHandoffSingle(panels,meta('MANAGE_PUBLICATION_PANEL','Editar, reprogramar o cancelar publicación','CONTROL_GROUP','Contextual Deep Linking ya abrió el panel editorial del publication ID exacto. El usuario conserva copy, fecha y elección explícita de guardar o cancelar.'));
  }
  if(targetKind==='LEAD'&&kind==='lead_conflict'){
    const groups=[...target.querySelectorAll('.w61-actions')].filter(group=>group.querySelectorAll('select').length===1);
    return controlHandoffSingleGroup(groups,text=>text==='Resolver conflicto exacto',meta('RESOLVE_EXACT_LEAD_CONFLICT','Seleccionar contacto + resolver conflicto exacto','CONTROL_GROUP','El grupo exige selección humana de identidad antes de vincular; nada se preselecciona ni ejecuta.'));
  }
  if(targetKind==='LEAD'&&kind==='lead_matched'){
    return controlHandoffSingle(controlHandoffButton(target,text=>text.startsWith('Vincular · ')),meta('LINK_EXACT_MATCH','Vincular coincidencia exacta','BUTTON','La coincidencia ya proviene del owner; el usuario conserva la decisión explícita de vincular.'));
  }
  if(targetKind==='LEAD'&&['lead_new','lead_unidentified'].includes(kind)){
    return controlHandoffSingle(controlHandoffButton(target,text=>text==='Crear contacto'),meta('CREATE_CONTACT_FROM_LEAD','Crear contacto','BUTTON','Usa la conversión explícita existente en la Mesa Comercial; no crea contactos automáticamente.'));
  }
  if(targetKind==='HANDOFF'&&kind==='needs_opportunity'){
    const forms=[...target.querySelectorAll('form.w61-form')];
    return controlHandoffSingleGroup(forms,text=>text==='Crear oportunidad',meta('CREATE_HANDOFF_OPPORTUNITY','Completar datos + crear oportunidad','CONTROL_GROUP','El formulario canónico conserva título, valor, moneda y submit explícito del usuario.'));
  }
  if(targetKind==='HANDOFF'&&kind==='needs_followup'){
    const forms=[...target.querySelectorAll('form.w61-form.follow')];
    return controlHandoffSingleGroup(forms,text=>text==='Programar seguimiento',meta('SCHEDULE_HANDOFF_FOLLOWUP','Completar datos + programar seguimiento','CONTROL_GROUP','El formulario canónico conserva resumen, fecha opcional y submit explícito del usuario.'));
  }
  if(targetKind==='CAMPAIGN'&&kind==='define_channels'){
    const selectedMatches=typeof campaignState!=='undefined'&&String(campaignState.selectedId||'')===String(deep.target_id||'');
    const forms=selectedMatches?[...document.querySelectorAll('#marketing-ops-view form.campaign-form')]:[];
    return controlHandoffSingleGroup(forms,text=>text==='Guardar cambios',meta('DEFINE_CAMPAIGN_CHANNELS','Seleccionar canales + guardar cambios','CONTROL_GROUP','La campaña exacta ya está seleccionada. El formulario canónico permite definir canales y exige Guardar cambios explícitamente; cambiar estado solo organiza trabajo y no envía ni activa providers.'));
  }
  if(targetKind==='CAMPAIGN_EXECUTION'){
    return controlHandoffSingle([...target.querySelectorAll('.w64-next button')].filter(button=>controlHandoffText(button.textContent)==='Ir'),meta('OPEN_EXECUTION_NEXT_OWNER','Ir al siguiente owner','BUTTON','Este botón solo navega al módulo canónico definido por Execution Workspace; no ejecuta la acción de negocio.'));
  }
  if(targetKind==='CAMPAIGN_INTELLIGENCE'&&kind==='optional_ai'){
    return controlHandoffSingle([...target.querySelectorAll('.w65-actions button')].filter(button=>['Analizar con IA','Analizando…'].includes(controlHandoffText(button.textContent))),meta('REQUEST_OPTIONAL_AI_ANALYSIS','Analizar con IA','BUTTON','La acción Action Center es OPTIONAL_AI. El control propietario exige una solicitud humana explícita y el owner muestra confirmación antes de enviar contexto marketing sanitizado; la IA no ejecuta recomendaciones.'));
  }
  if(targetKind==='CAMPAIGN_INTELLIGENCE'){
    return controlHandoffOwnerGap(kind,targetKind,'La campaña exacta está en Results Intelligence, pero esta acción no tiene un control específico mapeado. No se usa el botón Ir como sustituto cuando la semántica de Action Center exige otra operación.');
  }
  if(targetKind==='OPPORTUNITY'&&kind.startsWith('pipeline_')){
    return controlHandoffOwnerGap(kind,targetKind,'La oportunidad exacta existe, pero el CRM actual no ofrece dentro de esa card un control canónico específico para programar/editar el seguimiento que originó esta atención. No se sustituye por el selector de etapa.');
  }
  if(targetKind==='MEDIA'&&['create_creative','finish_creative','prepare_distribution','coordinate'].includes(kind)){
    return controlHandoffOwnerGap(kind,targetKind,'El activo exacto está localizado, pero Usar como Reel y Eliminar no equivalen de forma general a crear/terminar creativo o preparar/coordinar distribución. No se promueve un control destructivo ni uno de canal específico como sustituto.');
  }
  return controlHandoffOwnerGap(kind,targetKind,'El registro exacto está localizado, pero esta combinación acción/owner no tiene un control canónico inequívoco mapeado. No se elige un control por similitud.');
}
function controlHandoffResolve(){
  const execution=controlHandoffExecutionContext();
  if(!execution)return null;
  const action=controlHandoffActionRow(execution);
  if(action.state!=='ACTION_CONTEXT_RESOLVED')return{schema:POST_W99_CONTROL_HANDOFF_SCHEMA,state:action.state,execution,row:null,target:null,control:null,explanation:action.reason};
  const target=controlHandoffExactTarget();
  if(target.state!=='TARGET_EXACT')return{schema:POST_W99_CONTROL_HANDOFF_SCHEMA,state:target.state,execution,row:action.row,target:target.context||null,control:null,explanation:target.reason};
  const control=controlHandoffResolveControl(action.row,target);
  return{schema:POST_W99_CONTROL_HANDOFF_SCHEMA,state:control.state,execution,row:action.row,target:target.context,control,explanation:control.explanation};
}

function controlHandoffStyles(){
  if(document.querySelector('#post-w99-control-handoff-style'))return;
  const style=document.createElement('style');style.id='post-w99-control-handoff-style';style.textContent=`
.contextual-control-handoff-context{margin:0 0 12px;padding:10px 12px;border:1px solid #d8d2c8;border-radius:12px;background:#fff;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px;align-items:center}.contextual-control-handoff-copy{display:grid;gap:3px}.contextual-control-handoff-copy small{font-size:7px;letter-spacing:.09em;color:#777067}.contextual-control-handoff-copy strong{font-size:10px}.contextual-control-handoff-copy span{font-size:8px;color:#706a61}.contextual-control-handoff-chip{display:inline-flex;padding:4px 7px;border-radius:999px;background:#f1eee8;font-size:7px;white-space:nowrap}.contextual-control-handoff-highlight{outline:3px dashed #171717!important;outline-offset:5px!important}.contextual-control-handoff-highlight::after{content:'CONTROL CANÓNICO';display:inline-flex;width:max-content;margin:5px 0 0;padding:3px 6px;border-radius:999px;background:#171717;color:#fff;font-size:7px;letter-spacing:.07em}@media(max-width:700px){.contextual-control-handoff-context{grid-template-columns:1fr}.contextual-control-handoff-chip{width:max-content}}
`;document.head.append(style)
}
function controlHandoffClear(){
  document.querySelector('#post-w99-contextual-control-handoff')?.remove();
  document.querySelectorAll('.contextual-control-handoff-highlight').forEach(node=>{node.classList.remove('contextual-control-handoff-highlight');delete node.dataset.postW99ControlHandoff});
}
function controlHandoffMessage(result){
  if(result.state==='CONTROL_RESOLVED')return{title:'Control canónico localizado',detail:`${result.control.control_label}. El resaltado solo orienta: no dispara el control ni modifica estado.`,chip:'CONTROL EXACTO'};
  if(result.state==='OWNER_CONTROL_GAP')return{title:'Registro exacto, sin control específico',detail:result.explanation,chip:'OWNER GAP'};
  if(result.state==='CONTROL_NOT_AVAILABLE')return{title:'Control esperado no disponible',detail:result.explanation,chip:'NO DISPONIBLE'};
  if(result.state==='CONTROL_AMBIGUOUS')return{title:'Control ambiguo',detail:'El owner expone más de un candidato para esta regla. No se seleccionó ninguno.',chip:'AMBIGUO'};
  if(result.state==='TARGET_NOT_EXACT')return{title:'Sin target exacto',detail:result.explanation,chip:'FAIL CLOSED'};
  return{title:'Contexto de acción no resuelto',detail:result.explanation||'No existe contexto local suficiente para señalar un control.',chip:'FAIL CLOSED'};
}
function controlHandoffDecorate(){
  controlHandoffStyles();controlHandoffClear();const result=controlHandoffResolve();postW99ControlHandoffState.last=result;if(!result)return;
  if(result.state==='CONTROL_RESOLVED'&&result.control?.node){result.control.node.classList.add('contextual-control-handoff-highlight');result.control.node.dataset.postW99ControlHandoff='1'}
  const root=document.querySelector('#marketing-ops-view');if(!root)return;const message=controlHandoffMessage(result),card=opsEl('section','contextual-control-handoff-context');card.id='post-w99-contextual-control-handoff';const copy=opsEl('div','contextual-control-handoff-copy');copy.append(opsEl('small','','PLAN DE HOY · HANDOFF DE CONTROL'),opsEl('strong','',message.title),opsEl('span','',message.detail));card.append(copy,opsEl('span','contextual-control-handoff-chip',message.chip));const deepCard=root.querySelector('#post-w99-contextual-deep-link-context');if(deepCard)deepCard.insertAdjacentElement('afterend',card);else root.prepend(card)
}
function controlHandoffSchedule(){queueMicrotask(controlHandoffDecorate)}
function controlHandoffWrap(name){const base=globalThis[name];if(typeof base!=='function'||base.__postW99ControlHandoff)return;const wrapped=function(){const value=base.apply(this,arguments);controlHandoffSchedule();return value};wrapped.__postW99ControlHandoff=true;globalThis[name]=wrapped}
['renderMarketingOps','crmRenderCurrent','campaignRenderCurrent','wave61Render','wave64Render','wave65Render','contentRenderCurrent'].forEach(controlHandoffWrap);
window.addEventListener('marketing-ops-refreshed',controlHandoffSchedule);window.addEventListener('pageshow',controlHandoffSchedule);controlHandoffStyles();controlHandoffSchedule();
