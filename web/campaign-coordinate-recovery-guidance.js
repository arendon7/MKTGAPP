const POST_W99_CAMPAIGN_COORDINATE_RECOVERY_SCHEMA='binario.marketing.campaign-coordinate-recovery-guidance.v1';

function coordinateRecoveryText(value){return value===null||value===undefined?'':String(value).trim()}
function coordinateRecoveryKind(row){return coordinateRecoveryText(row?.kind).toLowerCase()}
function coordinateRecoveryMeta(key,label,controlKind,explanation){return{schema:POST_W99_CAMPAIGN_COORDINATE_RECOVERY_SCHEMA,control_key:key,control_label:label,control_kind:controlKind,action_kind:'coordinate',target_kind:'MEDIA',explanation}}

function coordinateRecoveryMediaControl(row,targetInfo){
  const guidance=row?.coordinate_recovery||{},deep=targetInfo?.context||{};
  if(coordinateRecoveryKind(row)!=='coordinate'||guidance.state!=='EXACT_RECOVERY_OWNER'||guidance.intent!=='CREATE_NEW_DISTRIBUTION_FROM_CANCELLED_LINEAGE')return null;
  if(coordinateRecoveryText(deep.target_kind).toUpperCase()!=='MEDIA'||coordinateRecoveryText(deep.target_id)!==coordinateRecoveryText(guidance.target_id))return null;
  const selected=typeof wave49CreativeState!=='undefined'&&coordinateRecoveryText(wave49CreativeState.selectedId)===coordinateRecoveryText(guidance.target_id),item=selected&&typeof wave49SelectedItem==='function'?wave49SelectedItem():null;
  if(!item||coordinateRecoveryText(item?.media?.id)!==coordinateRecoveryText(guidance.target_id))return controlHandoffOwnerGap('coordinate','MEDIA','Creative Studio no confirma el media_id exacto derivado de la lineage cancelada. No se elige otra pieza.');
  const groups=[...document.querySelectorAll('.w49-editor > .w49-actions')];
  if(groups.length!==1)return groups.length?{state:'CONTROL_AMBIGUOUS',node:null,...coordinateRecoveryMeta('W49_RECREATE_CANCELLED_DISTRIBUTION','Elegir nueva distribución','CONTROL_GROUP','Creative Studio expone más de un grupo operativo para la pieza exacta. No se elige uno.')}:controlHandoffOwnerGap('coordinate','MEDIA','La pieza exacta está abierta, pero W49 no expone su grupo canónico de distribución.');
  const labels={PREPARE_FACEBOOK:'Preparar Facebook',PREPARE_INSTAGRAM:'Preparar Instagram',SEND_TO_PAID:'Enviar a Pauta'},expected=(guidance.recovery_controls||[]).map(key=>labels[key]).filter(Boolean),buttons=[...groups[0].querySelectorAll('button')].filter(button=>expected.includes(coordinateRecoveryText(button.textContent)));
  const meta=coordinateRecoveryMeta('W49_RECREATE_CANCELLED_DISTRIBUTION',expected.length===1?expected[0]:'Elegir nueva distribución',expected.length===1?'BUTTON':'CONTROL_GROUP','Los objetos CANCELLED permanecen terminales. Este control crea una ruta nueva desde el creativo exacto y solo se ejecuta tras acción humana explícita.');
  if(expected.length===0)return controlHandoffOwnerGap('coordinate','MEDIA','La lineage exacta existe, pero no hay un control W49 certificado para ese tipo de distribución cancelada.');
  if(buttons.length!==expected.length)return{state:'CONTROL_NOT_AVAILABLE',node:null,...meta,explanation:`${meta.explanation} Uno o más controles esperados no están disponibles en el owner.`};
  if(buttons.length>1)return{state:'CONTROL_AMBIGUOUS',node:null,...meta,explanation:`${meta.explanation} Hay ${buttons.length} rutas humanas válidas (${expected.join(', ')}); no se preselecciona ninguna.`};
  return controlHandoffSingle(buttons,meta)
}

const coordinateRecoveryBaseResolve=globalThis.controlHandoffResolveControl;
if(typeof coordinateRecoveryBaseResolve==='function')globalThis.controlHandoffResolveControl=function(row,targetInfo){
  const guidance=row?.coordinate_recovery||{},kind=coordinateRecoveryKind(row),deep=targetInfo?.context||{};
  if(kind==='coordinate'&&guidance.state==='EXACT_EXISTING_OWNER'&&guidance.intent==='OBSERVE_PUBLICATION_IN_FLIGHT'&&coordinateRecoveryText(deep.target_kind).toUpperCase()==='PUBLICATION'&&coordinateRecoveryText(deep.target_id)===coordinateRecoveryText(guidance.target_id)){
    return controlHandoffOwnerGap('coordinate','PUBLICATION','La publicación PUBLISHING exacta está localizada para observación. Este estado está en vuelo dentro del owner canónico: no se autoriza retry, completar, cancelar ni otra mutación desde Coordinate Recovery Guidance.')
  }
  const media=coordinateRecoveryMediaControl(row,targetInfo);if(media)return media;
  return coordinateRecoveryBaseResolve.apply(this,arguments)
};

