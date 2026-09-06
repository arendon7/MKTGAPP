(function installPostW99InboxCRMIdentity(){
  if(globalThis.POST_W99_INBOX_CRM_IDENTITY)return;
  globalThis.POST_W99_INBOX_CRM_IDENTITY=true;
  if(typeof inboxCrmActions!=='function')return;

  const busy=new Set();

  function styles(){
    if(document.querySelector('#post-w99-inbox-crm-identity-style'))return;
    const s=document.createElement('style');s.id='post-w99-inbox-crm-identity-style';s.textContent=`
      .inbox-crm-linker{flex:1 0 100%;display:grid;gap:7px;margin-top:4px;padding:9px;border:1px solid #d8d3ca;border-radius:9px;background:#fbfaf7}.inbox-crm-linker select{width:100%;padding:7px;border:1px solid #cfc9bf;border-radius:8px;background:#fff;font:inherit}.inbox-crm-linker p{margin:0;font-size:8px;color:#6f685f;line-height:1.4}.inbox-crm-link-actions{display:flex;gap:6px;justify-content:flex-end;flex-wrap:wrap}.inbox-crm-link-warning{flex:1 0 100%;font-size:8px;color:#6f685f}.inbox-crm-link-primary{background:#171717;color:#fff}
    `;document.head.append(s)
  }

  function providerKind(kind){return kind==='message'?'facebook_message':kind==='comment'?'instagram_comment':null}
  function identity(item){return item?.crm_identity&&typeof item.crm_identity==='object'?item.crm_identity:null}
  function currentContactId(meta){return String(meta?.current_contact?.id||meta?.current_contact_id||'').trim()||null}
  function personId(item){return String(item?.from?.id||'').trim()}

  async function refreshLocalViews(){
    const jobs=[];
    if(typeof globalThis.actionCenterLoad==='function')jobs.push(globalThis.actionCenterLoad(true));
    if(typeof globalThis.todayPortfolioLoad==='function')jobs.push(globalThis.todayPortfolioLoad(true));
    if(typeof globalThis.portfolioLoad==='function')jobs.push(globalThis.portfolioLoad());
    if(jobs.length)await Promise.allSettled(jobs)
  }

  function applyLinkedIdentity(kind,item,result){
    const sourceId=personId(item),mapped=providerKind(kind);if(!sourceId||!mapped)return;
    function apply(row,rowKind){
      if(providerKind(rowKind)!==mapped||personId(row)!==sourceId)return;
      const previous=identity(row)||{};
      row.crm_contact=result.contact;
      row.crm_identity={...previous,state:'LINKED',can_link:true,current_contact:result.contact,current_contact_id:null};
    }
    for(const conversation of inboxState.data?.conversations||[])for(const row of conversation?.messages||[])apply(row,'message');
    for(const row of inboxState.data?.comments||[])apply(row,'comment');
  }

  async function saveLink(kind,item,meta,select,wrap){
    const companyId=inboxCompanyId(),mappedKind=providerKind(kind),interactionId=String(item?.id||'').trim(),actorId=personId(item),contactId=String(select.value||'').trim();
    if(!companyId||!mappedKind||!interactionId||!actorId||!contactId)return;
    const currentId=currentContactId(meta),replacing=Boolean(currentId&&currentId!==contactId);
    const chosen=Array.from(select.options).find(option=>option.value===contactId)?.textContent||'este contacto';
    const prompt=replacing
      ?`Vas a cambiar el vínculo social actual y asociar esta persona con ${chosen}. Esta acción sólo modifica la relación local en CRM; no escribe en Meta. ¿Confirmar?`
      :`Vas a asociar explícitamente esta identidad social con ${chosen}. Se guardará sólo una huella HMAC local, nunca el ID personal de Meta en CRM. ¿Confirmar?`;
    if(!window.confirm(prompt))return;
    const key=`${companyId}:${mappedKind}:${interactionId}`;if(busy.has(key))return;busy.add(key);wrap.querySelectorAll('button,select').forEach(node=>node.disabled=true);
    try{
      const result=await opsApi(`/api/companies/${encodeURIComponent(companyId)}/inbox/crm-identity-link`,{method:'POST',body:{
        kind:mappedKind,
        interaction_id:interactionId,
        provider_person_id:actorId,
        intent_token:String(meta.intent_token||''),
        observed_at:String(meta.observed_at||''),
        contact_id:contactId,
        expected_contact_id:currentId,
        replace_confirmed:replacing,
      }});
      applyLinkedIdentity(kind,item,result);
      await refreshLocalViews();
      if(typeof inboxRenderCurrent==='function')inboxRenderCurrent();
      opsToast(result.reused?'El vínculo CRM ya estaba confirmado':'Identidad social vinculada al CRM');
    }catch(err){opsToast(err.message);wrap.querySelectorAll('button,select').forEach(node=>node.disabled=false)}
    finally{busy.delete(key)}
  }

  async function openLinker(kind,item,meta,actions,button){
    if(actions.querySelector('.inbox-crm-linker'))return;
    button.disabled=true;
    try{
      if(typeof crmRefresh!=='function'||typeof crmState==='undefined'){opsToast('CRM no está disponible');return}
      await crmRefresh(true);
      const contacts=Array.isArray(crmState.contacts)?crmState.contacts:[];
      if(!contacts.length){opsToast('Crea primero el contacto en CRM y vuelve a Inbox para vincularlo');return}
      const wrap=opsEl('div','inbox-crm-linker'),copy=opsEl('p','','Selecciona el contacto correcto. El vínculo es local y explícito; no modifica Meta ni copia el ID social al CRM.'),select=document.createElement('select');
      const blank=opsEl('option','','Selecciona un contacto…');blank.value='';select.append(blank);
      for(const contact of contacts){const option=opsEl('option','',[contact.name,contact.organization].filter(Boolean).join(' · '));option.value=contact.id;if(contact.id===currentContactId(meta))option.selected=true;select.append(option)}
      if(meta.state==='LINKED_USERNAME_MISMATCH')wrap.append(opsEl('div','inbox-crm-link-warning',`Aviso: el vínculo explícito apunta a ${meta.current_contact?.name||'otro contacto'}, mientras el @usuario coincide con ${meta.username_contact?.name||'un contacto distinto'}. El vínculo explícito tiene prioridad hasta que lo cambies.`));
      if(meta.state==='BROKEN')wrap.append(opsEl('div','inbox-crm-link-warning','El contacto previamente vinculado ya no está disponible. Selecciona un contacto válido para reparar la relación.'));
      const controls=opsEl('div','inbox-crm-link-actions'),cancel=opsEl('button','','Cancelar'),save=opsEl('button','inbox-crm-link-primary','Guardar vínculo');cancel.type='button';save.type='button';cancel.addEventListener('click',()=>{wrap.remove();button.disabled=false});save.addEventListener('click',()=>{if(!select.value){opsToast('Selecciona un contacto CRM');return}saveLink(kind,item,meta,select,wrap)});controls.append(cancel,save);wrap.append(copy,select,controls);actions.append(wrap)
    }catch(err){opsToast(err.message);button.disabled=false}
  }

  const baseActions=inboxCrmActions;
  inboxCrmActions=function postW99InboxCRMIdentityActions(person,crmContact,kind,item,text){
    const actions=baseActions(person,crmContact,kind,item,text),meta=identity(item);if(!meta)return actions;styles();
    if(meta.state==='INTEGRITY_BLOCKED')actions.append(opsEl('span','inbox-crm-link-warning','Vínculo CRM bloqueado: revisa la integridad de la clave local.'));
    if(!meta.can_link||!meta.intent_token||!meta.observed_at)return actions;
    const labels={UNLINKED:'Vincular a CRM',LINKED:'Cambiar vínculo CRM',LINKED_USERNAME_MISMATCH:'Revisar vínculo CRM',BROKEN:'Reparar vínculo CRM'};
    const label=labels[meta.state];if(!label)return actions;
    const open=opsEl('button','inbox-local-action',label);open.type='button';open.title='Asocia esta identidad social con un contacto existente sin escribir en Meta';open.addEventListener('click',()=>openLinker(kind,item,meta,actions,open));actions.append(open);return actions
  };

  const baseRender=inboxRenderCurrent;
  inboxRenderCurrent=function postW99InboxCRMIdentityRender(){
    baseRender();if(marketingOpsState.view!=='inbox')return;styles();
    const summary=inboxState.data?.summary||{},notice=document.querySelector('.inbox-readonly');
    if(notice&&Number(summary.crm_identity_links||0)>0)notice.textContent=`Inbox usa ${summary.crm_identity_links} vínculo(s) social→CRM confirmados localmente. Se persisten huellas HMAC, no IDs personales de Meta; cada cambio requiere una acción explícita.`;
  };

  styles();
})();
