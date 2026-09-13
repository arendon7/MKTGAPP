(function installPostW99PilotReadiness(){
  if(globalThis.POST_W99_PILOT_READINESS)return;
  globalThis.POST_W99_PILOT_READINESS=true;

  const state={routed:false,bootstrapFailed:false};

  function ensureStyles(){
    if(document.querySelector('#post-w99-pilot-style'))return;
    const style=document.createElement('style');
    style.id='post-w99-pilot-style';
    style.textContent=`
      .post-w99-pilot-badge{display:inline-flex;align-items:center;gap:5px;padding:5px 8px;border:1px solid #d8d2c8;border-radius:999px;background:#f8f6f1;color:#5f594f;font-size:8px;white-space:nowrap}
      .post-w99-pilot-badge::before{content:'';width:6px;height:6px;border-radius:50%;background:#171717}
      .post-w99-pilot-failure{margin:12px;padding:14px;border:1px solid #cfc7bb;border-left:4px solid #171717;border-radius:12px;background:#fff;display:grid;gap:8px}
      .post-w99-pilot-failure strong{font-size:12px}.post-w99-pilot-failure p{margin:0;color:#756f65;font-size:9px;line-height:1.45}
      @media(max-width:700px){.post-w99-pilot-badge{display:none}}
    `;
    document.head.append(style);
  }

  function ensureIdentity(){
    document.title='MERCADEO APP · Centro de operaciones';
    let icon=document.querySelector('link[rel="icon"]');
    if(!icon){icon=document.createElement('link');icon.rel='icon';document.head.append(icon)}
    icon.type='image/svg+xml';icon.href='/favicon.svg';
    const top=document.querySelector('.topbar');
    if(!top)return;
    const eyebrow=top.querySelector('.eyebrow');
    const title=top.querySelector('h1');
    if(eyebrow)eyebrow.textContent='MERCADEO APP';
    if(title)title.textContent='Centro de operaciones';
    if(!top.querySelector('[data-post-w99-pilot-badge]')){
      ensureStyles();
      const badge=document.createElement('span');
      badge.className='post-w99-pilot-badge';
      badge.dataset.postW99PilotBadge='1';
      badge.textContent='Piloto local';
      const status=top.querySelector('.status-wrap');
      if(status)status.prepend(badge);
      else top.append(badge);
    }
  }

  function showBootstrapFailure(detail){
    state.bootstrapFailed=true;
    ensureIdentity();ensureStyles();
    const existing=document.querySelector('[data-post-w99-pilot-failure]');
    if(existing)return;
    const host=document.querySelector('#marketing-ops-view')||document.querySelector('main')||document.body;
    const box=document.createElement('section');
    box.className='post-w99-pilot-failure';
    box.dataset.postW99PilotFailure='1';
    const title=document.createElement('strong');title.textContent='La interfaz no terminó de iniciar';
    const copy=document.createElement('p');copy.textContent='El backend local sigue protegido. Recarga la aplicación; si persiste, revisa el arranque de serve-dev antes de operar cuentas o publicaciones.';
    if(detail?.error){const reason=document.createElement('p');reason.textContent=String(detail.error).slice(0,240);box.append(title,copy,reason)}else box.append(title,copy);
    const reload=document.createElement('button');reload.type='button';reload.textContent='Recargar';reload.addEventListener('click',()=>location.reload());box.append(reload);
    host.prepend(box);
  }

  function routeInitial(){
    ensureIdentity();
    if(state.routed||state.bootstrapFailed)return;
    if(typeof marketingOpsState==='undefined'||!Array.isArray(marketingOpsState.companies)||typeof opsShowView!=='function')return;
    // `dashboard === null` means the first local refresh has not completed yet.
    // Do not infer an empty portfolio from the initial in-memory [] value.
    if(marketingOpsState.dashboard===null)return;
    if(marketingOpsState.view&&marketingOpsState.view!=='home'){state.routed=true;return}
    state.routed=true;
    if(marketingOpsState.companies.length===0){opsShowView('companies');return}
    opsShowView('today-execution');
  }

  window.addEventListener('wave73-bootstrap-failed',event=>showBootstrapFailure(event.detail||{}));
  window.addEventListener('wave73-bootstrap-ready',()=>{ensureIdentity();routeInitial()});
  window.addEventListener('marketing-ops-refreshed',()=>{ensureIdentity();routeInitial()});
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)ensureIdentity()});

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>{ensureIdentity();routeInitial()},{once:true});
  else{ensureIdentity();routeInitial()}
})();
