const wave62State={companyId:null,contacts:[],selectedContactId:null,data:null,loading:false};

function wave62Company(){return typeof wave61Company==='function'?wave61Company():(typeof wave60Company==='function'?wave60Company():null)}
function wave62Styles(){
  if(document.querySelector('#wave62-contact360-style'))return;
  const s=document.createElement('style');s.id='wave62-contact360-style';s.textContent=`
  .w62-shell{display:grid;gap:12px}.w62-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-end}.w62-actions{display:flex;gap:7px;flex-wrap:wrap}.w62-select{min-width:260px;max-width:420px}.w62-kpis{display:grid;grid-template-columns:repeat(6,minmax(100px,1fr));gap:8px}.w62-kpi,.w62-card,.w62-next,.w62-strip{border:1px solid #dedad1;border-radius:13px;background:#fff}.w62-kpi{padding:11px;display:grid;gap:4px}.w62-kpi span{font-size:8px;color:#716d65}.w62-kpi strong{font-size:19px}.w62-grid{display:grid;grid-template-columns:1.1fr 1fr;gap:10px}.w62-card{padding:13px;display:grid;gap:9px;align-content:start}.w62-card h3{margin:0;font-size:14px}.w62-card h4{margin:0;font-size:11px}.w62-card p{margin:0}.w62-next{padding:13px;display:grid;grid-template-columns:1fr auto;gap:12px;align-items:center;border-left:4px solid #171717}.w62-next strong{font-size:12px}.w62-next p{margin:3px 0 0}.w62-identity{display:flex;gap:6px;flex-wrap:wrap}.w62-chip{display:inline-flex;padding:3px 7px;border-radius:999px;background:#efede7;font-size:8px}.w62-chip.good{background:#e5f0e6}.w62-chip.warn{background:#fff0df}.w62-list{display:grid;gap:7px}.w62-row{padding:9px;border:1px solid #e8e3da;border-radius:10px;background:#fbfaf7;display:grid;gap:5px}.w62-row-head{display:flex;justify-content:space-between;gap:8px;align-items:flex-start}.w62-row strong{font-size:10px}.w62-row p{font-size:8px;color:#716d65;line-height:1.45}.w62-timeline{display:grid;gap:0}.w62-event{display:grid;grid-template-columns:105px 1fr;gap:10px;padding:8px 0;border-bottom:1px solid #eee9e0}.w62-event:last-child{border-bottom:0}.w62-event time{font-size:8px;color:#716d65}.w62-event span{font-size:9px}.w62-empty{padding:10px;border:1px dashed #d5d0c7;border-radius:9px;color:#716d65;font-size:9px}.w62-strip{padding:10px 12px;margin:0 0 10px;display:flex;justify-content:space-between;gap:10px;align-items:center}.w62-strip-copy{display:flex;gap:7px;align-items:center;flex-wrap:wrap}.w62-strip-copy strong{font-size:10px}
  @media(max-width:1180px){.w62-kpis{grid-template-columns:repeat(3,1fr)}}@media(max-width:800px){.w62-grid,.w62-kpis{grid-template-columns:1fr}.w62-head,.w62-next,.w62-row-head,.w62-strip{align-items:flex-start;grid-template-columns:1fr;flex-direction:column}.w62-select{min-width:0;width:100%}.w62-event{grid-template-columns:1fr}}
  `;document.head.append(s)
}
function wave62EnsureNav(){
  const nav=document.querySelector('.marketing-ops-nav');if(!nav||nav.querySelector('[data-ops-view="contact-360"]'))return;
  const b=opsEl('button','','Contacto 360');b.type='button';b.dataset.opsView='contact-360';b.innerHTML='Contacto 360 <small>W62</small>';b.addEventListener('click',()=>opsShowView('contact-360'));
  const commercial=nav.querySelector('[data-ops-view="commercial-desk"]');if(commercial)commercial.insertAdjacentElement('afterend',b);else nav.prepend(b)
}
function wave62Reset(){wave62State.companyId=null;wave62State.contacts=[];wave62State.selectedContactId=null;wave62State.data=null}
async function wave62LoadContacts(force=false){
  const c=wave62Company();if(!c){wave62Reset();return []}
  if(!force&&wave62State.companyId===c.id&&wave62State.contacts.length)return wave62State.contacts;
  const contacts=await opsApi(`/api/companies/${encodeURIComponent(c.id)}/contacts`);
  wave62State.companyId=c.id;wave62State.contacts=Array.isArray(contacts)?contacts:[];
  if(wave62State.selectedContactId&&!wave62State.contacts.some(row=>row.id===wave62State.selectedContactId))wave62State.selectedContactId=null;
  if(!wave62State.selectedContactId&&wave62State.contacts.length)wave62State.selectedContactId=wave62State.contacts[0].id;
  return wave62State.contacts
}
async function wave62LoadContact(contactId,force=false){
  const c=wave62Company();if(!c)return null;const id=String(contactId||wave62State.selectedContactId||'').trim();if(!id)return null;
  if(wave62State.loading)return wave62State.data;
  if(!force&&wave62State.companyId===c.id&&wave62State.selectedContactId===id&&wave62State.data)return wave62State.data;
  wave62State.loading=true;
  try{wave62State.data=await opsApi(`/api/companies/${encodeURIComponent(c.id)}/contacts/${encodeURIComponent(id)}/360`);wave62State.companyId=c.id;wave62State.selectedContactId=id;return wave62State.data}
  catch(err){wave62State.data=null;opsToast(err.message);return null}
  finally{wave62State.loading=false}
}
async function wave62OpenContact(contactId){
  const c=wave62Company();if(!c)return;wave62State.selectedContactId=contactId||wave62State.selectedContactId;wave62State.data=null;opsShowView('contact-360');await wave62LoadContacts();if(wave62State.selectedContactId)await wave62LoadContact(wave62State.selectedContactId,true);renderMarketingOps()
}
function wave62Kpi(title,value,copy){const x=opsEl('div','w62-kpi');x.append(opsEl('span','',title),opsEl('strong','',String(value??0)),opsEl('span','',copy));return x}
function wave62Identity(contact){const values=[];if(contact.email)values.push(contact.email);if(contact.phone)values.push(contact.phone);if(contact.whatsapp)values.push(`WA ${contact.whatsapp}`);if(contact.instagram)values.push(`@${String(contact.instagram).replace(/^@/,'')}`);return values}
function wave62OpenCRM(contactId,tab='contacts'){
  if(typeof wave61OpenContact==='function'){wave61OpenContact(contactId,tab);return}
  try{crmState.selectedContactId=contactId||null;crmState.tab=tab}catch(_err){}opsShowView('crm')
}
function wave62Selector(head){
  const box=opsEl('div','w62-actions'),select=document.createElement('select');select.className='w62-select';select.setAttribute('aria-label','Seleccionar contacto 360');
  if(!wave62State.contacts.length){const o=opsEl('option','','Sin contactos CRM');o.value='';select.append(o);select.disabled=true}else for(const row of wave62State.contacts){const label=[row.name,row.organization,row.email||row.instagram].filter(Boolean).join(' · ');const o=opsEl('option','',label);o.value=row.id;o.selected=row.id===wave62State.selectedContactId;select.append(o)}
  select.addEventListener('change',async()=>{wave62State.selectedContactId=select.value||null;wave62State.data=null;if(select.value)await wave62LoadContact(select.value,true);renderMarketingOps()});
  const crm=opsEl('button','','Abrir en CRM');crm.type='button';crm.addEventListener('click',()=>wave62OpenCRM(wave62State.selectedContactId,'contacts'));box.append(select,crm);head.append(box)
}
function wave62Next(data,shell){
  const next=data.next_action||{},box=opsEl('section','w62-next'),copy=opsEl('div','');copy.append(opsEl('p','eyebrow','SIGUIENTE ACCIÓN'),opsEl('strong','',next.label||'Revisar relación comercial'),opsEl('p','muted',next.reason||'Sin acción pendiente.'));const actions=opsEl('div','w62-actions');
  if(next.code==='CREATE_OPPORTUNITY'||next.code==='PLAN_FOLLOWUP'||next.code==='RESOLVE_OVERDUE_FOLLOWUP'||next.code==='FOLLOW_UP_AS_PLANNED'){const b=opsEl('button','primary',next.code==='CREATE_OPPORTUNITY'?'Abrir pipeline':'Gestionar en CRM');b.type='button';b.addEventListener('click',()=>wave62OpenCRM(data.contact.id,'pipeline'));actions.append(b)}
  const desk=opsEl('button','','Abrir Mesa comercial');desk.type='button';desk.addEventListener('click',()=>opsShowView('commercial-desk'));actions.append(desk);box.append(copy,actions);shell.append(box)
}
function wave62OpportunityCard(data){
  const card=opsEl('section','w62-card');card.append(opsEl('h3','','Oportunidades'),opsEl('p','muted','Pipeline local asociado al contacto. No se suman monedas distintas.'));const list=opsEl('div','w62-list');for(const row of data.opportunities||[]){const line=opsEl('div','w62-row'),head=opsEl('div','w62-row-head'),copy=opsEl('div','');copy.append(opsEl('strong','',row.title),opsEl('p','',row.next_action||'Sin siguiente acción escrita'));const chip=opsEl('span',row.stage==='WON'?'w62-chip good':row.stage==='LOST'?'w62-chip':'w62-chip warn',row.stage);head.append(copy,chip);line.append(head);if(row.value!=null)line.append(opsEl('p','',`${row.currency||''} ${new Intl.NumberFormat('es-CO').format(row.value)}`));if(row.next_action_at)line.append(opsEl('p','',`Siguiente: ${opsDate(row.next_action_at)}`));list.append(line)}if(!list.children.length)list.append(opsEl('div','w62-empty','Este contacto aún no tiene oportunidades.'));card.append(list);return card
}
function wave62ActivityCard(data){
  const card=opsEl('section','w62-card');card.append(opsEl('h3','','Actividad comercial'),opsEl('p','muted','Historial y seguimientos registrados; registrar una actividad no envía mensajes.'));const list=opsEl('div','w62-list');for(const row of (data.activities||[]).slice(0,12)){const line=opsEl('div','w62-row'),head=opsEl('div','w62-row-head'),copy=opsEl('div','');copy.append(opsEl('strong','',row.summary),opsEl('p','',`${row.kind}${row.due_at?` · ${opsDate(row.due_at)}`:''}`));head.append(copy,opsEl('span',row.completed_at?'w62-chip good':row.due_at&&new Date(row.due_at)<new Date()?'w62-chip warn':'w62-chip',row.completed_at?'COMPLETA':'PENDIENTE'));line.append(head);list.append(line)}if(!list.children.length)list.append(opsEl('div','w62-empty','No hay actividades comerciales registradas.'));card.append(list);return card
}
function wave62OriginCard(data){
  const card=opsEl('section','w62-card');card.append(opsEl('h3','','Origen & atribución'),opsEl('p','muted','Solo se muestra evidencia durable; no se expone bm_tid, tracking code ni URL rastreada.'));const list=opsEl('div','w62-list');
  for(const row of data.lead_origins||[]){const line=opsEl('div','w62-row'),head=opsEl('div','w62-row-head'),copy=opsEl('div','');copy.append(opsEl('strong','',row.source||row.connector||'Lead Intake'),opsEl('p','',`${row.connector||'INTAKE'} · ${row.received_at?opsDate(row.received_at):'sin fecha'}`));head.append(copy,opsEl('span',row.attribution_verified?'w62-chip good':'w62-chip',row.attribution_verified?'ATRIBUCIÓN VALIDADA':'SIN ATRIBUCIÓN'));line.append(head);const utm=[row.utm_source,row.utm_medium,row.utm_campaign].filter(Boolean).join(' / ');if(utm)line.append(opsEl('p','',utm));list.append(line)}
  for(const row of data.attribution||[]){const line=opsEl('div','w62-row'),head=opsEl('div','w62-row-head'),copy=opsEl('div','');copy.append(opsEl('strong','','Atribución verificada'),opsEl('p','',`${row.utm_source||'source desconocido'} / ${row.utm_medium||'medium desconocido'}${row.utm_campaign?` · ${row.utm_campaign}`:''}`));head.append(copy,opsEl('span','w62-chip good',row.evidence||'EVIDENCIA'));line.append(head);list.append(line)}
  if(!list.children.length)list.append(opsEl('div','w62-empty','No hay origen de intake ni atribución first-party asociada.'));card.append(list);return card
}
function wave62CampaignCard(data){
  const card=opsEl('section','w62-card');card.append(opsEl('h3','','Campañas relacionadas'),opsEl('p','muted','Relación por snapshot de audiencia y/o evidencia de atribución; no se infiere exposición.'));const list=opsEl('div','w62-list');for(const row of data.campaigns||[]){const line=opsEl('div','w62-row'),head=opsEl('div','w62-row-head'),copy=opsEl('div','');copy.append(opsEl('strong','',row.name),opsEl('p','',`${row.objective} · ${(row.channels||[]).join(', ')||'sin canal'}`));head.append(copy,opsEl('span','w62-chip',row.status));line.append(head);const chips=opsEl('div','w62-identity');if(row.audience_membership)chips.append(opsEl('span','w62-chip','AUDIENCIA'));if(row.attribution_evidence)chips.append(opsEl('span','w62-chip good','ATRIBUCIÓN'));line.append(chips);list.append(line)}if(!list.children.length)list.append(opsEl('div','w62-empty','No hay campañas relacionadas por evidencia local.'));card.append(list);return card
}
function wave62TimelineCard(data){
  const card=opsEl('section','w62-card');card.style.gridColumn='1/-1';card.append(opsEl('h3','','Línea de tiempo'),opsEl('p','muted','Eventos locales ordenados por fecha. No se atribuye causalidad donde no existe evidencia.'));const list=opsEl('div','w62-timeline');for(const row of (data.timeline||[]).slice(0,24)){const line=opsEl('div','w62-event'),time=document.createElement('time');time.textContent=row.at?opsDate(row.at):'Sin fecha';line.append(time,opsEl('span','',row.label||row.kind));list.append(line)}if(!list.children.length)list.append(opsEl('div','w62-empty','Sin eventos para mostrar.'));card.append(list);return card
}
function wave62Render(){
  wave62EnsureNav();wave62Styles();const root=document.querySelector('#marketing-ops-view');if(!root)return;root.replaceChildren();document.querySelector('#marketing-ops-eyebrow').textContent='COMMERCIAL CONTEXT';document.querySelector('#marketing-ops-title').textContent='Contacto 360';document.querySelector('#marketing-ops-subtitle').textContent='Identidad, origen, oportunidades, actividades, campañas y atribución en una sola ficha local y verificable.';document.querySelectorAll('[data-ops-view]').forEach(b=>b.classList.toggle('active',b.dataset.opsView==='contact-360'));
  const c=wave62Company();if(!c){root.append(opsEmpty('Selecciona una empresa para abrir Contacto 360.'));return}
  if(wave62State.companyId!==c.id||!wave62State.contacts.length){root.append(opsEmpty('Preparando contactos CRM locales…'));wave62LoadContacts(true).then(async()=>{if(wave62State.selectedContactId)await wave62LoadContact(wave62State.selectedContactId,true);renderMarketingOps()}).catch(err=>opsToast(err.message));return}
  const shell=opsEl('div','w62-shell'),head=opsEl('div','w62-head'),copy=opsEl('div','');copy.append(opsEl('p','eyebrow','CRM → EVIDENCIA → SIGUIENTE ACCIÓN'),opsEl('h3','',`Contexto comercial · ${c.name}`),opsEl('p','muted','La ficha reúne fuentes existentes sin duplicar CRM ni consultar proveedores.'));head.append(copy);wave62Selector(head);shell.append(head);
  if(!wave62State.selectedContactId){shell.append(opsEl('div','w62-empty','No hay contactos CRM para esta empresa.'));root.append(shell);return}
  if(!wave62State.data||wave62State.data.contact?.id!==wave62State.selectedContactId){shell.append(opsEl('div','w62-empty','Componiendo evidencia local del contacto…'));root.append(shell);wave62LoadContact(wave62State.selectedContactId,true).then(renderMarketingOps);return}
  const data=wave62State.data,s=data.summary||{},contact=data.contact||{};const identity=opsEl('div','w62-identity');for(const value of wave62Identity(contact))identity.append(opsEl('span','w62-chip',value));if(contact.organization)identity.append(opsEl('span','w62-chip',contact.organization));if(contact.role)identity.append(opsEl('span','w62-chip',contact.role));shell.append(opsEl('h3','',contact.name||'Contacto CRM'),identity);const kpis=opsEl('div','w62-kpis');kpis.append(wave62Kpi('OPORTUNIDADES',s.open_opportunities,'abiertas'),wave62Kpi('GANADAS',s.won_opportunities,'históricas'),wave62Kpi('PENDIENTES',s.pending_activities,'actividades'),wave62Kpi('VENCIDAS',s.overdue_activities,'requieren atención'),wave62Kpi('ORÍGENES',s.lead_origins,'Lead Intake'),wave62Kpi('CAMPAÑAS',s.campaigns,'con evidencia'));shell.append(kpis);wave62Next(data,shell);const grid=opsEl('div','w62-grid');grid.append(wave62OpportunityCard(data),wave62ActivityCard(data),wave62OriginCard(data),wave62CampaignCard(data),wave62TimelineCard(data));shell.append(grid,opsEl('p','muted','W62 es una composición GET local: no consulta Meta, no ejecuta acciones, no envía mensajes y no requiere cloud.'));root.append(shell)
}
function wave62CommercialStrip(){
  if(marketingOpsState?.view!=='commercial-desk')return;const root=document.querySelector('#marketing-ops-view');if(!root||root.querySelector('#wave62-commercial-strip'))return;const handoffs=(typeof wave61State!=='undefined'&&wave61State.data?.handoffs)||[];const rows=handoffs.filter(row=>row.contact_id).slice(0,3);if(!rows.length)return;wave62Styles();const strip=opsEl('section','w62-strip');strip.id='wave62-commercial-strip';const copy=opsEl('div','w62-strip-copy');copy.append(opsEl('strong','','Contacto 360'));for(const row of rows){const b=opsEl('button','',row.contact_name||'Abrir contacto');b.type='button';b.addEventListener('click',()=>wave62OpenContact(row.contact_id));copy.append(b)}strip.append(copy,opsEl('span','muted','Contexto completo sin salir del flujo comercial'));root.prepend(strip)
}
function wave62Enhance(){wave62EnsureNav();if(marketingOpsState?.view==='contact-360'){wave62Render();return}wave62CommercialStrip()}
const wave62BaseRenderMarketingOps=globalThis.renderMarketingOps;
if(typeof wave62BaseRenderMarketingOps==='function')globalThis.renderMarketingOps=function(){if(marketingOpsState?.view==='contact-360'){wave62Render();return}const result=wave62BaseRenderMarketingOps();queueMicrotask(wave62Enhance);return result};
window.addEventListener('marketing-company-change',()=>{wave62Reset();queueMicrotask(wave62Enhance)});
wave62Enhance();
