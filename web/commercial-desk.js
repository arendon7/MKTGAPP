const wave61State={companyId:null,data:null,loading:false};

function wave61Company(){return typeof wave60Company==='function'?wave60Company():(typeof wave47Company==='function'?wave47Company():null)}
function wave61Styles(){
  if(document.querySelector('#wave61-commercial-style'))return;
  const s=document.createElement('style');s.id='wave61-commercial-style';s.textContent=`
  .w61-shell{display:grid;gap:12px}.w61-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-end}.w61-actions{display:flex;gap:7px;flex-wrap:wrap}.w61-grid{display:grid;grid-template-columns:repeat(5,minmax(120px,1fr));gap:8px}.w61-kpi,.w61-section,.w61-lane,.w61-strip{border:1px solid #dedad1;border-radius:13px;background:#fff}.w61-kpi{padding:12px;display:grid;gap:4px}.w61-kpi span{font-size:8px;color:#716d65}.w61-kpi strong{font-size:20px}.w61-board{display:grid;grid-template-columns:1fr 1.25fr 1.25fr;gap:10px}.w61-lane{padding:12px;display:grid;gap:9px;align-content:start}.w61-lane-head{display:flex;justify-content:space-between;gap:8px;align-items:flex-start}.w61-lane-head h3{margin:0;font-size:14px}.w61-lane-head p{margin:3px 0 0}.w61-list{display:grid;gap:7px}.w61-row{padding:9px;border:1px solid #e8e3da;border-radius:10px;background:#fbfaf7;display:grid;gap:6px}.w61-row.hot{border-left:4px solid #171717}.w61-row-head{display:flex;justify-content:space-between;gap:8px;align-items:flex-start}.w61-row strong{font-size:10px}.w61-row p{margin:0;font-size:8px;color:#716d65;line-height:1.45}.w61-chip{display:inline-flex;padding:3px 7px;border-radius:999px;background:#efede7;font-size:8px}.w61-chip.hot{background:#171717;color:#fff}.w61-chip.good{background:#e5f0e6}.w61-chip.warn{background:#fff0df}.w61-identities{display:flex;gap:5px;flex-wrap:wrap}.w61-form{display:grid;gap:6px;padding-top:5px}.w61-form .fields{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(90px,.7fr) 70px;gap:5px}.w61-form.follow .fields{grid-template-columns:minmax(0,1.5fr) minmax(155px,.8fr)}.w61-form input,.w61-form select{min-width:0}.w61-empty{padding:10px;border:1px dashed #d5d0c7;border-radius:9px;color:#716d65;font-size:9px;line-height:1.45}.w61-note{font-size:8px;color:#716d65;line-height:1.45}.w61-strip{padding:10px 12px;margin-bottom:10px;display:flex;justify-content:space-between;gap:10px;align-items:center}.w61-strip-copy{display:flex;gap:7px;align-items:center;flex-wrap:wrap}.w61-strip-copy strong{font-size:10px}
  @media(max-width:1180px){.w61-board{grid-template-columns:1fr 1fr}.w61-board>.w61-lane:first-child{grid-column:1/-1}.w61-grid{grid-template-columns:repeat(3,1fr)}}@media(max-width:760px){.w61-board,.w61-grid{grid-template-columns:1fr}.w61-board>.w61-lane:first-child{grid-column:auto}.w61-head,.w61-row-head,.w61-strip{align-items:flex-start;flex-direction:column}.w61-form .fields,.w61-form.follow .fields{grid-template-columns:1fr}}
  `;document.head.append(s)
}
function wave61EnsureNav(){
  const nav=document.querySelector('.marketing-ops-nav');if(!nav||nav.querySelector('[data-ops-view="commercial-desk"]'))return;
  const b=opsEl('button','','Mesa comercial');b.type='button';b.dataset.opsView='commercial-desk';b.innerHTML='Mesa comercial <small>W61</small>';b.addEventListener('click',()=>opsShowView('commercial-desk'));
  const inbox=nav.querySelector('[data-ops-view="inbox"]');if(inbox)nav.insertBefore(b,inbox);else nav.prepend(b)
}
async function wave61Load(force=false){
  const c=wave61Company();if(!c){wave61State.companyId=null;wave61State.data=null;return null}
  if(wave61State.loading)return wave61State.data;
  if(!force&&wave61State.companyId===c.id&&wave61State.data)return wave61State.data;
  wave61State.loading=true;
  try{wave61State.data=await opsApi(`/api/companies/${encodeURIComponent(c.id)}/commercial-desk`);wave61State.companyId=c.id;return wave61State.data}
  catch(err){wave61State.data=null;opsToast(err.message);return null}
  finally{wave61State.loading=false}
}
async function wave61Refresh(message){
  wave61State.data=null;
  if(typeof wave55Load==='function')await wave55Load(true);
  await wave61Load(true);
  if(typeof wave60Load==='function')await wave60Load(true);
  if(message)opsToast(message);
  renderMarketingOps()
}
function wave61Kpi(title,value,copy){const x=opsEl('div','w61-kpi');x.append(opsEl('span','',title),opsEl('strong','',String(value??0)),opsEl('span','',copy));return x}
function wave61Identity(row){const out=[];if(row.email)out.push(row.email);if(row.phone)out.push(row.phone);if(row.whatsapp)out.push(`WA ${row.whatsapp}`);if(row.instagram)out.push(`@${String(row.instagram).replace(/^@/,'')}`);return out}
function wave61OpenContact(contactId,tab='contacts'){
  try{crmState.selectedContactId=contactId||null;crmState.tab=tab}catch(_err){}
  opsShowView('crm')
}
function wave61ExplicitInboxRefresh(){
  opsShowView('inbox');setTimeout(()=>{if(typeof inboxRefresh==='function')inboxRefresh()},0)
}
function wave61InboxCandidates(){
  const c=wave61Company();if(!c||typeof inboxState==='undefined'||inboxState.companyKey!==c.id||!inboxState.data)return [];
  const result=[],seen=new Set();
  const push=(kind,row,parentId)=>{
    const person=row?.from||{};if(row?.crm_contact?.id)return;
    const username=String(person.username||'').trim().replace(/^@/,'');const personId=String(person.id||'').trim();const name=String(person.name||username||'').trim();
    const identity=username?`ig:${username.toLowerCase()}`:personId?`id:${personId}`:name?`name:${name.toLowerCase()}`:'';if(!identity||seen.has(identity))return;seen.add(identity);
    const interactionId=String(row?.id||parentId||identity).replace(/[^A-Za-z0-9_.:-]/g,'_').slice(0,120);
    result.push({kind,interactionId,name:name||'Persona sin nombre',instagram:username||null,personId:personId||null})
  };
  for(const conversation of inboxState.data.conversations||[]){for(const message of conversation.messages||[])push('MENSAJE',message,conversation.id)}
  for(const comment of inboxState.data.comments||[])push('COMENTARIO',comment,comment.media_id);
  return result.slice(0,12)
}
async function wave61StageInbox(candidate,button){
  const c=wave61Company();if(!c)return;button.disabled=true;
  try{
    const body={connector:'MANUAL',source_ref:`meta_inbox:${candidate.kind.toLowerCase()}:${candidate.interactionId}`,name:candidate.name,source:'Meta Inbox',tags:['inbox']};
    if(candidate.instagram)body.instagram=candidate.instagram;
    await opsApi(`/api/companies/${encodeURIComponent(c.id)}/lead-intake`,{method:'POST',body});
    await wave61Refresh('Interacción enviada a Lead Intake; CRM sigue sin cambios')
  }catch(err){opsToast(err.message)}finally{button.disabled=false}
}
async function wave61ConvertLead(row,action,contactId,button){
  const c=wave61Company();button.disabled=true;
  try{const body={action};if(contactId)body.contact_id=contactId;await opsApi(`/api/companies/${encodeURIComponent(c.id)}/lead-intake/${encodeURIComponent(row.lead_id)}/convert`,{method:'POST',body});await wave61Refresh(action==='CREATE_CONTACT'?'Contacto creado explícitamente':'Lead vinculado al contacto exacto')}
  catch(err){opsToast(err.message)}finally{button.disabled=false}
}
function wave61LeadActions(row,box){
  if(row.status==='MATCHED'&&row.candidate_contacts?.length===1){const m=row.candidate_contacts[0],b=opsEl('button','primary',`Vincular · ${m.name}`);b.type='button';b.addEventListener('click',()=>wave61ConvertLead(row,'LINK_CONTACT',m.id,b));box.append(b);return}
  if(row.status==='CONFLICT'&&row.candidate_contacts?.length){const select=document.createElement('select');for(const m of row.candidate_contacts){const o=opsEl('option','',`${m.name}${m.organization?` · ${m.organization}`:''}`);o.value=m.id;select.append(o)}const b=opsEl('button','primary','Resolver conflicto exacto');b.type='button';b.addEventListener('click',()=>wave61ConvertLead(row,'LINK_CONTACT',select.value,b));box.append(select,b);return}
  if(row.status==='NEW'||row.status==='UNIDENTIFIED'){const b=opsEl('button','primary','Crear contacto');b.type='button';b.addEventListener('click',()=>wave61ConvertLead(row,'CREATE_CONTACT',null,b));box.append(b)}
}
function wave61OpportunityForm(row,box){
  const form=opsEl('form','w61-form'),fields=opsEl('div','fields'),title=document.createElement('input'),value=document.createElement('input'),currency=document.createElement('input');title.required=true;title.placeholder=`Oportunidad · ${row.contact_name||'Contacto'}`;value.type='number';value.min='0';value.step='1';value.placeholder='Valor';currency.value='COP';currency.maxLength=3;fields.append(title,value,currency);const b=opsEl('button','primary','Crear oportunidad');b.type='submit';form.append(fields,b);form.addEventListener('submit',async ev=>{ev.preventDefault();b.disabled=true;try{const c=wave61Company(),body={contact_id:row.contact_id,title:title.value.trim(),stage:'NEW',currency:currency.value.trim().toUpperCase()||'COP'};if(value.value!=='')body.value=Number(value.value);await opsApi(`/api/companies/${encodeURIComponent(c.id)}/opportunities`,{method:'POST',body});await wave61Refresh('Oportunidad creada explícitamente')}catch(err){opsToast(err.message)}finally{b.disabled=false}});box.append(form)
}
function wave61FollowupForm(row,box){
  const form=opsEl('form','w61-form follow'),fields=opsEl('div','fields'),summary=document.createElement('input'),due=document.createElement('input');summary.required=true;summary.placeholder='Próximo seguimiento';due.type='datetime-local';fields.append(summary,due);const b=opsEl('button','primary','Programar seguimiento');b.type='submit';form.append(fields,b);form.addEventListener('submit',async ev=>{ev.preventDefault();b.disabled=true;try{const c=wave61Company(),body={contact_id:row.contact_id,opportunity_id:row.opportunity_id,kind:'TASK',summary:summary.value.trim()};if(due.value)body.due_at=new Date(due.value).toISOString();await opsApi(`/api/companies/${encodeURIComponent(c.id)}/activities`,{method:'POST',body});await wave61Refresh('Seguimiento comercial programado')}catch(err){opsToast(err.message)}finally{b.disabled=false}});box.append(form)
}
function wave61InboxLane(board){
  const lane=opsEl('section','w61-lane'),head=opsEl('div','w61-lane-head'),copy=opsEl('div','');copy.append(opsEl('h3','','1 · Conversaciones'),opsEl('p','muted','La consulta a Meta sigue siendo manual. La mesa usa solo la caché de esta sesión.'));const refresh=opsEl('button','','Actualizar Inbox');refresh.type='button';refresh.addEventListener('click',wave61ExplicitInboxRefresh);head.append(copy,refresh);lane.append(head);const cache=typeof wave60InboxCache==='function'?wave60InboxCache():null,candidates=wave61InboxCandidates(),list=opsEl('div','w61-list');if(cache){const row=opsEl('div','w61-row');row.append(opsEl('strong','',`${cache.interactions} interacciones · ${cache.unmatchedInteractions} sin vínculo CRM`),opsEl('p','',`${cache.crmMatches} contacto(s) CRM identificados en la última consulta explícita.`));list.append(row)}else list.append(opsEl('div','w61-empty','Inbox aún no fue consultado en esta sesión. Nada se consulta automáticamente.'));
  for(const candidate of candidates.slice(0,5)){const row=opsEl('div','w61-row'),rh=opsEl('div','w61-row-head'),person=opsEl('div','');person.append(opsEl('strong','',candidate.name),opsEl('p','',candidate.instagram?`@${candidate.instagram}`:`${candidate.kind} sin identidad social exacta`));const chip=opsEl('span','w61-chip warn',candidate.kind);rh.append(person,chip);const b=opsEl('button','primary','Pasar a Lead Intake');b.type='button';b.addEventListener('click',()=>wave61StageInbox(candidate,b));row.append(rh,b,opsEl('p','w61-note','Acción explícita: crea un candidato en intake; no crea ni modifica contactos CRM.'));list.append(row)}lane.append(list);board.append(lane)
}
function wave61LeadLane(board,data){
  const lane=opsEl('section','w61-lane'),head=opsEl('div','w61-lane-head'),copy=opsEl('div','');copy.append(opsEl('h3','','2 · Resolver leads'),opsEl('p','muted','Conflictos y coincidencias exactas primero. No fuzzy, no merge automático.'));const all=opsEl('button','','Abrir Lead Intake');all.type='button';all.addEventListener('click',()=>opsShowView('lead-intake'));head.append(copy,all);lane.append(head);const list=opsEl('div','w61-list');for(const row of (data.lead_queue||[]).slice(0,8)){const line=opsEl('div',`w61-row ${row.priority<=1?'hot':''}`),rh=opsEl('div','w61-row-head'),person=opsEl('div','');person.append(opsEl('strong','',row.display_name),opsEl('p','',`${row.connector||'INTAKE'} · ${row.attribution_verified?'atribución validada':'sin atribución inferida'}`));rh.append(person,opsEl('span',row.status==='CONFLICT'?'w61-chip hot':row.status==='MATCHED'?'w61-chip warn':'w61-chip',row.status));line.append(rh);const ids=opsEl('div','w61-identities');for(const value of wave61Identity(row))ids.append(opsEl('span','w61-chip',value));if(row.duplicate_open_lead_count)ids.append(opsEl('span','w61-chip warn',`${row.duplicate_open_lead_count} duplicado(s) intake`));line.append(ids);const actions=opsEl('div','w61-actions');wave61LeadActions(row,actions);line.append(actions);list.append(line)}if(!(data.lead_queue||[]).length)list.append(opsEl('div','w61-empty','No hay leads abiertos por resolver.'));lane.append(list);board.append(lane)
}
function wave61HandoffLane(board,data){
  const lane=opsEl('section','w61-lane'),head=opsEl('div','w61-lane-head'),copy=opsEl('div','');copy.append(opsEl('h3','','3 · Convertir en venta'),opsEl('p','muted','Después del contacto: oportunidad y siguiente seguimiento, siempre explícitos.'));const crm=opsEl('button','','Abrir CRM');crm.type='button';crm.addEventListener('click',()=>wave61OpenContact(null,'pipeline'));head.append(copy,crm);lane.append(head);const list=opsEl('div','w61-list');for(const row of (data.handoffs||[]).slice(0,8)){if(row.handoff_state==='CLOSED')continue;const line=opsEl('div',`w61-row ${['NEEDS_OPPORTUNITY','NEEDS_FOLLOWUP'].includes(row.handoff_state)?'hot':''}`),rh=opsEl('div','w61-row-head'),person=opsEl('div','');person.append(opsEl('strong','',row.contact_name||'Contacto CRM'),opsEl('p','',row.contact_organization||'CRM'));const labels={NEEDS_OPPORTUNITY:'Falta oportunidad',NEEDS_FOLLOWUP:'Falta seguimiento',FOLLOWUP_PLANNED:'Seguimiento listo'};rh.append(person,opsEl('span',row.handoff_state==='FOLLOWUP_PLANNED'?'w61-chip good':'w61-chip warn',labels[row.handoff_state]||row.handoff_state));line.append(rh);if(row.opportunity_title)line.append(opsEl('p','',`${row.opportunity_title} · ${row.opportunity_stage}${row.opportunity_value!=null?` · ${row.opportunity_currency} ${new Intl.NumberFormat('es-CO').format(row.opportunity_value)}`:''}`));if(row.next_activity)line.append(opsEl('p','',`Próximo: ${row.next_activity.summary}${row.next_activity.due_at?` · ${opsDate(row.next_activity.due_at)}`:' · sin fecha'}`));const actions=opsEl('div','w61-actions'),open=opsEl('button','','Abrir contacto');open.type='button';open.addEventListener('click',()=>wave61OpenContact(row.contact_id,row.opportunity_id?'pipeline':'contacts'));actions.append(open);line.append(actions);if(row.handoff_state==='NEEDS_OPPORTUNITY')wave61OpportunityForm(row,line);else if(row.handoff_state==='NEEDS_FOLLOWUP')wave61FollowupForm(row,line);list.append(line)}if(!list.children.length)list.append(opsEl('div','w61-empty','No hay handoffs comerciales pendientes.'));lane.append(list);board.append(lane)
}
function wave61Render(){
  wave61EnsureNav();wave61Styles();const root=document.querySelector('#marketing-ops-view');if(!root)return;root.replaceChildren();document.querySelector('#marketing-ops-eyebrow').textContent='COMMERCIAL OPERATIONS';document.querySelector('#marketing-ops-title').textContent='Mesa comercial';document.querySelector('#marketing-ops-subtitle').textContent='De conversación a lead, contacto, oportunidad y seguimiento sin perder el contexto ni automatizar decisiones.';document.querySelectorAll('[data-ops-view]').forEach(b=>b.classList.toggle('active',b.dataset.opsView==='commercial-desk'));
  const c=wave61Company();if(!c){root.append(opsEmpty('Selecciona una empresa para abrir la mesa comercial.'));return}if(!wave61State.data||wave61State.companyId!==c.id){root.append(opsEmpty('Preparando mesa comercial local…'));wave61Load(true).then(renderMarketingOps);return}const data=wave61State.data,s=data.summary||{},shell=opsEl('div','w61-shell'),head=opsEl('div','w61-head'),copy=opsEl('div','');copy.append(opsEl('p','eyebrow','INBOX → LEAD → CRM'),opsEl('h3','',`Operación comercial · ${c.name}`),opsEl('p','muted','La identidad exacta y la decisión humana siguen siendo el gate antes de modificar CRM.'));const actions=opsEl('div','w61-actions'),local=opsEl('button','','Actualizar estado local');local.type='button';local.addEventListener('click',()=>wave61Refresh());actions.append(local);head.append(copy,actions);shell.append(head);const grid=opsEl('div','w61-grid');grid.append(wave61Kpi('LEADS ABIERTOS',s.open_leads,'por resolver'),wave61Kpi('MATCHED',s.matched,'1 contacto exacto'),wave61Kpi('CONFLICTOS',s.conflicts,'requieren selección'),wave61Kpi('OPORTUNIDADES',s.open_opportunities,'abiertas'),wave61Kpi('HANDOFFS',s.handoffs_needing_action,'sin oportunidad/seguimiento'));shell.append(grid);const board=opsEl('div','w61-board');wave61InboxLane(board);wave61LeadLane(board,data);wave61HandoffLane(board,data);shell.append(board,opsEl('p','w61-note','W61 no consulta Meta al renderizar, no fusiona identidades, no convierte leads automáticamente y no envía mensajes.'));root.append(shell)
}
function wave61Strip(){
  if(!['inbox','lead-intake','crm'].includes(marketingOpsState?.view))return;wave61Styles();const root=document.querySelector('#marketing-ops-view');if(!root||root.querySelector('#wave61-strip'))return;const data=wave61State.data,c=wave61Company();if(c&&wave61State.companyId!==c.id&&!wave61State.loading)wave61Load(true).then(renderMarketingOps);const s=data?.summary||{},strip=opsEl('section','w61-strip');strip.id='wave61-strip';const copy=opsEl('div','w61-strip-copy');copy.append(opsEl('strong','','Mesa comercial'),opsEl('span',s.conflicts?'w61-chip hot':'w61-chip',`${s.conflicts||0} conflictos`),opsEl('span','w61-chip',`${s.open_leads||0} leads abiertos`),opsEl('span','w61-chip',`${s.handoffs_needing_action||0} handoffs`));const b=opsEl('button','primary','Abrir mesa');b.type='button';b.addEventListener('click',()=>opsShowView('commercial-desk'));strip.append(copy,b);root.prepend(strip)
}
function wave61Enhance(){wave61EnsureNav();if(marketingOpsState?.view==='commercial-desk'){wave61Render();return}wave61Strip()}
const wave61BaseRenderMarketingOps=globalThis.renderMarketingOps;
if(typeof wave61BaseRenderMarketingOps==='function')globalThis.renderMarketingOps=function(){if(marketingOpsState?.view==='commercial-desk'){wave61Render();return}const result=wave61BaseRenderMarketingOps();queueMicrotask(wave61Enhance);return result};
window.addEventListener('marketing-company-change',()=>{wave61State.companyId=null;wave61State.data=null;queueMicrotask(wave61Enhance)});
wave61Enhance();
