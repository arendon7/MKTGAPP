(function installPostW99PortfolioCompanies(){
  if(globalThis.POST_W99_PORTFOLIO_COMPANIES)return;
  globalThis.POST_W99_PORTFOLIO_COMPANIES=true;

  const state={payload:null,loading:false,ownerMode:false};
  const allCompanies=()=>typeof marketingOpsState!=='undefined'&&!marketingOpsState.selectedCompanyId;

  function styles(){
    if(document.querySelector('#post-w99-portfolio-companies-style'))return;
    const style=document.createElement('style');style.id='post-w99-portfolio-companies-style';style.textContent=`
      .pco-hero,.pco-summary,.pco-card,.pco-owner{border:1px solid #dedad2;background:#fff;border-radius:14px}.pco-hero{padding:15px;display:flex;justify-content:space-between;gap:14px;align-items:flex-start}.pco-hero h3{font-size:19px;margin:0 0 5px}.pco-actions,.pco-meta,.pco-steps{display:flex;gap:6px;flex-wrap:wrap}.pco-summary{padding:10px;display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}.pco-stat{background:#faf9f6;border:1px solid #ece8e0;border-radius:10px;padding:9px}.pco-stat strong{display:block;font-size:18px}.pco-stat span{font-size:7px;color:#777168}.pco-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.pco-card{padding:12px;display:grid;gap:10px}.pco-card.attention{border-left:4px solid #171717}.pco-head{display:flex;justify-content:space-between;gap:8px}.pco-head h4{margin:0;font-size:11px}.pco-percent{font-size:17px;font-weight:700}.pco-bar{height:7px;background:#eeeae3;border-radius:999px;overflow:hidden}.pco-bar>span{display:block;height:100%;background:#171717}.pco-chip{font-size:7px;padding:4px 6px;border-radius:999px;background:#f1eee8}.pco-chip.ready{background:#171717;color:#fff}.pco-next{padding:9px;border-radius:10px;background:#f5f2eb;display:flex;justify-content:space-between;gap:8px;align-items:center}.pco-next p{font-size:8px;margin:2px 0 0;color:#716b62}.pco-note,.pco-empty{padding:10px;border-radius:9px;background:#f5f2eb;color:#756f65;font-size:8px;line-height:1.45}.pco-owner{margin-bottom:10px;padding:9px;display:flex;justify-content:space-between;gap:8px;align-items:center;font-size:8px}@media(max-width:850px){.pco-grid{grid-template-columns:1fr}.pco-summary{grid-template-columns:repeat(2,minmax(0,1fr))}.pco-hero,.pco-next,.pco-owner{display:grid}}
    `;document.head.append(style);
  }

  async function load(force=false){
    if(state.loading)return state.payload;if(!force&&state.payload)return state.payload;state.loading=true;
    try{state.payload=await opsApi('/api/portfolio/companies');return state.payload}catch(err){state.payload=null;opsToast(err.message);return null}finally{state.loading=false}
  }

  function stat(value,label){const box=opsEl('div','pco-stat');box.append(opsEl('strong','',String(value||0)),opsEl('span','',label));return box}

  async function openOwner(companyId,view='companies'){
    state.ownerMode=false;
    if(typeof globalThis.portfolioNavigate==='function'){await globalThis.portfolioNavigate(companyId,{view});return}
    marketingOpsState.selectedCompanyId=companyId;try{localStorage.setItem('marketingOpsCompany',companyId)}catch(_err){}if(typeof fillCompanyFilter==='function')fillCompanyFilter();if(typeof globalThis.refreshMarketingOps==='function')await globalThis.refreshMarketingOps(false);if(typeof opsShowView==='function')opsShowView(view);
  }

  function card(row){
    const readiness=row.readiness||{},next=row.next_action||{},node=opsEl('article',`pco-card ${row.status==='READY'?'':'attention'}`),head=opsEl('div','pco-head'),copy=opsEl('div','');copy.append(opsEl('h4','',row.company?.name||'Empresa'),opsEl('p','muted',row.status==='LOCAL_STATE_ERROR'?'Lectura local no disponible':row.status==='READY'?'Flujo base completo':'Configuración incompleta'));head.append(copy,opsEl('span','pco-percent',`${readiness.percent||0}%`));node.append(head);const bar=opsEl('div','pco-bar'),fill=opsEl('span','');fill.style.width=`${Math.max(0,Math.min(100,readiness.percent||0))}%`;bar.append(fill);node.append(bar);
    const steps=opsEl('div','pco-steps');(readiness.steps||[]).forEach(step=>steps.append(opsEl('span',`pco-chip ${step.ready?'ready':''}`,`${step.ready?'✓':'○'} ${step.label}`)));node.append(steps);
    const nextBox=opsEl('div','pco-next'),nextCopy=opsEl('div','');nextCopy.append(opsEl('strong','',next.label||'Abrir empresa'),opsEl('p','',next.code||''));const go=opsEl('button',row.status==='READY'?'':'primary','Ir');go.type='button';go.addEventListener('click',()=>openOwner(row.company?.id,next.view||'companies'));nextBox.append(nextCopy,go);node.append(nextBox);return node;
  }

  function renderPortfolio(){
    if(marketingOpsState.view!=='companies'||!allCompanies()||state.ownerMode)return false;styles();const root=document.querySelector('#marketing-ops-view');if(!root)return false;root.replaceChildren();document.querySelector('#marketing-ops-eyebrow').textContent='EMPRESAS / MULTIEMPRESA';document.querySelector('#marketing-ops-title').textContent='Empresas';document.querySelector('#marketing-ops-subtitle').textContent='Qué está listo, qué falta y cuál es la siguiente acción por marca.';
    const hero=opsEl('section','pco-hero'),copy=opsEl('div','');copy.append(opsEl('p','eyebrow','ONBOARDING · ESTADO LOCAL'),opsEl('h3','','Preparación operativa'),opsEl('p','muted','W50 conserva la verdad de readiness. Esta vista no consulta Meta ni cambia cuentas.'));const actions=opsEl('div','pco-actions'),refresh=opsEl('button','','Actualizar lectura local'),create=opsEl('button','primary','+ Nueva empresa');refresh.type=create.type='button';refresh.addEventListener('click',async()=>{await load(true);renderPortfolio()});create.addEventListener('click',()=>{state.ownerMode=true;baseRender();if(typeof primaryNavigationEnsure==='function')primaryNavigationEnsure()});actions.append(refresh,create);hero.append(copy,actions);root.append(hero);
    if(!state.payload){root.append(opsEl('div','pco-empty','Componiendo readiness local de todas las empresas…'));load(true).then(()=>{if(marketingOpsState.view==='companies'&&allCompanies()&&!state.ownerMode)renderPortfolio()});return true}
    const s=state.payload.summary||{},summary=opsEl('section','pco-summary');summary.append(stat(s.companies,'EMPRESAS'),stat(s.fully_ready,'LISTAS'),stat(s.needs_setup,'POR COMPLETAR'),stat(`${s.average_percent||0}%`,'PROMEDIO READINESS'));root.append(summary);
    const grid=opsEl('section','pco-grid');(state.payload.items||[]).forEach(row=>grid.append(card(row)));if(!(state.payload.items||[]).length)grid.append(opsEl('div','pco-empty','No hay empresas todavía. Usa “Nueva empresa” para crear la primera desde el módulo propietario.'));root.append(grid,opsEl('div','pco-note','Los pasos y porcentajes provienen de W50 Command Center. Las credenciales, IDs remotos y asociaciones Meta no se serializan en este portfolio.'));
    if(typeof primaryNavigationEnsure==='function')primaryNavigationEnsure();return true;
  }

  const baseRender=globalThis.renderMarketingOps;
  globalThis.renderMarketingOps=function(){if(renderPortfolio())return;const result=baseRender.apply(this,arguments);if(marketingOpsState.view==='companies'&&!allCompanies()){styles();const root=document.querySelector('#marketing-ops-view');if(root&&!root.querySelector('[data-pco-owner]')){const bar=opsEl('div','pco-owner');bar.dataset.pcoOwner='1';bar.append(opsEl('span','','Configurando la empresa activa. Las verificaciones y cambios permanecen en este módulo propietario.'));const back=opsEl('button','','Ver todas las empresas');back.type='button';back.addEventListener('click',async()=>{state.ownerMode=false;marketingOpsState.selectedCompanyId=null;try{localStorage.setItem('marketingOpsCompany','')}catch(_err){}if(typeof fillCompanyFilter==='function')fillCompanyFilter();state.payload=null;await globalThis.refreshMarketingOps(false);renderPortfolio()});bar.append(back);root.prepend(bar)}}return result};

  const baseRefresh=globalThis.refreshMarketingOps;
  globalThis.refreshMarketingOps=async function(forceMeta=false){
    if(marketingOpsState.view==='companies'&&allCompanies()){
      try{marketingOpsState.companies=await opsApi('/api/companies');if(typeof fillCompanyFilter==='function')fillCompanyFilter();const [dashboard,calendar]=await Promise.all([opsApi('/api/ops/dashboard'),opsApi('/api/ops/calendar')]);marketingOpsState.dashboard=dashboard;marketingOpsState.calendar=calendar||[];state.payload=null;await load(true);globalThis.renderMarketingOps()}catch(err){opsToast(err.message)}return;
    }
    return baseRefresh.call(this,forceMeta);
  };

  if(marketingOpsState?.view==='companies'&&allCompanies())renderPortfolio();
})();
