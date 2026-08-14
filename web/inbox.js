const inboxState={companyKey:undefined,data:null,loading:false,crmBusy:new Set()};

function inboxEnsureStyles(){
  if(document.querySelector('#inbox-wave39-style'))return;
  const style=document.createElement('style');style.id='inbox-wave39-style';style.textContent=`
  .inbox-grid{display:grid;grid-template-columns:repeat(3,minmax(140px,1fr));gap:10px}.inbox-columns{display:grid;grid-template-columns:minmax(330px,1fr) minmax(330px,1fr);gap:12px}.inbox-list{display:grid;gap:8px}.inbox-card{border:1px solid #dedbd2;border-radius:11px;background:#fff;padding:11px;display:grid;gap:8px}.inbox-card-head{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}.inbox-message{padding:8px;border-radius:9px;background:#f7f4ed;display:grid;gap:4px}.inbox-message small,.inbox-comment small{color:#77736b}.inbox-comment{border:1px solid #e3dfd7;border-radius:9px;padding:9px;display:grid;gap:5px}.inbox-person{font-weight:700;font-size:10px}.inbox-body{font-size:10px;line-height:1.4;white-space:pre-wrap;overflow-wrap:anywhere}.inbox-actions{display:flex;gap:7px;align-items:center;flex-wrap:wrap}.inbox-warning{border:1px solid #ddcfbd;background:#fff8ed;border-radius:9px;padding:8px;font-size:9px;line-height:1.4}.inbox-readonly{border:1px solid #ccd6c9;background:#f3f8f1;border-radius:10px;padding:9px;font-size:10px;line-height:1.45}.inbox-empty{padding:18px;border:1px dashed #d7d2c8;border-radius:10px;text-align:center;color:#77736b;font-size:10px}.inbox-local-action{font-size:9px}.inbox-local-action.primary{background:#171717;color:#fff}.inbox-local-action:disabled{opacity:.5;cursor:wait}
  @media(max-width:900px){.inbox-columns{grid-template-columns:1fr}}@media(max-width:650px){.inbox-grid{grid-template-columns:1fr}}
  `;document.head.append(style)
}

function inboxEnsureNav(){
  const nav=document.querySelector('.marketing-ops-nav');if(!nav||nav.querySelector('[data-ops-view="inbox"]'))return;
  const button=opsEl('button','','Bandeja');button.type='button';button.dataset.opsView='inbox';button.innerHTML='Bandeja <small>W40</small>';button.addEventListener('click',()=>opsShowView('inbox'));
  const analytics=nav.querySelector('[data-ops-view="analytics"]');if(analytics?.nextSibling)nav.insertBefore(button,analytics.nextSibling);else nav.append(button)
}

function inboxCompanyId(){return marketingOpsState.selectedCompanyId||null}
function inboxCompanyKey(){return inboxCompanyId()||'__none__'}
function inboxDate(value){return value?opsDate(value):'Sin fecha'}
function inboxText(value,limit=180){const text=String(value||'').trim();return text.length>limit?`${text.slice(0,limit-1)}…`:text||'(sin texto)'}
function inboxPerson(person){return person?.username?`@${person.username}`:(person?.id?`Meta ${String(person.id).slice(-6)}`:'Persona')}
function inboxHandle(person){return String(person?.username||'').trim().replace(/^@+/,'').toLocaleLowerCase()}
function inboxInteractionKey(kind,item){return `${kind}:${String(item?.id||'').trim()}`}
function inboxInteractionMarker(kind,item){return `[MKTGAPP_META_${kind.toUpperCase()}:${String(item?.id||'').trim()}]`}

function inboxOpenCrm(contact){
  if(!contact?.id)return;
  try{crmState.selectedContactId=contact.id}catch(_err){}
  opsShowView('crm');setTimeout(()=>{try{renderCRMCurrent()}catch(_err){}},0)
}