const coordinateRecoveryBaseMessage=globalThis.controlHandoffMessage;
if(typeof coordinateRecoveryBaseMessage==='function')globalThis.controlHandoffMessage=function(result){
  if(result?.state==='CONTROL_AMBIGUOUS'&&result?.control?.schema===POST_W99_CAMPAIGN_COORDINATE_RECOVERY_SCHEMA)return{title:'Owner exacto, varias rutas humanas',detail:result.explanation||result.control.explanation,chip:'ELECCIÓN HUMANA'};
  return coordinateRecoveryBaseMessage.apply(this,arguments)
};

function coordinateRecoveryCurrentRow(){
  if(typeof controlHandoffExecutionContext!=='function'||typeof controlHandoffActionRow!=='function')return null;
  const execution=controlHandoffExecutionContext(),resolved=controlHandoffActionRow(execution);return resolved?.state==='ACTION_CONTEXT_RESOLVED'?resolved.row:null
}
function coordinateRecoveryStateCopy(guidance){
  const state=coordinateRecoveryText(guidance?.state).toUpperCase();
  if(state==='EXACT_EXISTING_OWNER')return['Publicación en curso localizada','El publication_id PUBLISHING es único. Solo se observa su owner; no existe una acción de retry o cierre autorizada aquí.','OBSERVACIÓN'];
  if(state==='EXACT_RECOVERY_OWNER')return['Origen cancelado localizado','Los objetos cancelados siguen terminales. La pieza de origen es exacta y una nueva distribución requiere una decisión humana en Creative Studio.','RECUPERACIÓN'];
  if(state==='AMBIGUOUS_EXISTING_OWNER')return['Varias publicaciones en curso','Hay más de un publication_id PUBLISHING. No se eligió uno automáticamente.','AMBIGUO'];
  if(state==='AMBIGUOUS_RECOVERY_OWNER')return['Varios creativos de origen','La lineage cancelada conduce a más de un media_id. No se eligió una pieza automáticamente.','AMBIGUO'];
  if(state==='RECOVERY_OWNER_GAP')return['Sin owner de recuperación exacto',guidance?.explanation||'No existe lineage suficiente para elegir un owner sin inferencia.','OWNER GAP'];
  if(state==='RECOVERY_INVARIANT_GAP')return['Estado cambió durante la resolución',guidance?.explanation||'El diagnóstico y los objetos exactos no coinciden.','FAIL CLOSED'];
  return['Diagnóstico sin handoff',guidance?.explanation||'Este estado no autoriza una ruta de recuperación.','DIAGNÓSTICO']
}
function coordinateRecoveryStyles(){if(document.querySelector('#post-w99-coordinate-recovery-style'))return;const style=document.createElement('style');style.id='post-w99-coordinate-recovery-style';style.textContent=`
.coordinate-recovery-context{margin:0 0 12px;padding:10px 12px;border:1px solid #d8d2c8;border-radius:12px;background:#fbfaf7;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px;align-items:center}.coordinate-recovery-copy{display:grid;gap:3px}.coordinate-recovery-copy small{font-size:7px;letter-spacing:.09em;color:#777067}.coordinate-recovery-copy strong{font-size:10px}.coordinate-recovery-copy span{font-size:8px;color:#706a61}.coordinate-recovery-chip{display:inline-flex;padding:4px 7px;border-radius:999px;background:#efede7;font-size:7px;white-space:nowrap}@media(max-width:700px){.coordinate-recovery-context{grid-template-columns:1fr}.coordinate-recovery-chip{width:max-content}}
`;document.head.append(style)}
function coordinateRecoveryDecorate(){
  coordinateRecoveryStyles();document.querySelector('#post-w99-coordinate-recovery-guidance')?.remove();const row=coordinateRecoveryCurrentRow(),guidance=row?.coordinate_recovery;if(coordinateRecoveryKind(row)!=='coordinate'||!guidance)return;
  const expected=coordinateRecoveryText((row.action||{}).view),current=coordinateRecoveryText(typeof marketingOpsState!=='undefined'?marketingOpsState.view:'');if(expected&&current&&expected!==current)return;
  const root=document.querySelector('#marketing-ops-view');if(!root)return;const [title,detail,chip]=coordinateRecoveryStateCopy(guidance),card=opsEl('section','coordinate-recovery-context');card.id='post-w99-coordinate-recovery-guidance';const copy=opsEl('div','coordinate-recovery-copy');copy.append(opsEl('small','','PLAN DE HOY · COORDINATE RECOVERY'),opsEl('strong','',title),opsEl('span','',detail));card.append(copy,opsEl('span','coordinate-recovery-chip',chip));const control=root.querySelector('#post-w99-contextual-control-handoff'),deep=root.querySelector('#post-w99-contextual-deep-link-context');if(control)control.insertAdjacentElement('afterend',card);else if(deep)deep.insertAdjacentElement('afterend',card);else root.prepend(card)
}
function coordinateRecoverySchedule(){queueMicrotask(coordinateRecoveryDecorate)}
function coordinateRecoveryWrap(name){const base=globalThis[name];if(typeof base!=='function'||base.__postW99CoordinateRecovery)return;const wrapped=function(){const value=base.apply(this,arguments);coordinateRecoverySchedule();return value};wrapped.__postW99CoordinateRecovery=true;globalThis[name]=wrapped}
['renderMarketingOps','contentRenderCurrent','campaignRenderCurrent','wave64Render'].forEach(coordinateRecoveryWrap);
window.addEventListener('marketing-ops-refreshed',coordinateRecoverySchedule);window.addEventListener('pageshow',coordinateRecoverySchedule);coordinateRecoveryStyles();coordinateRecoverySchedule();
