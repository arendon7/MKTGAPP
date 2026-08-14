const marketingOpsState={companies:[],selectedCompanyId:null,view:'home',dashboard:null,calendar:[],timer:null,metaPages:[],metaAdAccounts:[]};

function opsEl(tag,className,text){const node=document.createElement(tag);if(className)node.className=className;if(text!==undefined)node.textContent=String(text);return node}
function opsToast(message){if(typeof toast==='function')toast(message);else console.log(message)}
function opsApi(path,options){if(typeof api!=='function')return Promise.reject(new Error('API local no disponible'));return api(path,options)}
function opsDate(value){if(!value)return 'Sin fecha';const date=new Date(value);return Number.isNaN(date.getTime())?String(value):new Intl.DateTimeFormat('es-CO',{dateStyle:'medium',timeStyle:'short'}).format(date)}
function opsSelectedCompany(){return marketingOpsState.companies.find(row=>row.id===marketingOpsState.selectedCompanyId)||null}
function opsStatusLabel(value){return ({DRAFT:'Borrador',QUEUED:'Programada',PUBLISHING:'Publicando',PUBLISHED:'Publicada',FAILED:'Error',CANCELLED:'Cancelada'})[value]||value}

function loadMarketingOpsStyles(){if(document.querySelector('link[data-marketing-ops]'))return;const link=document.createElement('link');link.rel='stylesheet';link.href='/marketing-ops.css';link.dataset.marketingOps='1';document.head.append(link)}

function ensureMarketingOpsShell(){
  if(document.querySelector('#marketing-ops-shell'))return;
  loadMarketingOpsStyles();
  const topbar=document.querySelector('.topbar');
  const legacy=document.querySelector('main.shell');
  if(!legacy)return;
  const returnButton=opsEl('button','','Operaciones');returnButton.id='marketing-ops-return';returnButton.type='button';returnButton.classList.add('marketing-ops-hidden');returnButton.addEventListener('click',()=>opsShowView(marketingOpsState.view||'home'));
  topbar?.append(returnButton);
  const shell=opsEl('main','marketing-ops-shell');shell.id='marketing-ops-shell';
  shell.innerHTML=`<aside class="marketing-ops-rail"><div class="marketing-ops-brand"><p class="eyebrow">MERCADEO APP</p><strong>Centro de operaciones</strong><span>Redes, calendario y relaciones comerciales de tus empresas.</span></div><nav class="marketing-ops-nav" aria-label="Navegación principal"><button type="button" data-ops-view="home">Inicio</button><button type="button" data-ops-view="calendar">Calendario</button><button type="button" data-ops-view="publish">Publicar</button><button type="button" data-ops-view="crm">CRM <small>W32</small></button><button type="button" data-ops-view="companies">Empresas</button><button type="button" data-ops-view="content">Contenido</button></nav></aside><section class="marketing-ops-main"><header class="marketing-ops-top"><div><p id="marketing-ops-eyebrow" class="eyebrow">OPERACIONES</p><h2 id="marketing-ops-title">Inicio</h2><p id="marketing-ops-subtitle" class="muted">Qué necesita atención y qué viene después.</p></div><label class="marketing-ops-company-select">Empresa<select id="marketing-ops-company-filter"><option value="">Todas las empresas</option></select></label></header><div id="marketing-ops-view" class="marketing-ops-view"></div></section>`;
  legacy.insertAdjacentElement('beforebegin',shell);
  legacy.classList.add('marketing-ops-hidden');
  shell.querySelectorAll('[data-ops-view]').forEach(button=>button.addEventListener('click',()=>{const view=button.dataset.opsView;if(view==='content')opsShowLegacy();else opsShowView(view)}));
  shell.querySelector('#marketing-ops-company-filter').addEventListener('change',event=>{marketingOpsState.selectedCompanyId=event.target.value||null;try{localStorage.setItem('marketingOpsCompany',marketingOpsState.selectedCompanyId||'')}catch(_err){}refreshMarketingOps(true)});
}

