const POST_W99_CONTEXTUAL_ACTION_HANDOFF_SCHEMA='binario.marketing.contextual-action-handoff.v1';
const postW99ContextualActionHandoffState={active:null,lastStatus:null,control:null};

function contextualActionHandoffText(value){return value===null||value===undefined?'':String(value)}
function contextualActionHandoffReason(item){return contextualActionHandoffText(item?.reason?.code).toUpperCase()}
function contextualActionHandoffKind(item){return contextualActionHandoffText(item?.kind).toLowerCase()}
function contextualActionHandoffSource(item){return{
  schema:POST_W99_CONTEXTUAL_ACTION_HANDOFF_SCHEMA,
  action_id:contextualActionHandoffText(item?.id)||null,
  source:contextualActionHandoffText(item?.source)||null,
  kind:contextualActionHandoffKind(item)||null,
  reason_code:contextualActionHandoffReason(item)||null,
  title:contextualActionHandoffText(item?.title)||contextualActionHandoffText(item?.action?.label)||'Acción operativa',
  action_label:contextualActionHandoffText(item?.action?.label)||null,
};}

function contextualActionHandoffClear(removeSource=true){
  document.querySelector('#post-w99-contextual-action-handoff')?.remove();
  document.querySelectorAll('.contextual-action-control-highlight').forEach(node=>node.classList.remove('contextual-action-control-highlight'));
  if(removeSource){postW99ContextualActionHandoffState.active=null;postW99ContextualActionHandoffState.lastStatus=null;postW99ContextualActionHandoffState.control=null}
}

function contextualActionHandoffStyles(){
  if(document.querySelector('#post-w99-contextual-action-handoff-style'))return;
  const style=document.createElement('style');style.id='post-w99-contextual-action-handoff-style';style.textContent=`
  .contextual-action-handoff{margin:0 0 12px;padding:11px 12px;border:1px solid #c9c3b9;border-radius:12px;background:#fff;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px;align-items:center}.contextual-action-handoff-copy{display:grid;gap:3px;min-width:0}.contextual-action-handoff-copy small{font-size:7px;letter-spacing:.09em;color:#777067}.contextual-action-handoff-copy strong{font-size:10px}.contextual-action-handoff-copy span{font-size:8px;color:#706a61;line-height:1.45}.contextual-action-handoff-chip{display:inline-flex;padding:4px 7px;border-radius:999px;background:#efede7;color:#171717;font-size:7px;white-space:nowrap}.contextual-action-handoff-chip.ready{background:#171717;color:#fff}.contextual-action-handoff-chip.review{background:#e7eee8}.contextual-action-handoff-chip.blocked{background:#f4e8df}.contextual-action-control-highlight{outline:2px solid #171717!important;outline-offset:2px!important;box-shadow:0 0 0 4px rgba(23,23,23,.07)!important}@media(max-width:700px){.contextual-action-handoff{grid-template-columns:1fr}.contextual-action-handoff-chip{width:max-content}}
  `;document.head.append(style)
}

function contextualActionHandoffButtons(root){return root?[...root.querySelectorAll('button')]:[]}
function contextualActionHandoffButton(root,{exact=[],prefix=[]}={}){
  for(const button of contextualActionHandoffButtons(root)){
    const label=contextualActionHandoffText(button.textContent).trim();
    if(exact.includes(label)||prefix.some(value=>label.startsWith(value)))return button;
  }
  return null
}
function contextualActionHandoffResult(status,{control=null,label=null,mode='PRESENTATION',detail='',confirmation=false,prerequisite=null}={}){
  return{status,control,label,mode,detail,confirmation:Boolean(confirmation),prerequisite};
}
function contextualActionHandoffControlStatus(control,mode){
  if(!control)return'CONTROL_NOT_FOUND';
  if(control.disabled)return'CONTROL_NOT_READY';
  return mode==='NAVIGATION'||mode==='REVIEW_ONLY'?'REVIEW_READY':'ACTION_READY'
}

