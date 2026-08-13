const socialState={status:null,pages:[],adAccounts:[],projectId:null,refreshTimer:null,busy:false};

function socialOption(value,label){const option=el('option','',label);option.value=value;return option}
function socialJsonDate(value){if(!value)return null;const date=new Date(value);if(Number.isNaN(date.getTime()))throw new Error('Fecha u hora inválida');return date.toISOString()}
function socialProjectId(){return state.current?.project?.id||null}
function socialEligibleReels(){return (state.current?.renders||[]).filter(row=>row.status==='PASS'&&Number(row.width)*16===Number(row.height)*9&&Number(row.width)>=540&&Number(row.height)>=960&&(Number(row.end)-Number(row.start))>=4&&(Number(row.end)-Number(row.start))<=60)}
function paidMediaRows(){return state.current?.paid_media||[]}

function ensureSocialWorkspace(){
  let panel=$('#social-distribution');if(panel)return panel;
  const projectView=$('#project-view');if(!projectView)return null;
  panel=document.createElement('section');panel.id='social-distribution';panel.className='panel';
  panel.innerHTML=`
    <div class="section-head">
      <div><p class="eyebrow">DISTRIBUCIÓN</p><h3>Meta, publicaciones y pauta</h3></div>
      <div class="toolbar"><span id="meta-status-badge" class="badge">Meta · revisando</span><button id="meta-refresh" type="button">Actualizar conexión</button></div>
    </div>
    <p class="muted">Publica, programa y prepara pauta desde el mismo proyecto. Las credenciales de Meta no se guardan dentro del proyecto y el token nunca se devuelve al navegador.</p>
    <div class="grid-two">
      <div class="composer-card">
        <div class="composer-head"><div><p class="eyebrow">PUBLICACIÓN</p><h4>Preparar contenido</h4></div><span id="social-scheduler-chip" class="count-chip">AUTO</span></div>
        <form id="social-publication-form" class="stack composer-form">
          <div class="mini-grid">
            <label>Canal<select id="social-channel"><option value="facebook_page">Facebook Page</option><option value="instagram">Instagram</option></select></label>
            <label>Cuenta<select id="social-target"><option value="">Conecta Meta para cargar cuentas</option></select></label>
          </div>
          <div class="mini-grid">
            <label>Formato<select id="social-kind"><option value="text">Texto</option><option value="link">Enlace</option><option value="image">Imagen</option></select></label>
            <label>Programar<input id="social-scheduled-for" type="datetime-local"></label>
          </div>
          <label>Copy / caption<textarea id="social-message" rows="5" placeholder="Texto de la publicación"></textarea></label>
          <label id="social-link-wrap">Enlace<input id="social-link-url" type="url" placeholder="https://..."></label>
          <label id="social-render-wrap" class="hidden">Render local 9:16<select id="social-render-id"><option value="">Genera primero un render vertical PASS de 4–60 s</option></select></label>
          <p id="social-render-note" class="microcopy hidden">Facebook Reel se sube directamente desde el MP4 administrado del proyecto: sin CDN, sin copiar el archivo y verificando SHA-256 antes de enviarlo.</p>
          <label id="social-media-wrap">URL pública del medio<input id="social-media-url" type="url" placeholder="https://cdn.../imagen-o-reel"></label>
          <p id="social-media-note" class="microcopy">Instagram y las imágenes por URL requieren que Meta pueda descargar el medio desde Internet. Instagram local seguirá bloqueado hasta certificar su upload binario.</p>
          <div class="toolbar composer-toolbar"><button id="social-save" class="secondary" type="submit">Guardar / programar</button><button id="social-publish-now" class="primary" type="button">Publicar ahora</button></div>
        </form>
      </div>
      <div class="composer-card">
        <div class="composer-head"><div><p class="eyebrow">CONEXIÓN META</p><h4>Cuenta y activos</h4></div><span id="meta-api-version" class="count-chip">—</span></div>
        <div id="meta-connection-copy" class="muted">Comprobando configuración…</div>
        <form id="meta-connect-form" class="stack composer-form hidden" autocomplete="off">
          <label>Access token<input id="meta-token-input" type="password" autocomplete="off" spellcheck="false" placeholder="Pega el token una sola vez"></label>
          <p class="microcopy">Se valida contra Meta antes de guardarlo. En la app Mac se conserva mediante Keychain; no se escribe en JSON ni en el proyecto.</p>
          <button id="meta-connect-button" class="primary" type="submit">Conectar Meta</button>
        </form>
        <div id="meta-connected-actions" class="toolbar hidden"><button id="meta-disconnect" type="button">Desconectar Meta</button></div>
        <div id="meta-assets" class="composer-list"></div>
        <p id="meta-connection-help" class="microcopy">Para publicar necesitas una cuenta con permisos sobre la Página/Instagram y, para pauta, acceso a la cuenta publicitaria.</p>
      </div>
    </div>
    <div class="grid-two">
      <div class="composer-card">
        <div class="composer-head"><div><p class="eyebrow">CALENDARIO / COLA</p><h4>Publicaciones del proyecto</h4></div><span id="social-publication-count" class="count-chip">0</span></div>
        <div id="social-publication-list" class="results"><p class="muted">Sin publicaciones.</p></div>
      </div>
      <div class="composer-card paid-media-card">
        <div class="composer-head"><div><p class="eyebrow">PAUTA META</p><h4>Campaña + Ad Set + Creative + Ad</h4></div><span class="count-chip">PAUSED</span></div>
        <p class="muted">Prepara toda la estructura sin activarla. Los IDs confirmados se guardan para poder reanudar si Meta falla a mitad del proceso.</p>
        <form id="meta-campaign-form" class="stack composer-form">
          <label>Cuenta publicitaria<select id="meta-ad-account"><option value="">Conecta Meta para cargar cuentas</option></select></label>
          <div class="mini-grid"><label>Campaña<input id="meta-campaign-name" required placeholder="Campaña agosto"></label><label>Ad Set<input id="meta-adset-name" required placeholder="Colombia 21–55"></label></div>
          <div class="mini-grid"><label>Creative<input id="meta-creative-name" required placeholder="Creative A"></label><label>Ad<input id="meta-ad-name" required placeholder="Anuncio A"></label></div>
          <div class="mini-grid">
            <label>Objetivo<select id="meta-campaign-objective"><option value="OUTCOME_AWARENESS">Awareness</option><option value="OUTCOME_TRAFFIC">Traffic</option><option value="OUTCOME_ENGAGEMENT">Engagement</option><option value="OUTCOME_LEADS">Leads</option><option value="OUTCOME_APP_PROMOTION">App promotion</option><option value="OUTCOME_SALES">Sales</option></select></label>
            <label>Optimización<select id="meta-optimization-goal"><option value="LINK_CLICKS">Link clicks</option><option value="LANDING_PAGE_VIEWS">Landing page views</option><option value="IMPRESSIONS">Impressions</option><option value="REACH">Reach</option></select></label>
          </div>
          <div class="mini-grid"><label>Presupuesto diario<input id="meta-daily-budget" type="number" min="1" step="1" value="10000" required></label><label>Categoría especial<select id="meta-special-category"><option value="">Ninguna</option><option value="CREDIT">Crédito</option><option value="EMPLOYMENT">Empleo</option><option value="HOUSING">Vivienda</option><option value="ISSUES_ELECTIONS_POLITICS">Temas sociales, elecciones o política</option></select></label></div>
          <p class="microcopy">El presupuesto se envía en la unidad monetaria que Meta espera para esa cuenta. Aquí se guarda como intención; nada queda activo.</p>
          <div class="mini-grid"><label>Países<input id="meta-target-countries" value="CO" placeholder="CO,US"></label><label>Edad mínima<input id="meta-age-min" type="number" min="18" max="65" value="21"></label></div>
          <div class="mini-grid"><label>Edad máxima<input id="meta-age-max" type="number" min="18" max="65" value="55"></label><label>Página<select id="meta-paid-page"><option value="">Selecciona Página</option></select></label></div>
          <label>Copy<textarea id="meta-ad-message" rows="3" required placeholder="Texto del anuncio"></textarea></label>
          <label>URL destino<input id="meta-ad-link" type="url" required placeholder="https://..."></label>
          <label>Imagen pública<input id="meta-ad-picture" type="url" required placeholder="https://cdn.../creative.jpg"></label>
          <label>CTA<select id="meta-ad-cta"><option value="LEARN_MORE">Más información</option><option value="SHOP_NOW">Comprar</option><option value="SIGN_UP">Registrarse</option><option value="CONTACT_US">Contactar</option><option value="GET_OFFER">Ver oferta</option><option value="APPLY_NOW">Aplicar</option></select></label>
          <div class="toolbar composer-toolbar"><button id="meta-save-draft" class="secondary" type="submit">Guardar borrador</button><button id="meta-create-campaign" class="primary" type="submit" data-remote="1">Crear campaña pausada completa</button></div>
          <p class="microcopy">No activa pauta ni genera gasto. No existe activación desde este gate. Campaign, Ad Set y Ad se crean en PAUSED.</p>
        </form>
        <div id="meta-campaign-result" class="results"></div>
      </div>
    </div>
    <section class="composer-card paid-media-list-card">
      <div class="composer-head"><div><p class="eyebrow">PAUTA DEL PROYECTO</p><h4>Borradores y estructuras remotas</h4></div><span id="paid-media-count" class="count-chip">0</span></div>
      <div id="paid-media-list" class="results"><p class="muted">Sin borradores de pauta.</p></div>
    </section>`;
  const grids=[...projectView.querySelectorAll(':scope > .grid-two')];
  const before=grids[grids.length-1]||null;
  projectView.insertBefore(panel,before);
  bindSocialWorkspace();
  return panel;
}