function inboxApplyCrmMatch(person,contact){
  const handle=inboxHandle(person);if(!handle||!contact||!inboxState.data)return;
  for(const conversation of inboxState.data.conversations||[]){for(const message of conversation.messages||[]){if(inboxHandle(message.from)===handle)message.crm_contact=contact}}
  for(const comment of inboxState.data.comments||[]){if(inboxHandle(comment.from)===handle)comment.crm_contact=contact}
  const ids=new Set();for(const conversation of inboxState.data.conversations||[]){for(const message of conversation.messages||[]){if(message.crm_contact?.id)ids.add(message.crm_contact.id)}}for(const comment of inboxState.data.comments||[]){if(comment.crm_contact?.id)ids.add(comment.crm_contact.id)}
  if(inboxState.data.summary)inboxState.data.summary.crm_matches=ids.size
}

async function inboxRefreshCrmLocal(){
  if(typeof crmRefresh==='function')await crmRefresh(true);
  if(typeof refreshMarketingOps==='function')await refreshMarketingOps(false)
}

async function inboxCreateContact(person,kind,item,button){
  const companyId=inboxCompanyId(),handle=inboxHandle(person);if(!companyId||!handle){opsToast('Esta interacción no expone un @usuario suficiente para crear el contacto sin riesgo de duplicado');return}
  const key=`contact:${handle}`;if(inboxState.crmBusy.has(key))return;inboxState.crmBusy.add(key);if(button)button.disabled=true;
  try{
    await inboxRefreshCrmLocal();
    const existing=(typeof crmState!=='undefined'?crmState.contacts:[]).find(contact=>String(contact.instagram||'').trim().replace(/^@+/,'').toLocaleLowerCase()===handle);
    if(existing){inboxApplyCrmMatch(person,existing);opsToast('Ese @usuario ya existía en CRM');inboxRenderCurrent();return}
    const marker=inboxInteractionMarker(kind,item),contact=await opsApi(`/api/companies/${encodeURIComponent(companyId)}/contacts`,{method:'POST',body:{name:`@${handle}`,instagram:`@${handle}`,source:'Bandeja Meta',tags:['redes','bandeja'],notes:`Creado manualmente desde una interacción de ${kind==='comment'?'comentario':'mensajería'} en la Bandeja. ${marker}`}});
    inboxApplyCrmMatch(person,contact);await inboxRefreshCrmLocal();opsToast('Contacto creado en CRM');inboxRenderCurrent()
  }catch(err){opsToast(err.message)}finally{inboxState.crmBusy.delete(key);if(button)button.disabled=false}
}

async function inboxCreateFollowup(contact,person,kind,item,text,button){
  const companyId=inboxCompanyId();if(!companyId||!contact?.id)return;const interactionId=String(item?.id||'').trim();if(!interactionId){opsToast('La interacción no tiene un identificador estable');return}
  const marker=inboxInteractionMarker(kind,item),key=`followup:${kind}:${interactionId}`;if(inboxState.crmBusy.has(key))return;inboxState.crmBusy.add(key);if(button)button.disabled=true;
  try{
    await inboxRefreshCrmLocal();
    const duplicate=(typeof crmState!=='undefined'?crmState.activities:[]).some(activity=>activity.contact_id===contact.id&&String(activity.summary||'').includes(marker));
    if(duplicate){opsToast('Ya existe un seguimiento para esta interacción');if(button){button.textContent='Seguimiento creado';button.disabled=true}return}
    const origin=kind==='comment'?'comentario de Instagram':'mensaje de redes',who=inboxPerson(person),excerpt=inboxText(text,900),summary=`Atender ${origin} de ${who}: ${excerpt} ${marker}`;
    await opsApi(`/api/companies/${encodeURIComponent(companyId)}/activities`,{method:'POST',body:{contact_id:contact.id,opportunity_id:null,kind:'TASK',summary,due_at:null}});
    await inboxRefreshCrmLocal();opsToast('Seguimiento creado en CRM');if(button){button.textContent='Seguimiento creado';button.disabled=true}
  }catch(err){opsToast(err.message);if(button)button.disabled=false}finally{inboxState.crmBusy.delete(key)}
}

