(function installPostW99InboxActionCenter(){
  if(globalThis.POST_W99_INBOX_ACTION_CENTER)return;
  globalThis.POST_W99_INBOX_ACTION_CENTER=true;
  if(typeof inboxRefresh!=='function')return;

  let exactTarget=null;

  function captureTarget(companyId,action){
    if(!action||action.view!=='inbox'||!action.entity_id)return;
    const interactionId=String(action.entity_id||'').trim();
    if(!interactionId)return;
    exactTarget={
      companyId:String(companyId||'').trim()||null,
      interactionId,
      kind:String(action.tab||'').trim()||null,
    };
  }

  function applyExactTarget(data,companyId){
    const target=exactTarget;
    if(!target||!data||target.companyId&&target.companyId!==String(companyId||'').trim())return false;
    let matched=false;
    if(!target.kind||target.kind==='facebook_message'){
      const conversations=Array.isArray(data.conversations)?data.conversations:[];
      for(let ci=0;ci<conversations.length&&!matched;ci+=1){
        const messages=Array.isArray(conversations[ci]?.messages)?conversations[ci].messages:[];
        const mi=messages.findIndex(row=>String(row?.id||'').trim()===target.interactionId);
        if(mi<0)continue;
        if(mi>0)messages.unshift(messages.splice(mi,1)[0]);
        if(ci>0)conversations.unshift(conversations.splice(ci,1)[0]);
        matched=true;
      }
    }
    if(!matched&&(!target.kind||target.kind==='instagram_comment')){
      const comments=Array.isArray(data.comments)?data.comments:[];
      const index=comments.findIndex(row=>String(row?.id||'').trim()===target.interactionId);
      if(index>=0){
        if(index>0)comments.unshift(comments.splice(index,1)[0]);
        matched=true;
      }
    }
    exactTarget=null;
    return matched;
  }

  function invalidateLocalAttentionViews(companyId){
    if(typeof globalThis.postW99ActionState==='object'&&globalThis.postW99ActionState){
      if(globalThis.postW99ActionState.companyId===companyId){
        globalThis.postW99ActionState.payload=null;
      }
    }
    if(typeof globalThis.postW99PortfolioState==='object'&&globalThis.postW99PortfolioState){
      globalThis.postW99PortfolioState.payload=null;
    }
    if(typeof globalThis.postW99TodayPortfolioState==='object'&&globalThis.postW99TodayPortfolioState){
      globalThis.postW99TodayPortfolioState.payload=null;
    }
  }

  if(typeof globalThis.actionCenterOpen==='function'){
    const baseActionCenterOpen=globalThis.actionCenterOpen;
    globalThis.actionCenterOpen=function postW99InboxActionCenterOpen(item){
      captureTarget(typeof inboxCompanyId==='function'?inboxCompanyId():null,item?.action||{});
      return baseActionCenterOpen(item);
    };
  }

  if(typeof globalThis.portfolioNavigate==='function'){
    const basePortfolioNavigate=globalThis.portfolioNavigate;
    globalThis.portfolioNavigate=async function postW99InboxPortfolioNavigate(companyId,action){
      captureTarget(companyId,action||{});
      return basePortfolioNavigate(companyId,action);
    };
  }

  inboxRefresh=async function postW99InboxRefresh(){
    const companyId=inboxCompanyId();
    if(!companyId){opsToast('Selecciona una empresa para abrir la bandeja');return}
    if(inboxState.loading)return;
    inboxState.loading=true;inboxState.data=null;inboxState.companyKey=inboxCompanyKey();inboxRenderCurrent();
    try{
      inboxState.data=await opsApi(`/api/companies/${encodeURIComponent(companyId)}/inbox/refresh-attention`,{method:'POST'});
      const exactLocated=applyExactTarget(inboxState.data,companyId);
      invalidateLocalAttentionViews(companyId);
      if(exactLocated)opsToast('Interacción objetivo localizada en la bandeja');
      else opsToast(inboxState.data.configured?'Bandeja Meta actualizada y enviada a Hoy':'Meta no está conectado');
    }catch(err){exactTarget=null;opsToast(err.message)}finally{inboxState.loading=false;inboxRenderCurrent()}
  };

  const baseRender=inboxRenderCurrent;
  inboxRenderCurrent=function postW99InboxRender(){
    baseRender();
    if(marketingOpsState.view!=='inbox')return;
    const notice=document.querySelector('.inbox-readonly');
    if(notice&&inboxState.data?.attention_snapshot){
      const captured=inboxState.data.attention_snapshot.captured_at;
      notice.textContent=`Esta actualización explícita quedó guardada localmente como evidencia mínima para Hoy y Action Center (${captured?opsDate(captured):'ahora'}). No se guardan enlaces Meta, IDs personales del proveedor ni cuerpos completos.`;
    }
  };

  if(marketingOpsState.view==='inbox')inboxRenderCurrent();
})();
