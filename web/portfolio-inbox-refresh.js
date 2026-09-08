(function installPostW99PortfolioInboxRefresh(){
  if(globalThis.POST_W99_PORTFOLIO_INBOX_REFRESH)return;
  globalThis.POST_W99_PORTFOLIO_INBOX_REFRESH=true;

  const state={plan:null,loading:false,busy:false,lastResult:null};

  async function loadPlan(force=false){
    if(state.loading)return state.plan;
    if(!force&&state.plan)return state.plan;
    state.loading=true;
    try{state.plan=await opsApi('/api/portfolio/inbox-refresh-plan');return state.plan}
    catch(err){state.plan=null;opsToast(err.message);return null}
    finally{state.loading=false}
  }

  function statusText(){
    const summary=state.plan?.summary||{};
    if(!state.plan)return state.loading?'Leyendo estado local de Inbox…':'Estado de Inbox no disponible.';
    if(!(summary.configured_companies||0))return 'No hay empresas con Facebook o Instagram configurados.';
    const base=`${summary.configured_companies||0} bandeja(s) configuradas · ${summary.refresh_required||0} requieren actualización local`;
    if(!state.lastResult)return base;
    const result=state.lastResult.summary||{};
    return `${base} · última ejecución: ${result.refreshed||0}/${result.requested||0} actualizadas${result.failed?` · ${result.failed} fallaron`:''}`;
  }

  async function refreshLocalProjections(){
    const jobs=[];
    if(typeof globalThis.todayPortfolioLoad==='function')jobs.push(globalThis.todayPortfolioLoad(true));
    if(typeof globalThis.portfolioLoad==='function')jobs.push(globalThis.portfolioLoad());
    if(typeof globalThis.actionCenterLoad==='function')jobs.push(globalThis.actionCenterLoad(true));
    if(jobs.length)await Promise.allSettled(jobs);
  }

  async function run(button){
    if(state.busy)return null;
    const plan=await loadPlan(true);if(!plan)return null;
    const ids=Array.isArray(plan.company_ids)?plan.company_ids:[];
    const summary=plan.summary||{};
    if(!ids.length){opsToast('No hay bandejas configuradas para actualizar.');render();return null}
    if((summary.eligible_overflow||0)>0){opsToast('Hay más empresas configuradas que el límite seguro de esta operación.');return null}
    const confirmed=window.confirm(`Vas a consultar secuencialmente Meta para ${ids.length} empresa(s). Esto solo actualiza snapshots locales de Inbox: no responde mensajes, no comenta, no modifica CRM, no publica y no genera IA. ¿Continuar?`);
    if(!confirmed)return null;
    state.busy=true;if(button)button.disabled=true;
    try{
      state.lastResult=await opsApi('/api/portfolio/inbox-refresh',{method:'POST',body:{company_ids:ids}});
      await refreshLocalProjections();
      await loadPlan(true);
      const result=state.lastResult?.summary||{};
      opsToast(`Inbox multiempresa: ${result.refreshed||0}/${result.requested||0} actualizadas${result.failed?`; ${result.failed} fallaron`:''}`);
      return state.lastResult;
    }catch(err){opsToast(err.message);return null}
    finally{state.busy=false;render()}
  }

  function render(){
    if(typeof marketingOpsState==='undefined'||marketingOpsState.view!=='today-execution')return;
    const toolbar=document.querySelector('.today-portfolio-actions');if(!toolbar)return;
    let wrap=toolbar.querySelector('[data-portfolio-inbox-refresh]');
    if(!wrap){wrap=opsEl('div','');wrap.dataset.portfolioInboxRefresh='1';wrap.style.display='grid';wrap.style.gap='3px';const button=opsEl('button','','Actualizar Inbox de todas');button.type='button';button.dataset.portfolioInboxRefreshButton='1';button.addEventListener('click',()=>run(button));const note=opsEl('span','','');note.dataset.portfolioInboxRefreshStatus='1';note.style.fontSize='7px';note.style.color='#777168';note.style.maxWidth='260px';wrap.append(button,note);toolbar.prepend(wrap)}
    const button=wrap.querySelector('[data-portfolio-inbox-refresh-button]'),note=wrap.querySelector('[data-portfolio-inbox-refresh-status]');
    if(button)button.disabled=state.busy||state.loading||Boolean((state.plan?.summary||{}).eligible_overflow);
    if(note)note.textContent=statusText();
    if(!state.plan&&!state.loading)loadPlan().then(render);
  }

  globalThis.postW99PortfolioInboxRefreshRun=run;
  globalThis.postW99PortfolioInboxRefreshLoadPlan=loadPlan;

  if(typeof globalThis.todayPortfolioRender==='function'){
    const baseRender=globalThis.todayPortfolioRender;
    globalThis.todayPortfolioRender=function postW99PortfolioInboxRefreshRender(){const value=baseRender.apply(this,arguments);queueMicrotask(render);return value};
  }
  const baseMarketingRender=globalThis.renderMarketingOps;
  if(typeof baseMarketingRender==='function')globalThis.renderMarketingOps=function postW99PortfolioInboxRefreshMarketingRender(){const value=baseMarketingRender.apply(this,arguments);queueMicrotask(render);return value};
  window.addEventListener('marketing-ops-refreshed',()=>{state.plan=null;loadPlan(true).then(render)});
  loadPlan();queueMicrotask(render);
})();