function contextualActionHandoffResolve(target,context,item){
  const targetKind=contextualActionHandoffText(context?.target_kind),reason=contextualActionHandoffReason(item),kind=contextualActionHandoffKind(item);
  if(!target||!targetKind)return contextualActionHandoffResult('OWNER_ONLY',{detail:'No existe un target exacto sobre el cual resolver un control propietario.'});

  if(targetKind==='ACTIVITY'){
    if(kind==='crm_unscheduled'||reason.includes('UNSCHEDULED')){
      const control=contextualActionHandoffButton(target,{exact:['Reprogramar']});
      const status=contextualActionHandoffControlStatus(control,'LOCAL_WRITE');
      return contextualActionHandoffResult(status,{control,label:'Reprogramar',mode:'LOCAL_WRITE',detail:control?'Este control cambia únicamente la fecha del seguimiento local.':'La prioridad exige programación/reprogramación, pero este registro CRM no expone ese control inline. “Completar” no se usa como sustituto.',prerequisite:'Elegir una fecha futura válida.'});
    }
    const control=contextualActionHandoffButton(target,{exact:['Completar']});
    const status=contextualActionHandoffControlStatus(control,'LOCAL_WRITE');
    return contextualActionHandoffResult(status,{control,label:'Completar',mode:'LOCAL_WRITE',detail:control?'Marca explícitamente este seguimiento local como completado; el módulo CRM conserva la mutación.':'El registro exacto está visible, pero no expone el control “Completar”. La ausencia del botón no significa que la tarea esté completada.'});
  }

  if(targetKind==='OPPORTUNITY'){
    if(reason.startsWith('PIPELINE_'))return contextualActionHandoffResult('NO_ACTION_MAPPING',{label:'Seguimiento de oportunidad',mode:'REVIEW_ONLY',detail:'La alerta proviene de seguimiento o fecha. El selector de etapa visible en la oportunidad no resuelve ese motivo y no se propone como sustituto.'});
    return contextualActionHandoffResult('NO_ACTION_MAPPING',{label:'Revisar oportunidad',mode:'REVIEW_ONLY',detail:'La oportunidad exacta está localizada, pero Action Handoff no tiene evidencia suficiente para escoger un control de mutación sin cambiar la semántica de la tarea.'});
  }

  if(targetKind==='CONTACT'){
    return contextualActionHandoffResult('REVIEW_READY',{control:target,label:'Ver ficha',mode:'NAVIGATION',detail:'La tarjeta exacta abre la ficha CRM existente. Es navegación local; no modifica el contacto por sí sola.'});
  }

  if(targetKind==='PUBLICATION'){
    if(reason==='WORKDESK_PUBLICATION_TODAY')return contextualActionHandoffResult('REVIEW_READY',{label:'Revisar publicación',mode:'REVIEW_ONLY',detail:'La publicación de hoy está localizada. La prioridad requiere revisión, no una mutación automática.'});
    const selected=typeof editorialState!=='undefined'&&String(editorialState.selectedId||'')===String(context.target_id||'');
    const panel=selected?document.querySelector('.editorial-panel'):null;
    const control=contextualActionHandoffButton(panel,{exact:['Guardar nueva versión']});
    const status=contextualActionHandoffControlStatus(control,'LOCAL_WRITE');
    return contextualActionHandoffResult(status,{control,label:'Guardar nueva versión',mode:'LOCAL_WRITE',detail:control?'Corrige copy/fecha creando una nueva versión trazable; Editorial conserva todas las reglas de revisión y programación.':'La publicación exacta está visible, pero el panel de gestión no expone “Guardar nueva versión” en este estado.',prerequisite:'Revisar copy y, si aplica, elegir una fecha válida.'});
  }

  if(targetKind==='LEAD'){
    const actions=target.querySelector('.w61-actions');
    const control=contextualActionHandoffButton(actions,{exact:['Resolver conflicto exacto','Crear contacto'],prefix:['Vincular · ']});
    const status=contextualActionHandoffControlStatus(control,'LOCAL_WRITE');
    const label=control?contextualActionHandoffText(control.textContent).trim():'Resolver lead';
    const select=actions?.querySelector('select')||null;
    return contextualActionHandoffResult(status,{control,label,mode:'LOCAL_WRITE',detail:control?'Usa la decisión explícita ya implementada por Mesa Comercial. No hay matching difuso ni conversión automática.':'El lead exacto está visible, pero su estado actual no expone una acción de conversión canónica.',prerequisite:select?'Seleccionar explícitamente el contacto exacto antes de resolver el conflicto.':null});
  }

  if(targetKind==='HANDOFF'){
    const control=contextualActionHandoffButton(target.querySelector('form.w61-form'),{exact:['Crear oportunidad','Programar seguimiento']});
    const status=contextualActionHandoffControlStatus(control,'LOCAL_WRITE');
    return contextualActionHandoffResult(status,{control,label:control?contextualActionHandoffText(control.textContent).trim():'Completar handoff',mode:'LOCAL_WRITE',detail:control?'El formulario ya existente crea exactamente el siguiente objeto comercial faltante; la decisión sigue siendo explícita y humana.':'El handoff exacto está visible, pero no expone el formulario esperado para su estado actual.'});
  }

  if(targetKind==='CAMPAIGN'){
    const selected=typeof campaignState!=='undefined'&&String(campaignState.selectedId||'')===String(context.target_id||'');
    const form=selected?document.querySelector('.campaign-form'):null;
    const control=contextualActionHandoffButton(form,{exact:['Guardar cambios']});
    const status=contextualActionHandoffControlStatus(control,'LOCAL_WRITE');
    return contextualActionHandoffResult(status,{control,label:'Guardar cambios',mode:'LOCAL_WRITE',detail:control?'Guarda explícitamente la edición de la campaña. Cambiarla a “En curso” organiza trabajo; no envía ni activa providers.':'La campaña exacta está localizada, pero el formulario editable no está disponible en la lectura actual.'});
  }

  if(targetKind==='CAMPAIGN_EXECUTION'){
    const control=contextualActionHandoffButton(target.querySelector('.w64-next'),{exact:['Ir']});
    const status=contextualActionHandoffControlStatus(control,'NAVIGATION');
    return contextualActionHandoffResult(status,{control,label:'Ir',mode:'NAVIGATION',detail:control?'Este control abre el módulo canónico del siguiente paso. Execution Workspace no ejecuta la mutación por debajo.':'La campaña está localizada, pero su bloque de siguiente paso no expone el control de navegación esperado.'});
  }

  if(targetKind==='CAMPAIGN_INTELLIGENCE'){
    if(reason==='CAMPAIGN_OPTIONAL_AI'){
      const control=contextualActionHandoffButton(target.querySelector('.w65-actions'),{prefix:['Analizar con IA','Analizando…']});
      const status=contextualActionHandoffControlStatus(control,'EXPLICIT_AI_REQUEST');
      return contextualActionHandoffResult(status,{control,label:'Analizar con IA',mode:'EXPLICIT_AI_REQUEST',detail:control?'La solicitud de IA permanece opcional, explícita y sujeta a la confirmación del módulo; no ejecuta recomendaciones.':'La campaña exacta está visible, pero el análisis IA no está disponible en este estado.',confirmation:true});
    }
    const control=contextualActionHandoffButton(target.querySelector('.w65-next'),{exact:['Ir']});
    const status=contextualActionHandoffControlStatus(control,'NAVIGATION');
    return contextualActionHandoffResult(status,{control,label:'Ir',mode:'NAVIGATION',detail:control?'Abre el owner canónico de la siguiente acción derivada de evidencia/decisión. Results Intelligence no ejecuta esa acción.':'La campaña está localizada, pero no aparece el control canónico de siguiente paso.'});
  }

  if(targetKind==='MEDIA'){
    return contextualActionHandoffResult('NO_ACTION_MAPPING',{label:'Revisar contenido',mode:'REVIEW_ONLY',detail:'El activo exacto está localizado. “Eliminar” nunca se recomienda como siguiente acción por defecto y “Usar como Reel” no se equipara a cualquier tarea creativa sin evidencia adicional.'});
  }

  return contextualActionHandoffResult('NO_ACTION_MAPPING',{label:'Revisar owner',mode:'REVIEW_ONLY',detail:'El registro exacto existe, pero no hay un mapeo determinístico a un control canónico para este tipo de acción.'});
}

