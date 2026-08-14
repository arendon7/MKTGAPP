const companyContentState={companyId:null,media:[],loading:false,loaded:false,pickId:null};

function contentEnsureStyles(){
  if(document.querySelector('#company-content-wave34-style'))return;
  const style=document.createElement('style');style.id='company-content-wave34-style';style.textContent=`
    .company-content-actions{display:flex;gap:8px;flex-wrap:wrap;align-items:center}.company-content-upload{display:grid;grid-template-columns:minmax(220px,1fr) 150px auto;gap:8px;align-items:end}
    .company-content-grid{display:grid;grid-template-columns:repeat(3,minmax(220px,1fr));gap:10px}.company-content-card{display:grid;gap:8px;padding:10px;border:1px solid #dedbd2;border-radius:12px;background:#fff;min-width:0}.company-content-preview{aspect-ratio:9/10;background:#efede7;border-radius:9px;overflow:hidden;display:grid;place-items:center}.company-content-preview img,.company-content-preview video{width:100%;height:100%;object-fit:contain;background:#111}.company-content-meta{font-size:10px;color:#77736b;overflow-wrap:anywhere}.company-content-meta strong{display:block;color:#171717;font-size:11px}.company-content-card .company-content-actions button{font-size:10px}.company-content-pill{display:inline-flex;padding:3px 7px;border-radius:999px;background:#efede7;font-size:9px}.company-content-publish-source{display:grid;grid-template-columns:180px minmax(0,1fr);gap:8px}.company-content-hidden{display:none!important}
    @media(max-width:1050px){.company-content-grid{grid-template-columns:repeat(2,minmax(200px,1fr))}}@media(max-width:700px){.company-content-grid,.company-content-upload,.company-content-publish-source{grid-template-columns:1fr}}
  `;document.head.append(style);
}

function contentCompany(){return typeof opsSelectedCompany==='function'?opsSelectedCompany():null}
function contentBytes(value){const bytes=Number(value||0);if(bytes<1024)return `${bytes} B`;if(bytes<1024*1024)return `${(bytes/1024).toFixed(1)} KB`;if(bytes<1024*1024*1024)return `${(bytes/1024/1024).toFixed(1)} MB`;return `${(bytes/1024/1024/1024).toFixed(2)} GB`}
function contentDimensions(row){return row.width&&row.height?`${row.width}×${row.height}`:'Sin dimensiones'}
function contentDuration(row){return Number.isFinite(Number(row.duration))?`${Number(row.duration).toFixed(1)} s`:'Sin duración'}
function contentFileUrl(companyId,mediaId){return `/api/companies/${encodeURIComponent(companyId)}/media/${encodeURIComponent(mediaId)}/file`}
function contentEligibleReel(row,channel){
  if(row.kind!=='video'||!row.width||!row.height||row.width*16!==row.height*9)return false;
  const duration=Number(row.duration),name=String(row.original_name||'').toLowerCase();
  if(!Number.isFinite(duration)||!name.match(/\.(mp4|mov)$/))return false;
  if(channel==='instagram')return row.width<=1920&&duration>=3&&duration<=60&&Number(row.bytes)<=1000000000;
  return row.width>=540&&row.height>=960&&duration>=4&&duration<=60;
}

async function contentRefresh(force=false){
  const company=contentCompany(),companyId=company?.id||null;
  if(!companyId){companyContentState.companyId=null;companyContentState.media=[];companyContentState.loaded=true;return}
  if(companyContentState.loading)return;
  if(!force&&companyContentState.loaded&&companyContentState.companyId===companyId)return;
  companyContentState.loading=true;companyContentState.companyId=companyId;
  try{companyContentState.media=await opsApi(`/api/companies/${encodeURIComponent(companyId)}/media`)||[];companyContentState.loaded=true}catch(err){opsToast(err.message)}finally{companyContentState.loading=false}
}

