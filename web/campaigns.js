const campaignState={companyId:null,rows:[],contacts:[],media:[],publications:[],selectedId:null,loading:false,loaded:false};

const CAMPAIGN_OBJECTIVE_LABELS={AWARENESS:'Reconocimiento',ENGAGEMENT:'Interacción',LEADS:'Leads',SALES:'Ventas',RETENTION:'Retención',OTHER:'Otro'};
const CAMPAIGN_STATUS_LABELS={PLANNING:'Planeando',READY:'Lista',IN_PROGRESS:'En curso',COMPLETED:'Completada',ARCHIVED:'Archivada'};
const CAMPAIGN_CHANNEL_LABELS={facebook_page:'Facebook',instagram:'Instagram',email:'Email',whatsapp:'WhatsApp'};

function campaignEnsureStyles(){
  if(document.querySelector('#campaign-wave35-style'))return;
  const style=document.createElement('style');style.id='campaign-wave35-style';style.textContent=`
  .campaign-layout{display:grid;grid-template-columns:minmax(260px,.8fr) minmax(420px,1.6fr);gap:12px}.campaign-list{display:grid;gap:8px}.campaign-card{border:1px solid #dedbd2;border-radius:12px;padding:11px;background:#fff;display:grid;gap:6px;cursor:pointer}.campaign-card.active{outline:2px solid #171717}.campaign-card-head{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}.campaign-tags{display:flex;flex-wrap:wrap;gap:5px}.campaign-chip{font-size:9px;padding:3px 7px;border-radius:999px;background:#efede7}.campaign-form{display:grid;gap:10px}.campaign-form .two{display:grid;grid-template-columns:1fr 1fr;gap:8px}.campaign-checks{display:flex;flex-wrap:wrap;gap:8px}.campaign-check{display:flex;align-items:center;gap:5px;font-size:11px}.campaign-check input{width:auto}.campaign-multiselect{min-height:100px}.campaign-readiness{display:grid;grid-template-columns:repeat(2,minmax(160px,1fr));gap:7px}.campaign-readiness-card{border:1px solid #e5e1d9;border-radius:9px;padding:8px;display:grid;gap:3px}.campaign-readiness-card strong{font-size:11px}.campaign-readiness-card span{font-size:9px;color:#77736b}.campaign-warning{padding:9px;border:1px solid #dedbd2;border-radius:9px;background:#f5f2eb;font-size:10px}.campaign-counts{display:flex;gap:8px;flex-wrap:wrap}.campaign-count{font-size:9px;color:#625f58}.campaign-actions{display:flex;gap:8px;flex-wrap:wrap}.campaign-empty{padding:18px;border:1px dashed #d8d3c8;border-radius:10px;color:#77736b;font-size:11px}
  @media(max-width:950px){.campaign-layout{grid-template-columns:1fr}.campaign-readiness{grid-template-columns:1fr}.campaign-form .two{grid-template-columns:1fr}}
  `;document.head.append(style);
}

function campaignCompany(){return typeof opsSelectedCompany==='function'?opsSelectedCompany():null}
function campaignLabelStatus(value){return CAMPAIGN_STATUS_LABELS[value]||value}
function campaignLabelObjective(value){return CAMPAIGN_OBJECTIVE_LABELS[value]||value}
function campaignDateInput(value){if(!value)return '';const date=new Date(value);if(Number.isNaN(date.getTime()))return '';const local=new Date(date.getTime()-date.getTimezoneOffset()*60000);return local.toISOString().slice(0,16)}
function campaignSelectedValues(select){return [...select.selectedOptions].map(option=>option.value).filter(Boolean)}

function campaignEnsureNav(){
  const nav=document.querySelector('.marketing-ops-nav');if(!nav||nav.querySelector('[data-ops-view="campaigns"]'))return;
  const button=opsEl('button','','Campañas');button.type='button';button.dataset.opsView='campaigns';button.innerHTML='Campañas <small>W35</small>';button.addEventListener('click',()=>opsShowView('campaigns'));
  const crm=nav.querySelector('[data-ops-view="crm"]');if(crm)nav.insertBefore(button,crm);else nav.append(button);
}

