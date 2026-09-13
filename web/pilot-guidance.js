(function installPostW99PilotGuidance(){
  if(globalThis.POST_W99_PILOT_GUIDANCE)return;
  globalThis.POST_W99_PILOT_GUIDANCE=true;

  const state={payload:null,loading:false,error:null};
  const guidedViews=new Set(['today-execution','companies','content','calendar','crm','inbox','intelligence','campaigns','pauta','publish']);

  function selectedCompany(){
    if(typeof marketingOpsState==='undefined'||!marketingOpsState.selectedCompanyId)return null;
    return (marketingOpsState.companies||[]).find(row=>row.id===marketingOpsState.selectedCompanyId)||null;
  }

  function eligible(){return Boolean(selectedCompany()&&guidedViews.has(marketingOpsState.view))}

  function ensureStyles(){
    if(document.querySelector('#post-w99-pilot-guidance-style'))return;
    const style=document.createElement('style');style.id='post-w99-pilot-guidance-style';style.textContent=`
      .pilot-guide{margin:0 0 10px;padding:10px 12px;border:1px solid #dedad2;border-radius:12px;background:#fff;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px;align-items:center}.pilot-guide.attention{border-left:4px solid #171717}.pilot-guide.error{border-left:4px solid #8a8174}.pilot-guide-copy{display:grid;gap:4px}.pilot-guide-head{display:flex;gap:7px;align-items:center;flex-wrap:wrap}.pilot-guide-head strong{font-size:10px}.pilot-guide-copy p{margin:0;color:#746e65;font-size:8px;line-height:1.45}.pilot-guide-progress{display:flex;gap:5px;flex-wrap:wrap}.pilot-guide-chip{font-size:7px;padding:4px 6px;border-radius:999px;background:#f1eee8}.pilot-guide-chip.ready{background:#171717;color:#fff}.pilot-guide-actions{display:flex;gap:6px;align-items:center;flex-wrap:wrap}.pilot-guide-actions button{white-space:nowrap}@media(max-width:760px){.pilot-guide{grid-template-columns:1fr}.pilot-guide-actions{justify-content:flex-start}}
    `;document.head.append(style);
  }

  async function load(force=false){
    if(state.loading)return state.payload;
    if(!force&&state.payload)return state.payload;
    state.loading=true;state.error=null;
    try{state.payload=await opsApi('/api/portfolio/companies');return state.payload}
    catch(err){state.payload=null;state.error=String(err?.message||err);return null}
    finally{state.loading=false}
  }

  function currentRow(){
    const company=selectedCompany();if(!company||!state.payload)return null;
    return (state.payload.items||[]).find(row=>row.company?.id===company.id)||null;
  }

  async function openOwner(action){
    const company=selectedCompany();if(!company)return;
    const view=action?.view||'companies';
    marketingOpsState.selectedCompanyId=company.id;
    try{localStorage.setItem('marketingOpsCompany',company.id)}catch(_err){}
    if(typeof fillCompanyFilter==='function')fillCompanyFilter();
    if(typeof opsShowView==='function')opsShowView(view);
    if(typeof globalThis.refreshMarketingOps==='function')await globalThis.refreshMarketingOps(view==='companies');
  }

  function button(label,handler,primary=false){const node=opsEl('button',primary?'primary':'',label);node.type='button';node.addEventListener('click',handler);return node}
  function removeExisting(){document.querySelector('[data-post-w99-pilot-guide]')?.remove()}

  function render(){
    removeExisting();if(!eligible())return;
    const root=document.querySelector('#marketing-ops-view');if(!root)return;
    ensureStyles();

    if(!state.payload&&!state.error){
      const box=opsEl('section','pilot-guide');box.dataset.postW99PilotGuide='1';const copy=opsEl('div','pilot-guide-copy');copy.append(opsEl('div','pilot-guide-head',''),opsEl('p','','Leyendo preparación operativa local…'));box.append(copy);root.prepend(box);load().then(render);return;
    }

    if(state.error){
      const box=opsEl('section','pilot-guide error');box.dataset.postW99PilotGuide='1';const copy=opsEl('div','pilot-guide-copy'),head=opsEl('div','pilot-guide-head');head.append(opsEl('strong','','Preparación operativa no disponible'));copy.append(head,opsEl('p','',`No se pudo leer el estado local de W50. ${state.error.slice(0,180)}`));const actions=opsEl('div','pilot-guide-actions');actions.append(button('Reintentar lectura local',async()=>{await load(true);render()},true));box.append(copy,actions);root.prepend(box);return;
    }

    const row=currentRow();if(!row)return;
    const readiness=row.readiness||{},steps=readiness.steps||[],missing=steps.find(step=>!step.ready),next=row.next_action||{};
    const complete=row.status==='READY';
    const box=opsEl('section',`pilot-guide ${complete?'':'attention'} ${row.status==='LOCAL_STATE_ERROR'?'error':''}`.trim());box.dataset.postW99PilotGuide='1';
    const copy=opsEl('div','pilot-guide-copy'),head=opsEl('div','pilot-guide-head');
    head.append(opsEl('strong','',row.status==='LOCAL_STATE_ERROR'?'Estado local incompleto':complete?'Empresa lista para operar':'Preparación operativa incompleta'),opsEl('span',`pilot-guide-chip ${complete?'ready':''}`,`${readiness.ready||0}/${readiness.total||0} · ${readiness.percent||0}%`));
    copy.append(head);
    if(row.status==='LOCAL_STATE_ERROR')copy.append(opsEl('p','','W50 no pudo componer el estado local de esta empresa. No se infiere disponibilidad de Meta ni de los módulos operativos.'));
    else if(complete)copy.append(opsEl('p','','Los ocho pasos de readiness reportados por W50 están completos. Las acciones siguen sujetas a revisión humana y al estado real de cada módulo.'));
    else copy.append(opsEl('p','',missing?`Siguiente paso pendiente: ${missing.label}. Completa ese paso antes de asumir que Inbox, publicación o pauta están disponibles.`:'W50 reporta preparación incompleta. Abre la preparación de la empresa para resolver el siguiente paso.'));
    const chips=opsEl('div','pilot-guide-progress');steps.forEach(step=>chips.append(opsEl('span',`pilot-guide-chip ${step.ready?'ready':''}`,`${step.ready?'✓':'○'} ${step.label}`)));if(steps.length)copy.append(chips);
    const actions=opsEl('div','pilot-guide-actions');
    actions.append(button('Actualizar estado',async()=>{await load(true);render()}));
    if(row.status==='LOCAL_STATE_ERROR')actions.append(button('Abrir empresa',()=>openOwner({view:'companies'}),true));
    else if(complete)actions.append(button('Ver preparación',()=>openOwner({view:'companies'})));
    else actions.append(button(next.label||'Resolver preparación',()=>openOwner(next),true));
    box.append(copy,actions);root.prepend(box);
  }

  function wrapDirectRenderer(name){
    const original=globalThis[name];if(typeof original!=='function'||original.__postW99PilotGuided)return;
    const wrapped=function(){const result=original.apply(this,arguments);if(result&&typeof result.then==='function')return result.finally(render);render();return result};
    wrapped.__postW99PilotGuided=true;globalThis[name]=wrapped;
  }

  const baseRender=globalThis.renderMarketingOps;
  globalThis.renderMarketingOps=function(){const result=baseRender.apply(this,arguments);render();return result};
  ['inboxRenderCurrent','campaignRenderCurrent','contentRenderCurrent','wave65Render','renderWave47Pauta','renderCRMCurrent','renderOpsPublish','renderOpsCalendar','todayRender','todayPortfolioRender'].forEach(wrapDirectRenderer);

  window.addEventListener('marketing-ops-refreshed',()=>{state.payload=null;state.error=null;if(eligible())load(true).then(render);else removeExisting()});
  window.addEventListener('wave73-bootstrap-ready',()=>{if(eligible())load().then(render)});
  globalThis.postW99PilotGuidanceRender=render;
  if(eligible())load().then(render);
})();
