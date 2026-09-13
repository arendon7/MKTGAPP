(function installPostW99PilotJourneySmoke(){
  if(globalThis.POST_W99_PILOT_JOURNEY_SMOKE)return;
  globalThis.POST_W99_PILOT_JOURNEY_SMOKE=true;

  const PILOT_JOURNEY_STEPS=[
    {view:'today-execution',label:'Hoy'},
    {view:'companies',label:'Empresas'},
    {view:'inbox',label:'Inbox'},
    {view:'crm',label:'CRM'},
    {view:'content',label:'Contenido'},
    {view:'calendar',label:'Calendario'},
    {view:'campaigns',label:'Campañas'},
    {view:'pauta',label:'Pauta'},
    {view:'intelligence',label:'Resultados'},
    {view:'publish',label:'Publicar',requiresCompany:true},
  ];
  const state={visits:{PORTFOLIO:{},COMPANY:{}},panelOpen:false};

  function mode(){return marketingOpsState?.selectedCompanyId?'COMPANY':'PORTFOLIO'}
  function company(){return typeof globalThis.opsSelectedCompany==='function'?globalThis.opsSelectedCompany():null}
  function required(row,currentMode=mode()){return !(row.requiresCompany&&currentMode==='PORTFOLIO')}
  function navFor(view){return document.querySelector(`[data-ops-view="${view}"]`)}

  function ensureStyles(){
    if(document.querySelector('#post-w99-pilot-journey-style'))return;
    const s=document.createElement('style');s.id='post-w99-pilot-journey-style';s.textContent=`
      .pilot-journey-action{margin-left:7px}.pilot-journey-action button{border:1px solid #d8d3ca;background:#fff;border-radius:7px;padding:7px 9px;cursor:pointer;font:inherit}.pilot-journey-panel{position:fixed;inset:6vh 6vw;z-index:10030;background:#fff;border:1px solid #d8d3ca;border-radius:16px;box-shadow:0 20px 70px rgba(0,0,0,.18);padding:18px;overflow:auto;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}.pilot-journey-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.pilot-journey-head h3{margin:3px 0}.pilot-journey-meta{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}.pilot-journey-chip{font-size:8px;padding:5px 7px;border-radius:999px;background:#f1eee8}.pilot-journey-chip.pass{background:#171717;color:#fff}.pilot-journey-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-top:14px}.pilot-journey-row{border:1px solid #e1ddd5;border-radius:11px;padding:11px;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:9px;align-items:center}.pilot-journey-row.pass{background:#f1f6f2}.pilot-journey-row.fail{border-left:4px solid #171717}.pilot-journey-row.owner_only{background:#f7f4ef}.pilot-journey-copy{display:grid;gap:4px}.pilot-journey-copy strong{font-size:11px}.pilot-journey-copy span{font-size:9px;color:#6e6961;line-height:1.4}.pilot-journey-status{font-size:8px;padding:4px 6px;border-radius:999px;background:#eeeae3;width:max-content}.pilot-journey-row.pass .pilot-journey-status{background:#171717;color:#fff}.pilot-journey-summary{margin-top:12px;padding:11px;border-radius:10px;background:#f4f1eb;font-size:10px;line-height:1.45}.pilot-journey-actions{display:flex;gap:7px;align-items:center;flex-wrap:wrap}@media(max-width:760px){.pilot-journey-panel{inset:3vh 3vw}.pilot-journey-grid{grid-template-columns:1fr}.pilot-journey-row{grid-template-columns:1fr}.pilot-journey-actions{justify-content:flex-start}}
    `;document.head.append(s);
  }

  function suppressLegacy(){
    document.querySelector('.w73-journey-action')?.remove();
    document.querySelector('#wave73-journey-panel')?.remove();
  }

  function inspect(view){
    if(!PILOT_JOURNEY_STEPS.some(row=>row.view===view))return null;
    const currentMode=mode(),errors=[];
    const shell=document.querySelector('#marketing-ops-shell'),root=document.querySelector('#marketing-ops-view'),nav=navFor(view);
    if(marketingOpsState?.view!==view)errors.push('la vista activa no coincide');
    if(!shell||shell.classList.contains('marketing-ops-hidden'))errors.push('shell empresarial no visible');
    if(!root||root.textContent.trim().length<3)errors.push('vista sin contenido renderizado');
    if(!nav)errors.push('navegación no declarada');
    else if(!nav.classList.contains('active'))errors.push('navegación no sincronizada');
    const evidence={view,status:errors.length?'FAIL':'PASS',detail:errors.length?errors.join(' · '):'Vista abierta manualmente, shell visible y navegación sincronizada',checkedAt:new Date().toISOString()};
    state.visits[currentMode][view]=evidence;
    window.dispatchEvent(new CustomEvent('post-w99-pilot-journey-observed',{detail:{mode:currentMode,...evidence}}));
    if(state.panelOpen)pilotJourneyShow();
    return evidence;
  }

  function report(){
    const currentMode=mode(),seen=state.visits[currentMode],rows=PILOT_JOURNEY_STEPS.map(step=>{
      const isRequired=required(step,currentMode),nav=navFor(step.view),visit=seen[step.view];
      if(!isRequired)return {...step,required:false,status:'OWNER_ONLY',detail:'Disponible cuando selecciones una empresa exacta.'};
      if(!nav)return {...step,required:true,status:'FAIL',detail:'La navegación actual no declara esta vista.'};
      if(visit)return {...step,required:true,status:visit.status,detail:visit.detail,checkedAt:visit.checkedAt};
      return {...step,required:true,status:'READY',detail:'Ruta declarada; todavía no fue visitada en esta sesión.'};
    });
    const requiredRows=rows.filter(row=>row.required),pass=requiredRows.filter(row=>row.status==='PASS').length;
    return {schema:'binario.marketing.pilot-journey-smoke.v1',mode:currentMode,company:company()?{id:company().id,name:company().name}:null,pass,total:requiredRows.length,ready:pass===requiredRows.length,rows,checkedAt:new Date().toISOString(),safety:{automaticNavigation:false,providerReads:false,providerMutations:false,formSubmission:false,publishing:false,backgroundPolling:false}};
  }

  function statusLabel(status){return ({PASS:'PASS',READY:'POR VISITAR',FAIL:'REVISAR',OWNER_ONLY:'EMPRESA EXACTA'})[status]||status}

  function pilotJourneyOpen(row){
    if(row.requiresCompany&&mode()==='PORTFOLIO')return;
    if(typeof globalThis.opsShowView!=='function')return;
    globalThis.opsShowView(row.view);
    setTimeout(()=>inspect(row.view),350);
  }

  function rowNode(row){
    const item=document.createElement('article');item.className=`pilot-journey-row ${row.status.toLowerCase()}`;
    const copy=document.createElement('div');copy.className='pilot-journey-copy';const title=document.createElement('strong');title.textContent=row.label;const status=document.createElement('span');status.className='pilot-journey-status';status.textContent=statusLabel(row.status);const detail=document.createElement('span');detail.textContent=row.detail;copy.append(title,status,detail);
    const actions=document.createElement('div');actions.className='pilot-journey-actions';const open=document.createElement('button');open.type='button';open.textContent=row.status==='PASS'?'Abrir de nuevo':'Abrir';open.disabled=row.status==='OWNER_ONLY';open.addEventListener('click',()=>pilotJourneyOpen(row));actions.append(open);item.append(copy,actions);return item;
  }

  function pilotJourneyShow(){
    ensureStyles();suppressLegacy();document.querySelector('#post-w99-pilot-journey-panel')?.remove();
    const r=report(),panel=document.createElement('section');panel.id='post-w99-pilot-journey-panel';panel.className='pilot-journey-panel';state.panelOpen=true;
    const head=document.createElement('div');head.className='pilot-journey-head';const copy=document.createElement('div');const eyebrow=document.createElement('p');eyebrow.className='eyebrow';eyebrow.textContent='PILOTO · RECORRIDO OPERATIVO';const title=document.createElement('h3');title.textContent=r.ready?'Recorrido observado completo':'Recorrido de piloto';const desc=document.createElement('p');desc.className='muted';desc.textContent='Verificación pasiva: registra únicamente las vistas que tú abres. No navega sola, no consulta proveedores y no ejecuta acciones.';copy.append(eyebrow,title,desc);const chips=document.createElement('div');chips.className='pilot-journey-meta';const modeChip=document.createElement('span');modeChip.className='pilot-journey-chip';modeChip.textContent=r.mode==='COMPANY'?`Empresa · ${r.company?.name||'—'}`:'Todas las empresas';const score=document.createElement('span');score.className=`pilot-journey-chip ${r.ready?'pass':''}`;score.textContent=`${r.pass}/${r.total} PASS`;chips.append(modeChip,score);copy.append(chips);
    const close=document.createElement('button');close.type='button';close.textContent='Cerrar';close.addEventListener('click',()=>{state.panelOpen=false;panel.remove()});head.append(copy,close);panel.append(head);
    const grid=document.createElement('div');grid.className='pilot-journey-grid';r.rows.forEach(row=>grid.append(rowNode(row)));panel.append(grid);
    const summary=document.createElement('div');summary.className='pilot-journey-summary';summary.textContent=r.ready?'Todas las rutas requeridas para este modo fueron abiertas y renderizadas durante esta sesión. Esto valida navegación local; no demuestra publicación, entrega de proveedor ni producción.':`Faltan ${r.total-r.pass} ruta(s) requeridas por observar. Abre cada paso manualmente; el smoke registra el resultado después del render.`;panel.append(summary);
    const footer=document.createElement('div');footer.className='pilot-journey-actions';footer.style.marginTop='10px';const reset=document.createElement('button');reset.type='button';reset.textContent='Reiniciar evidencia de sesión';reset.addEventListener('click',()=>{state.visits[r.mode]={};pilotJourneyShow()});footer.append(reset);panel.append(footer);document.body.append(panel);return r;
  }

  function installAction(){
    suppressLegacy();ensureStyles();const top=document.querySelector('.marketing-ops-top');if(!top||top.querySelector('.pilot-journey-action'))return;const wrap=document.createElement('div');wrap.className='pilot-journey-action';const button=document.createElement('button');button.type='button';button.textContent='Recorrido piloto';button.addEventListener('click',()=>pilotJourneyShow());wrap.append(button);top.append(wrap);
  }

  document.addEventListener('click',event=>{const target=event.target instanceof Element?event.target.closest('[data-ops-view]'):null;if(!target)return;const view=target.dataset.opsView;if(PILOT_JOURNEY_STEPS.some(row=>row.view===view))setTimeout(()=>inspect(view),350)});
  window.addEventListener('marketing-ops-refreshed',()=>{installAction();setTimeout(()=>inspect(marketingOpsState?.view),250)});
  window.addEventListener('wave73-entry-ready',()=>{installAction();setTimeout(()=>inspect(marketingOpsState?.view),350)});
  window.addEventListener('wave73-bootstrap-ready',()=>{installAction();setTimeout(()=>inspect(marketingOpsState?.view),350)});

  globalThis.wave73RunJourneyCheck=pilotJourneyShow;
  globalThis.pilotJourneyShow=pilotJourneyShow;
  globalThis.pilotJourneyReport=report;
  globalThis.postW99PilotJourneyState=state;
  globalThis.POST_W99_PILOT_JOURNEY_STEPS=PILOT_JOURNEY_STEPS;
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(installAction,0),{once:true});else setTimeout(installAction,0);
})();