async function campaignRefresh(force=false){
  const company=campaignCompany(),companyId=company?.id||null;
  if(!companyId){campaignState.companyId=null;campaignState.rows=[];campaignState.contacts=[];campaignState.media=[];campaignState.publications=[];campaignState.loaded=true;return}
  if(campaignState.loading)return;
  if(!force&&campaignState.loaded&&campaignState.companyId===companyId)return;
  campaignState.loading=true;campaignState.companyId=companyId;
  try{
    const [rows,contacts,media,detail]=await Promise.all([
      opsApi(`/api/companies/${encodeURIComponent(companyId)}/campaigns`),
      opsApi(`/api/companies/${encodeURIComponent(companyId)}/contacts`),
      opsApi(`/api/companies/${encodeURIComponent(companyId)}/media`),
      opsApi(`/api/companies/${encodeURIComponent(companyId)}`),
    ]);
    campaignState.rows=rows||[];campaignState.contacts=contacts||[];campaignState.media=media||[];campaignState.publications=detail?.publications||[];campaignState.loaded=true;
    if(campaignState.selectedId&&!campaignState.rows.some(row=>row.id===campaignState.selectedId))campaignState.selectedId=null;
  }catch(err){opsToast(err.message)}finally{campaignState.loading=false}
}

function campaignReadinessNode(row){
  const grid=opsEl('div','campaign-readiness');
  for(const channel of row.channels||[]){const info=row.readiness?.[channel]||{},card=opsEl('div','campaign-readiness-card');card.append(opsEl('strong','',CAMPAIGN_CHANNEL_LABELS[channel]||channel));if(info.planned_only){card.append(opsEl('span','','Planificado · provider todavía no habilitado'));if(Number.isFinite(Number(info.audience_reachable)))card.append(opsEl('span','',`${info.audience_reachable} contactos alcanzables por dato CRM`))}else card.append(opsEl('span','',info.provider_configured?`Cuenta configurada${info.label?` · ${info.label}`:''}`:'Cuenta no configurada'));grid.append(card)}
  if(!(row.channels||[]).length)grid.append(opsEl('div','campaign-warning','Selecciona al menos un canal para convertir el plan en una campaña operativa.'));
  return grid;
}

function campaignCard(row){
  const card=opsEl('article',`campaign-card ${row.id===campaignState.selectedId?'active':''}`),head=opsEl('div','campaign-card-head'),left=opsEl('div','');left.append(opsEl('strong','',row.name),opsEl('p','muted',campaignLabelObjective(row.objective)));head.append(left,opsEl('span','status',campaignLabelStatus(row.status)));card.append(head);
  const tags=opsEl('div','campaign-tags');(row.channels||[]).forEach(channel=>tags.append(opsEl('span','campaign-chip',CAMPAIGN_CHANNEL_LABELS[channel]||channel)));card.append(tags);
  const counts=opsEl('div','campaign-counts');counts.append(opsEl('span','campaign-count',`${(row.audience_contact_ids||[]).length} contactos`),opsEl('span','campaign-count',`${(row.media_ids||[]).length} piezas`),opsEl('span','campaign-count',`${(row.publication_ids||[]).length} publicaciones`));card.append(counts);if(row.start_at||row.end_at)card.append(opsEl('span','campaign-count',`${row.start_at?opsDate(row.start_at):'Sin inicio'} → ${row.end_at?opsDate(row.end_at):'Sin cierre'}`));card.addEventListener('click',()=>{campaignState.selectedId=row.id;campaignRenderCurrent()});return card
}

function campaignOptions(select,rows,labeler,selectedIds){
  const selected=new Set(selectedIds||[]);select.replaceChildren();rows.forEach(row=>{const option=opsEl('option','',labeler(row));option.value=row.id;option.selected=selected.has(row.id);select.append(option)})
}

