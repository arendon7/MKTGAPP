(function installPostW99PilotSessionStatus(){
  if(globalThis.POST_W99_PILOT_SESSION_STATUS)return;
  globalThis.POST_W99_PILOT_SESSION_STATUS=true;

  const API='/api/pilot-session/status';
  const state={open:false,busy:false,payload:null,error:null};

  function ensureStyles(){
    if(document.querySelector('#post-w99-pilot-session-status-style'))return;
    const style=document.createElement('style');style.id='post-w99-pilot-session-status-style';style.textContent=`
      .pilot-session-action{margin-left:7px}.pilot-session-action button{border:1px solid #d8d3ca;background:#171717;color:#fff;border-radius:7px;padding:7px 9px;cursor:pointer;font:inherit}.pilot-session-panel{position:fixed;inset:8vh 10vw;z-index:10050;background:#fff;border:1px solid #d8d3ca;border-radius:16px;box-shadow:0 20px 70px rgba(0,0,0,.18);padding:18px;overflow:auto;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}.pilot-session-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.pilot-session-head h3{margin:3px 0}.pilot-session-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;margin-top:14px}.pilot-session-card{border:1px solid #e1ddd5;border-radius:12px;padding:12px;display:grid;gap:6px}.pilot-session-card strong{font-size:11px}.pilot-session-card span,.pilot-session-card p{font-size:9px;color:#6e6961;line-height:1.45;margin:0}.pilot-session-chip{font-size:8px!important;width:max-content;border-radius:999px;padding:4px 7px;background:#eeeae3!important;color:#171717!important}.pilot-session-chip.pass{background:#171717!important;color:#fff!important}.pilot-session-checks{display:flex;gap:5px;flex-wrap:wrap}.pilot-session-actions{display:flex;gap:7px;align-items:center;flex-wrap:wrap;margin-top:12px}.pilot-session-error{background:#fbefec;padding:10px;border-radius:9px;margin-top:10px;font-size:10px}.pilot-session-note{margin-top:12px;padding:11px;border-radius:10px;background:#f4f1eb;font-size:10px;line-height:1.5}@media(max-width:760px){.pilot-session-panel{inset:3vh 3vw}.pilot-session-grid{grid-template-columns:1fr}}
    `;document.head.append(style);
  }

  function bytes(value){let n=Number(value)||0;const units=['B','KB','MB','GB','TB'];let i=0;while(n>=1024&&i<units.length-1){n/=1024;i+=1}return `${n>=10||i===0?n.toFixed(0):n.toFixed(1)} ${units[i]}`}
  function date(value){const d=new Date(value);return Number.isNaN(d.getTime())?'—':d.toLocaleString()}
  function journey(){try{return typeof globalThis.pilotJourneyReport==='function'?globalThis.pilotJourneyReport():null}catch(_error){return null}}

  async function refresh(){
    if(state.busy)return;state.busy=true;state.error=null;if(state.open)render();
    try{
      const response=await fetch(API,{method:'GET',cache:'no-store'});
      const payload=await response.json().catch(()=>({error:'Respuesta local inválida'}));
      if(!response.ok)throw new Error(payload.error||`Error local ${response.status}`);
      state.payload=payload;
    }catch(error){state.error=String(error?.message||error)}finally{state.busy=false;if(state.open)render()}
  }

  function card(title,status,detail,extra){
    const node=document.createElement('article');node.className='pilot-session-card';const strong=document.createElement('strong');strong.textContent=title;const chip=document.createElement('span');chip.className=`pilot-session-chip ${status==='OK'||status==='READY'||status==='PASS'?'pass':''}`;chip.textContent=status;const copy=document.createElement('p');copy.textContent=detail;node.append(strong,chip,copy);if(extra)node.append(extra);return node;
  }

  function localChecks(payload){
    const wrap=document.createElement('div');wrap.className='pilot-session-checks';for(const row of payload?.local_data?.checks||[]){const chip=document.createElement('span');chip.className=`pilot-session-chip ${row.status==='OK'?'pass':''}`;chip.textContent=`${row.label}: ${row.status}${row.count===null?'':` · ${row.count}`}`;wrap.append(chip)}return wrap;
  }

  function render(){
    ensureStyles();document.querySelector('#post-w99-pilot-session-status-panel')?.remove();
    const panel=document.createElement('section');panel.id='post-w99-pilot-session-status-panel';panel.className='pilot-session-panel';state.open=true;
    const head=document.createElement('div');head.className='pilot-session-head';const copy=document.createElement('div');const eyebrow=document.createElement('p');eyebrow.className='eyebrow';eyebrow.textContent='PILOTO · SESIÓN LOCAL';const title=document.createElement('h3');title.textContent='Estado piloto';const desc=document.createElement('p');desc.className='muted';desc.textContent='Estado operativo local bajo demanda. No consulta Meta, no ejecuta proveedores y no reemplaza la preparación empresarial de Command Center.';copy.append(eyebrow,title,desc);const close=document.createElement('button');close.type='button';close.textContent='Cerrar';close.addEventListener('click',()=>{state.open=false;panel.remove()});head.append(copy,close);panel.append(head);
    if(state.error){const error=document.createElement('div');error.className='pilot-session-error';error.textContent=state.error;panel.append(error)}
    const p=state.payload,r=journey(),grid=document.createElement('div');grid.className='pilot-session-grid';
    if(p){
      grid.append(card('Backend local',p.backend?.status||'ERROR',p.status==='READY'?'La sesión local responde y sus lecturas base están disponibles.':'La sesión responde, pero al menos una lectura local requiere revisión.'));
      grid.append(card('Datos locales',p.local_data?.status||'ERROR',`${Number(p.local_data?.ready)||0}/${Number(p.local_data?.total)||0} stores legibles.`,localChecks(p)));
      const journeyStatus=r?(r.ready?'PASS':'EN CURSO'):'NO OBSERVADO';const journeyDetail=r?`${r.pass}/${r.total} rutas verificadas manualmente en modo ${r.mode==='COMPANY'?'empresa':'portfolio'}.`:'El recorrido de esta sesión todavía no está disponible.';grid.append(card('Recorrido operativo',journeyStatus,journeyDetail));
      const snap=p.snapshot||{};let snapDetail='Todavía no existe un snapshot local.';if(snap.status==='AVAILABLE'&&snap.latest)snapDetail=`Último: ${date(snap.latest.created_at)} · ${Number(snap.latest.file_count)||0} archivos · ${bytes(snap.latest.total_bytes)}. Integridad no se recalcula automáticamente.`;else if(snap.status==='ERROR')snapDetail='No fue posible leer el inventario local de snapshots.';grid.append(card('Respaldo local',snap.status||'ERROR',snapDetail));
    }else{grid.append(card('Estado local',state.busy?'CARGANDO':'SIN DATOS',state.busy?'Leyendo únicamente estado local…':'Pulsa Actualizar para consultar la sesión.'))}
    panel.append(grid);
    const actions=document.createElement('div');actions.className='pilot-session-actions';const reload=document.createElement('button');reload.type='button';reload.disabled=state.busy;reload.textContent=state.busy?'Consultando…':'Actualizar';reload.addEventListener('click',()=>refresh());const route=document.createElement('button');route.type='button';route.textContent='Abrir recorrido';route.disabled=typeof globalThis.pilotJourneyShow!=='function';route.addEventListener('click',()=>globalThis.pilotJourneyShow?.());const backup=document.createElement('button');backup.type='button';backup.textContent='Abrir respaldo';backup.disabled=typeof globalThis.pilotDataSafetyOpen!=='function';backup.addEventListener('click',()=>globalThis.pilotDataSafetyOpen?.());actions.append(reload,route,backup);panel.append(actions);
    const note=document.createElement('div');note.className='pilot-session-note';note.textContent='“READY” aquí significa que el runtime y las lecturas locales base están operativas. No acredita conexión Meta, publicación remota, UAT física ni producción. La preparación de cada empresa sigue perteneciendo al Command Center/W50.';panel.append(note);document.body.append(panel);
  }

  function installAction(){ensureStyles();const top=document.querySelector('.marketing-ops-top');if(!top||top.querySelector('.pilot-session-action'))return;const wrap=document.createElement('div');wrap.className='pilot-session-action';const button=document.createElement('button');button.type='button';button.textContent='Estado piloto';button.addEventListener('click',async()=>{render();await refresh()});wrap.append(button);top.append(wrap)}

  window.addEventListener('marketing-ops-refreshed',installAction);window.addEventListener('wave73-entry-ready',installAction);window.addEventListener('wave73-bootstrap-ready',installAction);window.addEventListener('post-w99-pilot-journey-observed',()=>{if(state.open)render()});
  globalThis.pilotSessionStatusOpen=()=>{render();return refresh()};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(installAction,0),{once:true});else setTimeout(installAction,0);
})();
