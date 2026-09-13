(function installPostW99PilotMonthTracker(){
  if(globalThis.POST_W99_PILOT_MONTH_TRACKER)return;
  globalThis.POST_W99_PILOT_MONTH_TRACKER=true;

  const API='/api/pilot/daily-receipts?limit=365';
  const state={busy:false,history:null,error:null};

  function ensureStyles(){
    if(document.querySelector('#post-w99-pilot-month-tracker-style'))return;
    const style=document.createElement('style');
    style.id='post-w99-pilot-month-tracker-style';
    style.textContent=`
      .pilot-month-panel{position:fixed;inset:6vh 7vw;z-index:10110;background:#fff;border:1px solid #d8d3ca;border-radius:16px;box-shadow:0 20px 70px rgba(0,0,0,.2);padding:18px;overflow:auto;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}.pilot-month-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.pilot-month-head h3{margin:3px 0}.pilot-month-summary{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px;margin:14px 0}.pilot-month-metric{border:1px solid #e1ddd5;border-radius:11px;padding:10px;display:grid;gap:3px}.pilot-month-metric strong{font-size:16px}.pilot-month-metric span{font-size:8px;color:#6e6961}.pilot-month-grid{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:7px}.pilot-month-day{min-height:68px;border:1px solid #e1ddd5;border-radius:10px;padding:8px;display:grid;align-content:space-between;gap:6px}.pilot-month-day strong{font-size:9px}.pilot-month-day span{font-size:8px;color:#6e6961}.pilot-month-day.ready{background:#171717;color:#fff;border-color:#171717}.pilot-month-day.ready span{color:#fff}.pilot-month-day.attention{background:#fbefec;border-color:#e7c8c1}.pilot-month-day.missing{background:#f8f6f2}.pilot-month-legend,.pilot-month-note,.pilot-month-error{margin-top:12px;padding:10px 11px;border-radius:10px;font-size:9px;line-height:1.5}.pilot-month-legend,.pilot-month-note{background:#f4f1eb}.pilot-month-error{background:#fbefec;color:#5f2721}.pilot-month-legend{display:flex;gap:12px;flex-wrap:wrap}.pilot-month-legend span{display:inline-flex;align-items:center;gap:5px}.pilot-month-dot{width:8px;height:8px;border-radius:999px;background:#d7d1c7}.pilot-month-dot.ready{background:#171717}.pilot-month-dot.attention{background:#c96f61}.pilot-month-empty{padding:18px;border:1px dashed #d8d3ca;border-radius:10px;font-size:10px;color:#6e6961}@media(max-width:900px){.pilot-month-summary{grid-template-columns:repeat(2,minmax(0,1fr))}.pilot-month-grid{grid-template-columns:repeat(5,minmax(0,1fr))}}@media(max-width:620px){.pilot-month-panel{inset:3vh 3vw}.pilot-month-grid{grid-template-columns:repeat(3,minmax(0,1fr))}}
    `;
    document.head.append(style);
  }

  function localKey(date){
    const y=date.getFullYear();
    const m=String(date.getMonth()+1).padStart(2,'0');
    const d=String(date.getDate()).padStart(2,'0');
    return `${y}-${m}-${d}`;
  }

  function recentDates(days=30){
    const now=new Date();
    const values=[];
    for(let offset=days-1;offset>=0;offset--){
      const d=new Date(now.getFullYear(),now.getMonth(),now.getDate()-offset,12,0,0,0);
      values.push({key:localKey(d),label:d.toLocaleDateString(undefined,{day:'2-digit',month:'short'})});
    }
    return values;
  }

  async function load(){
    state.busy=true;state.error=null;
    try{
      const response=await fetch(API,{method:'GET',cache:'no-store'});
      const payload=await response.json().catch(()=>({error:'Respuesta local inválida'}));
      if(!response.ok)throw new Error(payload.error||`Error local ${response.status}`);
      state.history=payload;
    }catch(error){state.error=String(error?.message||error);state.history=null}
    finally{state.busy=false}
  }

  function model(){
    const dates=recentDates(30);
    const latest=new Map();
    const rows=Array.isArray(state.history?.receipts)?state.history.receipts:[];
    rows.forEach(row=>{const key=String(row?.local_date||'');if(key&&!latest.has(key))latest.set(key,row)});
    const days=dates.map(date=>{
      const receipt=latest.get(date.key)||null;
      const status=!receipt?'missing':receipt.gate?.ready?'ready':'attention';
      return {...date,status,receipt};
    });
    const observed=days.filter(day=>day.status!=='missing').length;
    const ready=days.filter(day=>day.status==='ready').length;
    const attention=days.filter(day=>day.status==='attention').length;
    const missing=days.length-observed;
    let currentStreak=0;
    for(let index=days.length-1;index>=0;index--){if(days[index].status==='missing')break;currentStreak++}
    return {days,observed,ready,attention,missing,currentStreak,total:days.length};
  }

  function metric(label,value){const box=document.createElement('div');box.className='pilot-month-metric';const strong=document.createElement('strong');strong.textContent=String(value);const span=document.createElement('span');span.textContent=label;box.append(strong,span);return box}

  function render(){
    ensureStyles();document.querySelector('#post-w99-pilot-month-panel')?.remove();
    const panel=document.createElement('section');panel.id='post-w99-pilot-month-panel';panel.className='pilot-month-panel';
    const head=document.createElement('div');head.className='pilot-month-head';const copy=document.createElement('div');const eyebrow=document.createElement('p');eyebrow.className='eyebrow';eyebrow.textContent='PILOTO · 30 DÍAS';const title=document.createElement('h3');title.textContent='Seguimiento del mes piloto';const desc=document.createElement('p');desc.className='muted';desc.textContent='Vista local derivada de los recibos diarios. No modifica jornadas, respaldos, empresas ni publicaciones.';copy.append(eyebrow,title,desc);const close=document.createElement('button');close.type='button';close.textContent='Cerrar';close.addEventListener('click',()=>panel.remove());head.append(copy,close);panel.append(head);
    if(state.error){const error=document.createElement('div');error.className='pilot-month-error';error.textContent=state.error;panel.append(error)}
    if(state.busy&&!state.history){const loading=document.createElement('div');loading.className='pilot-month-empty';loading.textContent='Leyendo historial local…';panel.append(loading);document.body.append(panel);return}
    const data=model();
    const summary=document.createElement('div');summary.className='pilot-month-summary';summary.append(metric('Días observados',`${data.observed}/${data.total}`),metric('Días listos',data.ready),metric('Días con atención',data.attention),metric('Sin registro',data.missing),metric('Racha actual',`${data.currentStreak} d`));panel.append(summary);
    const legend=document.createElement('div');legend.className='pilot-month-legend';[['ready','LISTO'],['attention','ATENCIÓN'],['','SIN REGISTRO']].forEach(([kind,label])=>{const item=document.createElement('span');const dot=document.createElement('i');dot.className=`pilot-month-dot ${kind}`.trim();item.append(dot,document.createTextNode(label));legend.append(item)});panel.append(legend);
    const grid=document.createElement('div');grid.className='pilot-month-grid';data.days.forEach(day=>{const cell=document.createElement('article');cell.className=`pilot-month-day ${day.status}`;const date=document.createElement('strong');date.textContent=day.label;const status=document.createElement('span');if(day.status==='ready')status.textContent='LISTO';else if(day.status==='attention')status.textContent='ATENCIÓN';else status.textContent='SIN REGISTRO';cell.append(date,status);grid.append(cell)});panel.append(grid);
    const note=document.createElement('div');note.className='pilot-month-note';note.textContent='La continuidad se basa únicamente en jornadas que el operador cerró explícitamente. Un día sin recibo significa “sin registro”, no una falla de la aplicación ni ausencia de trabajo.';panel.append(note);
    document.body.append(panel);
  }

  async function openTracker(){
    globalThis.pilotLaunchGateClose?.();
    state.history=null;state.error=null;state.busy=true;render();
    await load();render();
  }

  function installGateControl(){
    ensureStyles();const panel=document.querySelector('#post-w99-pilot-launch-gate-panel');if(!panel)return;const actions=panel.querySelector('.pilot-launch-actions');if(!actions||actions.querySelector('[data-pilot-month-tracker]'))return;
    const button=document.createElement('button');button.type='button';button.dataset.pilotMonthTracker='1';button.textContent='Seguimiento 30 días';button.addEventListener('click',openTracker);actions.append(button);
  }

  window.addEventListener('post-w99-pilot-launch-gate-rendered',installGateControl);
  globalThis.pilotMonthTrackerOpen=openTracker;
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(installGateControl,0),{once:true});else setTimeout(installGateControl,0);
})();
