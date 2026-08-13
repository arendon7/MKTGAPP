const socialState={status:null,pages:[],adAccounts:[],projectId:null,refreshTimer:null,busy:false};

function socialOption(value,label){const option=el('option','',label);option.value=value;return option}
function socialJsonDate(value){if(!value)return null;const date=new Date(value);if(Number.isNaN(date.getTime()))throw new Error('Fecha u hora inválida');return date.toISOString()}
function socialProjectId(){return state.current?.project?.id||null}
function socialEligibleReels(){return (state.current?.renders||[]).filter(row=>row.status==='PASS'&&Number(row.width)*16===Number(row.height)*9&&Number(row.width)>=540&&Number(row.height)>=960&&(Number(row.end)-Number(row.start))>=4&&(Number(row.end)-Number(row.start))<=60)}

function ensureSocialWorkspace(){
  let panel=$('#social-distribution');if(panel)return panel;
  const projectView=$('#project-view');if(!projectView)return null;
  panel=document.createElement('section');panel.id='social-distribution';panel.className='panel';
  panel.innerHTML=`
    <div class="section-head">
      <div><p class="eyebrow">DISTRIBUCIÓN</p><h3>Meta, publicaciones y pauta</h3></div>
      <div class="toolbar"><span id="meta-status-badge" class="badge">Meta · revisando</span><button id="meta-refresh" type="button">Actualizar conexión</button></div>
    </div>
    <p class="muted">Crea, programa y audita publicaciones desde el mismo proyecto. Las credenciales de Meta no se guardan dentro del proyecto.</p>
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
          <p id="social-render-note" class="microcopy hidden">Facebook Reel se sube directamente desde el MP4 administrado del proyecto: sin CDN, sin copiar el archivo y verificando el registro del render antes de enviarlo.</p>
          <label id="social-media-wrap">URL pública del medio<input id="social-media-url" type="url" placeholder="https://cdn.../imagen-o-reel"></label>
          <p id="social-media-note" class="microcopy">Instagram y las imágenes por URL requieren que Meta pueda descargar el medio desde Internet. Instagram local seguirá bloqueado hasta certificar su upload binario.</p>
          <div class="toolbar composer-toolbar"><button id="social-save" class="secondary" type="submit">Guardar / programar</button><button id="social-publish-now" class="primary" type="button">Publicar ahora</button></div>
        </form>
      </div>
      <div class="composer-card">
        <div class="composer-head"><div><p class="eyebrow">CONEXIÓN META</p><h4>Activos disponibles</h4></div><span id="meta-api-version" class="count-chip">—</span></div>
        <div id="meta-connection-copy" class="muted">Comprobando configuración…</div>
        <div id="meta-assets" class="composer-list"></div>
        <p class="microcopy">La conexión actual usa una credencial de Meta mantenida fuera de los proyectos. El flujo OAuth visual será el siguiente endurecimiento de conexión.</p>
      </div>
    </div>
    <div class="grid-two">
      <div class="composer-card">
        <div class="composer-head"><div><p class="eyebrow">CALENDARIO / COLA</p><h4>Publicaciones del proyecto</h4></div><span id="social-publication-count" class="count-chip">0</span></div>
        <div id="social-publication-list" class="results"><p class="muted">Sin publicaciones.</p></div>
      </div>
      <div class="composer-card">
        <div class="composer-head"><div><p class="eyebrow">PAUTA META</p><h4>Nueva campaña controlada</h4></div><span class="count-chip">PAUSED</span></div>
        <form id="meta-campaign-form" class="stack composer-form">
          <label>Cuenta publicitaria<select id="meta-ad-account"><option value="">Conecta Meta para cargar cuentas</option></select></label>
          <label>Nombre<input id="meta-campaign-name" required placeholder="Campaña agosto"></label>
          <label>Objetivo<select id="meta-campaign-objective"><option value="OUTCOME_AWARENESS">Awareness</option><option value="OUTCOME_TRAFFIC">Traffic</option><option value="OUTCOME_ENGAGEMENT">Engagement</option><option value="OUTCOME_LEADS">Leads</option><option value="OUTCOME_APP_PROMOTION">App promotion</option><option value="OUTCOME_SALES">Sales</option></select></label>
          <label>Categoría especial<select id="meta-special-category"><option value="">Ninguna</option><option value="CREDIT">Crédito</option><option value="EMPLOYMENT">Empleo</option><option value="HOUSING">Vivienda</option><option value="ISSUES_ELECTIONS_POLITICS">Temas sociales, elecciones o política</option></select></label>
          <p class="microcopy">Este gate sólo crea la campaña en estado PAUSED. No activa pauta ni genera gasto.</p>
          <button id="meta-create-campaign" class="secondary" type="submit">Crear campaña pausada</button>
        </form>
        <div id="meta-campaign-result" class="results"></div>
      </div>
    </div>`;
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
function renderMetaAssets(){
  const root=$('#meta-assets');if(!root)return;root.replaceChildren();
  for(const page of socialState.pages){const item=el('div','result-item');const ig=page.instagram?` · Instagram @${page.instagram.username||page.instagram.id}`:' · sin Instagram vinculado';item.append(el('strong','',page.name||page.id),el('p','',`Facebook ${page.id}${ig}`));root.append(item)}
  for(const account of socialState.adAccounts){const item=el('div','result-item');item.append(el('strong','',account.name||account.id),el('p','',`Ads ${account.id}${account.currency?` · ${account.currency}`:''}${account.timezone_name?` · ${account.timezone_name}`:''}`));root.append(item)}
  if(!socialState.pages.length&&!socialState.adAccounts.length)root.append(el('p','muted',socialState.status?.configured?'Meta respondió, pero no hay activos disponibles con esta credencial.':'Configura la conexión Meta para descubrir Páginas, Instagram y cuentas publicitarias.'));
}
function renderMetaStatus(){
  const status=socialState.status;if(!status)return;const badge=$('#meta-status-badge'),copy=$('#meta-connection-copy'),version=$('#meta-api-version'),scheduler=$('#social-scheduler-chip');version.textContent=status.graph_version||'—';
  if(status.configured){badge.textContent='Meta · configurado';badge.classList.add('ok');copy.textContent=`Credencial disponible fuera del proyecto · ${socialState.pages.length} Página(s) · ${socialState.adAccounts.length} cuenta(s) Ads.`}else{badge.textContent='Meta · pendiente';badge.classList.remove('ok');copy.textContent=`Falta ${status.missing?.join(', ')||'credencial Meta'}. No se publicará ni se creará pauta hasta configurarla.`}
  scheduler.textContent=status.scheduler?.running?'AUTO ON':'AUTO OFF';fillSocialTargets();fillAdAccounts();renderMetaAssets();
}
async function refreshMetaConnection(){
  if(socialState.busy)return;socialState.busy=true;const button=$('#meta-refresh');if(button)button.disabled=true;
  try{socialState.status=await api('/api/meta/status');socialState.pages=[];socialState.adAccounts=[];if(socialState.status.configured){const results=await Promise.allSettled([api('/api/meta/pages'),api('/api/meta/ad-accounts')]);if(results[0].status==='fulfilled')socialState.pages=results[0].value;else toast(`Meta Pages: ${results[0].reason.message}`);if(results[1].status==='fulfilled')socialState.adAccounts=results[1].value;else toast(`Meta Ads: ${results[1].reason.message}`)}renderMetaStatus()}catch(err){toast(err.message)}finally{socialState.busy=false;if(button)button.disabled=false}
}
function renderSocialPublications(){
  const root=$('#social-publication-list');if(!root)return;const rows=[...(state.current?.publications||[])].reverse();root.replaceChildren();$('#social-publication-count').textContent=String(rows.length);
  for(const row of rows){const item=el('div','result-item');const when=row.scheduled_for?fmtTime(row.scheduled_for):'sin programación';item.append(el('strong','',`${row.status} · ${row.channel==='instagram'?'Instagram':'Facebook'} · ${row.kind}`),el('p','',row.message||'(sin copy)'),el('span','',`${row.target_name||row.target_id} · ${when} · intento ${row.attempts||0}`));if(row.render_id)item.append(el('p','muted',`Render local: ${row.render_id}`));if(row.remote_id)item.append(el('p','muted',`Meta ID: ${row.remote_id}`));if(row.error)item.append(el('p','muted',row.error));const actions=el('div','toolbar');if(row.status==='DRAFT'||row.status==='FAILED'){const publish=el('button','primary','Publicar ahora');publish.type='button';publish.addEventListener('click',()=>socialPublishNow(row.id));actions.append(publish);const queue=el('button','','Encolar ahora');queue.type='button';queue.addEventListener('click',()=>socialQueue(row.id));actions.append(queue)}if(['DRAFT','QUEUED','FAILED'].includes(row.status)){const cancel=el('button','','Cancelar');cancel.type='button';cancel.addEventListener('click',()=>socialCancel(row.id));actions.append(cancel)}item.append(actions);root.append(item)}
  if(!rows.length)root.append(el('p','muted','Todavía no hay publicaciones en este proyecto.'));
}
async function refreshSocialProject(){const projectId=socialProjectId();if(!projectId)return;try{const detail=await api(`/api/projects/${projectId}`);if(state.current?.project?.id!==projectId)return;state.current.renders=detail.renders||[];state.current.publications=detail.publications||[];fillSocialRenders();renderSocialPublications()}catch(err){toast(err.message)}}
async function createSocialPublication({publishNow=false}={}){
  const projectId=socialProjectId();if(!projectId)return;const target=$('#social-target'),channel=$('#social-channel'),kind=$('#social-kind');if(!target.value){toast('Selecciona una cuenta Meta');return}
  const localFacebookReel=channel.value==='facebook_page'&&kind.value==='reel';const renderId=localFacebookReel?$('#social-render-id').value:null;if(localFacebookReel&&!renderId){toast('Selecciona un render 9:16 PASS de 4–60 s');return}
  const scheduled=socialJsonDate($('#social-scheduled-for').value);const selected=target.options[target.selectedIndex];const payload={channel:channel.value,target_id:target.value,target_name:selected?.textContent||target.value,kind:kind.value,message:$('#social-message').value.trim(),link_url:$('#social-link-url').value.trim()||null,media_url:localFacebookReel?null:($('#social-media-url').value.trim()||null),render_id:renderId,...(!publishNow&&scheduled?{scheduled_for:scheduled}:{})};
  try{const row=await api(`/api/projects/${projectId}/publications`,{method:'POST',body:payload});if(publishNow)await api(`/api/projects/${projectId}/publications/${row.id}/publish-now`,{method:'POST',body:{}});$('#social-message').value='';$('#social-link-url').value='';$('#social-media-url').value='';if(!publishNow)$('#social-scheduled-for').value='';toast(publishNow?'Publicación enviada a Meta':scheduled?'Publicación programada':'Borrador guardado');await refreshSocialProject();if(typeof refreshTimeline==='function')refreshTimeline()}catch(err){toast(err.message)}
}
async function socialQueue(id){const projectId=socialProjectId();if(!projectId)return;try{await api(`/api/projects/${projectId}/publications/${id}/queue`,{method:'POST',body:{}});toast('Publicación en cola');await refreshSocialProject()}catch(err){toast(err.message)}}
async function socialPublishNow(id){const projectId=socialProjectId();if(!projectId)return;try{const row=await api(`/api/projects/${projectId}/publications/${id}/publish-now`,{method:'POST',body:{}});toast(row.status==='PUBLISHED'?'Publicación confirmada por Meta':`Publicación ${row.status.toLowerCase()}`);await refreshSocialProject();if(typeof refreshTimeline==='function')refreshTimeline()}catch(err){toast(err.message)}}
async function socialCancel(id){const projectId=socialProjectId();if(!projectId)return;try{await api(`/api/projects/${projectId}/publications/${id}`,{method:'DELETE'});toast('Publicación cancelada');await refreshSocialProject()}catch(err){toast(err.message)}}
async function createMetaCampaign(event){event.preventDefault();const account=$('#meta-ad-account').value;if(!account){toast('Selecciona una cuenta publicitaria');return}const category=$('#meta-special-category').value;const button=$('#meta-create-campaign');button.disabled=true;try{const row=await api('/api/meta/campaigns',{method:'POST',body:{ad_account_id:account,name:$('#meta-campaign-name').value.trim(),objective:$('#meta-campaign-objective').value,special_ad_categories:category?[category]:[]}});const root=$('#meta-campaign-result');root.replaceChildren();const item=el('div','result-item');item.append(el('strong','',`PAUSED · ${row.name}`),el('p','',`${row.objective} · ${row.id}`));root.prepend(item);$('#meta-campaign-name').value='';toast('Campaña creada en PAUSED; no hay gasto activo');if(typeof refreshTimeline==='function')refreshTimeline()}catch(err){toast(err.message)}finally{button.disabled=false}}
function bindSocialWorkspace(){$('#meta-refresh').addEventListener('click',refreshMetaConnection);$('#social-channel').addEventListener('change',setSocialKinds);$('#social-kind').addEventListener('change',renderSocialFieldVisibility);$('#social-publication-form').addEventListener('submit',event=>{event.preventDefault();createSocialPublication()});$('#social-publish-now').addEventListener('click',()=>createSocialPublication({publishNow:true}));$('#meta-campaign-form').addEventListener('submit',createMetaCampaign);setSocialKinds()}
async function renderSocialWorkspace(){ensureSocialWorkspace();const projectId=socialProjectId();if(!projectId)return;if(socialState.projectId!==projectId){socialState.projectId=projectId;renderSocialPublications();await refreshSocialProject()}else{fillSocialRenders()}if(!socialState.status)await refreshMetaConnection();else renderMetaStatus()}
function socialWatchProject(){ensureSocialWorkspace();const title=$('#active-project-name');if(title)new MutationObserver(()=>renderSocialWorkspace()).observe(title,{childList:true,characterData:true,subtree:true});clearInterval(socialState.refreshTimer);socialState.refreshTimer=setInterval(()=>{if(socialProjectId())refreshSocialProject()},15000);renderSocialWorkspace()}
window.addEventListener('beforeunload',()=>clearInterval(socialState.refreshTimer));
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',socialWatchProject,{once:true});else socialWatchProject();
globalThis.renderSocialWorkspace=renderSocialWorkspace;