function inboxCrmActions(person,crmContact,kind,item,text){
  const actions=opsEl('div','inbox-actions');
  if(crmContact){actions.append(opsEl('span','analytics-chip',`CRM · ${crmContact.name||'Contacto'}`));const open=opsEl('button','inbox-local-action','Abrir CRM');open.type='button';open.addEventListener('click',()=>inboxOpenCrm(crmContact));const follow=opsEl('button','inbox-local-action primary','Crear seguimiento');follow.type='button';follow.title='Guarda una tarea local en CRM; no responde en Meta';follow.addEventListener('click',()=>inboxCreateFollowup(crmContact,person,kind,item,text,follow));actions.append(open,follow);return actions}
  if(inboxHandle(person)){const create=opsEl('button','inbox-local-action','Crear contacto CRM');create.type='button';create.title='Crea un contacto local usando el @usuario; no escribe en Meta';create.addEventListener('click',()=>inboxCreateContact(person,kind,item,create));actions.append(create)}
  return actions
}

async function inboxRefresh(){
  const companyId=inboxCompanyId();
  if(!companyId){opsToast('Selecciona una empresa para abrir la bandeja');return}
  if(inboxState.loading)return;
  inboxState.loading=true;inboxState.data=null;inboxState.companyKey=inboxCompanyKey();inboxRenderCurrent();
  try{
    inboxState.data=await opsApi(`/api/inbox/meta?company_id=${encodeURIComponent(companyId)}&limit=10`);
    opsToast(inboxState.data.configured?'Bandeja Meta actualizada':'Meta no está conectado')
  }catch(err){opsToast(err.message)}finally{inboxState.loading=false;inboxRenderCurrent()}
}

function inboxMetrics(root,data){
  const grid=opsEl('div','inbox-grid'),summary=data.summary||{};
  grid.append(opsMetric('CONVERSACIONES',summary.conversations||0,'Messenger / Instagram accesibles'),opsMetric('COMENTARIOS',summary.comments||0,'Instagram reciente'),opsMetric('COINCIDENCIAS CRM',summary.crm_matches||0,'personas vinculadas por @usuario'));
  root.append(grid)
}

function inboxConversationCard(conversation){
  const card=opsEl('article','inbox-card'),head=opsEl('div','inbox-card-head'),left=opsEl('div','');left.append(opsEl('strong','',`Conversación ${String(conversation.id||'').slice(-8)}`),opsEl('small','',`Actualizada ${inboxDate(conversation.updated_time)}`));head.append(left,opsEl('span','status','META READ ONLY'));card.append(head);
  const messages=conversation.messages||[];
  if(!messages.length){card.append(opsEl('div','inbox-empty','Meta no devolvió mensajes recientes para esta conversación.'));return card}
  for(const message of messages.slice(0,5)){
    const row=opsEl('div','inbox-message'),top=opsEl('div','inbox-card-head'),identity=opsEl('span','inbox-person',inboxPerson(message.from));top.append(identity,opsEl('small','',inboxDate(message.created_time)));const body=message.unavailable?'Mensaje no disponible por permisos/ventana de API.':inboxText(message.message,300);row.append(top,opsEl('div','inbox-body',body));const actions=inboxCrmActions(message.from,message.crm_contact,'message',message,message.message);if(actions.childElementCount)row.append(actions);card.append(row)
  }
  return card
}

function inboxCommentsColumn(section,data){
  const list=opsEl('div','inbox-list');
  for(const comment of data.comments||[]){const card=opsEl('article','inbox-comment'),head=opsEl('div','inbox-card-head'),identity=opsEl('span','inbox-person',inboxPerson(comment.from));head.append(identity,opsEl('small','',inboxDate(comment.timestamp)));card.append(head,opsEl('div','inbox-body',inboxText(comment.text,500)));const actions=inboxCrmActions(comment.from,comment.crm_contact,'comment',comment,comment.text);if(actions.childElementCount)card.append(actions);list.append(card)}
  if(!(data.comments||[]).length)list.append(opsEl('div','inbox-empty','No se encontraron comentarios recientes en publicaciones Instagram conocidas por la app.'));section.append(list)
}

