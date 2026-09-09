(function installPostW99PortfolioCRM(){
  if(globalThis.POST_W99_PORTFOLIO_CRM)return;
  globalThis.POST_W99_PORTFOLIO_CRM=true;
  if(typeof globalThis.crmRenderCurrent!=='function')return;

  const state={payload:null,loading:false,mode:'PORTFOLIO',filter:'ALL'};
  let ownerNavigation=false;

  function styles(){
    if(document.querySelector('#post-w99-portfolio-crm-style'))return;
    const style=document.createElement('style');style.id='post-w99-portfolio-crm-style';style.textContent=`
.portfolio-crm-hero,.portfolio-crm-summary,.portfolio-crm-panel,.portfolio-crm-card{border:1px solid #dedad2;background:#fff;border-radius:14px}.portfolio-crm-hero{padding:15px;display:flex;justify-content:space-between;gap:14px;align-items:flex-start}.portfolio-crm-hero h3{font-size:19px;margin:0 0 5px}.portfolio-crm-hero p{margin:0}.portfolio-crm-actions,.portfolio-crm-filters,.portfolio-crm-meta{display:flex;gap:6px;flex-wrap:wrap}.portfolio-crm-summary{padding:10px;display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px}.portfolio-crm-stat{background:#faf9f6;border:1px solid #ece8e0;border-radius:10px;padding:9px}.portfolio-crm-stat strong{display:block;font-size:18px}.portfolio-crm-stat span{font-size:7px;color:#777168}.portfolio-crm-panel{padding:13px;display:grid;gap:10px}.portfolio-crm-toolbar{display:flex;justify-content:space-between;gap:10px;align-items:center}.portfolio-crm-filter.active{background:#171717;color:#fff}.portfolio-crm-list{display:grid;gap:8px}.portfolio-crm-card{padding:11px;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px;align-items:center}.portfolio-crm-copy{display:grid;gap:5px}.portfolio-crm-copy strong{font-size:10px}.portfolio-crm-copy p{font-size:8px;color:#716b62;line-height:1.45;margin:0}.portfolio-crm-chip{font-size:7px;padding:4px 6px;border-radius:999px;background:#f1eee8}.portfolio-crm-chip.company{background:#171717;color:#fff}.portfolio-crm-note,.portfolio-crm-empty{padding:10px;border-radius:9px;background:#f5f2eb;color:#756f65;font-size:8px;line-height:1.45}.portfolio-crm-empty{border:1px dashed #d9d4ca;background:#fff}.portfolio-crm-company-mode{margin-bottom:10px;padding:9px;border:1px solid #dedad2;border-radius:10px;background:#faf9f6;display:flex;justify-content:space-between;gap:8px;align-items:center;font-size:8px}@media(max-width:800px){.portfolio-crm-hero,.portfolio-crm-toolbar,.portfolio-crm-company-mode{display:grid}.portfolio-crm-summary{grid-template-columns:repeat(2,minmax(0,1fr))}.portfolio-crm-card{grid-template-columns:1fr}.portfolio-crm-card>button{width:100%}}
`;document.head.append(style)
  }

  async function load(force=false){
    if(state.loading)return state.payload;
    if(!force&&state.payload)return state.payload;
    state.loading=true;
    try{state.payload=await opsApi('/api/portfolio/crm');return state.payload}
    catch(err){state.payload=null;opsToast(err.message);return null}
    finally{state.loading=false}
  }

  function stat(value,label){const box=opsEl('div','portfolio-crm-stat');box.append(opsEl('strong','',String(value||0)),opsEl('span','',label));return box}
  function date(value){return value?(typeof opsDate==='function'?opsDate(value):String(value)):'Sin fecha'}
  function money(row){if(row?.value===null||row?.value===undefined)return 'Sin valor';return `${row.currency||'COP'} ${Number(row.value||0).toLocaleString()}`}
  function opportunityDue(row){return row?.followup?.next_due_at||row?.next_action_at||null}
  function isOverdueOpportunity(row){return ['OVERDUE_FOLLOWUP','OVERDUE_NEXT_ACTION'].includes(String(row?.attention?.code||''))}
  function isUnscheduledOpportunity(row){return ['NO_FOLLOWUP','UNSCHEDULED_NEXT_ACTION','UNSCHEDULED_FOLLOWUP'].includes(String(row?.attention?.code||''))}
  function opportunities(){const rows=Array.isArray(state.payload?.opportunities)?state.payload.opportunities:[];if(state.filter==='ACTIVITY'||state.filter==='TODAY')return [];if(state.filter==='OVERDUE')return rows.filter(isOverdueOpportunity);if(state.filter==='UNSCHEDULED')return rows.filter(isUnscheduledOpportunity);return rows}
  function activities(){const rows=Array.isArray(state.payload?.activities)?state.payload.activities:[];if(state.filter==='OPPORTUNITY')return [];if(state.filter==='OVERDUE')return rows.filter(row=>row.kind==='crm_overdue');if(state.filter==='TODAY')return rows.filter(row=>row.kind==='crm_today');if(state.filter==='UNSCHEDULED')return rows.filter(row=>row.kind==='crm_unscheduled');return rows}

  async function openOwner(row){
    const companyId=String(row?.company?.id||'').trim(),action=row?.action||{view:'crm'};if(!companyId)return;
    state.mode='COMPANY';ownerNavigation=true;
    try{
      if(typeof crmState!=='undefined'&&action.tab)crmState.tab=action.tab;
      if(typeof globalThis.portfolioNavigate==='function')await globalThis.portfolioNavigate(companyId,action);
      if(typeof globalThis.actionCenterOpen==='function')globalThis.actionCenterOpen({kind:row.kind||`pipeline_${String(row?.attention?.code||'').toLowerCase()}`,title:row.title||row.label||'CRM',action});
    }finally{ownerNavigation=false}
  }

  function opportunityCard(row){
    const card=opsEl('article','portfolio-crm-card'),copy=opsEl('div','portfolio-crm-copy'),due=opportunityDue(row);copy.append(opsEl('strong','',row.title||'Oportunidad'),opsEl('p','',`${row.attention?.label||'Revisar oportunidad'} · ${row.stage||'Pipeline'} · ${money(row)}`));
    const meta=opsEl('div','portfolio-crm-meta');meta.append(opsEl('span','portfolio-crm-chip company',row.company?.name||'Empresa'),opsEl('span','portfolio-crm-chip',row.attention?.code||'ATENCIÓN'),opsEl('span','portfolio-crm-chip',due?date(due):'Sin fecha'));if((row.followup?.overdue_activities||0)>0)meta.append(opsEl('span','portfolio-crm-chip',`${row.followup.overdue_activities} seguimiento(s) vencido(s)`));copy.append(meta);const open=opsEl('button',isOverdueOpportunity(row)?'primary':'','Abrir oportunidad');open.type='button';open.addEventListener('click',()=>openOwner(row));card.append(copy,open);return card
  }

  function activityCard(row){
    const card=opsEl('article','portfolio-crm-card'),copy=opsEl('div','portfolio-crm-copy');copy.append(opsEl('strong','',row.label||'Seguimiento'),opsEl('p','',row.opportunity_title?`Oportunidad: ${row.opportunity_title}`:'Seguimiento CRM pendiente'));
    const meta=opsEl('div','portfolio-crm-meta');meta.append(opsEl('span','portfolio-crm-chip company',row.company?.name||'Empresa'),opsEl('span','portfolio-crm-chip',String(row.kind||'').replace('crm_','').toUpperCase()),opsEl('span','portfolio-crm-chip',date(row.due_at)));copy.append(meta);const open=opsEl('button',row.kind==='crm_overdue'?'primary':'','Abrir seguimiento');open.type='button';open.addEventListener('click',()=>openOwner(row));card.append(copy,open);return card
  }

  function renderPortfolio(){
    if(typeof marketingOpsState==='undefined'||marketingOpsState.view!=='crm'||state.mode!=='PORTFOLIO')return false;
    styles();const root=document.querySelector('#marketing-ops-view');if(!root)return false;root.replaceChildren();
    document.querySelector('#marketing-ops-eyebrow').textContent='CRM / MULTIEMPRESA';document.querySelector('#marketing-ops-title').textContent='CRM';document.querySelector('#marketing-ops-subtitle').textContent='Oportunidades y seguimientos que requieren atención en todas tus empresas. Cada cambio se ejecuta únicamente en el CRM propietario.';document.querySelectorAll('[data-ops-view]').forEach(button=>button.classList.toggle('active',button.dataset.opsView==='crm'));
    if(!state.payload){root.append(opsEl('div','portfolio-crm-empty','Construyendo CRM local de todas las empresas…'));load(true).then(renderPortfolio);return true}
    const summary=state.payload.summary||{},hero=opsEl('section','portfolio-crm-hero'),copy=opsEl('div','');copy.append(opsEl('p','eyebrow','TODAS LAS EMPRESAS · LOCAL'),opsEl('h3','','Control comercial transversal sin mezclar propietarios'),opsEl('p','muted','Oportunidades reutilizan la clasificación de Commercial Pipeline; seguimientos reutilizan Daily Workdesk. No existe un score nuevo entre ambos tipos.'));
    const actions=opsEl('div','portfolio-crm-actions'),refresh=opsEl('button','','Actualizar lectura local'),company=opsEl('button','','Ver empresa activa');refresh.type='button';refresh.addEventListener('click',async()=>{await load(true);renderPortfolio()});company.type='button';company.addEventListener('click',()=>{state.mode='COMPANY';globalThis.crmRenderCurrent()});actions.append(refresh,company);hero.append(copy,actions);root.append(hero);
    const stats=opsEl('section','portfolio-crm-summary');stats.append(stat(summary.open_opportunities,'OPORTUNIDADES ABIERTAS'),stat(summary.opportunity_attention,'OPORTUNIDADES CON ATENCIÓN'),stat(summary.pending_activities,'SEGUIMIENTOS PENDIENTES'),stat(summary.overdue_activities,'SEGUIMIENTOS VENCIDOS'),stat(summary.companies_with_attention,'EMPRESAS CON ATENCIÓN'));root.append(stats);
    const panel=opsEl('section','portfolio-crm-panel'),toolbar=opsEl('div','portfolio-crm-toolbar'),heading=opsEl('div','');heading.append(opsEl('p','eyebrow','ATENCIÓN COMERCIAL'),opsEl('h3','','Trabajo pendiente del portfolio'));const filters=opsEl('div','portfolio-crm-filters');[['ALL','Todo'],['OPPORTUNITY','Oportunidades'],['ACTIVITY','Seguimientos'],['OVERDUE','Vencidos'],['TODAY','Hoy'],['UNSCHEDULED','Sin fecha']].forEach(([key,label])=>{const button=opsEl('button',`portfolio-crm-filter ${state.filter===key?'active':''}`,label);button.type='button';button.addEventListener('click',()=>{state.filter=key;renderPortfolio()});filters.append(button)});toolbar.append(heading,filters);panel.append(toolbar);
    const opp=opportunities(),acts=activities();if(opp.length){panel.append(opsEl('p','eyebrow','OPORTUNIDADES · ORDEN WAVE63'));const list=opsEl('div','portfolio-crm-list');opp.forEach(row=>list.append(opportunityCard(row)));panel.append(list)}if(acts.length){panel.append(opsEl('p','eyebrow','SEGUIMIENTOS · ORDEN WORKDESK'));const list=opsEl('div','portfolio-crm-list');acts.forEach(row=>list.append(activityCard(row)));panel.append(list)}if(!opp.length&&!acts.length)panel.append(opsEl('div','portfolio-crm-empty','No hay trabajo CRM para este filtro.'));
    const scope=state.payload.scope||{};panel.append(opsEl('div','portfolio-crm-note',`${summary.active_companies||0} empresa(s) activas · ${scope.opportunity_displayed||0}/${scope.opportunity_total||0} oportunidades de atención · ${scope.activity_displayed||0}/${scope.activity_total||0} seguimientos de atención. La proyección omite teléfonos, emails, notas y datos de contacto; abrir entrega el control al CRM exacto.`));root.append(panel);return true
  }

  const baseCrmRender=globalThis.crmRenderCurrent;
  globalThis.crmRenderCurrent=function postW99PortfolioCRMRender(){
    if(marketingOpsState?.view==='crm'&&state.mode==='PORTFOLIO'){renderPortfolio();return}
    baseCrmRender.apply(this,arguments);
    if(marketingOpsState?.view!=='crm'||state.mode!=='COMPANY')return;
    styles();const root=document.querySelector('#marketing-ops-view');if(!root||root.querySelector('[data-portfolio-crm-company-mode]'))return;
    const bar=opsEl('div','portfolio-crm-company-mode');bar.dataset.portfolioCrmCompanyMode='1';bar.append(opsEl('span','','Estás trabajando en el CRM de la empresa activa. Formularios, etapas y seguimientos conservan aquí su autoridad canónica.'));const back=opsEl('button','','Volver a todas las empresas');back.type='button';back.addEventListener('click',()=>{state.mode='PORTFOLIO';load(true).then(renderPortfolio)});bar.append(back);root.prepend(bar)
  };

  if(typeof globalThis.portfolioNavigate==='function'){
    const basePortfolioNavigate=globalThis.portfolioNavigate;
    globalThis.portfolioNavigate=async function postW99PortfolioCRMNavigate(companyId,action){if(action?.view==='crm'){state.mode='COMPANY';ownerNavigation=true;try{return await basePortfolioNavigate(companyId,action)}finally{ownerNavigation=false}}return basePortfolioNavigate(companyId,action)};
  }
  if(typeof globalThis.opsShowView==='function'){
    const baseShowView=globalThis.opsShowView;
    globalThis.opsShowView=function postW99PortfolioCRMShowView(view){if(view==='crm'&&!ownerNavigation&&marketingOpsState?.view!=='crm')state.mode='PORTFOLIO';return baseShowView.apply(this,arguments)};
  }
  window.addEventListener('marketing-ops-refreshed',()=>{state.payload=null;if(marketingOpsState?.view==='crm'&&state.mode==='PORTFOLIO')load(true).then(renderPortfolio)});
  load();
})();