function opsShowLegacy(){
  document.querySelector('#marketing-ops-shell')?.classList.add('marketing-ops-hidden');
  document.querySelector('main.shell')?.classList.remove('marketing-ops-hidden');
  document.querySelector('#marketing-ops-return')?.classList.remove('marketing-ops-hidden');
  document.querySelector('.topbar h1')?.replaceChildren(document.createTextNode('Marketing Workspace · Contenido'));
}

function opsShowView(view){
  marketingOpsState.view=view;
  document.querySelector('main.shell')?.classList.add('marketing-ops-hidden');
  document.querySelector('#marketing-ops-shell')?.classList.remove('marketing-ops-hidden');
  document.querySelector('#marketing-ops-return')?.classList.add('marketing-ops-hidden');
  document.querySelector('.topbar h1')?.replaceChildren(document.createTextNode('Marketing Workspace'));
  document.querySelectorAll('[data-ops-view]').forEach(button=>button.classList.toggle('active',button.dataset.opsView===view));
  renderMarketingOps();
}

function fillCompanyFilter(){
  const select=document.querySelector('#marketing-ops-company-filter');if(!select)return;const previous=marketingOpsState.selectedCompanyId||'';select.replaceChildren();
  const all=opsEl('option','','Todas las empresas');all.value='';select.append(all);
  marketingOpsState.companies.forEach(company=>{const option=opsEl('option','',company.name);option.value=company.id;select.append(option)});
  if(marketingOpsState.companies.some(row=>row.id===previous))select.value=previous;else{marketingOpsState.selectedCompanyId=null;select.value=''}
}

function opsMetric(title,value,copy){const card=opsEl('article','marketing-ops-card');card.append(opsEl('p','eyebrow',title),opsEl('strong','metric',value),opsEl('p','',copy));return card}
function opsEmpty(text){return opsEl('div','marketing-ops-empty',text)}

function renderOpsHome(root){
  const data=marketingOpsState.dashboard||{summary:{}};const summary=data.summary||{};
  const grid=opsEl('div','marketing-ops-grid');grid.append(opsMetric('HOY',data.scheduled_today||0,'publicaciones programadas'),opsMetric('BORRADORES',summary.draft||0,'pendientes de revisar'),opsMetric('PUBLICADAS',summary.published||0,'en el historial'),opsMetric('REQUIEREN ATENCIÓN',summary.failed||0,'publicaciones con error'));root.append(grid);
  const actions=opsEl('div','marketing-ops-actions');[['+ Programar publicación','publish'],['Ver calendario','calendar'],['Empresas y cuentas','companies'],['Abrir contenido','content']].forEach(([label,view])=>{const button=opsEl('button',view==='publish'?'primary':'',label);button.type='button';button.addEventListener('click',()=>view==='content'?opsShowLegacy():opsShowView(view));actions.append(button)});root.append(actions);
  const section=opsEl('section','marketing-ops-section');const head=opsEl('div','marketing-ops-section-head');const copy=opsEl('div','');copy.append(opsEl('p','eyebrow','PRÓXIMAS'),opsEl('h3','','Publicaciones programadas'));head.append(copy,opsEl('span','marketing-ops-badge',`${(data.upcoming||[]).length} visibles`));section.append(head);
  const list=opsEl('div','marketing-ops-list');for(const row of data.upcoming||[]){const item=opsEl('div','marketing-ops-row');const left=opsEl('div','');left.append(opsEl('strong','',row.company_name||'Empresa'),opsEl('p','',row.message||'(sin copy)'));const middle=opsEl('div','');middle.append(opsEl('span','status',opsStatusLabel(row.status)),opsEl('p','',opsDate(row.scheduled_for)));const right=opsEl('span','marketing-ops-badge',row.channel==='instagram'?'Instagram':'Facebook');item.append(left,middle,right);list.append(item)}if(!(data.upcoming||[]).length)list.append(opsEmpty(marketingOpsState.companies.length?'No hay publicaciones futuras programadas.':'Crea tu primera empresa para empezar.'));section.append(list);root.append(section);
}