async function contentUpload(file,kind){
  const company=contentCompany();if(!company||!file)return;
  const url=`/api/companies/${encodeURIComponent(company.id)}/media/upload?filename=${encodeURIComponent(file.name)}&kind=${encodeURIComponent(kind)}`;
  const response=await fetch(url,{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file});
  let payload={};try{payload=await response.json()}catch(_err){}
  if(!response.ok)throw new Error(payload.error||`Upload HTTP ${response.status}`);
  return payload;
}

async function contentDelete(row){
  const company=contentCompany();if(!company)return;
  try{await opsApi(`/api/companies/${encodeURIComponent(company.id)}/media/${encodeURIComponent(row.id)}`,{method:'DELETE'});if(companyContentState.pickId===row.id)companyContentState.pickId=null;opsToast('Archivo eliminado de la biblioteca');await contentRefresh(true);contentRenderCurrent()}catch(err){opsToast(err.message)}
}

function contentRenderCard(row){
  const company=contentCompany(),card=opsEl('article','company-content-card');const preview=opsEl('div','company-content-preview');
  if(row.kind==='image'){const image=document.createElement('img');image.src=contentFileUrl(company.id,row.id);image.alt=row.original_name;image.loading='lazy';preview.append(image)}else{const video=document.createElement('video');video.src=contentFileUrl(company.id,row.id);video.controls=true;video.preload='metadata';preview.append(video)}
  const meta=opsEl('div','company-content-meta');meta.append(opsEl('strong','',row.original_name),opsEl('span','',`${row.kind==='video'?'Video':'Imagen'} · ${contentBytes(row.bytes)} · ${contentDimensions(row)}${row.kind==='video'?` · ${contentDuration(row)}`:''}`),opsEl('span','',`SHA-256 ${String(row.sha256||'').slice(0,12)}…`));card.append(preview,meta);
  const actions=opsEl('div','company-content-actions');
  if(row.kind==='video'){const use=opsEl('button',contentEligibleReel(row,'instagram')||contentEligibleReel(row,'facebook_page')?'primary':'','Usar como Reel');use.type='button';use.disabled=!(contentEligibleReel(row,'instagram')||contentEligibleReel(row,'facebook_page'));use.addEventListener('click',()=>{companyContentState.pickId=row.id;opsShowView('publish')});actions.append(use)}else actions.append(opsEl('span','company-content-pill','Disponible en biblioteca'));
  const remove=opsEl('button','','Eliminar');remove.type='button';remove.addEventListener('click',()=>contentDelete(row));actions.append(remove);card.append(actions);return card;
}