function campaignForm(root,row){
  const company=campaignCompany(),section=opsEl('section','marketing-ops-section');const head=opsEl('div','marketing-ops-section-head'),copy=opsEl('div','');copy.append(opsEl('p','eyebrow',row?'EDITAR CAMPAÑA':'NUEVA CAMPAÑA'),opsEl('h3','',row?row.name:'Plan de campaña'));head.append(copy);if(row){const fresh=opsEl('button','','+ Nueva');fresh.type='button';fresh.addEventListener('click',()=>{campaignState.selectedId=null;campaignRenderCurrent()});head.append(fresh)}section.append(head);
  const form=opsEl('form','campaign-form');
  const first=opsEl('div','two');const nameLabel=opsEl('label','','Nombre');const name=document.createElement('input');name.required=true;name.maxLength=180;name.value=row?.name||'';name.placeholder='Ej. Lanzamiento Wondergreen Q4';nameLabel.append(name);const objectiveLabel=opsEl('label','','Objetivo');const objective=document.createElement('select');Object.entries(CAMPAIGN_OBJECTIVE_LABELS).forEach(([value,label])=>{const option=opsEl('option','',label);option.value=value;option.selected=(row?.objective||'LEADS')===value;objective.append(option)});objectiveLabel.append(objective);first.append(nameLabel,objectiveLabel);form.append(first);
  const second=opsEl('div','two');const startLabel=opsEl('label','','Inicio');const start=document.createElement('input');start.type='datetime-local';start.value=campaignDateInput(row?.start_at);startLabel.append(start);const endLabel=opsEl('label','','Cierre');const end=document.createElement('input');end.type='datetime-local';end.value=campaignDateInput(row?.end_at);endLabel.append(end);second.append(startLabel,endLabel);form.append(second);
  const statusLabel=opsEl('label','','Estado de trabajo');const status=document.createElement('select');Object.entries(CAMPAIGN_STATUS_LABELS).forEach(([value,label])=>{const option=opsEl('option','',label);option.value=value;option.selected=(row?.status||'PLANNING')===value;status.append(option)});statusLabel.append(status);form.append(statusLabel);
  const channelsWrap=opsEl('div','');channelsWrap.append(opsEl('span','muted','Canales'));const checks=opsEl('div','campaign-checks');const channelInputs={};for(const [value,label] of Object.entries(CAMPAIGN_CHANNEL_LABELS)){const wrap=opsEl('label','campaign-check');const input=document.createElement('input');input.type='checkbox';input.checked=(row?.channels||[]).includes(value);channelInputs[value]=input;wrap.append(input,document.createTextNode(label));checks.append(wrap)}channelsWrap.append(checks);form.append(channelsWrap);
  const audienceLabel=opsEl('label','','Audiencia CRM');const audience=document.createElement('select');audience.multiple=true;audience.className='campaign-multiselect';campaignOptions(audience,campaignState.contacts,item=>`${item.name}${item.organization?` · ${item.organization}`:''}${item.email?' · email':''}${item.whatsapp||item.phone?' · WhatsApp':''}`,row?.audience_contact_ids);audienceLabel.append(audience);form.append(audienceLabel);
  const mediaLabel=opsEl('label','','Piezas de biblioteca');const media=document.createElement('select');media.multiple=true;media.className='campaign-multiselect';campaignOptions(media,campaignState.media,item=>`${item.original_name} · ${item.kind}`,row?.media_ids);mediaLabel.append(media);form.append(mediaLabel);
  const publicationsLabel=opsEl('label','','Publicaciones vinculadas');const publications=document.createElement('select');publications.multiple=true;publications.className='campaign-multiselect';campaignOptions(publications,campaignState.publications,item=>`${opsStatusLabel(item.status)} · ${CAMPAIGN_CHANNEL_LABELS[item.channel]||item.channel} · ${(item.message||'(sin copy)').slice(0,80)}`,row?.publication_ids);publicationsLabel.append(publications);form.append(publicationsLabel);
  const notesLabel=opsEl('label','','Notas / hipótesis');const notes=document.createElement('textarea');notes.maxLength=10000;notes.value=row?.notes||'';notes.placeholder='Oferta, audiencia, CTA, criterios de éxito, pendientes…';notesLabel.append(notes);form.append(notesLabel);
  if(row)form.append(campaignReadinessNode(row));form.append(opsEl('div','campaign-warning','Cambiar una campaña a “En curso” sólo organiza el trabajo. No envía email, WhatsApp, publicaciones ni activa pauta automáticamente.'));
  const actions=opsEl('div','campaign-actions'),save=opsEl('button','primary',row?'Guardar cambios':'Crear campaña');save.type='submit';actions.append(save);form.append(actions);
  form.addEventListener('submit',async event=>{event.preventDefault();const payload={name:name.value.trim(),objective:objective.value,status:status.value,start_at:start.value?new Date(start.value).toISOString():null,end_at:end.value?new Date(end.value).toISOString():null,channels:Object.entries(channelInputs).filter(([_key,input])=>input.checked).map(([key])=>key),audience_contact_ids:campaignSelectedValues(audience),media_ids:campaignSelectedValues(media),publication_ids:campaignSelectedValues(publications),notes:notes.value.trim()||null};save.disabled=true;try{let saved;if(row)saved=await opsApi(`/api/companies/${encodeURIComponent(company.id)}/campaigns/${encodeURIComponent(row.id)}`,{method:'PATCH',body:payload});else saved=await opsApi(`/api/companies/${encodeURIComponent(company.id)}/campaigns`,{method:'POST',body:payload});campaignState.selectedId=saved.id;opsToast(row?'Campaña actualizada':'Campaña creada');await Promise.all([campaignRefresh(true),refreshMarketingOps(true)]);campaignRenderCurrent()}catch(err){opsToast(err.message)}finally{save.disabled=false}});section.append(form);root.append(section)
}