function contextualActionHandoffModeLabel(mode){
  const labels={LOCAL_WRITE:'ESCRITURA LOCAL',NAVIGATION:'NAVEGACIÓN',REVIEW_ONLY:'REVISIÓN',EXPLICIT_AI_REQUEST:'IA EXPLÍCITA',PRESENTATION:'PRESENTACIÓN'};return labels[mode]||mode;
}
function contextualActionHandoffStatusCopy(result){
  if(result.status==='ACTION_READY')return['Acción canónica disponible',`${result.label} · ${contextualActionHandoffModeLabel(result.mode)}. ${result.detail}`,'ACTION READY','ready'];
  if(result.status==='REVIEW_READY')return['Siguiente control disponible',`${result.label||'Revisar'} · ${contextualActionHandoffModeLabel(result.mode)}. ${result.detail}`,'REVIEW READY','review'];
  if(result.status==='CONTROL_NOT_READY')return['Control presente, todavía no disponible',`${result.label||'Control'} está deshabilitado en el estado actual. ${result.detail}`,'NOT READY','blocked'];
  if(result.status==='CONTROL_NOT_FOUND')return['El control esperado no está disponible',result.detail||'No se sustituye por otro control ni se infiere completitud.','CONTROL MISSING','blocked'];
  if(result.status==='NO_ACTION_MAPPING')return['Registro localizado; acción no inferida',result.detail||'No existe un mapeo seguro a un control canónico.','NO MAPPING',''];
  return['Owner sin acción exacta','Se conserva la navegación existente sin inventar una mutación.','OWNER ONLY',''];
}

