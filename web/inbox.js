const inboxState={companyKey:undefined,data:null,loading:false};

function inboxEnsureStyles(){
  if(document.querySelector('#inbox-wave39-style'))return;
  const style=document.createElement('style');style.id='inbox-wave39-style';style.textContent=`
  .inbox-grid{display:grid;grid-template-columns:repeat(3,minmax(140px,1fr));gap:10px}.inbox-columns{display:grid;grid-template-columns:minmax(330px,1fr) minmax(330px,1fr);gap:12px}.inbox-list{display:grid;gap:8px}.inbox-card{border:1px solid #dedbd2;border-radius:11px;background:#fff;padding:11px;display:grid;gap:8px}.inbox-card-head{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}.inbox-message{padding:8px;border-radius:9px;background:#f7f4ed;display:grid;gap:4px}.inbox-message small,.inbox-comment small{color:#77736b}.inbox-comment{border:1px solid #e3dfd7;border-radius:9px;padding:9px;display:grid;gap:5px}.inbox-person{font-weight:700;font-size:10px}.inbox-body{font-size:10px;line-height:1.4;white-space:pre-wrap;overflow-wrap:anywhere}.inbox-actions{display:flex;gap:7px;align-items:center;flex-wrap:wrap}.inbox-warning{border:1px solid #ddcfbd;background:#fff8ed;border-radius:9px;padding:8px;font-size:9px;line-height:1.4}.inbox-readonly{border:1px solid #ccd6c9;background:#f3f8f1;border-radius:10px;padding:9px;font-size:10px;line-height:1.45}.inbox-empty{padding:18px;border:1px dashed #d7d2c8;border-radius:10px;text-align:center;color:#77736b;font-size:10px}
  @media(max-width:900px){.inbox-columns{grid-template-columns:1fr}}@media(max-width:650px){.inbox-grid{grid-template-columns:1fr}}
  `;document.head.append(style)
}

function inboxEnsureNav(){
  const nav=document.querySelector('.marketing-ops-nav');if(!nav||nav.querySelector('[data-ops-view="inbox"]'))return;
  const button=opsEl('button','','Bandeja');button.type='button';button.dataset.opsView='inbox';button.innerHTML='Bandeja <small>W39</small>';button.addEventListener('click',()=>opsShowView('inbox'));
  const analytics=nav.querySelector('[data-ops-view="analytics"]');if(analytics?.nextSibling)nav.insertBefore(button,analytics.nextSibling);else nav.append(button)
}

function inboxCompanyId(){return marketingOpsState.selectedCompanyId||null}
function inboxCompanyKey(){return inboxCompanyId()||'__none__'}
function inboxDate(value){return value?opsDate(value):'Sin fecha'}
function inboxText(value,limit=180){const text=String(value||'').trim();return text.length>limit?`${text.slice(0,limit-1)}…`:text||'(sin texto)'}
function inboxPerson(person){return person?.username?`@${person.username}`:(person?.id?`Meta ${String(person.id).slice(-6)}`:'Persona')}

function inboxOpenCrm(contact){
  if(!contact?.id)return;
  try{crmState.selectedContactId=contact.id}catch(_err){}
  opsShowView('crm');setTimeout(()=>{try{renderCRMCurrent()}catch(_err){}},0)
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
  const card=opsEl('article','inbox-card'),head=opsEl('div','inbox-card-head'),left=opsEl('div','');left.append(opsEl('strong','',`Conversación ${String(conversation.id||'').slice(-8)}`),opsEl('small','',`Actualizada ${inboxDate(conversation.updated_time)}`));head.append(left,opsEl('span','status','READ ONLY'));card.append(head);
  const messages=conversation.messages||[];
  if(!messages.length){card.append(opsEl('div','inbox-empty','Meta no devolvió mensajes recientes para esta conversación.'));return card}
  for(const message of messages.slice(0,5)){
    const row=opsEl('div','inbox-message'),top=opsEl('div','inbox-card-head'),identity=opsEl('span','inbox-person',inboxPerson(message.from));top.append(identity,opsEl('small','',inboxDate(message.created_time)));row.append(top,opsEl('div','inbox-body',message.unavailable?'Mensaje no disponible por permisos/ventana de API.':inboxText(message.message,300)));
    if(message.crm_contact){const actions=opsEl('div','inbox-actions');actions.append(opsEl('span','analytics-chip',`CRM · ${message.crm_contact.name||'Contacto'}`));const open=opsEl('button','','Abrir CRM');open.type='button';open.addEventListener('click',()=>inboxOpenCrm(message.crm_contact));actions.append(open);row.append(actions)}
    card.append(row)
  }
  return card
}

