const POST_W99_CAMPAIGN_EXECUTION_OWNER_CARDINALITY_SCHEMA='binario.marketing.campaign-execution-owner-cardinality-hardening.v1';

function campaignExecutionCardinalityText(value){return value===null||value===undefined?'':String(value).trim()}
function campaignExecutionCardinalityKind(item){return campaignExecutionCardinalityText(item?.kind||item?.post_w99_action_kind).toLowerCase()}
function campaignExecutionCardinalityMeta(key,label,kind,targetKind,explanation){return{schema:POST_W99_CAMPAIGN_EXECUTION_OWNER_CARDINALITY_SCHEMA,control_key:key,control_label:label,control_kind:'CONTROL_GROUP',action_kind:kind,target_kind:targetKind,explanation}}

const campaignExecutionCardinalityBaseResolve=globalThis.controlHandoffResolveControl;
if(typeof campaignExecutionCardinalityBaseResolve==='function')globalThis.controlHandoffResolveControl=function(row,targetInfo){
  const kind=campaignExecutionCardinalityKind(row),deep=targetInfo?.context||{},targetKind=campaignExecutionCardinalityText(deep.target_kind).toUpperCase();
  if(kind==='finish_creative'&&targetKind==='MEDIA'){
    const targetId=campaignExecutionCardinalityText(deep.target_id),selected=typeof wave49CreativeState!=='undefined'&&String(wave49CreativeState.selectedId||'')===targetId,item=selected&&typeof wave49SelectedItem==='function'?wave49SelectedItem():null;
    if(!item||String(item?.media?.id||'')!==targetId)return controlHandoffOwnerGap(kind,'MEDIA','Creative Studio no confirma el media_id exacto seleccionado. No se elige otra pieza.');
    if(typeof controlHandoffSingleGroup!=='function')return controlHandoffOwnerGap(kind,'MEDIA','El invariant de submit canónico no está disponible; se falla cerrado.');
    const forms=[...document.querySelectorAll('.w49-editor form.w49-form')];
    return controlHandoffSingleGroup(forms,text=>text==='Guardar ficha creativa',campaignExecutionCardinalityMeta('W49_FINISH_CREATIVE_CANONICAL_SUBMIT','Editar estado + Guardar ficha creativa',kind,'MEDIA','El formulario pertenece al media_id exacto y solo se considera listo con un único Guardar ficha creativa habilitado. El operador conserva la decisión de Estado y el submit final.'))
  }
  if(kind==='define_channels'&&targetKind==='CAMPAIGN'){
    const targetId=campaignExecutionCardinalityText(deep.target_id),selected=typeof campaignState!=='undefined'&&String(campaignState.selectedId||'')===targetId;
    if(!selected)return controlHandoffOwnerGap(kind,'CAMPAIGN','La campaña exacta no está seleccionada en W35; no se usa otro formulario.');
    if(typeof controlHandoffSingleGroup!=='function')return controlHandoffOwnerGap(kind,'CAMPAIGN','El invariant de submit canónico no está disponible; se falla cerrado.');
    const forms=[...document.querySelectorAll('.campaign-form')];
    return controlHandoffSingleGroup(forms,text=>text==='Guardar cambios',campaignExecutionCardinalityMeta('W35_DEFINE_CHANNELS_CANONICAL_SUBMIT','Definir canales + Guardar cambios',kind,'CAMPAIGN','El formulario de campaña exacta solo se considera accionable con un único Guardar cambios habilitado. El usuario conserva canales, estado y submit.'))
  }
  return campaignExecutionCardinalityBaseResolve.apply(this,arguments)
};
