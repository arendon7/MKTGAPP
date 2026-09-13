(function installPostW99PilotLaunchGate(){
  if(globalThis.POST_W99_PILOT_LAUNCH_GATE)return;
  globalThis.POST_W99_PILOT_LAUNCH_GATE=true;

  const SESSION_API='/api/pilot-session/status';
  const COMPANIES_API='/api/portfolio/companies';
  const state={open:false,busy:false,session:null,companies:null,error:null};

  function ensureStyles(){
    if(document.querySelector('#post-w99-pilot-launch-gate-style'))return;
    const style=document.createElement('style');style.id='post-w99-pilot-launch-gate-style';style.textContent=`
      .pilot-launch-action{margin-left:7px}.pilot-launch-action button{border:1px solid #171717;background:#171717;color:#fff;border-radius:7px;padding:7px 10px;cursor:pointer;font:inherit}.pilot-launch-panel{position:fixed;inset:6vh 7vw;z-index:10070;background:#fff;border:1px solid #d8d3ca;border-radius:16px;box-shadow:0 20px 70px rgba(0,0,0,.18);padding:18px;overflow:auto;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}.pilot-launch-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.pilot-launch-head h3{margin:3px 0}.pilot-launch-summary{margin-top:12px;padding:13px;border-radius:12px;background:#f4f1eb;display:flex;justify-content:space-between;gap:12px;align-items:center}.pilot-launch-summary.pass{background:#171717;color:#fff}.pilot-launch-summary strong{font-size:13px}.pilot-launch-summary span{font-size:9px}.pilot-launch-grid{display:grid;gap:8px;margin-top:12px}.pilot-launch-row{border:1px solid #e1ddd5;border-radius:11px;padding:11px;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px;align-items:center}.pilot-launch-copy{display:grid;gap:4px}.pilot-launch-copy strong{font-size:11px}.pilot-launch-copy span{font-size:9px;color:#6e6961;line-height:1.45}.pilot-launch-badge{font-size:8px;padding:4px 7px;border-radius:999px;background:#eeeae3;width:max-content}.pilot-launch-badge.pass{background:#171717;color:#fff}.pilot-launch-actions{display:flex;gap:7px;flex-wrap:wrap;margin-top:12px}.pilot-launch-note,.pilot-launch-error{margin-top:12px;padding:11px;border-radius:10px;font-size:9px;line-height:1.5}.pilot-launch-note{background:#f4f1eb}.pilot-launch-error{background:#fbefec;color:#5f2721}@media(max-width:760px){.pilot-launch-panel{inset:3vh 3vw}.pilot-launch-row{grid-template-columns:1fr}.pilot-launch-summary{align-items:flex-start;flex-direction:column}}
    `;document.head.append(style);
  }

  function suppressLegacyActions(){
    document.querySelector('.pilot-session-action')?.remove();
    document.querySelector('.pilot-journey-action')?.remove();
    document.querySelector('.pilot-data-safety-action')?.remove();
  }

  function closeGate(){state.open=false;document.querySelector('#post-w99-pilot-launch-gate-panel')?.remove()}

  async function getJson(path){
    const response=await fetch(path,{method:'GET',cache:'no-store'});
    const payload=await response.json().catch(()=>({error:'Respuesta local inválida'}));
    if(!response.ok)throw new Error(payload.error||`Error local ${response.status}`);
    return payload;
  }

  function journey(){try{return typeof globalThis.pilotJourneyReport==='function'?globalThis.pilotJourneyReport():null}catch(_error){return null}}
  function recovery(){try{return typeof globalThis.pilotRecoveryRehearsalReport==='function'?globalThis.pilotRecoveryRehearsalReport():null}catch(_error){return null}}

  function report(){
    const session=state.session,companies=state.companies,j=journey(),r=recovery(),summary=companies?.summary||{},snapshot=session?.snapshot||{};
    const runtimePass=Boolean(session&&session.backend?.status==='OK'&&session.local_data?.status==='OK');
    const companiesPass=Boolean(companies&&Number(summary.companies)>0&&Number(summary.local_state_errors)===0);
    const journeyPass=Boolean(j?.ready);
    const snapshotPass=Boolean(snapshot.status==='AVAILABLE'&&snapshot.latest?.id);
    const recoveryPass=Boolean(snapshotPass&&r?.status==='PASS'&&r.snapshot_id===snapshot.latest.id&&r.active_data_unchanged&&r.workspace_cleaned);
    const checks=[
      {id:'runtime',label:'Aplicación local',pass:runtimePass,detail:runtimePass?`${Number(session.local_data?.ready)||0}/${Number(session.local_data?.total)||0} fuentes de datos disponibles.`:'La aplicación local o una lectura base requiere revisión.'},
      {id:'companies',label:'Empresas',pass:companiesPass,detail:companies?`${Number(summary.companies)||0} empresa(s) · ${Number(summary.fully_ready)||0} con preparación completa · promedio ${Number(summary.average_percent)||0}%.`:'No se pudo leer el estado local de empresas.'},
      {id:'journey',label:'Recorrido observado',pass:journeyPass,detail:j?`${Number(j.pass)||0}/${Number(j.total)||0} rutas verificadas en modo ${j.mode==='COMPANY'?'empresa':'todas las empresas'}.`:'El recorrido todavía no tiene evidencia en esta sesión.'},
      {id:'snapshot',label:'Respaldo local',pass:snapshotPass,detail:snapshotPass?`Hay ${Number(snapshot.count)||0} respaldo(s); se usará el más reciente.`:'Crea al menos un respaldo local antes de iniciar el piloto.'},
      {id:'recovery',label:'Recuperación ensayada',pass:recoveryPass,detail:recoveryPass?`El respaldo más reciente fue probado en aislamiento: ${Number(r.files_checked)||0} archivos.`:'Prueba la recuperación del respaldo más reciente durante esta sesión.'},
    ];
    const passed=checks.filter(row=>row.pass).length;
    return {schema:'binario.marketing.pilot-launch-gate.v1',ready:passed===checks.length,passed,total:checks.length,checks,journey:j,recovery:r};
  }

  async function refresh(){
    if(state.busy)return;state.busy=true;state.error=null;if(state.open)render();
    try{[state.session,state.companies]=await Promise.all([getJson(SESSION_API),getJson(COMPANIES_API)])}catch(error){state.error=String(error?.message||error)}finally{state.busy=false;if(state.open)render()}
  }

  function handoff(callback){closeGate();callback()}
  function openView(view){handoff(()=>{if(typeof globalThis.opsShowView==='function')globalThis.opsShowView(view)})}

  function rowNode(row){
    const item=document.createElement('article');item.className='pilot-launch-row';const copy=document.createElement('div');copy.className='pilot-launch-copy';const title=document.createElement('strong');title.textContent=row.label;const badge=document.createElement('span');badge.className=`pilot-launch-badge ${row.pass?'pass':''}`;badge.textContent=row.pass?'LISTO':'PENDIENTE';const detail=document.createElement('span');detail.textContent=row.detail;copy.append(title,badge,detail);item.append(copy);
    const action=document.createElement('button');action.type='button';
    if(row.id==='companies'){action.textContent='Abrir empresas';action.addEventListener('click',()=>openView('companies'))}
    else if(row.id==='journey'){action.textContent='Abrir recorrido';action.disabled=typeof globalThis.pilotJourneyShow!=='function';action.addEventListener('click',()=>handoff(()=>globalThis.pilotJourneyShow?.()))}
    else if(row.id==='snapshot'||row.id==='recovery'){action.textContent='Abrir respaldo';action.disabled=typeof globalThis.pilotDataSafetyOpen!=='function';action.addEventListener('click',()=>handoff(()=>globalThis.pilotDataSafetyOpen?.()))}
    else{action.textContent='Actualizar';action.addEventListener('click',()=>refresh())}
    item.append(action);return item;
  }

  function render(){
    ensureStyles();suppressLegacyActions();document.querySelector('#post-w99-pilot-launch-gate-panel')?.remove();
    const panel=document.createElement('section');panel.id='post-w99-pilot-launch-gate-panel';panel.className='pilot-launch-panel';state.open=true;
    const head=document.createElement('div');head.className='pilot-launch-head';const copy=document.createElement('div');const eyebrow=document.createElement('p');eyebrow.className='eyebrow';eyebrow.textContent='PILOTO · PUERTA DE INICIO';const title=document.createElement('h3');title.textContent='Preparación piloto';const desc=document.createElement('p');desc.className='muted';desc.textContent='Consolida las verificaciones locales necesarias antes de iniciar el piloto operativo de MERCADEO APP.';copy.append(eyebrow,title,desc);const close=document.createElement('button');close.type='button';close.textContent='Cerrar';close.addEventListener('click',closeGate);head.append(copy,close);panel.append(head);
    if(state.error){const error=document.createElement('div');error.className='pilot-launch-error';error.textContent=state.error;panel.append(error)}
    const r=report();const summary=document.createElement('div');summary.className=`pilot-launch-summary ${r.ready?'pass':''}`;const s1=document.createElement('strong');s1.textContent=r.ready?'LISTO PARA PILOTO LOCAL':'PILOTO AÚN NO HABILITADO';const s2=document.createElement('span');s2.textContent=`${r.passed}/${r.total} controles listos`;summary.append(s1,s2);panel.append(summary);
    const grid=document.createElement('div');grid.className='pilot-launch-grid';r.checks.forEach(row=>grid.append(rowNode(row)));panel.append(grid);
    const actions=document.createElement('div');actions.className='pilot-launch-actions';const reload=document.createElement('button');reload.type='button';reload.disabled=state.busy;reload.textContent=state.busy?'Comprobando…':'Actualizar controles';reload.addEventListener('click',()=>refresh());actions.append(reload);panel.append(actions);
    const note=document.createElement('div');note.className='pilot-launch-note';note.textContent='Este gate habilita únicamente el piloto local. No acredita producción, publicación remota, UAT física, release 0.9.0 ni que todas las empresas tengan preparación W50 completa. Las conexiones y mutaciones siguen perteneciendo a sus módulos propietarios.';panel.append(note);document.body.append(panel);window.dispatchEvent(new CustomEvent('post-w99-pilot-launch-gate-rendered',{detail:{ready:r.ready,passed:r.passed,total:r.total}}));return r;
  }

  function installAction(){suppressLegacyActions();ensureStyles();const top=document.querySelector('.marketing-ops-top');if(!top||top.querySelector('.pilot-launch-action'))return;const wrap=document.createElement('div');wrap.className='pilot-launch-action';const button=document.createElement('button');button.type='button';button.textContent='Preparación piloto';button.addEventListener('click',async()=>{render();await refresh()});wrap.append(button);top.append(wrap)}

  window.addEventListener('marketing-ops-refreshed',()=>{installAction();if(state.open)render()});
  window.addEventListener('wave73-entry-ready',installAction);
  window.addEventListener('wave73-bootstrap-ready',installAction);
  window.addEventListener('post-w99-pilot-journey-observed',()=>{if(state.open)render()});
  window.addEventListener('post-w99-pilot-recovery-rehearsed',()=>{if(state.open)render()});
  globalThis.pilotLaunchGateOpen=()=>{render();return refresh()};
  globalThis.pilotLaunchGateClose=closeGate;
  globalThis.pilotLaunchGateReport=report;
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(installAction,0),{once:true});else setTimeout(installAction,0);
})();
