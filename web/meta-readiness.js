const metaReadinessState={data:null,busy:false,timer:null};

function metaReadinessReason(reason){
  const labels={
    meta_not_connected:'Conecta Meta',
    no_facebook_pages:'No hay Páginas accesibles',
    no_page_with_create_content_task:'Falta permiso/tarea para crear contenido',
    page_access_token_unavailable:'Page token no disponible',
    page_create_content_task_missing:'La Página no permite crear contenido',
    no_linked_instagram_professional_account:'No hay Instagram profesional vinculado',
    no_ad_accounts:'No hay cuenta publicitaria accesible',
    pages_show_list:'Falta pages_show_list',
    instagram_basic:'Falta instagram_basic',
    instagram_content_publish:'Falta instagram_content_publish',
    pages_read_engagement:'Falta pages_read_engagement',
    ads_read:'Falta ads_read',
    ads_management:'Falta ads_management',
  };
  return labels[reason]||String(reason||'Pendiente');
}

function ensureMetaReadinessPanel(){
  let root=$('#meta-readiness-panel');if(root)return root;
  const assets=$('#meta-assets');if(!assets)return null;
  root=el('div','meta-readiness-panel');root.id='meta-readiness-panel';
  root.innerHTML='<div class="composer-head"><div><p class="eyebrow">READINESS</p><h4>Canales</h4></div><button id="meta-readiness-refresh" type="button">Revisar</button></div><div id="meta-readiness-list" class="composer-list"><p class="muted">Comprobando permisos…</p></div>';
  assets.parentNode.insertBefore(root,assets);
  $('#meta-readiness-refresh').addEventListener('click',refreshMetaReadiness);
  return root;
}

function readinessRow(name,state){
  const item=el('div','result-item');
  const status=state?.ready?'LISTO':'PENDIENTE';
  item.append(el('strong','',`${status} · ${name}`));
  const reasons=[...(state?.reasons||[])];
  if(state?.missing_permissions)for(const permission of state.missing_permissions)if(!reasons.includes(permission))reasons.push(permission);
  if(state?.ready)item.append(el('p','muted','Conexión, permisos y activos mínimos disponibles.'));
  else item.append(el('p','muted',reasons.length?reasons.map(metaReadinessReason).join(' · '):'Revisa los activos de esta conexión.'));
  return item;
}

function renderMetaReadiness(){
  const root=ensureMetaReadinessPanel(),list=$('#meta-readiness-list');if(!root||!list)return;
  list.replaceChildren();const row=metaReadinessState.data;
  if(!row){list.append(el('p','muted','Comprobando permisos…'));return}
  list.append(readinessRow('Facebook',row.facebook),readinessRow('Instagram',row.instagram),readinessRow('Ads',row.ads));
  const granted=(row.permissions||[]).filter(item=>item.status==='granted').map(item=>item.name);
  if(granted.length){const details=el('details','');details.append(el('summary','','Permisos concedidos'),el('p','muted',granted.join(' · ')));list.append(details)}
}

async function refreshMetaReadiness(){
  if(metaReadinessState.busy)return;metaReadinessState.busy=true;
  const button=$('#meta-readiness-refresh');if(button)button.disabled=true;
  try{metaReadinessState.data=await api('/api/meta/readiness');renderMetaReadiness()}catch(err){metaReadinessState.data={facebook:{ready:false,reasons:['readiness_error']},instagram:{ready:false,reasons:['readiness_error']},ads:{ready:false,reasons:['readiness_error']},permissions:[]};renderMetaReadiness();if(typeof toast==='function')toast(err.message)}finally{metaReadinessState.busy=false;if(button)button.disabled=false}
}

function watchMetaReadiness(){
  ensureMetaReadinessPanel();const badge=$('#meta-status-badge');if(badge)new MutationObserver(()=>refreshMetaReadiness()).observe(badge,{childList:true,characterData:true,subtree:true});
  clearInterval(metaReadinessState.timer);metaReadinessState.timer=setInterval(refreshMetaReadiness,30000);refreshMetaReadiness();
}
window.addEventListener('beforeunload',()=>clearInterval(metaReadinessState.timer));
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',watchMetaReadiness,{once:true});else watchMetaReadiness();
globalThis.refreshMetaReadiness=refreshMetaReadiness;
