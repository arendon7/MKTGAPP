(function installPostW99PortfolioContent(){
  if(globalThis.POST_W99_PORTFOLIO_CONTENT)return;
  globalThis.POST_W99_PORTFOLIO_CONTENT=true;
  if(typeof globalThis.contentRenderCurrent!=='function')return;

  const state={payload:null,loading:false,mode:'PORTFOLIO',filter:'ACTIVE'};
  let ownerNavigation=false;

  function styles(){
    if(document.querySelector('#post-w99-portfolio-content-style'))return;
    const style=document.createElement('style');style.id='post-w99-portfolio-content-style';style.textContent=`
.portfolio-content-hero,.portfolio-content-summary,.portfolio-content-panel,.portfolio-content-card{border:1px solid #dedad2;background:#fff;border-radius:14px}.portfolio-content-hero{padding:15px;display:flex;justify-content:space-between;gap:14px;align-items:flex-start}.portfolio-content-hero h3{font-size:19px;margin:0 0 5px}.portfolio-content-hero p{margin:0}.portfolio-content-actions,.portfolio-content-filters,.portfolio-content-meta{display:flex;gap:6px;flex-wrap:wrap}.portfolio-content-summary{padding:10px;display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:8px}.portfolio-content-stat{background:#faf9f6;border:1px solid #ece8e0;border-radius:10px;padding:9px}.portfolio-content-stat strong{display:block;font-size:18px}.portfolio-content-stat span{font-size:7px;color:#777168}.portfolio-content-panel{padding:13px;display:grid;gap:10px}.portfolio-content-toolbar{display:flex;justify-content:space-between;gap:10px;align-items:center}.portfolio-content-filter.active{background:#171717;color:#fff}.portfolio-content-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.portfolio-content-card{padding:11px;display:grid;gap:8px}.portfolio-content-card-head{display:flex;justify-content:space-between;gap:8px;align-items:flex-start}.portfolio-content-card strong{font-size:10px}.portfolio-content-card p{font-size:8px;color:#716b62;line-height:1.45;margin:0}.portfolio-content-chip{font-size:7px;padding:4px 6px;border-radius:999px;background:#f1eee8}.portfolio-content-chip.company{background:#171717;color:#fff}.portfolio-content-card-actions{display:flex;justify-content:flex-end}.portfolio-content-note,.portfolio-content-empty{padding:10px;border-radius:9px;background:#f5f2eb;color:#756f65;font-size:8px;line-height:1.45}.portfolio-content-empty{border:1px dashed #d9d4ca;background:#fff}.portfolio-content-company-mode{margin-bottom:10px;padding:9px;border:1px solid #dedad2;border-radius:10px;background:#faf9f6;display:flex;justify-content:space-between;gap:8px;align-items:center;font-size:8px}@media(max-width:900px){.portfolio-content-summary{grid-template-columns:repeat(3,minmax(0,1fr))}.portfolio-content-list{grid-template-columns:1fr}}@media(max-width:650px){.portfolio-content-hero,.portfolio-content-toolbar,.portfolio-content-company-mode{display:grid}.portfolio-content-summary{grid-template-columns:repeat(2,minmax(0,1fr))}}
`;document.head.append(style)
  }

  async function load(force=false){
    if(state.loading)return state.payload;
    if(!force&&state.payload)return state.payload;
    state.loading=true;
    try{state.payload=await opsApi('/api/portfolio/content');return state.payload}
    catch(err){state.payload=null;opsToast(err.message);return null}
    finally{state.loading=false}
  }

  function stat(value,label){const box=opsEl('div','portfolio-content-stat');box.append(opsEl('strong','',String(value||0)),opsEl('span','',label));return box}
  function stageLabel(value){return ({UNPROFILED:'Sin brief',BRIEF:'Brief',DRAFT:'Borrador',READY:'Lista',SCHEDULED:'Programada',PUBLISHED:'Publicada',PAID:'Pauta',ARCHIVED:'Archivada'})[value]||value}
  function visibleItems(){const rows=Array.isArray(state.payload?.items)?state.payload.items:[];if(state.filter==='ALL')return rows;if(state.filter==='ACTIVE')return rows.filter(row=>!['PUBLISHED','PAID','ARCHIVED'].includes(row.stage));return rows.filter(row=>row.stage===state.filter)}

  async function openOwner(row){
    const companyId=String(row?.company?.id||'').trim();if(!companyId)return;
    state.mode='COMPANY';ownerNavigation=true;
    try{if(typeof globalThis.portfolioNavigate==='function')await globalThis.portfolioNavigate(companyId,{view:'content'});else{marketingOpsState.selectedCompanyId=companyId;await refreshMarketingOps(false);globalThis.contentRenderCurrent()}}
    finally{ownerNavigation=false}
  }

  async function openGlobalCalendar(){
    marketingOpsState.selectedCompanyId=null;
    try{localStorage.setItem('marketingOpsCompany','')}catch(_err){}
    if(typeof fillCompanyFilter==='function')fillCompanyFilter();
    if(typeof refreshMarketingOps==='function')await refreshMarketingOps(false);
    if(typeof opsShowView==='function')opsShowView('calendar');
  }

  function card(row){
    const box=opsEl('article','portfolio-content-card'),head=opsEl('div','portfolio-content-card-head'),copy=opsEl('div','');copy.append(opsEl('strong','',row.title||row.media?.name||'Contenido'),opsEl('p','',`${row.media?.kind==='video'?'Video':row.media?.kind==='image'?'Imagen':'Activo'} · ${stageLabel(row.stage)}`));head.append(copy,opsEl('span','portfolio-content-chip',stageLabel(row.stage)));box.append(head);
    const meta=opsEl('div','portfolio-content-meta');meta.append(opsEl('span','portfolio-content-chip company',row.company?.name||'Empresa'));if(row.campaign?.name)meta.append(opsEl('span','portfolio-content-chip',row.campaign.name));if(row.channels?.length)meta.append(opsEl('span','portfolio-content-chip',row.channels.join(' · ')));if(row.publication_count)meta.append(opsEl('span','portfolio-content-chip',`${row.publication_count} publicación(es)`));if(row.paid_media_count)meta.append(opsEl('span','portfolio-content-chip',`${row.paid_media_count} pauta(s)`));box.append(meta);
    const actions=opsEl('div','portfolio-content-card-actions'),open=opsEl('button',row.stage==='READY'||row.stage==='SCHEDULED'?'primary':'','Abrir en empresa');open.type='button';open.addEventListener('click',()=>openOwner(row));actions.append(open);box.append(actions);return box
  }

  function renderPortfolio(){
    if(typeof marketingOpsState==='undefined'||marketingOpsState.view!=='content'||state.mode!=='PORTFOLIO')return false;
    styles();const root=document.querySelector('#marketing-ops-view');if(!root)return false;root.replaceChildren();
    document.querySelector('#marketing-ops-eyebrow').textContent='CONTENIDO / MULTIEMPRESA';document.querySelector('#marketing-ops-title').textContent='Contenido';document.querySelector('#marketing-ops-subtitle').textContent='Biblioteca creativa transversal. Edición, publicación y pauta siguen ocurriendo únicamente dentro de la empresa propietaria.';document.querySelectorAll('[data-ops-view]').forEach(button=>button.classList.toggle('active',button.dataset.opsView==='content'));
    if(!state.payload){root.append(opsEl('div','portfolio-content-empty','Construyendo biblioteca creativa de todas las empresas…'));load(true).then(renderPortfolio);return true}
    const summary=state.payload.summary||{},hero=opsEl('section','portfolio-content-hero'),copy=opsEl('div','');copy.append(opsEl('p','eyebrow','TODAS LAS EMPRESAS · LOCAL'),opsEl('h3','','Biblioteca creativa del portfolio'),opsEl('p','muted','Reutiliza los estados de Creative Studio y el calendario editorial existente. No crea otro scheduler ni otra ruta de publicación.'));
    const actions=opsEl('div','portfolio-content-actions'),refresh=opsEl('button','','Actualizar lectura local'),calendar=opsEl('button','primary','Calendario global'),company=opsEl('button','','Ver empresa activa');refresh.type='button';refresh.addEventListener('click',async()=>{await load(true);renderPortfolio()});calendar.type='button';calendar.addEventListener('click',openGlobalCalendar);company.type='button';company.addEventListener('click',()=>{state.mode='COMPANY';globalThis.contentRenderCurrent()});actions.append(refresh,calendar,company);hero.append(copy,actions);root.append(hero);
    const stats=opsEl('section','portfolio-content-summary');stats.append(stat(summary.total_assets,'ACTIVOS'),stat(summary.in_creation,'EN CREACIÓN'),stat(summary.ready,'LISTOS'),stat(summary.scheduled,'PROGRAMADOS'),stat(summary.published,'PUBLICADOS'),stat(summary.paid,'EN PAUTA'));root.append(stats);
    const panel=opsEl('section','portfolio-content-panel'),toolbar=opsEl('div','portfolio-content-toolbar'),heading=opsEl('div','');heading.append(opsEl('p','eyebrow','FLUJO CREATIVO'),opsEl('h3','','Piezas del portfolio'));const filters=opsEl('div','portfolio-content-filters');[['ACTIVE','Trabajo activo'],['ALL','Todo'],['UNPROFILED','Sin brief'],['DRAFT','Borrador'],['READY','Listo'],['SCHEDULED','Programado'],['PUBLISHED','Publicado'],['PAID','Pauta']].forEach(([key,label])=>{const button=opsEl('button',`portfolio-content-filter ${state.filter===key?'active':''}`,label);button.type='button';button.addEventListener('click',()=>{state.filter=key;renderPortfolio()});filters.append(button)});toolbar.append(heading,filters);panel.append(toolbar);
    const rows=visibleItems(),list=opsEl('div','portfolio-content-list');rows.forEach(row=>list.append(card(row)));if(!rows.length)list.append(opsEl('div','portfolio-content-empty','No hay piezas para este filtro.'));panel.append(list);const scope=state.payload.scope||{};panel.append(opsEl('div','portfolio-content-note',`${summary.active_companies||0} empresa(s) · ${scope.displayed||0}/${scope.total||0} activo(s) visibles. Creative Studio conserva el estado creativo; Company Media conserva los archivos; Calendario conserva la programación.`));root.append(panel);return true
  }

  const baseContentRender=globalThis.contentRenderCurrent;
  globalThis.contentRenderCurrent=function postW99PortfolioContentRender(){
    if(marketingOpsState?.view==='content'&&state.mode==='PORTFOLIO'){renderPortfolio();return}
    baseContentRender.apply(this,arguments);
    if(marketingOpsState?.view!=='content'||state.mode!=='COMPANY')return;
    styles();const root=document.querySelector('#marketing-ops-view');if(!root||root.querySelector('[data-portfolio-content-company-mode]'))return;
    const bar=opsEl('div','portfolio-content-company-mode');bar.dataset.portfolioContentCompanyMode='1';bar.append(opsEl('span','','Estás trabajando en la biblioteca de la empresa activa. Aquí permanecen la carga, edición y preparación de publicaciones.'));const back=opsEl('button','','Volver a todas las empresas');back.type='button';back.addEventListener('click',()=>{state.mode='PORTFOLIO';load(true).then(renderPortfolio)});bar.append(back);root.prepend(bar)
  };

  const baseShowLegacy=globalThis.opsShowLegacy;
  globalThis.opsShowLegacy=function postW99PortfolioContentShowLegacy(){
    if(!ownerNavigation)state.mode='PORTFOLIO';
    const result=baseShowLegacy.apply(this,arguments);
    if(state.mode==='PORTFOLIO')load(false).then(renderPortfolio);
    return result
  };

  if(typeof globalThis.portfolioNavigate==='function'){
    const basePortfolioNavigate=globalThis.portfolioNavigate;
    globalThis.portfolioNavigate=async function postW99PortfolioContentNavigate(companyId,action){if(action?.view==='content'){state.mode='COMPANY';ownerNavigation=true;try{return await basePortfolioNavigate(companyId,action)}finally{ownerNavigation=false}}return basePortfolioNavigate(companyId,action)};
  }
  if(typeof globalThis.opsShowView==='function'){
    const baseShowView=globalThis.opsShowView;
    globalThis.opsShowView=function postW99PortfolioContentShowView(view){if(view==='content'&&!ownerNavigation&&marketingOpsState?.view!=='content')state.mode='PORTFOLIO';return baseShowView.apply(this,arguments)};
  }
  window.addEventListener('marketing-ops-refreshed',()=>{state.payload=null;if(marketingOpsState?.view==='content'&&state.mode==='PORTFOLIO')load(true).then(renderPortfolio)});
  load();
})();