function setSocialKinds(){
  const channel=$('#social-channel'),kind=$('#social-kind');if(!channel||!kind)return;
  const previous=kind.value;kind.replaceChildren();
  const rows=channel.value==='instagram'?[['image','Imagen'],['reel','Reel']]:[['text','Texto'],['link','Enlace'],['image','Imagen'],['reel','Reel local']];
  rows.forEach(([value,label])=>kind.append(socialOption(value,label)));
  if(rows.some(([value])=>value===previous))kind.value=previous;
  renderSocialFieldVisibility();fillSocialTargets();
}
function fillSocialRenders(){
  const select=$('#social-render-id');if(!select)return;const previous=select.value;select.replaceChildren();const rows=socialEligibleReels();
  if(!rows.length){select.append(socialOption('','Genera primero un render vertical PASS de 4–60 s'));select.disabled=true;return}
  select.disabled=false;for(const row of rows){const duration=(Number(row.end)-Number(row.start)).toFixed(1);select.append(socialOption(row.id,`${row.output_name||row.id} · ${row.width}×${row.height} · ${duration}s`))}if(rows.some(row=>row.id===previous))select.value=previous;
}
function renderSocialFieldVisibility(){
  const channel=$('#social-channel')?.value,kind=$('#social-kind')?.value;if(!channel||!kind)return;
  const localFacebookReel=channel==='facebook_page'&&kind==='reel';
  const needsMediaUrl=kind==='image'||(channel==='instagram'&&kind==='reel');
  $('#social-link-wrap').classList.toggle('hidden',kind!=='link');
  $('#social-render-wrap').classList.toggle('hidden',!localFacebookReel);$('#social-render-note').classList.toggle('hidden',!localFacebookReel);
  $('#social-media-wrap').classList.toggle('hidden',!needsMediaUrl);$('#social-media-note').classList.toggle('hidden',!needsMediaUrl);
  if(localFacebookReel)fillSocialRenders();
}
function fillSocialTargets(){
  const select=$('#social-target');if(!select)return;const previous=select.value;select.replaceChildren();const channel=$('#social-channel')?.value||'facebook_page';const rows=[];
  for(const page of socialState.pages){if(channel==='facebook_page')rows.push({id:page.id,name:page.name||page.id});if(channel==='instagram'&&page.instagram)rows.push({id:page.instagram.id,name:`@${page.instagram.username||page.instagram.id} · ${page.name||'Meta'}`})}
  if(!rows.length){select.append(socialOption('',socialState.status?.configured?'No hay activos compatibles':'Conecta Meta para cargar cuentas'));select.disabled=true;return}
  select.disabled=false;rows.forEach(row=>select.append(socialOption(row.id,row.name)));if(rows.some(row=>row.id===previous))select.value=previous;
}
function fillAdAccounts(){
  const select=$('#meta-ad-account');if(!select)return;const previous=select.value;select.replaceChildren();
  if(!socialState.adAccounts.length){select.append(socialOption('',socialState.status?.configured?'No hay cuentas publicitarias':'Conecta Meta para cargar cuentas'));select.disabled=true;return}
  select.disabled=false;for(const account of socialState.adAccounts){select.append(socialOption(account.id,`${account.name||account.id}${account.currency?` · ${account.currency}`:''}`))}if(socialState.adAccounts.some(row=>row.id===previous))select.value=previous;
}
function fillPaidPages(){
  const select=$('#meta-paid-page');if(!select)return;const previous=select.value;select.replaceChildren();
  if(!socialState.pages.length){select.append(socialOption('','Selecciona Página'));select.disabled=true;return}
  select.disabled=false;for(const page of socialState.pages)select.append(socialOption(page.id,`${page.name||page.id}${page.instagram?` · @${page.instagram.username||page.instagram.id}`:''}`));if(socialState.pages.some(row=>row.id===previous))select.value=previous;
}
function renderMetaAssets(){
  const root=$('#meta-assets');if(!root)return;root.replaceChildren();
  for(const page of socialState.pages){const item=el('div','result-item');const ig=page.instagram?` · Instagram @${page.instagram.username||page.instagram.id}`:' · sin Instagram vinculado';item.append(el('strong','',page.name||page.id),el('p','',`Facebook ${page.id}${ig}`));root.append(item)}
  for(const account of socialState.adAccounts){const item=el('div','result-item');item.append(el('strong','',account.name||account.id),el('p','',`Ads ${account.id}${account.currency?` · ${account.currency}`:''}${account.timezone_name?` · ${account.timezone_name}`:''}`));root.append(item)}
  if(!socialState.pages.length&&!socialState.adAccounts.length)root.append(el('p','muted',socialState.status?.configured?'Meta respondió, pero no hay activos disponibles con esta credencial.':'Conecta Meta para descubrir Páginas, Instagram y cuentas publicitarias.'));
}
function renderMetaConnectionControls(){
  const status=socialState.status,form=$('#meta-connect-form'),actions=$('#meta-connected-actions'),disconnect=$('#meta-disconnect'),help=$('#meta-connection-help');if(!status||!form||!actions)return;
  const canWrite=Boolean(status.credential_writable),source=status.credential_source||'none';
  form.classList.toggle('hidden',status.configured||!canWrite);
  const canDisconnect=status.configured&&source==='keychain';actions.classList.toggle('hidden',!canDisconnect);disconnect.disabled=!canDisconnect;
  if(status.configured&&source==='environment')help.textContent='Conexión administrada por META_ACCESS_TOKEN del entorno. Para cambiarla, retira esa variable y usa Keychain.';
  else if(status.configured&&source==='keychain')help.textContent='Token guardado en Keychain. Los proyectos sólo conservan IDs de Meta, nunca la credencial.';
  else if(canWrite)help.textContent='Pega el token una sola vez. La app lo valida y lo guarda en Keychain.';
  else help.textContent='Esta ejecución no tiene Keychain administrable. En desarrollo puedes usar META_ACCESS_TOKEN; la app Mac incluye el helper nativo.';
}
function renderMetaStatus(){
  const status=socialState.status;if(!status)return;const badge=$('#meta-status-badge'),copy=$('#meta-connection-copy'),version=$('#meta-api-version'),scheduler=$('#social-scheduler-chip');version.textContent=status.graph_version||'—';
  if(status.configured){badge.textContent='Meta · conectado';badge.classList.add('ok');copy.textContent=`${status.credential_source==='keychain'?'Keychain':'Entorno'} · ${socialState.pages.length} Página(s) · ${socialState.adAccounts.length} cuenta(s) Ads.`}else{badge.textContent='Meta · pendiente';badge.classList.remove('ok');copy.textContent='Sin conexión Meta activa. No se publicará ni se crearán objetos de pauta.'}
  scheduler.textContent=status.scheduler?.running?'AUTO ON':'AUTO OFF';renderMetaConnectionControls();fillSocialTargets();fillAdAccounts();fillPaidPages();renderMetaAssets();
}
async function refreshMetaConnection(){
  if(socialState.busy)return;socialState.busy=true;const button=$('#meta-refresh');if(button)button.disabled=true;
  try{socialState.status=await api('/api/meta/status');socialState.pages=[];socialState.adAccounts=[];if(socialState.status.configured){const results=await Promise.allSettled([api('/api/meta/pages'),api('/api/meta/ad-accounts')]);if(results[0].status==='fulfilled')socialState.pages=results[0].value;else toast(`Meta Pages: ${results[0].reason.message}`);if(results[1].status==='fulfilled')socialState.adAccounts=results[1].value;else toast(`Meta Ads: ${results[1].reason.message}`)}renderMetaStatus()}catch(err){toast(err.message)}finally{socialState.busy=false;if(button)button.disabled=false}
}
async function connectMeta(event){
  event.preventDefault();const input=$('#meta-token-input'),button=$('#meta-connect-button'),token=input.value.trim();if(!token){toast('Pega un access token de Meta');return}button.disabled=true;
  try{const result=await api('/api/meta/connection',{method:'POST',body:{access_token:token}});input.value='';socialState.status=result;toast(`Meta conectado${result.identity?.name?` · ${result.identity.name}`:''}`);await refreshMetaConnection()}catch(err){input.value='';toast(err.message)}finally{button.disabled=false}
}
async function disconnectMeta(){const button=$('#meta-disconnect');button.disabled=true;try{await api('/api/meta/connection',{method:'DELETE'});socialState.status=null;socialState.pages=[];socialState.adAccounts=[];toast('Meta desconectado');await refreshMetaConnection()}catch(err){toast(err.message)}finally{button.disabled=false}}

