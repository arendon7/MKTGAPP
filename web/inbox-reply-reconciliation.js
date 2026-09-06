(function installPostW99InboxReplyReconciliation(){
  if(globalThis.POST_W99_INBOX_REPLY_RECONCILIATION)return;
  globalThis.POST_W99_INBOX_REPLY_RECONCILIATION=true;
  if(typeof inboxCrmActions!=='function')return;

  const busy=new Set();

  function styles(){
    if(document.querySelector('#post-w99-inbox-reply-reconciliation-style'))return;
    const s=document.createElement('style');s.id='post-w99-inbox-reply-reconciliation-style';s.textContent=`
    .inbox-reconcile{flex:1 0 100%;display:grid;gap:7px;margin-top:4px;padding:9px;border:1px solid #b9b0a4;border-radius:9px;background:#f7f3ec}.inbox-reconcile strong{font-size:9px}.inbox-reconcile p{margin:0;font-size:8px;color:#6f685f;line-height:1.4}.inbox-reconcile-actions{display:flex;gap:6px;flex-wrap:wrap}.inbox-reconcile-actions button{font-size:8px}.inbox-reconcile-sent{background:#171717;color:#fff}.inbox-reconcile-conflict{border-style:dashed;background:#fff8ef}
    `;document.head.append(s)
  }

  function providerKind(kind){return kind==='message'?'facebook_message':kind==='comment'?'instagram_comment':null}
  function resolution(item){const value=item?.reply_reconciliation;return value&&value.required===true&&Array.isArray(value.candidates)?value:null}

  async function refreshLocalProjections(){
    try{if(typeof actionCenterLoad==='function')await actionCenterLoad(true)}catch(_err){}
    try{if(typeof todayPortfolioLoad==='function')await todayPortfolioLoad(true)}catch(_err){}
    try{if(typeof portfolioLoad==='function'&&globalThis.postW99PortfolioState?.open)await portfolioLoad()}catch(_err){}
  }

  async function resolve(kind,item,candidate,outcome,wrap){
    const companyId=inboxCompanyId(),providerKind=providerKind(kind),interactionId=String(item?.id||'').trim();
    if(!companyId||!providerKind||!interactionId||!candidate)return;
    const sent=outcome==='SENT';
    const prompt=sent
      ?'Confirma únicamente si ya verificaste directamente en Meta que esta respuesta SÍ fue enviada. MERCADEO APP no consultará Meta ni enviará nada al confirmar.'
      :'Confirma únicamente si ya verificaste directamente en Meta que esta respuesta NO fue enviada. Esto sólo habilitará un nuevo intento manual; no enviará nada ahora.';
    if(!window.confirm(prompt))return;
    const key=`${companyId}:${providerKind}:${interactionId}`;if(busy.has(key))return;busy.add(key);
    wrap.querySelectorAll('button').forEach(button=>button.disabled=true);
    try{
      const result=await opsApi(`/api/companies/${encodeURIComponent(companyId)}/inbox/reply-reconcile`,{method:'POST',body:{
        kind:providerKind,
        interaction_id:interactionId,
        expected_stage:String(candidate.stage||''),
        expected_updated_at:String(candidate.updated_at||''),
        outcome,
        provider_checked:true,
      }});
      item.reply_reconciliation=null;
      if(sent){item.reply_eligible=false;item.reply_reason='Respuesta confirmada manualmente después de verificar Meta.'}
      await refreshLocalProjections();
      if(typeof inboxRenderCurrent==='function')inboxRenderCurrent();
      opsToast(sent?'Respuesta marcada como enviada después de verificación manual':'Verificación registrada. Un nuevo envío requerirá otro clic explícito.');
      return result;
    }catch(err){opsToast(err.message);wrap.querySelectorAll('button').forEach(button=>button.disabled=false)}
    finally{busy.delete(key)}
  }

  function reconcileBox(kind,item,openReply){
    const state=resolution(item);if(!state)return null;
    const wrap=opsEl('div',`inbox-reconcile ${state.candidates.length===1?'':'inbox-reconcile-conflict'}`);
    if(openReply)openReply.disabled=true;
    if(state.candidates.length!==1){
      wrap.append(opsEl('strong','','Reconciliación bloqueada'),opsEl('p','','Hay más de un intento histórico sin resolución para esta interacción. La app no elegirá uno ni permitirá reenviar. Revisa el historial antes de intervenir manualmente.'));
      return wrap;
    }
    const candidate=state.candidates[0];
    wrap.append(
      opsEl('strong','',candidate.stage==='AMBIGUOUS'?'Respuesta con resultado ambiguo':'Respuesta interrumpida sin confirmación'),
      opsEl('p','','Verifica primero la conversación o comentario directamente en Meta. Después registra aquí lo que realmente ocurrió. Ninguna de estas opciones hace una llamada a Meta.')
    );
    const actions=opsEl('div','inbox-reconcile-actions'),yes=opsEl('button','inbox-reconcile-sent','Sí, se envió'),no=opsEl('button','','No se envió');yes.type='button';no.type='button';
    yes.addEventListener('click',()=>resolve(kind,item,candidate,'SENT',wrap));
    no.addEventListener('click',()=>resolve(kind,item,candidate,'NOT_SENT',wrap));
    actions.append(yes,no);wrap.append(actions);return wrap
  }

  const baseActions=inboxCrmActions;
  inboxCrmActions=function postW99InboxReconciliationActions(person,crmContact,kind,item,text){
    const actions=baseActions(person,crmContact,kind,item,text),state=resolution(item);
    if(!state)return actions;
    styles();
    const openReply=actions.querySelector('.inbox-reply-open');
    const box=reconcileBox(kind,item,openReply);if(box)actions.append(box);
    return actions
  };

  const baseRender=inboxRenderCurrent;
  inboxRenderCurrent=function postW99InboxReconciliationRender(){
    baseRender();
    if(marketingOpsState.view!=='inbox')return;
    styles();
    const notice=document.querySelector('.inbox-readonly');
    if(notice&&document.querySelector('.inbox-reconcile'))notice.textContent='Hay una respuesta que requiere reconciliación humana. Verifica primero Meta y registra el resultado. La reconciliación no consulta Meta y nunca reenvía automáticamente.';
  };

  styles();
})();
