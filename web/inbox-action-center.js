(function installPostW99InboxActionCenter(){
  if(globalThis.POST_W99_INBOX_ACTION_CENTER)return;
  globalThis.POST_W99_INBOX_ACTION_CENTER=true;
  if(typeof inboxRefresh!=='function')return;

  inboxRefresh=async function postW99InboxRefresh(){
    const companyId=inboxCompanyId();
    if(!companyId){opsToast('Selecciona una empresa para abrir la bandeja');return}
    if(inboxState.loading)return;
    inboxState.loading=true;inboxState.data=null;inboxState.companyKey=inboxCompanyKey();inboxRenderCurrent();
    try{
      inboxState.data=await opsApi(`/api/companies/${encodeURIComponent(companyId)}/inbox/refresh-attention`,{method:'POST'});
      opsToast(inboxState.data.configured?'Bandeja Meta actualizada y enviada a Hoy':'Meta no está conectado')
    }catch(err){opsToast(err.message)}finally{inboxState.loading=false;inboxRenderCurrent()}
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
})();