function renderCompanyContent(root){
  contentEnsureStyles();const company=contentCompany();
  const header=opsEl('section','marketing-ops-section');const head=opsEl('div','marketing-ops-section-head');const copy=opsEl('div','');copy.append(opsEl('p','eyebrow','CONTENIDO'),opsEl('h3','','Biblioteca de la empresa'),opsEl('p','muted',company?`Archivos administrados de ${company.name}. No dependen de proyectos de Video Studio.`:'Selecciona una empresa para administrar su biblioteca.'));const legacy=opsEl('button','','Abrir Video Studio');legacy.type='button';legacy.addEventListener('click',()=>companyContentOpenVideoStudio());head.append(copy,legacy);header.append(head);
  if(!company){header.append(opsEmpty('Selecciona una empresa en el filtro superior.'));root.append(header);return}
  const upload=opsEl('form','company-content-upload');const fileLabel=opsEl('label','','Archivo local');const file=document.createElement('input');file.type='file';file.accept='image/jpeg,image/png,image/webp,video/mp4,video/quicktime';file.required=true;fileLabel.append(file);const kindLabel=opsEl('label','','Tipo');const kind=document.createElement('select');[['image','Imagen'],['video','Video']].forEach(([value,label])=>{const option=opsEl('option','',label);option.value=value;kind.append(option)});kindLabel.append(kind);const submit=opsEl('button','primary','Agregar a biblioteca');submit.type='submit';upload.append(fileLabel,kindLabel,submit);file.addEventListener('change',()=>{const selected=file.files?.[0];if(selected)kind.value=selected.type.startsWith('image/')?'image':'video'});upload.addEventListener('submit',async event=>{event.preventDefault();const selected=file.files?.[0];if(!selected)return;submit.disabled=true;submit.textContent='Guardando…';try{await contentUpload(selected,kind.value);file.value='';opsToast('Archivo agregado a la biblioteca');await contentRefresh(true);await refreshMarketingOps(false);contentRenderCurrent()}catch(err){opsToast(err.message)}finally{submit.disabled=false;submit.textContent='Agregar a biblioteca'}});header.append(upload);root.append(header);
  const section=opsEl('section','marketing-ops-section');const sectionHead=opsEl('div','marketing-ops-section-head');const sectionCopy=opsEl('div','');sectionCopy.append(opsEl('p','eyebrow','ARCHIVOS'),opsEl('h3','',`${companyContentState.media.length} en biblioteca`));sectionHead.append(sectionCopy);section.append(sectionHead);if(!companyContentState.loaded||companyContentState.companyId!==company.id){section.append(opsEmpty('Cargando biblioteca…'));root.append(section);contentRefresh(true).then(contentRenderCurrent);return}const grid=opsEl('div','company-content-grid');companyContentState.media.forEach(row=>grid.append(contentRenderCard(row)));if(!companyContentState.media.length)grid.append(opsEmpty('Agrega imágenes o videos para reutilizarlos en campañas y publicaciones.'));section.append(grid);root.append(section);
}

function contentRenderCurrent(){
  if(marketingOpsState.view!=='content')return;const root=document.querySelector('#marketing-ops-view');if(!root)return;root.replaceChildren();document.querySelector('#marketing-ops-eyebrow').textContent='CONTENIDO';document.querySelector('#marketing-ops-title').textContent='Biblioteca de contenido';document.querySelector('#marketing-ops-subtitle').textContent='Archivos reutilizables por empresa, separados del editor de video.';document.querySelectorAll('[data-ops-view]').forEach(button=>button.classList.toggle('active',button.dataset.opsView==='content'));renderCompanyContent(root)
}

const companyContentBaseShowLegacy=globalThis.opsShowLegacy;
function companyContentOpenVideoStudio(){companyContentBaseShowLegacy()}
globalThis.opsShowLegacy=function(){marketingOpsState.view='content';document.querySelector('main.shell')?.classList.add('marketing-ops-hidden');document.querySelector('#marketing-ops-shell')?.classList.remove('marketing-ops-hidden');document.querySelector('#marketing-ops-return')?.classList.add('marketing-ops-hidden');document.querySelector('.topbar h1')?.replaceChildren(document.createTextNode('Marketing Workspace'));contentRefresh(false).then(contentRenderCurrent);contentRenderCurrent()};

const companyContentBaseRenderMarketingOps=globalThis.renderMarketingOps;
globalThis.renderMarketingOps=function(){if(marketingOpsState.view==='content'){contentRenderCurrent();return}companyContentBaseRenderMarketingOps()};

const companyContentBaseKinds=globalThis.opsPublicationKindOptions;
globalThis.opsPublicationKindOptions=function(channel){if(channel==='facebook_page')return [['text','Texto'],['link','Enlace'],['image','Imagen por URL'],['reel','Reel local']];return companyContentBaseKinds(channel)};