function contextualActionHandoffRender(result,source){
  const root=document.querySelector('#marketing-ops-view');if(!root)return;
  root.querySelector('#post-w99-contextual-action-handoff')?.remove();
  const card=opsEl('section','contextual-action-handoff');card.id='post-w99-contextual-action-handoff';
  const copy=opsEl('div','contextual-action-handoff-copy'),[title,detail,chip,chipClass]=contextualActionHandoffStatusCopy(result);
  const suffix=result.prerequisite?` Requisito: ${result.prerequisite}`:'';
  copy.append(opsEl('small','','PLAN DE HOY · HANDOFF AL OWNER'),opsEl('strong','',title),opsEl('span','',`${source?.title||'Acción'} · ${detail}${suffix} La app no acciona este control por ti; después de actuar, vuelve al Plan de hoy para releer Action Center.`));
  card.append(copy,opsEl('span',`contextual-action-handoff-chip ${chipClass}`,chip));
  const anchor=root.querySelector('#post-w99-contextual-deep-link-context');if(anchor)anchor.insertAdjacentElement('afterend',card);else root.prepend(card)
}

function contextualActionHandoffDecorate(){
  contextualActionHandoffStyles();
  document.querySelectorAll('.contextual-action-control-highlight').forEach(node=>node.classList.remove('contextual-action-control-highlight'));
  const source=postW99ContextualActionHandoffState.active,deep=typeof postW99ContextualDeepLinkState!=='undefined'?postW99ContextualDeepLinkState:null,context=deep?.active||null;
  if(!source||!context){contextualActionHandoffClear(Boolean(source&&!context));return}
  if(typeof contextualDeepLinkViewMatches==='function'&&!contextualDeepLinkViewMatches(context)){document.querySelector('#post-w99-contextual-action-handoff')?.remove();return}
  if(deep.lastStatus!=='FOUND_EXACT'){
    document.querySelector('#post-w99-contextual-action-handoff')?.remove();postW99ContextualActionHandoffState.lastStatus=deep.lastStatus||'OWNER_ONLY';postW99ContextualActionHandoffState.control=null;return
  }
  const target=typeof contextualDeepLinkFindTarget==='function'?contextualDeepLinkFindTarget(context):null;
  if(!target){document.querySelector('#post-w99-contextual-action-handoff')?.remove();postW99ContextualActionHandoffState.lastStatus='CONTROL_NOT_FOUND';return}
  const result=contextualActionHandoffResolve(target,context,source.raw);
  postW99ContextualActionHandoffState.lastStatus=result.status;postW99ContextualActionHandoffState.control=result.control||null;
  if(result.control)result.control.classList.add('contextual-action-control-highlight');
  contextualActionHandoffRender(result,source)
}
function contextualActionHandoffSchedule(){queueMicrotask(contextualActionHandoffDecorate)}

const contextualActionHandoffBaseOpen=globalThis.actionCenterOpen;
if(typeof contextualActionHandoffBaseOpen==='function')globalThis.actionCenterOpen=function(item){
  const source=contextualActionHandoffSource(item);source.raw=item;postW99ContextualActionHandoffState.active=source;postW99ContextualActionHandoffState.lastStatus=null;postW99ContextualActionHandoffState.control=null;
  const value=contextualActionHandoffBaseOpen.apply(this,arguments);contextualActionHandoffSchedule();return value
};

function contextualActionHandoffWrapRender(name){
  const base=globalThis[name];if(typeof base!=='function'||base.__postW99ContextualActionHandoff)return;
  const wrapped=function(){const value=base.apply(this,arguments);contextualActionHandoffSchedule();return value};wrapped.__postW99ContextualActionHandoff=true;globalThis[name]=wrapped
}
['renderMarketingOps','crmRenderCurrent','campaignRenderCurrent','wave61Render','wave64Render','wave65Render','contentRenderCurrent'].forEach(contextualActionHandoffWrapRender);

window.addEventListener('marketing-company-change',()=>contextualActionHandoffClear(true));
contextualActionHandoffStyles();contextualActionHandoffSchedule();