function inboxRenderCurrent(){
  if(marketingOpsState.view!=='inbox')return;
  inboxEnsureStyles();inboxEnsureNav();const root=document.querySelector('#marketing-ops-view');if(!root)return;root.replaceChildren();document.querySelector('#marketing-ops-eyebrow').textContent='BANDEJA';document.querySelector('#marketing-ops-title').textContent='Atención de redes';document.querySelector('#marketing-ops-subtitle').textContent='Lee interacciones de Meta y conviértelas manualmente en trabajo CRM, sin responder desde esta vista.';document.querySelectorAll('[data-ops-view]').forEach(button=>button.classList.toggle('active',button.dataset.opsView==='inbox'));
  const intro=opsEl('section','marketing-ops-section'),head=opsEl('div','marketing-ops-section-head'),copy=opsEl('div','');copy.append(opsEl('p','eyebrow','META · SINCRONIZACIÓN MANUAL'),opsEl('h3','','Bandeja + CRM'),opsEl('p','muted','La app no consulta Meta en segundo plano. Pulsa Actualizar cuando quieras revisar conversaciones y comentarios.'));const actions=opsEl('div','inbox-actions'),refresh=opsEl('button','primary',inboxState.loading?'Actualizando…':'Actualizar desde Meta');refresh.type='button';refresh.disabled=inboxState.loading||!inboxCompanyId();refresh.addEventListener('click',inboxRefresh);actions.append(refresh);head.append(copy,actions);intro.append(head,opsEl('div','inbox-readonly','Meta sigue siendo sólo lectura: no respondemos mensajes, no contestamos ni ocultamos comentarios. Wave 40 sólo permite acciones CRM locales y explícitas: crear un contacto o una tarea de seguimiento.'));root.append(intro);
  if(!inboxCompanyId()){root.append(opsEl('div','inbox-empty','Selecciona una empresa arriba. La bandeja nunca mezcla conversaciones entre empresas.'));return}
  if(inboxState.companyKey!==inboxCompanyKey()){inboxState.data=null;inboxState.companyKey=inboxCompanyKey()}
  if(inboxState.loading){root.append(opsEl('div','inbox-empty','Consultando Meta…'));return}
  const data=inboxState.data;if(!data){root.append(opsEl('div','inbox-empty','Pulsa “Actualizar desde Meta” para consultar la bandeja.'));return}
  if(!data.configured){root.append(opsEl('div','inbox-warning','Meta no está conectado para esta instalación. Conecta Meta desde Empresas antes de consultar la bandeja.'));return}
  inboxMetrics(root,data);
  for(const warning of data.warnings||[])root.append(opsEl('div','inbox-warning',warning));
  const columns=opsEl('div','inbox-columns'),conversations=opsEl('section','marketing-ops-section'),conversationHead=opsEl('div','marketing-ops-section-head'),conversationCopy=opsEl('div','');conversationCopy.append(opsEl('p','eyebrow','MENSAJERÍA'),opsEl('h3','','Conversaciones recientes'));conversationHead.append(conversationCopy);conversations.append(conversationHead);const conversationList=opsEl('div','inbox-list');for(const conversation of data.conversations||[])conversationList.append(inboxConversationCard(conversation));if(!(data.conversations||[]).length)conversationList.append(opsEl('div','inbox-empty','No hay conversaciones accesibles con los permisos actuales.'));conversations.append(conversationList);
  const comments=opsEl('section','marketing-ops-section'),commentsHead=opsEl('div','marketing-ops-section-head'),commentsCopy=opsEl('div','');commentsCopy.append(opsEl('p','eyebrow','INSTAGRAM'),opsEl('h3','','Comentarios recientes'));commentsHead.append(commentsCopy);comments.append(commentsHead);inboxCommentsColumn(comments,data);columns.append(conversations,comments);root.append(columns)
}

const inboxBaseRender=globalThis.renderMarketingOps;
globalThis.renderMarketingOps=function(){inboxEnsureNav();if(marketingOpsState.view==='inbox'){inboxRenderCurrent();return}inboxBaseRender()};

const inboxBaseHome=globalThis.renderOpsHome;
if(typeof inboxBaseHome==='function')globalThis.renderOpsHome=function(root){inboxBaseHome(root);const section=opsEl('section','marketing-ops-section'),head=opsEl('div','marketing-ops-section-head'),copy=opsEl('div','');copy.append(opsEl('p','eyebrow','BANDEJA'),opsEl('h3','','Atención de redes'),opsEl('p','muted','Revisa interacciones y conviértelas en contactos o seguimientos CRM sin salir de MERCADEO APP.'));const open=opsEl('button','','Abrir bandeja');open.type='button';open.addEventListener('click',()=>opsShowView('inbox'));head.append(copy,open);section.append(head);root.append(section)};

inboxEnsureStyles();inboxEnsureNav();