function renderOpsCalendar(root){
  const section=opsEl('section','marketing-ops-section');const head=opsEl('div','marketing-ops-section-head');const copy=opsEl('div','');copy.append(opsEl('p','eyebrow','CALENDARIO EDITORIAL'),opsEl('h3','','Publicaciones'));head.append(copy);const add=opsEl('button','primary','+ Programar');add.type='button';add.addEventListener('click',()=>opsShowView('publish'));head.append(add);section.append(head);
  if(!marketingOpsState.calendar.length){section.append(opsEmpty('Todavía no hay publicaciones para este filtro.'));root.append(section);return}
  const table=opsEl('div','marketing-ops-calendar');const header=opsEl('div','marketing-ops-calendar-head');['Fecha','Empresa','Canal','Contenido','Estado'].forEach(text=>header.append(opsEl('span','',text)));table.append(header);
  [...marketingOpsState.calendar].sort((a,b)=>String(a.scheduled_for||a.created_at).localeCompare(String(b.scheduled_for||b.created_at))).forEach(row=>{const line=opsEl('div','marketing-ops-calendar-row');line.append(opsEl('span','',opsDate(row.scheduled_for||row.created_at)),opsEl('span','',row.company_name||'—'),opsEl('span','',row.channel==='instagram'?'Instagram':'Facebook'),opsEl('p','',row.message||'(sin copy)'),opsEl('span','status',opsStatusLabel(row.status)));table.append(line)});section.append(table);root.append(section);
}

function opsPublicationKindOptions(channel){return channel==='instagram'?[['image','Imagen'],['reel','Reel por URL']]:[['text','Texto'],['link','Enlace'],['image','Imagen por URL']]}
function renderOpsPublish(root){
  const company=opsSelectedCompany();const section=opsEl('section','marketing-ops-section');const head=opsEl('div','marketing-ops-section-head');const copy=opsEl('div','');copy.append(opsEl('p','eyebrow','PUBLICAR'),opsEl('h3','','Nueva publicación'),opsEl('p','muted',company?`Publicando como ${company.name}.`:'Selecciona una empresa arriba antes de publicar.'));head.append(copy);section.append(head);
  if(!company){section.append(opsEmpty('El publicador necesita una empresa concreta. Selecciónala en el filtro superior o créala en Empresas.'));root.append(section);return}
  const form=opsEl('form','marketing-ops-form');form.id='marketing-ops-publish-form';
  const first=opsEl('div','two');const channelLabel=opsEl('label','','Canal');const channel=document.createElement('select');channel.id='ops-publish-channel';[['facebook_page','Facebook'],['instagram','Instagram']].forEach(([value,label])=>{const option=opsEl('option','',label);option.value=value;channel.append(option)});channelLabel.append(channel);const kindLabel=opsEl('label','','Formato');const kind=document.createElement('select');kind.id='ops-publish-kind';kindLabel.append(kind);first.append(channelLabel,kindLabel);form.append(first);
  const second=opsEl('div','two');const dateLabel=opsEl('label','','Programar para');const date=document.createElement('input');date.type='datetime-local';date.id='ops-publish-date';dateLabel.append(date);const account=opsEl('div','marketing-ops-note');account.id='ops-publish-account';second.append(dateLabel,account);form.append(second);
  const messageLabel=opsEl('label','','Copy / caption');const message=document.createElement('textarea');message.id='ops-publish-message';message.placeholder='Escribe el texto de la publicación';messageLabel.append(message);form.append(messageLabel);
  const linkLabel=opsEl('label','','Enlace');linkLabel.id='ops-publish-link-wrap';const link=document.createElement('input');link.type='url';link.id='ops-publish-link';link.placeholder='https://...';linkLabel.append(link);form.append(linkLabel);
  const mediaLabel=opsEl('label','','URL pública de imagen o Reel');mediaLabel.id='ops-publish-media-wrap';const media=document.createElement('input');media.type='url';media.id='ops-publish-media';media.placeholder='https://...';mediaLabel.append(media);form.append(mediaLabel);
  const note=opsEl('div','marketing-ops-note','Para usar un video local o editar una pieza, entra a Contenido → Video Studio. El publicador principal no te obliga a pasar por el editor.');form.append(note);
  const actions=opsEl('div','marketing-ops-actions');const save=opsEl('button','','Guardar / programar');save.type='submit';const publish=opsEl('button','primary','Publicar ahora');publish.type='button';publish.addEventListener('click',()=>submitOpsPublication(true));actions.append(save,publish);form.append(actions);form.addEventListener('submit',event=>{event.preventDefault();submitOpsPublication(false)});section.append(form);root.append(section);
  function sync(){kind.replaceChildren();opsPublicationKindOptions(channel.value).forEach(([value,label])=>{const option=opsEl('option','',label);option.value=value;kind.append(option)});syncFields()}
  function syncFields(){const value=kind.value;linkLabel.classList.toggle('marketing-ops-hidden',value!=='link');mediaLabel.classList.toggle('marketing-ops-hidden',!['image','reel'].includes(value));const configured=channel.value==='instagram'?(company.instagram_username?`Instagram @${company.instagram_username}`:company.instagram_id?`Instagram ${company.instagram_id}`:'Instagram no configurado'):(company.facebook_page_name?`Facebook ${company.facebook_page_name}`:company.facebook_page_id?`Facebook ${company.facebook_page_id}`:'Facebook no configurado');account.textContent=configured}
  channel.addEventListener('change',sync);kind.addEventListener('change',syncFields);sync();
}

