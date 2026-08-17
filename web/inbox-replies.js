const inboxReplyState={busy:new Set()};

function inboxReplyEnsureStyles(){
  if(document.querySelector('#inbox-replies-wave41-style'))return;
  const style=document.createElement('style');style.id='inbox-replies-wave41-style';style.textContent=`
  .inbox-reply-wrap{flex:1 0 100%;display:grid;gap:7px;margin-top:3px;padding:9px;border:1px solid #d8d3ca;border-radius:9px;background:#fcfbf8}.inbox-reply-wrap textarea{width:100%;min-height:72px;resize:vertical;border:1px solid #cfc9bf;border-radius:8px;padding:8px;font:inherit;line-height:1.4;background:#fff}.inbox-reply-controls{display:flex;gap:7px;justify-content:flex-end;flex-wrap:wrap}.inbox-reply-help{font-size:9px;color:#77736b;line-height:1.35}.inbox-reply-open{background:#171717;color:#fff}.inbox-reply-send{background:#171717;color:#fff}.inbox-reply-wrap button:disabled{opacity:.55;cursor:wait}
  `;document.head.append(style)
}

function inboxReplyProviderKind(kind){return kind==='message'?'facebook_message':kind==='comment'?'instagram_comment':null}
function inboxReplyLabel(kind){return kind==='message'?'Responder en Messenger':'Responder comentario'}
function inboxReplyHelp(kind){return kind==='message'?'Se enviará como respuesta manual a este mensaje. El servidor valida Página, remitente y ventana conservadora de 24 h.':'Se publicará una respuesta visible a este comentario. El servidor verifica que pertenezca a contenido Instagram de esta empresa.'}

async function inboxReplySend(kind,item,textarea,send,wrap,openButton){
  const companyId=inboxCompanyId(),providerKind=inboxReplyProviderKind(kind),interactionId=String(item?.id||'').trim(),text=String(textarea.value||'').trim();
  if(!companyId||!providerKind||!interactionId)return;
  if(!text){opsToast('Escribe la respuesta antes de enviarla');textarea.focus();return}
  const key=`${companyId}:${providerKind}:${interactionId}`;if(inboxReplyState.busy.has(key))return;
  inboxReplyState.busy.add(key);send.disabled=true;textarea.disabled=true;send.textContent='Enviando…';
  try{
    const result=await opsApi(`/api/companies/${encodeURIComponent(companyId)}/inbox/reply`,{method:'POST',body:{kind:providerKind,interaction_id:interactionId,text}});
    wrap.replaceChildren(opsEl('div','inbox-reply-help',result.reused?'Esta respuesta ya había sido confirmada por Meta; no se envió de nuevo.':'Respuesta confirmada por Meta. Pulsa “Actualizar desde Meta” cuando quieras refrescar la bandeja.'));
    openButton.textContent='Respondido';openButton.disabled=true;opsToast(result.reused?'Respuesta ya confirmada; no se duplicó':'Respuesta enviada desde MERCADEO APP')
  }catch(err){
    send.disabled=false;textarea.disabled=false;send.textContent='Enviar respuesta';opsToast(err.message)
  }finally{inboxReplyState.busy.delete(key)}
}

function inboxReplyComposer(kind,item,openButton){
  const wrap=opsEl('div','inbox-reply-wrap'),help=opsEl('div','inbox-reply-help',inboxReplyHelp(kind)),textarea=document.createElement('textarea');textarea.maxLength=2000;textarea.placeholder=kind==='message'?'Escribe tu respuesta…':'Escribe la respuesta pública…';
  const controls=opsEl('div','inbox-reply-controls'),cancel=opsEl('button','','Cancelar'),send=opsEl('button','inbox-reply-send','Enviar respuesta');cancel.type='button';send.type='button';cancel.addEventListener('click',()=>{wrap.remove();openButton.disabled=false});send.addEventListener('click',()=>inboxReplySend(kind,item,textarea,send,wrap,openButton));controls.append(cancel,send);wrap.append(help,textarea,controls);setTimeout(()=>textarea.focus(),0);return wrap
}

const inboxReplyBaseCrmActions=inboxCrmActions;
inboxCrmActions=function(person,crmContact,kind,item,text){
  const actions=inboxReplyBaseCrmActions(person,crmContact,kind,item,text),providerKind=inboxReplyProviderKind(kind);
  if(!providerKind||!item?.reply_eligible||!item?.id)return actions;
  const open=opsEl('button','inbox-local-action inbox-reply-open',inboxReplyLabel(kind));open.type='button';open.addEventListener('click',()=>{if(actions.querySelector('.inbox-reply-wrap'))return;open.disabled=true;actions.append(inboxReplyComposer(kind,item,open))});actions.append(open);return actions
};

const inboxReplyBaseRender=inboxRenderCurrent;
inboxRenderCurrent=function(){
  inboxReplyBaseRender();if(marketingOpsState.view!=='inbox')return;inboxReplyEnsureStyles();
  const subtitle=document.querySelector('#marketing-ops-subtitle');if(subtitle)subtitle.textContent='Lee interacciones de Meta, conviértelas en trabajo CRM y responde manualmente cuando la interacción sea elegible.';
  const notice=document.querySelector('.inbox-readonly');if(notice)notice.textContent='Meta se consulta sólo cuando pulsas Actualizar. Las respuestas también son explícitas: abre Responder y luego pulsa Enviar respuesta. No hay auto-respuestas, polling, ocultar/eliminar comentarios ni moderación automática.';
  document.querySelectorAll('.inbox-card .status').forEach(tag=>{if(tag.textContent==='META READ ONLY')tag.textContent='META · RESPUESTA MANUAL'})
};

inboxReplyEnsureStyles();if(marketingOpsState.view==='inbox')inboxRenderCurrent();
