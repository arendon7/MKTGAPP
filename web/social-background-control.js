const socialBackgroundControlState={overview:null,loading:false,error:null};

function socialBackgroundStyles(){
  if(document.querySelector('#post-w99-social-background-style'))return;
  const style=document.createElement('style');
  style.id='post-w99-social-background-style';
  style.textContent=`
    .post-w99-bg-card{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:16px;align-items:center;border:1px solid #ddd8cf;border-radius:14px;padding:16px;margin-bottom:16px;background:#fbfaf7}
    .post-w99-bg-card h3{margin:3px 0 5px;font-size:17px}.post-w99-bg-card p{margin:0}.post-w99-bg-meta{display:flex;gap:8px;flex-wrap:wrap;margin-top:9px}
    .post-w99-bg-actions{display:flex;gap:8px;align-items:center;flex-wrap:wrap;justify-content:flex-end}.post-w99-bg-actions button{white-space:nowrap}
    .post-w99-bg-state{display:inline-flex;align-items:center;border-radius:999px;padding:4px 9px;border:1px solid #d4d0c8;font-size:11px;background:#fff}.post-w99-bg-state.active{background:#171717;color:#fff;border-color:#171717}
    @media(max-width:760px){.post-w99-bg-card{grid-template-columns:1fr}.post-w99-bg-actions{justify-content:flex-start}}
  `;
  document.head.append(style);
}

function socialBackgroundDate(value){
  if(!value)return null;
  const date=new Date(value);
  if(Number.isNaN(date.getTime()))return null;
  return new Intl.DateTimeFormat('es-CO',{dateStyle:'medium',timeStyle:'short'}).format(date);
}

async function socialBackgroundLoad(){
  if(socialBackgroundControlState.loading)return socialBackgroundControlState.overview;
  socialBackgroundControlState.loading=true;socialBackgroundControlState.error=null;
  try{socialBackgroundControlState.overview=await opsApi('/api/social/background');return socialBackgroundControlState.overview}
  catch(err){socialBackgroundControlState.error=err.message;return null}
  finally{socialBackgroundControlState.loading=false}
}

function socialBackgroundStateLabel(agent){
  if(!agent?.platform_supported)return ['Sólo macOS',''];
  if(agent.stale)return ['Requiere reinstalar',''];
  if(agent.loaded)return ['Activa','active'];
  if(agent.installed)return ['Instalada · detenida',''];
  return ['Inactiva',''];
}

function socialBackgroundCopy(agent){
  if(!agent?.platform_supported)return 'La programación en segundo plano se habilita desde la aplicación empaquetada para macOS.';
  if(agent.stale)return 'La app fue movida o cambió su ruta. Reinstala este servicio desde la ubicación actual para evitar rutas antiguas.';
  if(agent.loaded)return 'Las publicaciones ya programadas pueden salir aunque cierres la interfaz, mientras este Mac esté disponible.';
  if(agent.installed)return 'La integración existe pero launchd no la reporta activa. Puedes reinstalarla de forma segura.';
  return 'Actívala para que las publicaciones ya aprobadas y programadas sigan procesándose aunque cierres la interfaz.';
}

function renderSocialBackgroundControl(host){
  socialBackgroundStyles();host.replaceChildren();
  const overview=socialBackgroundControlState.overview;const agent=overview?.agent||null;const last=overview?.last_run||null;
  const card=opsEl('section','post-w99-bg-card');
  const info=opsEl('div','');const eyebrow=opsEl('p','eyebrow','PUBLICACIÓN EN SEGUNDO PLANO');const title=opsEl('h3','','Programación continua en este Mac');const copy=opsEl('p','muted',socialBackgroundControlState.loading?'Consultando estado…':socialBackgroundControlState.error?`No se pudo consultar: ${socialBackgroundControlState.error}`:socialBackgroundCopy(agent));info.append(eyebrow,title,copy);
  const meta=opsEl('div','post-w99-bg-meta');const [label,stateClass]=socialBackgroundStateLabel(agent);const badge=opsEl('span',`post-w99-bg-state ${stateClass}`,label);meta.append(badge);
  if(agent?.interval_seconds)meta.append(opsEl('span','marketing-ops-badge',`Cada ${agent.interval_seconds}s`));
  const lastDate=socialBackgroundDate(last?.ran_at);if(lastDate)meta.append(opsEl('span','marketing-ops-badge',`Última revisión ${lastDate}`));
  if(last?.published)meta.append(opsEl('span','marketing-ops-badge',`${last.published} publicada${last.published===1?'':'s'}`));
  if(last?.failed)meta.append(opsEl('span','marketing-ops-badge',`${last.failed} con error`));
  info.append(meta);card.append(info);
  const actions=opsEl('div','post-w99-bg-actions');
  if(agent?.platform_supported){
    if(agent.loaded&&!agent.stale){
      const off=opsEl('button','','Desactivar');off.type='button';off.addEventListener('click',socialBackgroundDisable);actions.append(off);
    }else{
      const on=opsEl('button','primary',agent?.installed||agent?.stale?'Reinstalar':'Activar en este Mac');on.type='button';on.addEventListener('click',socialBackgroundEnable);actions.append(on);
      if(agent?.installed){const off=opsEl('button','','Eliminar configuración');off.type='button';off.addEventListener('click',socialBackgroundDisable);actions.append(off)}
    }
  }
  const refresh=opsEl('button','','Actualizar');refresh.type='button';refresh.addEventListener('click',()=>socialBackgroundRefresh(host));actions.append(refresh);card.append(actions);host.append(card);
}

async function socialBackgroundRefresh(host){
  socialBackgroundControlState.overview=null;socialBackgroundControlState.error=null;
  renderSocialBackgroundControl(host);await socialBackgroundLoad();renderSocialBackgroundControl(host);
}

async function socialBackgroundEnable(event){
  const host=event.currentTarget.closest('.post-w99-bg-host');
  if(!window.confirm('¿Activar la publicación programada en segundo plano en este Mac?'))return;
  event.currentTarget.disabled=true;
  try{socialBackgroundControlState.overview=await opsApi('/api/social/background/install',{method:'POST',body:{}});opsToast('Programación en segundo plano activada')}
  catch(err){opsToast(err.message);socialBackgroundControlState.error=err.message}
  finally{if(host)renderSocialBackgroundControl(host)}
}

async function socialBackgroundDisable(event){
  const host=event.currentTarget.closest('.post-w99-bg-host');
  if(!window.confirm('¿Desactivar la publicación programada en segundo plano en este Mac?'))return;
  event.currentTarget.disabled=true;
  try{socialBackgroundControlState.overview=await opsApi('/api/social/background',{method:'DELETE'});opsToast('Programación en segundo plano desactivada')}
  catch(err){opsToast(err.message);socialBackgroundControlState.error=err.message}
  finally{if(host)renderSocialBackgroundControl(host)}
}

const postW99SocialBackgroundBaseCalendar=globalThis.renderOpsCalendar;
globalThis.renderOpsCalendar=function(root){
  const host=opsEl('div','post-w99-bg-host');root.append(host);renderSocialBackgroundControl(host);
  Promise.resolve(socialBackgroundLoad()).then(()=>{if(host.isConnected)renderSocialBackgroundControl(host)});
  postW99SocialBackgroundBaseCalendar(root);
};
