(function installPostW99PilotHealthSummary(){
  if(globalThis.POST_W99_PILOT_HEALTH_SUMMARY)return;
  globalThis.POST_W99_PILOT_HEALTH_SUMMARY=true;

  const RECEIPTS_API='/api/pilot/daily-receipts?limit=90';
  const INCIDENTS_API='/api/pilot/incidents?status=ALL&limit=100';
  const WINDOW_DAYS=30;
  const RECENT_DAYS=7;
  const state={busy:false,receipts:null,incidents:null,error:null};

  function ensureStyles(){
    if(document.querySelector('#post-w99-pilot-health-summary-style'))return;
    const style=document.createElement('style');style.id='post-w99-pilot-health-summary-style';style.textContent=`
      .pilot-health-panel{position:fixed;inset:6vh 8vw;z-index:10150;background:#fff;border:1px solid #d8d3ca;border-radius:16px;box-shadow:0 20px 70px rgba(0,0,0,.22);padding:18px;overflow:auto;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}.pilot-health-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.pilot-health-head h3{margin:3px 0}.pilot-health-state{margin-top:14px;border-radius:13px;padding:14px;background:#f4f1eb;display:flex;justify-content:space-between;gap:12px;align-items:center}.pilot-health-state strong{font-size:14px}.pilot-health-state span{font-size:9px}.pilot-health-state.stable{background:#171717;color:#fff}.pilot-health-state.blocked{background:#5f2721;color:#fff}.pilot-health-state.attention{background:#fbefec;color:#5f2721}.pilot-health-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin:12px 0}.pilot-health-metric{border:1px solid #e1ddd5;border-radius:11px;padding:11px;display:grid;gap:4px}.pilot-health-metric strong{font-size:15px}.pilot-health-metric span{font-size:8px;color:#6e6961}.pilot-health-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}.pilot-health-card{border:1px solid #e1ddd5;border-radius:12px;padding:12px}.pilot-health-card h4{margin:0 0 8px;font-size:11px}.pilot-health-card p{margin:5px 0;font-size:9px;line-height:1.45;color:#6e6961}.pilot-health-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}.pilot-health-note,.pilot-health-error{margin-top:12px;padding:11px;border-radius:10px;font-size:9px;line-height:1.5}.pilot-health-note{background:#f4f1eb}.pilot-health-error{background:#fbefec;color:#5f2721}@media(max-width:760px){.pilot-health-panel{inset:3vh 3vw}.pilot-health-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.pilot-health-grid{grid-template-columns:1fr}}
    `;document.head.append(style);
  }

  function localDate(date=new Date()){const y=date.getFullYear();const m=String(date.getMonth()+1).padStart(2,'0');const d=String(date.getDate()).padStart(2,'0');return `${y}-${m}-${d}`}
  function shiftDate(date,delta){const copy=new Date(date.getFullYear(),date.getMonth(),date.getDate());copy.setDate(copy.getDate()+delta);return copy}
  function dateMs(value){const n=new Date(value).getTime();return Number.isFinite(n)?n:0}

  async function getJson(path){const response=await fetch(path,{method:'GET',cache:'no-store'});const payload=await response.json().catch(()=>({error:'Respuesta local inválida'}));if(!response.ok)throw new Error(payload.error||`Error local ${response.status}`);return payload}

  function report(){
    const today=new Date();const todayKey=localDate(today);const windowKeys=[];for(let i=WINDOW_DAYS-1;i>=0;i--)windowKeys.push(localDate(shiftDate(today,-i)));
    const windowSet=new Set(windowKeys);const latestByDay=new Map();
    for(const row of state.receipts?.receipts||[]){const key=String(row.local_date||'');if(!windowSet.has(key))continue;const current=latestByDay.get(key);if(!current||dateMs(row.recorded_at)>dateMs(current.recorded_at))latestByDay.set(key,row)}
    let readyDays=0,attentionDays=0;for(const row of latestByDay.values()){if(row.gate?.ready)readyDays++;else attentionDays++}
    const observedDays=latestByDay.size;const missingDays=Math.max(0,WINDOW_DAYS-observedDays);
    let streak=0;for(let i=0;i<WINDOW_DAYS;i++){if(latestByDay.has(localDate(shiftDate(today,-i))))streak++;else break}
    const recentKeys=new Set(Array.from({length:RECENT_DAYS},(_,i)=>localDate(shiftDate(today,-i))));let recentAttention=0;for(const [key,row] of latestByDay){if(recentKeys.has(key)&&!row.gate?.ready)recentAttention++}
    const todayReceipt=latestByDay.get(todayKey)||null;
    const incidentSummary=state.incidents?.summary||{};const openCount=Number(incidentSummary.open_count)||0;const blocking=Number(incidentSummary.blocking_open)||0;const high=Number(incidentSummary.high_open)||0;
    let status='NO_EVIDENCE',label='SIN EVIDENCIA',detail='Todavía no hay jornadas registradas dentro de la ventana de 30 días.';
    if(blocking>0){status='BLOCKED';label='BLOQUEADO';detail=`Hay ${blocking} incidencia(s) bloqueante(s) abierta(s).`}
    else if(observedDays===0){status='NO_EVIDENCE';label='SIN EVIDENCIA';detail='Registra jornadas para comenzar a evaluar estabilidad del piloto.'}
    else if(high>0||recentAttention>0||!todayReceipt||!todayReceipt.gate?.ready){status='ATTENTION';label='ATENCIÓN';detail=high>0?`Hay ${high} incidencia(s) alta(s) abierta(s).`:recentAttention>0?`${recentAttention} jornada(s) con pendientes en los últimos 7 días.`:!todayReceipt?'Hoy todavía no tiene jornada registrada.':'La jornada de hoy conserva pendientes.'}
    else{status='STABLE';label='ESTABLE';detail='La jornada de hoy está lista y no hay incidencias altas o bloqueantes abiertas.'}
    return {schema:'binario.marketing.pilot-health-summary.v1',status,label,detail,window_days:WINDOW_DAYS,recent_days:RECENT_DAYS,observed_days:observedDays,ready_days:readyDays,attention_days:attentionDays,missing_days:missingDays,current_streak:streak,recent_attention:recentAttention,today_recorded:Boolean(todayReceipt),today_ready:Boolean(todayReceipt?.gate?.ready),incidents:{open_count:openCount,blocking_open:blocking,high_open:high,resolved_count:Number(incidentSummary.resolved_count)||0}};
  }

  function closePanel(){document.querySelector('#post-w99-pilot-health-panel')?.remove()}
  function metric(label,value){const node=document.createElement('div');node.className='pilot-health-metric';const strong=document.createElement('strong');strong.textContent=String(Number(value)||0);const span=document.createElement('span');span.textContent=label;node.append(strong,span);return node}

  function render(){
    ensureStyles();closePanel();const panel=document.createElement('section');panel.id='post-w99-pilot-health-panel';panel.className='pilot-health-panel';
    const head=document.createElement('div');head.className='pilot-health-head';const copy=document.createElement('div');const eyebrow=document.createElement('p');eyebrow.className='eyebrow';eyebrow.textContent='PILOTO · SALUD LOCAL';const title=document.createElement('h3');title.textContent='Salud del piloto';const desc=document.createElement('p');desc.className='muted';desc.textContent='Lectura derivada de jornadas e incidencias locales. No es un puntaje de IA ni una acreditación de producción.';copy.append(eyebrow,title,desc);const close=document.createElement('button');close.type='button';close.textContent='Cerrar';close.addEventListener('click',closePanel);head.append(copy,close);panel.append(head);
    if(state.error){const error=document.createElement('div');error.className='pilot-health-error';error.textContent=state.error;panel.append(error)}
    if(!state.receipts||!state.incidents){const note=document.createElement('div');note.className='pilot-health-note';note.textContent=state.busy?'Leyendo evidencia local…':'No se pudo completar la lectura local.';panel.append(note);document.body.append(panel);return null}
    const r=report();const status=document.createElement('div');status.className=`pilot-health-state ${r.status==='STABLE'?'stable':r.status==='BLOCKED'?'blocked':r.status==='ATTENTION'?'attention':''}`;const s1=document.createElement('strong');s1.textContent=r.label;const s2=document.createElement('span');s2.textContent=r.detail;status.append(s1,s2);panel.append(status);
    const metrics=document.createElement('div');metrics.className='pilot-health-metrics';metrics.append(metric('Días observados / 30',r.observed_days),metric('Días listos',r.ready_days),metric('Días con atención',r.attention_days),metric('Racha hasta hoy',r.current_streak),metric('Días sin registro',r.missing_days),metric('Incidencias abiertas',r.incidents.open_count),metric('Bloqueantes abiertas',r.incidents.blocking_open),metric('Altas abiertas',r.incidents.high_open));panel.append(metrics);
    const grid=document.createElement('div');grid.className='pilot-health-grid';const continuity=document.createElement('article');continuity.className='pilot-health-card';const ctitle=document.createElement('h4');ctitle.textContent='Continuidad';const cp=document.createElement('p');cp.textContent=`Ventana móvil: ${r.window_days} días. Pendientes recientes: ${r.recent_attention} en los últimos ${r.recent_days} días. Hoy: ${r.today_recorded?(r.today_ready?'LISTO':'ATENCIÓN'):'SIN REGISTRO'}.`;continuity.append(ctitle,cp);const incidents=document.createElement('article');incidents.className='pilot-health-card';const ititle=document.createElement('h4');ititle.textContent='Incidencias';const ip=document.createElement('p');ip.textContent=`Abiertas ${r.incidents.open_count} · bloqueantes ${r.incidents.blocking_open} · altas ${r.incidents.high_open} · resueltas ${r.incidents.resolved_count}.`;incidents.append(ititle,ip);grid.append(continuity,incidents);panel.append(grid);
    const actions=document.createElement('div');actions.className='pilot-health-actions';const refresh=document.createElement('button');refresh.type='button';refresh.textContent='Actualizar';refresh.addEventListener('click',()=>loadAndRender());const month=document.createElement('button');month.type='button';month.textContent='Seguimiento 30 días';month.disabled=typeof globalThis.pilotMonthTrackerOpen!=='function';month.addEventListener('click',()=>{closePanel();globalThis.pilotMonthTrackerOpen?.()});const incident=document.createElement('button');incident.type='button';incident.textContent='Incidencias';incident.disabled=typeof globalThis.pilotIncidentLogOpen!=='function';incident.addEventListener('click',()=>{closePanel();globalThis.pilotIncidentLogOpen?.()});actions.append(refresh,month,incident);panel.append(actions);
    const note=document.createElement('div');note.className='pilot-health-note';note.textContent='La clasificación es informativa y local. No habilita publicaciones, pauta, Meta, IA, restauraciones, producción, UAT física, release ni despliegues.';panel.append(note);document.body.append(panel);return r;
  }

  async function loadAndRender(){if(state.busy)return;state.busy=true;state.error=null;render();try{[state.receipts,state.incidents]=await Promise.all([getJson(RECEIPTS_API),getJson(INCIDENTS_API)])}catch(error){state.error=String(error?.message||error);state.receipts=null;state.incidents=null}finally{state.busy=false;render()}}
  function open(){globalThis.pilotLaunchGateClose?.();return loadAndRender()}
  function installGateControl(){ensureStyles();const panel=document.querySelector('#post-w99-pilot-launch-gate-panel');if(!panel)return;const actions=panel.querySelector('.pilot-launch-actions');if(!actions||actions.querySelector('[data-pilot-health-summary]'))return;const button=document.createElement('button');button.type='button';button.dataset.pilotHealthSummary='1';button.textContent='Salud del piloto';button.addEventListener('click',open);actions.append(button)}

  window.addEventListener('post-w99-pilot-launch-gate-rendered',installGateControl);
  globalThis.pilotHealthSummaryOpen=open;
  globalThis.pilotHealthSummaryReport=()=>state.receipts&&state.incidents?report():null;
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(installGateControl,0),{once:true});else setTimeout(installGateControl,0);
})();