function inboxCommentsColumn(section,data){
  const list=opsEl('div','inbox-list');
  for(const comment of data.comments||[]){const card=opsEl('article','inbox-comment'),head=opsEl('div','inbox-card-head'),identity=opsEl('span','inbox-person',inboxPerson(comment.from));head.append(identity,opsEl('small','',inboxDate(comment.timestamp)));card.append(head,opsEl('div','inbox-body',inboxText(comment.text,500)));if(comment.crm_contact){const actions=opsEl('div','inbox-actions');actions.append(opsEl('span','analytics-chip',`CRM · ${comment.crm_contact.name||'Contacto'}`));const open=opsEl('button','','Abrir CRM');open.type='button';open.addEventListener('click',()=>inboxOpenCrm(comment.crm_contact));actions.append(open);card.append(actions)}list.append(card)}
  if(!(data.comments||[]).length)list.append(opsEl('div','inbox-empty','No se encontraron comentarios recientes en publicaciones Instagram conocidas por la app.'));section.append(list)
}

function inboxRenderCurrent(){
  if(marketingOpsState.view!=='inbox')return;
  inboxEnsureStyles();inboxEnsureNav();const root=document.querySelector('#marketing-ops-view');if(!root)return;root.replaceChildren();document.querySelector('#marketing-ops-eyebrow').textContent='BANDEJA';document.querySelector('#marketing-ops-title').textContent='Atención de redes';document.querySelector('#marketing-ops-subtitle').textContent='Conversaciones y comentarios recientes, sin responder ni modificar Meta desde esta vista.';document.querySelectorAll('[data-ops-view]').forEach(button=>button.classList.toggle('active',button.dataset.opsView==='inbox'));
  const intro=opsEl('section','marketing-ops-section'),head=opsEl('div','marketing-ops-section-head'),copy=opsEl('div','');copy.append(opsEl('p','eyebrow','META · SINCRONIZACIÓN MANUAL'),opsEl('h3','','Bandeja read-only'),opsEl('p','muted','La app no consulta Meta en segundo plano. Pulsa Actualizar cuando quieras revisar conversaciones y comentarios.'));const actions=opsEl('div','inbox-actions'),refresh=opsEl('button','primary',inboxState.loading?'Actualizando…':'Actualizar desde Meta');refresh.type='button';refresh.disabled=inboxState.loading||!inboxCompanyId();refresh.addEventListener('click',inboxRefresh);actions.append(refresh);head.append(copy,actions);intro.append(head,opsEl('div','inbox-readonly','Wave 39 es sólo lectura: no responde mensajes, no contesta comentarios, no oculta comentarios y no inicia conversaciones. Esa capacidad requerirá un gate separado con permisos y ventanas de mensajería verificadas.'));root.append(intro);
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
if(typeof inboxBaseHome==='function')globalThis.renderOpsHome=function(root){inboxBaseHome(root);const section=opsEl('section','marketing-ops-section'),head=opsEl('div','marketing-ops-section-head'),copy=opsEl('div','');copy.append(opsEl('p','eyebrow','BANDEJA'),opsEl('h3','','Atención de redes'),opsEl('p','muted','Revisa conversaciones y comentarios de la empresa sin salir de MERCADEO APP.'));const open=opsEl('button','','Abrir bandeja');open.type='button';open.addEventListener('click',()=>opsShowView('inbox'));head.append(copy,open);section.append(head);root.append(section)};

inboxEnsureStyles();inboxEnsureNav();