async function submitOpsPublication(publishNow){
  const company=opsSelectedCompany();if(!company)return;const channel=document.querySelector('#ops-publish-channel')?.value,kind=document.querySelector('#ops-publish-kind')?.value,message=document.querySelector('#ops-publish-message')?.value.trim()||'',date=document.querySelector('#ops-publish-date')?.value||'',link=document.querySelector('#ops-publish-link')?.value.trim()||'',media=document.querySelector('#ops-publish-media')?.value.trim()||'';
  const payload={channel,kind,message,link_url:kind==='link'?link:null,media_url:['image','reel'].includes(kind)?media:null};if(!publishNow&&date){const parsed=new Date(date);if(Number.isNaN(parsed.getTime())){opsToast('Fecha inválida');return}payload.scheduled_for=parsed.toISOString()}
  try{const row=await opsApi(`/api/companies/${encodeURIComponent(company.id)}/publications`,{method:'POST',body:payload});if(publishNow)await opsApi(`/api/companies/${encodeURIComponent(company.id)}/publications/${encodeURIComponent(row.id)}/publish-now`,{method:'POST',body:{}});opsToast(publishNow?'Publicación enviada a Meta':date?'Publicación programada':'Borrador guardado');await refreshMarketingOps(true);opsShowView('calendar')}catch(err){opsToast(err.message)}
}