const companyContentBaseRenderPublish=globalThis.renderOpsPublish;
globalThis.renderOpsPublish=function(root){
  companyContentBaseRenderPublish(root);const company=contentCompany(),form=document.querySelector('#marketing-ops-publish-form');if(!company||!form)return;
  const existing=document.querySelector('#company-content-publish-source');if(existing)return;
  const wrap=opsEl('div','company-content-publish-source');wrap.id='company-content-publish-source';const sourceLabel=opsEl('label','','Origen del Reel');const source=document.createElement('select');source.id='ops-publish-reel-source';sourceLabel.append(source);const mediaLabel=opsEl('label','','Video de biblioteca');const select=document.createElement('select');select.id='ops-publish-library-media';mediaLabel.append(select);wrap.append(sourceLabel,mediaLabel);const mediaWrap=document.querySelector('#ops-publish-media-wrap');mediaWrap?.insertAdjacentElement('beforebegin',wrap);
  const channel=document.querySelector('#ops-publish-channel'),kind=document.querySelector('#ops-publish-kind');
  function syncLibrary(){
    const isReel=kind?.value==='reel',ch=channel?.value;wrap.classList.toggle('company-content-hidden',!isReel);if(!isReel)return;source.replaceChildren();const local=opsEl('option','','Biblioteca local');local.value='local';source.append(local);if(ch==='instagram'){const url=opsEl('option','','URL pública');url.value='url';source.append(url)}if(companyContentState.pickId&&companyContentState.media.some(row=>row.id===companyContentState.pickId))source.value='local';syncMedia()
  }
  function syncMedia(){const ch=channel?.value,isLocal=source.value==='local';mediaLabel.classList.toggle('company-content-hidden',!isLocal);if(mediaWrap)mediaWrap.classList.toggle('marketing-ops-hidden',kind?.value==='reel'&&isLocal);select.replaceChildren();const rows=companyContentState.media.filter(row=>contentEligibleReel(row,ch));if(!rows.length){const option=opsEl('option','','No hay videos 9:16 elegibles');option.value='';select.append(option);select.disabled=true}else{select.disabled=false;rows.forEach(row=>{const option=opsEl('option','',`${row.original_name} · ${contentDuration(row)}`);option.value=row.id;select.append(option)});if(companyContentState.pickId&&rows.some(row=>row.id===companyContentState.pickId))select.value=companyContentState.pickId}}
  channel?.addEventListener('change',()=>setTimeout(syncLibrary,0));kind?.addEventListener('change',()=>setTimeout(syncLibrary,0));source.addEventListener('change',syncMedia);contentRefresh(false).then(()=>{syncLibrary()});syncLibrary();
};

globalThis.submitOpsPublication=async function(publishNow){
  const company=contentCompany();if(!company)return;const channel=document.querySelector('#ops-publish-channel')?.value,kind=document.querySelector('#ops-publish-kind')?.value,message=document.querySelector('#ops-publish-message')?.value.trim()||'',date=document.querySelector('#ops-publish-date')?.value||'',link=document.querySelector('#ops-publish-link')?.value.trim()||'',mediaUrl=document.querySelector('#ops-publish-media')?.value.trim()||'',source=document.querySelector('#ops-publish-reel-source')?.value||'url',libraryId=document.querySelector('#ops-publish-library-media')?.value||'';
  const localReel=kind==='reel'&&source==='local';if(localReel&&!libraryId){opsToast('Selecciona un video elegible de la biblioteca');return}
  const payload={channel,kind,message,link_url:kind==='link'?link:null,media_url:kind==='image'||(kind==='reel'&&!localReel)?mediaUrl:null,asset_id:localReel?libraryId:null};if(!publishNow&&date){const parsed=new Date(date);if(Number.isNaN(parsed.getTime())){opsToast('Fecha inválida');return}payload.scheduled_for=parsed.toISOString()}
  try{const row=await opsApi(`/api/companies/${encodeURIComponent(company.id)}/publications`,{method:'POST',body:payload});if(publishNow)await opsApi(`/api/companies/${encodeURIComponent(company.id)}/publications/${encodeURIComponent(row.id)}/publish-now`,{method:'POST',body:{}});companyContentState.pickId=null;opsToast(publishNow?'Publicación enviada a Meta':date?'Publicación programada':'Borrador guardado');await Promise.all([refreshMarketingOps(true),contentRefresh(true)]);opsShowView('calendar')}catch(err){opsToast(err.message)}
};

contentEnsureStyles();