function renderSocialPublications(){
  const root=$('#social-publication-list');if(!root)return;const rows=[...(state.current?.publications||[])].reverse();root.replaceChildren();$('#social-publication-count').textContent=String(rows.length);
  for(const row of rows){const item=el('div','result-item');const when=row.scheduled_for?fmtTime(row.scheduled_for):'sin programación';item.append(el('strong','',`${row.status} · ${row.channel==='instagram'?'Instagram':'Facebook'} · ${row.kind}`),el('p','',row.message||'(sin copy)'),el('span','',`${row.target_name||row.target_id} · ${when} · intento ${row.attempts||0}`));if(row.render_id)item.append(el('p','muted',`Render local: ${row.render_id}`));if(row.remote_id)item.append(el('p','muted',`Meta ID: ${row.remote_id}`));if(row.error)item.append(el('p','muted',row.error));const actions=el('div','toolbar');if(row.status==='DRAFT'||row.status==='FAILED'){const publish=el('button','primary','Publicar ahora');publish.type='button';publish.addEventListener('click',()=>socialPublishNow(row.id));actions.append(publish);const queue=el('button','','Encolar ahora');queue.type='button';queue.addEventListener('click',()=>socialQueue(row.id));actions.append(queue)}if(['DRAFT','QUEUED','FAILED'].includes(row.status)){const cancel=el('button','','Cancelar');cancel.type='button';cancel.addEventListener('click',()=>socialCancel(row.id));actions.append(cancel)}item.append(actions);root.append(item)}
  if(!rows.length)root.append(el('p','muted','Todavía no hay publicaciones en este proyecto.'));
}
function renderPaidMedia(){
  const root=$('#paid-media-list');if(!root)return;const rows=[...paidMediaRows()].reverse();root.replaceChildren();$('#paid-media-count').textContent=String(rows.length);
  for(const row of rows){const item=el('div','result-item');item.append(el('strong','',`${row.status} · ${row.campaign_name}`),el('p','',`${row.campaign_objective} · presupuesto diario ${row.daily_budget} · ${row.adset_name}`),el('span','',`${row.ad_account_id} · ${row.page_id}`));const ids=[['Campaign',row.campaign_id],['AdSet',row.adset_id],['Creative',row.creative_id],['Ad',row.ad_id]].filter(([,id])=>id).map(([name,id])=>`${name}: ${id}`).join(' · ');if(ids)item.append(el('p','muted',ids));const actions=el('div','toolbar');if(row.status==='DRAFT'){const remote=el('button','primary',row.campaign_id?'Reanudar creación PAUSED':'Crear estructura PAUSED');remote.type='button';remote.addEventListener('click',()=>createPaidMediaRemote(row.id,remote));actions.append(remote);if(!row.campaign_id&&!row.adset_id&&!row.creative_id&&!row.ad_id){const cancel=el('button','','Cancelar borrador');cancel.type='button';cancel.addEventListener('click',()=>cancelPaidMedia(row.id));actions.append(cancel)}}item.append(actions);root.append(item)}
  if(!rows.length)root.append(el('p','muted','Todavía no hay borradores de pauta en este proyecto.'));
}
async function refreshSocialProject(){const projectId=socialProjectId();if(!projectId)return;try{const detail=await api(`/api/projects/${projectId}`);if(state.current?.project?.id!==projectId)return;state.current.renders=detail.renders||[];state.current.publications=detail.publications||[];state.current.paid_media=detail.paid_media||[];fillSocialRenders();renderSocialPublications();renderPaidMedia()}catch(err){toast(err.message)}}
async function createSocialPublication({publishNow=false}={}){
  const projectId=socialProjectId();if(!projectId)return;const target=$('#social-target'),channel=$('#social-channel'),kind=$('#social-kind');if(!target.value){toast('Selecciona una cuenta Meta');return}
  const localFacebookReel=channel.value==='facebook_page'&&kind.value==='reel';const renderId=localFacebookReel?$('#social-render-id').value:null;if(localFacebookReel&&!renderId){toast('Selecciona un render 9:16 PASS de 4–60 s');return}
  const scheduled=socialJsonDate($('#social-scheduled-for').value);const selected=target.options[target.selectedIndex];const payload={channel:channel.value,target_id:target.value,target_name:selected?.textContent||target.value,kind:kind.value,message:$('#social-message').value.trim(),link_url:$('#social-link-url').value.trim()||null,media_url:localFacebookReel?null:($('#social-media-url').value.trim()||null),render_id:renderId,...(!publishNow&&scheduled?{scheduled_for:scheduled}:{})};
  try{const row=await api(`/api/projects/${projectId}/publications`,{method:'POST',body:payload});if(publishNow)await api(`/api/projects/${projectId}/publications/${row.id}/publish-now`,{method:'POST',body:{}});$('#social-message').value='';$('#social-link-url').value='';$('#social-media-url').value='';if(!publishNow)$('#social-scheduled-for').value='';toast(publishNow?'Publicación enviada a Meta':scheduled?'Publicación programada':'Borrador guardado');await refreshSocialProject();if(typeof refreshTimeline==='function')refreshTimeline()}catch(err){toast(err.message)}
}
async function socialQueue(id){const projectId=socialProjectId();if(!projectId)return;try{await api(`/api/projects/${projectId}/publications/${id}/queue`,{method:'POST',body:{}});toast('Publicación en cola');await refreshSocialProject()}catch(err){toast(err.message)}}
async function socialPublishNow(id){const projectId=socialProjectId();if(!projectId)return;try{const row=await api(`/api/projects/${projectId}/publications/${id}/publish-now`,{method:'POST',body:{}});toast(row.status==='PUBLISHED'?'Publicación confirmada por Meta':`Publicación ${row.status.toLowerCase()}`);await refreshSocialProject();if(typeof refreshTimeline==='function')refreshTimeline()}catch(err){toast(err.message)}}
async function socialCancel(id){const projectId=socialProjectId();if(!projectId)return;try{await api(`/api/projects/${projectId}/publications/${id}`,{method:'DELETE'});toast('Publicación cancelada');await refreshSocialProject()}catch(err){toast(err.message)}}
function paidMediaPayload(){
  const pageId=$('#meta-paid-page').value,page=socialState.pages.find(item=>item.id===pageId),countries=$('#meta-target-countries').value.split(',').map(value=>value.trim().toUpperCase()).filter(Boolean),category=$('#meta-special-category').value;
  return {ad_account_id:$('#meta-ad-account').value,campaign_name:$('#meta-campaign-name').value.trim(),campaign_objective:$('#meta-campaign-objective').value,special_ad_categories:category?[category]:[],adset_name:$('#meta-adset-name').value.trim(),daily_budget:Number.parseInt($('#meta-daily-budget').value,10),optimization_goal:$('#meta-optimization-goal').value,targeting:{age_min:Number.parseInt($('#meta-age-min').value,10),age_max:Number.parseInt($('#meta-age-max').value,10),geo_locations:{countries}},page_id:pageId,instagram_actor_id:page?.instagram?.id||null,creative_name:$('#meta-creative-name').value.trim(),message:$('#meta-ad-message').value.trim(),link_url:$('#meta-ad-link').value.trim(),picture_url:$('#meta-ad-picture').value.trim(),call_to_action:$('#meta-ad-cta').value,ad_name:$('#meta-ad-name').value.trim()};
}
async function createMetaCampaign(event){
  event.preventDefault();const projectId=socialProjectId();if(!projectId)return;const remote=event.submitter?.dataset?.remote==='1',button=event.submitter;if(!$('#meta-ad-account').value){toast('Selecciona una cuenta publicitaria');return}if(!$('#meta-paid-page').value){toast('Selecciona una Página');return}button.disabled=true;
  try{const draft=await api(`/api/projects/${projectId}/paid-media`,{method:'POST',body:paidMediaPayload()});let result=draft;if(remote)result=await api(`/api/projects/${projectId}/paid-media/${draft.id}/create-paused`,{method:'POST',body:{}});toast(remote?'Estructura de pauta creada en PAUSED; sin gasto activo':'Borrador de pauta guardado');$('#meta-campaign-result').replaceChildren(el('p','muted',remote?`REMOTE_PAUSED · ${result.campaign_id} · ${result.adset_id} · ${result.ad_id}`:`DRAFT · ${draft.id}`));await refreshSocialProject();if(typeof refreshTimeline==='function')refreshTimeline()}catch(err){toast(err.message)}finally{button.disabled=false}
}
async function createPaidMediaRemote(id,button){button.disabled=true;const projectId=socialProjectId();try{const row=await api(`/api/projects/${projectId}/paid-media/${id}/create-paused`,{method:'POST',body:{}});toast(row.status==='REMOTE_PAUSED'?'Pauta creada completamente en PAUSED':'Pauta actualizada');await refreshSocialProject();if(typeof refreshTimeline==='function')refreshTimeline()}catch(err){toast(err.message);await refreshSocialProject()}finally{button.disabled=false}}
async function cancelPaidMedia(id){const projectId=socialProjectId();try{await api(`/api/projects/${projectId}/paid-media/${id}`,{method:'DELETE'});toast('Borrador de pauta cancelado');await refreshSocialProject()}catch(err){toast(err.message)}}
function bindSocialWorkspace(){$('#meta-refresh').addEventListener('click',refreshMetaConnection);$('#meta-connect-form').addEventListener('submit',connectMeta);$('#meta-disconnect').addEventListener('click',disconnectMeta);$('#social-channel').addEventListener('change',setSocialKinds);$('#social-kind').addEventListener('change',renderSocialFieldVisibility);$('#social-publication-form').addEventListener('submit',event=>{event.preventDefault();createSocialPublication()});$('#social-publish-now').addEventListener('click',()=>createSocialPublication({publishNow:true}));$('#meta-campaign-form').addEventListener('submit',createMetaCampaign);setSocialKinds()}
async function renderSocialWorkspace(){ensureSocialWorkspace();const projectId=socialProjectId();if(!projectId)return;if(socialState.projectId!==projectId){socialState.projectId=projectId;renderSocialPublications();renderPaidMedia();await refreshSocialProject()}else{fillSocialRenders()}if(!socialState.status)await refreshMetaConnection();else renderMetaStatus()}
function socialWatchProject(){ensureSocialWorkspace();const title=$('#active-project-name');if(title)new MutationObserver(()=>renderSocialWorkspace()).observe(title,{childList:true,characterData:true,subtree:true});clearInterval(socialState.refreshTimer);socialState.refreshTimer=setInterval(()=>{if(socialProjectId())refreshSocialProject()},15000);renderSocialWorkspace()}
window.addEventListener('beforeunload',()=>clearInterval(socialState.refreshTimer));
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',socialWatchProject,{once:true});else socialWatchProject();
globalThis.renderSocialWorkspace=renderSocialWorkspace;