function renderOpsCompanies(root){
  const wrap=opsEl('div','marketing-ops-company-grid');const left=opsEl('section','marketing-ops-section');const head=opsEl('div','marketing-ops-section-head');const copy=opsEl('div','');copy.append(opsEl('p','eyebrow','EMPRESAS'),opsEl('h3','','Marcas que administras'));head.append(copy);left.append(head);
  const form=opsEl('form','marketing-ops-form');const label=opsEl('label','','Nueva empresa');const input=document.createElement('input');input.required=true;input.placeholder='Ej. Greenatics';label.append(input);const button=opsEl('button','primary','Crear empresa');button.type='submit';form.append(label,button);form.addEventListener('submit',async event=>{event.preventDefault();try{const company=await opsApi('/api/companies',{method:'POST',body:{name:input.value.trim()}});marketingOpsState.selectedCompanyId=company.id;input.value='';opsToast('Empresa creada');await refreshMarketingOps(true);opsShowView('companies')}catch(err){opsToast(err.message)}});left.append(form);
  const list=opsEl('div','marketing-ops-company-list');marketingOpsState.companies.forEach(company=>{const item=opsEl('div',`marketing-ops-company-item ${company.id===marketingOpsState.selectedCompanyId?'active':''}`);item.append(opsEl('strong','',company.name),opsEl('span','',`${company.facebook_page_id?'Facebook ✓':'Facebook —'} · ${company.instagram_id?'Instagram ✓':'Instagram —'}`));item.addEventListener('click',()=>{marketingOpsState.selectedCompanyId=company.id;fillCompanyFilter();renderMarketingOps()});list.append(item)});if(!marketingOpsState.companies.length)list.append(opsEmpty('Crea la primera empresa.'));left.append(list);wrap.append(left);
  const right=opsEl('section','marketing-ops-section');renderCompanyConnection(right,opsSelectedCompany());wrap.append(right);root.append(wrap);
}

function renderCompanyConnection(root,company){
  const head=opsEl('div','marketing-ops-section-head');const copy=opsEl('div','');copy.append(opsEl('p','eyebrow','CUENTAS SOCIALES'),opsEl('h3','',company?company.name:'Selecciona una empresa'));head.append(copy);root.append(head);if(!company){root.append(opsEmpty('Selecciona una empresa para asociar sus cuentas Meta.'));return}
  const form=opsEl('form','marketing-ops-form');const pageLabel=opsEl('label','','Página de Facebook');const page=document.createElement('select');page.append(opsEl('option','','Sin asociar'));page.firstChild.value='';marketingOpsState.metaPages.forEach(row=>{const option=opsEl('option','',row.name||row.id);option.value=row.id;if(row.id===company.facebook_page_id)option.selected=true;page.append(option)});pageLabel.append(page);const adLabel=opsEl('label','','Cuenta publicitaria');const ad=document.createElement('select');ad.append(opsEl('option','','Sin asociar'));ad.firstChild.value='';marketingOpsState.metaAdAccounts.forEach(row=>{const option=opsEl('option','',row.name||row.id);option.value=row.id;if(row.id===company.ad_account_id)option.selected=true;ad.append(option)});adLabel.append(ad);form.append(pageLabel,adLabel);
  const info=opsEl('div','marketing-ops-note',marketingOpsState.metaPages.length?'La cuenta de Instagram vinculada a la Página se asociará automáticamente cuando exista.':'Conecta Meta en Contenido/Distribución para descubrir Páginas e Instagram.');form.append(info);const save=opsEl('button','primary','Guardar cuentas');save.type='submit';form.append(save);form.addEventListener('submit',async event=>{event.preventDefault();const selectedPage=marketingOpsState.metaPages.find(row=>row.id===page.value),selectedAd=marketingOpsState.metaAdAccounts.find(row=>row.id===ad.value);const payload={facebook_page_id:selectedPage?.id||null,facebook_page_name:selectedPage?.name||null,instagram_id:selectedPage?.instagram?.id||null,instagram_username:selectedPage?.instagram?.username||null,ad_account_id:selectedAd?.id||null,ad_account_name:selectedAd?.name||null};try{await opsApi(`/api/companies/${encodeURIComponent(company.id)}`,{method:'PATCH',body:payload});opsToast('Cuentas de la empresa actualizadas');await refreshMarketingOps(true);opsShowView('companies')}catch(err){opsToast(err.message)}});root.append(form);
}