function campaignRenderCurrent(){
  if(marketingOpsState.view!=='campaigns')return;campaignEnsureNav();campaignEnsureStyles();const root=document.querySelector('#marketing-ops-view');if(!root)return;root.replaceChildren();document.querySelector('#marketing-ops-eyebrow').textContent='CAMPAÑAS';document.querySelector('#marketing-ops-title').textContent='Centro de campañas';document.querySelector('#marketing-ops-subtitle').textContent='Une audiencia, contenido, calendario y canales sin automatizar envíos por debajo.';document.querySelectorAll('[data-ops-view]').forEach(button=>button.classList.toggle('active',button.dataset.opsView==='campaigns'));
  const company=campaignCompany();if(!company){root.append(opsEmpty('Selecciona una empresa para administrar sus campañas.'));return}
  if(!campaignState.loaded||campaignState.companyId!==company.id){root.append(opsEmpty('Cargando campañas…'));campaignRefresh(true).then(campaignRenderCurrent);return}
  const summary=opsEl('div','marketing-ops-grid'),data=marketingOpsState.dashboard?.campaigns||{};summary.append(opsMetric('CAMPAÑAS',data.total||0,'planes de esta empresa'),opsMetric('LISTAS',data.ready||0,'listas para coordinar'),opsMetric('EN CURSO',data.in_progress||0,'trabajo operativo'),opsMetric('COMPLETADAS',data.completed||0,'histórico cerrado'));root.append(summary);
  const layout=opsEl('div','campaign-layout'),left=opsEl('section','marketing-ops-section');const leftHead=opsEl('div','marketing-ops-section-head'),leftCopy=opsEl('div','');leftCopy.append(opsEl('p','eyebrow','PORTAFOLIO'),opsEl('h3','','Campañas de '+company.name));leftHead.append(leftCopy);const add=opsEl('button','','+ Nueva');add.type='button';add.addEventListener('click',()=>{campaignState.selectedId=null;campaignRenderCurrent()});leftHead.append(add);left.append(leftHead);const list=opsEl('div','campaign-list');campaignState.rows.forEach(row=>list.append(campaignCard(row)));if(!campaignState.rows.length)list.append(opsEl('div','campaign-empty','Crea la primera campaña para conectar CRM, piezas y publicaciones en un solo plan.'));left.append(list);layout.append(left);
  const right=opsEl('div','');const selected=campaignState.rows.find(row=>row.id===campaignState.selectedId)||null;campaignForm(right,selected);layout.append(right);root.append(layout)
}

const campaignBaseRender=globalThis.renderMarketingOps;
globalThis.renderMarketingOps=function(){campaignEnsureNav();if(marketingOpsState.view==='campaigns'){campaignRenderCurrent();return}campaignBaseRender()};

const campaignBaseHome=globalThis.renderOpsHome;
globalThis.renderOpsHome=function(root){campaignBaseHome(root);const data=marketingOpsState.dashboard?.campaigns||{};const section=opsEl('section','marketing-ops-section');const head=opsEl('div','marketing-ops-section-head'),copy=opsEl('div','');copy.append(opsEl('p','eyebrow','CAMPAÑAS'),opsEl('h3','','Orquestación comercial'),opsEl('p','muted','Conecta CRM, contenido y publicaciones antes de sumar nuevos providers.'));const open=opsEl('button','','Abrir campañas');open.type='button';open.addEventListener('click',()=>opsShowView('campaigns'));head.append(copy,open);section.append(head);const grid=opsEl('div','marketing-ops-grid');grid.append(opsMetric('TOTAL',data.total||0,'campañas'),opsMetric('LISTAS',data.ready||0,'preparadas'),opsMetric('EN CURSO',data.in_progress||0,'coordinándose'),opsMetric('COMPLETADAS',data.completed||0,'cerradas'));section.append(grid);root.append(section)};

campaignEnsureStyles();
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',campaignEnsureNav,{once:true});else campaignEnsureNav();
