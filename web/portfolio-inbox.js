(function installPostW99PortfolioInbox(){
  if(globalThis.POST_W99_PORTFOLIO_INBOX)return;
  globalThis.POST_W99_PORTFOLIO_INBOX=true;
  if(typeof globalThis.inboxRenderCurrent!=='function')return;

  const state={payload:null,loading:false,mode:'PORTFOLIO',filter:'ALL',refreshing:false};
  let ownerNavigation=false;

  function styles(){
    if(document.querySelector('#post-w99-portfolio-inbox-style'))return;
    const style=document.createElement('style');style.id='post-w99-portfolio-inbox-style';style.textContent=`
.portfolio-inbox-hero,.portfolio-inbox-summary,.portfolio-inbox-panel,.portfolio-inbox-card{border:1px solid #dedad2;background:#fff;border-radius:14px}.portfolio-inbox-hero{padding:15px;display:flex;justify-content:space-between;gap:14px;align-items:flex-start}.portfolio-inbox-hero h3{font-size:19px;margin:0 0 5px}.portfolio-inbox-hero p{margin:0}.portfolio-inbox-actions{display:flex;gap:6px;flex-wrap:wrap}.portfolio-inbox-summary{padding:10px;display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px}.portfolio-inbox-stat{background:#faf9f6;border:1px solid #ece8e0;border-radius:10px;padding:9px}.portfolio-inbox-stat strong{display:block;font-size:18px}.portfolio-inbox-stat span{font-size:7px;color:#777168}.portfolio-inbox-panel{padding:13px;display:grid;gap:10px}.portfolio-inbox-toolbar{display:flex;justify-content:space-between;gap:10px;align-items:center}.portfolio-inbox-filters{display:flex;gap:5px;flex-wrap:wrap}.portfolio-inbox-filter.active{background:#171717;color:#fff}.portfolio-inbox-list{display:grid;gap:8px}.portfolio-inbox-card{padding:11px;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px;align-items:center}.portfolio-inbox-card.blocking{border-left:4px solid #171717}.portfolio-inbox-copy{display:grid;gap:5px}.portfolio-inbox-copy strong{font-size:10px}.portfolio-inbox-copy p{font-size:8px;color:#716b62;line-height:1.45;margin:0}.portfolio-inbox-meta{display:flex;gap:5px;flex-wrap:wrap}.portfolio-inbox-chip{font-size:7px;padding:4px 6px;border-radius:999px;background:#f1eee8}.portfolio-inbox-chip.company{background:#171717;color:#fff}.portfolio-inbox-note,.portfolio-inbox-empty{padding:10px;border-radius:9px;background:#f5f2eb;color:#756f65;font-size:8px;line-height:1.45}.portfolio-inbox-empty{border:1px dashed #d9d4ca;background:#fff}.portfolio-inbox-company-mode{margin-bottom:10px;padding:9px;border:1px solid #dedad2;border-radius:10px;background:#faf9f6;display:flex;justify-content:space-between;gap:8px;align-items:center;font-size:8px}@media(max-width:800px){.portfolio-inbox-hero,.portfolio-inbox-toolbar,.portfolio-inbox-company-mode{display:grid}.portfolio-inbox-summary{grid-template-columns:repeat(2,minmax(0,1fr))}.portfolio-inbox-card{grid-template-columns:1fr}.portfolio-inbox-card>button{width:100%}}
`;document.head.append(style)
  }

  async function load(force=false){
    if(state.loading)return state.payload;
    if(!force&&state.payload)return state.payload;
    state.loading=true;
    try{state.payload=await opsApi('/api/portfolio/inbox-attention');return state.payload}
    catch(err){state.payload=null;opsToast(err.message);return null}
    finally{state.loading=false}
  }

  function stat(value,label){const box=opsEl('div','portfolio-inbox-stat');box.append(opsEl('strong','',String(value||0)),opsEl('span','',label));return box}
  function actor(row){return row?.actor_handle?`@${row.actor_handle}`:'Interacción social'}
  function kindLabel(row){if(row?.attention_kind==='reply_verification')return 'VERIFICAR RESPUESTA';return row?.kind==='facebook_message'?'MENSAJE':'COMENTARIO'}
  function filtered(){
    const queue=Array.isArray(state.payload?.queue)?state.payload.queue:[];
    if(state.filter==='MESSAGE')return queue.filter(row=>row.kind==='facebook_message'&&row.attention_kind!=='reply_verification');
    if(state.filter==='COMMENT')return queue.filter(row=>row.kind==='instagram_comment'&&row.attention_kind!=='reply_verification');
    if(state.filter==='VERIFY')return queue.filter(row=>row.attention_kind==='reply_verification');
    return queue;
  }

  async function openOwner(row){
    const companyId=String(row?.company?.id||'').trim();if(!companyId)return;
    state.mode='COMPANY';ownerNavigation=true;
    try{
      if(typeof globalThis.portfolioNavigate==='function'){await globalThis.portfolioNavigate(companyId,row.action||{view:'inbox'});return}
      if(typeof marketingOpsState==='undefined')return;
      marketingOpsState.selectedCompanyId=companyId;
      try{localStorage.setItem('marketingOpsCompany',companyId)}catch(_err){}
      if(typeof fillCompanyFilter==='function')fillCompanyFilter();
      if(typeof globalThis.refreshMarketingOps==='function')await globalThis.refreshMarketingOps(false);
      if(typeof opsShowView==='function')opsShowView('inbox');
    }finally{ownerNavigation=false}
  }

  function card(row){
    const item=opsEl('article',`portfolio-inbox-card ${row?.blocking?'blocking':''}`),copy=opsEl('div','portfolio-inbox-copy');
    copy.append(opsEl('strong','',row?.title||`${kindLabel(row)} · ${actor(row)}`),opsEl('p','',row?.excerpt||row?.detail||'Interacción capturada en el último snapshot local.'));
    const meta=opsEl('div','portfolio-inbox-meta');meta.append(opsEl('span','portfolio-inbox-chip company',row?.company?.name||'Empresa'),opsEl('span','portfolio-inbox-chip',kindLabel(row)),opsEl('span','portfolio-inbox-chip',row?.urgency||'—'));
    if(row?.blocking)meta.append(opsEl('span','portfolio-inbox-chip','Bloqueante'));
    if(row?.occurred_at)meta.append(opsEl('span','portfolio-inbox-chip',typeof opsDate==='function'?opsDate(row.occurred_at):String(row.occurred_at)));
    copy.append(meta);const open=opsEl('button',row?.blocking?'primary':'','Abrir en empresa');open.type='button';open.addEventListener('click',()=>openOwner(row));item.append(copy,open);return item
  }

  async function refreshAll(button){
    if(state.refreshing)return;
    if(typeof globalThis.postW99PortfolioInboxRefreshRun!=='function'){opsToast('Control de actualización multiempresa no disponible.');return}
    state.refreshing=true;if(button)button.disabled=true;
    try{const result=await globalThis.postW99PortfolioInboxRefreshRun(button);if(result)await load(true)}
    finally{state.refreshing=false;renderPortfolio()}
  }

  function renderPortfolio(){
    if(typeof marketingOpsState==='undefined'||marketingOpsState.view!=='inbox'||state.mode!=='PORTFOLIO')return false;
    styles();const root=document.querySelector('#marketing-ops-view');if(!root)return false;root.replaceChildren();
    document.querySelector('#marketing-ops-eyebrow').textContent='INBOX / MULTIEMPRESA';document.querySelector('#marketing-ops-title').textContent='Inbox';document.querySelector('#marketing-ops-subtitle').textContent='Atención social de todas tus empresas desde evidencia local minimizada. Abrir una interacción entrega el control al Inbox de su empresa.';document.querySelectorAll('[data-ops-view]').forEach(button=>button.classList.toggle('active',button.dataset.opsView==='inbox'));
    if(!state.payload){root.append(opsEl('div','portfolio-inbox-empty','Construyendo Inbox local de todas las empresas…'));load(true).then(renderPortfolio);return true}
    const summary=state.payload.summary||{},hero=opsEl('section','portfolio-inbox-hero'),copy=opsEl('div','');copy.append(opsEl('p','eyebrow','TODAS LAS EMPRESAS · LOCAL'),opsEl('h3','','Atiende primero lo que realmente necesita respuesta'),opsEl('p','muted','Esta vista no consulta Meta. Usa únicamente snapshots mínimos capturados por actualizaciones explícitas y respeta las resoluciones CRM/reply existentes.'));
    const actions=opsEl('div','portfolio-inbox-actions'),refresh=opsEl('button','primary',state.refreshing?'Actualizando…':'Actualizar todas desde Meta'),company=opsEl('button','','Ver empresa activa');refresh.type='button';refresh.disabled=state.refreshing;refresh.addEventListener('click',()=>refreshAll(refresh));company.type='button';company.addEventListener('click',()=>{state.mode='COMPANY';globalThis.inboxRenderCurrent()});actions.append(refresh,company);hero.append(copy,actions);root.append(hero);
    const stats=opsEl('section','portfolio-inbox-summary');stats.append(stat(summary.attention_total,'PENDIENTES'),stat(summary.blocking,'BLOQUEANTES'),stat(summary.facebook_messages,'MENSAJES'),stat(summary.instagram_comments,'COMENTARIOS'),stat(summary.companies_requiring_refresh,'POR ACTUALIZAR'));root.append(stats);
    const panel=opsEl('section','portfolio-inbox-panel'),toolbar=opsEl('div','portfolio-inbox-toolbar'),heading=opsEl('div','');heading.append(opsEl('p','eyebrow','COLA TRANSVERSAL'),opsEl('h3','','Interacciones pendientes'));
    const filters=opsEl('div','portfolio-inbox-filters');[['ALL','Todas'],['MESSAGE','Mensajes'],['COMMENT','Comentarios'],['VERIFY','Verificar']].forEach(([key,label])=>{const button=opsEl('button',`portfolio-inbox-filter ${state.filter===key?'active':''}`,label);button.type='button';button.addEventListener('click',()=>{state.filter=key;renderPortfolio()});filters.append(button)});toolbar.append(heading,filters);panel.append(toolbar);
    const list=opsEl('div','portfolio-inbox-list'),rows=filtered();rows.forEach(row=>list.append(card(row)));if(!rows.length)list.append(opsEl('div','portfolio-inbox-empty',state.filter==='ALL'?'No hay interacciones pendientes en los snapshots locales actuales.':'No hay interacciones pendientes para este filtro.'));panel.append(list);
    const states=summary.snapshot_states||{},stateText=Object.entries(states).map(([key,value])=>`${key}: ${value}`).join(' · ');panel.append(opsEl('div','portfolio-inbox-note',`${summary.configured_companies||0} empresa(s) configuradas. ${stateText||'Sin snapshots aún.'} Los excerpts están limitados y no contienen enlaces Meta ni IDs personales del proveedor.`));root.append(panel);return true
  }

  const baseInboxRender=globalThis.inboxRenderCurrent;
  globalThis.inboxRenderCurrent=function postW99PortfolioInboxRender(){
    if(typeof marketingOpsState!=='undefined'&&marketingOpsState.view==='inbox'&&state.mode==='PORTFOLIO'){renderPortfolio();return}
    baseInboxRender.apply(this,arguments);
    if(typeof marketingOpsState==='undefined'||marketingOpsState.view!=='inbox'||state.mode!=='COMPANY')return;
    styles();const root=document.querySelector('#marketing-ops-view');if(!root||root.querySelector('[data-portfolio-inbox-company-mode]'))return;
    const bar=opsEl('div','portfolio-inbox-company-mode');bar.dataset.portfolioInboxCompanyMode='1';bar.append(opsEl('span','','Estás atendiendo la empresa activa. Las respuestas y acciones CRM siguen perteneciendo a este Inbox propietario.'));const back=opsEl('button','','Volver a todas las empresas');back.type='button';back.addEventListener('click',()=>{state.mode='PORTFOLIO';load(true).then(renderPortfolio)});bar.append(back);root.prepend(bar)
  };

  if(typeof globalThis.portfolioNavigate==='function'){
    const basePortfolioNavigate=globalThis.portfolioNavigate;
    globalThis.portfolioNavigate=async function postW99PortfolioInboxNavigate(companyId,action){
      if(action?.view==='inbox'){state.mode='COMPANY';ownerNavigation=true;try{return await basePortfolioNavigate(companyId,action)}finally{ownerNavigation=false}}
      return basePortfolioNavigate(companyId,action)
    };
  }

  if(typeof globalThis.opsShowView==='function'){
    const baseShowView=globalThis.opsShowView;
    globalThis.opsShowView=function postW99PortfolioInboxShowView(view){if(view==='inbox'&&!ownerNavigation&&marketingOpsState?.view!=='inbox')state.mode='PORTFOLIO';return baseShowView.apply(this,arguments)};
  }

  window.addEventListener('marketing-ops-refreshed',()=>{state.payload=null;if(marketingOpsState?.view==='inbox'&&state.mode==='PORTFOLIO')load(true).then(renderPortfolio)});
  load();
})();