function renderOpsCrm(root){const section=opsEl('section','marketing-ops-section');section.append(opsEl('p','eyebrow','CRM · SIGUIENTE BLOQUE'),opsEl('h3','','Contactos, oportunidades y seguimientos'),opsEl('p','muted','La navegación ya reserva el CRM como núcleo operativo. Wave 32 añadirá contactos, pipeline y próxima gestión sin mezclarlo con proyectos de contenido.'));section.append(opsEmpty('Todavía no se ha creado información CRM en esta rama.'));root.append(section)}

function renderMarketingOps(){
  const root=document.querySelector('#marketing-ops-view');if(!root)return;root.replaceChildren();const titles={home:['INICIO','Centro de operaciones','Qué necesita atención y qué viene después.'],calendar:['CALENDARIO','Calendario editorial','Todo lo programado, publicado o con error.'],publish:['PUBLICAR','Nueva publicación','Publica sin tener que crear primero un proyecto de video.'],crm:['CRM','Relaciones comerciales','Contactos, oportunidades y seguimientos.'],companies:['EMPRESAS','Empresas y cuentas','Cada marca conserva sus propias redes y operación.']};const [eyebrow,title,subtitle]=titles[marketingOpsState.view]||titles.home;document.querySelector('#marketing-ops-eyebrow').textContent=eyebrow;document.querySelector('#marketing-ops-title').textContent=title;document.querySelector('#marketing-ops-subtitle').textContent=subtitle;
  if(marketingOpsState.view==='calendar')renderOpsCalendar(root);else if(marketingOpsState.view==='publish')renderOpsPublish(root);else if(marketingOpsState.view==='companies')renderOpsCompanies(root);else if(marketingOpsState.view==='crm')renderOpsCrm(root);else renderOpsHome(root);
}

async function refreshOpsMetaAssets(){
  marketingOpsState.metaPages=[];marketingOpsState.metaAdAccounts=[];
  try{const status=await opsApi('/api/meta/status');if(!status?.configured)return;const results=await Promise.allSettled([opsApi('/api/meta/pages'),opsApi('/api/meta/ad-accounts')]);if(results[0].status==='fulfilled')marketingOpsState.metaPages=results[0].value||[];if(results[1].status==='fulfilled')marketingOpsState.metaAdAccounts=results[1].value||[]}catch(_err){}
}

async function refreshMarketingOps(forceMeta=false){
  try{
    marketingOpsState.companies=await opsApi('/api/companies');
    if(marketingOpsState.selectedCompanyId&&!marketingOpsState.companies.some(row=>row.id===marketingOpsState.selectedCompanyId))marketingOpsState.selectedCompanyId=null;
    if(!marketingOpsState.selectedCompanyId){try{const saved=localStorage.getItem('marketingOpsCompany');if(saved&&marketingOpsState.companies.some(row=>row.id===saved))marketingOpsState.selectedCompanyId=saved}catch(_err){}}
    fillCompanyFilter();const query=marketingOpsState.selectedCompanyId?`?company_id=${encodeURIComponent(marketingOpsState.selectedCompanyId)}`:'';const [dashboard,calendar]=await Promise.all([opsApi(`/api/ops/dashboard${query}`),opsApi(`/api/ops/calendar${query}`)]);marketingOpsState.dashboard=dashboard;marketingOpsState.calendar=calendar||[];if(forceMeta||marketingOpsState.view==='companies')await refreshOpsMetaAssets();renderMarketingOps();
  }catch(err){opsToast(err.message)}
}

function marketingOpsStart(){
  ensureMarketingOpsShell();marketingOpsState.view='home';opsShowView('home');refreshMarketingOps(true);clearInterval(marketingOpsState.timer);marketingOpsState.timer=setInterval(()=>{if(!document.querySelector('#marketing-ops-shell')?.classList.contains('marketing-ops-hidden'))refreshMarketingOps(false)},30000);
}
window.addEventListener('beforeunload',()=>clearInterval(marketingOpsState.timer));
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',marketingOpsStart,{once:true});else marketingOpsStart();
globalThis.refreshMarketingOps=refreshMarketingOps;
