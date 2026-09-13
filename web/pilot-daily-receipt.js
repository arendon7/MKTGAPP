(function installPostW99PilotDailyReceipt(){
  if(globalThis.POST_W99_PILOT_DAILY_RECEIPT)return;
  globalThis.POST_W99_PILOT_DAILY_RECEIPT=true;

  const API='/api/pilot/daily-receipts';
  const OPERATOR_HEADER='X-Mercadeo-Operator';
  const OPERATOR_VALUE='pilot-daily-receipt';
  const state={busy:false,history:null,error:null};

  function ensureStyles(){
    if(document.querySelector('#post-w99-pilot-daily-receipt-style'))return;
    const style=document.createElement('style');style.id='post-w99-pilot-daily-receipt-style';style.textContent=`
      .pilot-daily-result{margin-top:10px;padding:10px 11px;border-radius:10px;background:#f4f1eb;font-size:9px;line-height:1.5}.pilot-daily-result.pass{background:#171717;color:#fff}.pilot-daily-result.error{background:#fbefec;color:#5f2721}.pilot-daily-panel{position:fixed;inset:7vh 10vw;z-index:10090;background:#fff;border:1px solid #d8d3ca;border-radius:16px;box-shadow:0 20px 70px rgba(0,0,0,.2);padding:18px;overflow:auto;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}.pilot-daily-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.pilot-daily-head h3{margin:3px 0}.pilot-daily-summary{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}.pilot-daily-summary span{font-size:9px;background:#f4f1eb;padding:6px 8px;border-radius:999px}.pilot-daily-list{display:grid;gap:8px}.pilot-daily-row{border:1px solid #e1ddd5;border-radius:11px;padding:11px;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px;align-items:center}.pilot-daily-copy{display:grid;gap:4px}.pilot-daily-copy strong{font-size:11px}.pilot-daily-copy span{font-size:9px;color:#6e6961}.pilot-daily-badge{font-size:8px;padding:4px 7px;border-radius:999px;background:#eeeae3}.pilot-daily-badge.pass{background:#171717;color:#fff}.pilot-daily-empty{padding:18px;border:1px dashed #d8d3ca;border-radius:10px;font-size:10px;color:#6e6961}@media(max-width:760px){.pilot-daily-panel{inset:3vh 3vw}.pilot-daily-row{grid-template-columns:1fr}}
    `;document.head.append(style);
  }

  function localDate(){const d=new Date();const y=d.getFullYear();const m=String(d.getMonth()+1).padStart(2,'0');const day=String(d.getDate()).padStart(2,'0');return `${y}-${m}-${day}`}
  function dateTime(value){const d=new Date(value);return Number.isNaN(d.getTime())?String(value||'—'):d.toLocaleString()}

  async function request(method,path,payload){
    const headers={};const options={method,cache:'no-store',headers};
    if(method==='POST'){headers['Content-Type']='application/json';headers[OPERATOR_HEADER]=OPERATOR_VALUE;options.body=JSON.stringify(payload)}
    const response=await fetch(path,options);const body=await response.json().catch(()=>({error:'Respuesta local inválida'}));
    if(!response.ok)throw new Error(body.error||`Error local ${response.status}`);return body;
  }

  function gateEvidence(){
    const report=typeof globalThis.pilotLaunchGateReport==='function'?globalThis.pilotLaunchGateReport():null;
    if(!report||!Array.isArray(report.checks))throw new Error('Abre Preparación piloto y actualiza los controles antes de cerrar la jornada.');
    const checks=report.checks.map(row=>({id:String(row.id||''),pass:Boolean(row.pass)}));
    const journey=report.journey?{
      mode:String(report.journey.mode||'NONE').toUpperCase(),
      pass:Number(report.journey.pass)||0,
      total:Number(report.journey.total)||0,
      ready:Boolean(report.journey.ready),
    }:{mode:'NONE',pass:0,total:0,ready:false};
    return {schema:'binario.marketing.pilot-launch-gate.v1',ready:Boolean(report.ready),passed:Number(report.passed)||0,total:Number(report.total)||0,checks,journey};
  }

  function showGateMessage(message,kind=''){
    const panel=document.querySelector('#post-w99-pilot-launch-gate-panel');if(!panel)return;
    let node=panel.querySelector('#post-w99-pilot-daily-result');if(!node){node=document.createElement('div');node.id='post-w99-pilot-daily-result';panel.append(node)}
    node.className=`pilot-daily-result ${kind}`.trim();node.textContent=message;
  }

  async function closeDay(button){
    if(state.busy)return;state.busy=true;button.disabled=true;button.textContent='Guardando…';state.error=null;
    try{
      const payload={local_date:localDate(),gate:gateEvidence()};
      const receipt=await request('POST',API,payload);
      showGateMessage(`JORNADA REGISTRADA · ${receipt.local_date} · ${receipt.gate.ready?'LISTA':'CON PENDIENTES'} · ${receipt.gate.passed}/${receipt.gate.total} controles.`,receipt.gate.ready?'pass':'');
      state.history=null;
    }catch(error){showGateMessage(String(error?.message||error),'error')}
    finally{state.busy=false;button.disabled=false;button.textContent='Cerrar jornada'}
  }

  function installGateControls(){
    ensureStyles();const panel=document.querySelector('#post-w99-pilot-launch-gate-panel');if(!panel)return;
    const actions=panel.querySelector('.pilot-launch-actions');if(!actions||actions.querySelector('[data-pilot-daily-close]'))return;
    const close=document.createElement('button');close.type='button';close.dataset.pilotDailyClose='1';close.textContent='Cerrar jornada';close.addEventListener('click',()=>closeDay(close));
    const history=document.createElement('button');history.type='button';history.dataset.pilotDailyHistory='1';history.textContent='Historial del piloto';history.addEventListener('click',()=>openHistory());
    actions.append(close,history);
  }

  async function loadHistory(){state.error=null;try{state.history=await request('GET',`${API}?limit=90`)}catch(error){state.error=String(error?.message||error)}}

  function renderHistory(){
    ensureStyles();document.querySelector('#post-w99-pilot-daily-panel')?.remove();const panel=document.createElement('section');panel.id='post-w99-pilot-daily-panel';panel.className='pilot-daily-panel';
    const head=document.createElement('div');head.className='pilot-daily-head';const copy=document.createElement('div');const eyebrow=document.createElement('p');eyebrow.className='eyebrow';eyebrow.textContent='PILOTO · HISTORIAL LOCAL';const title=document.createElement('h3');title.textContent='Jornadas registradas';const desc=document.createElement('p');desc.className='muted';desc.textContent='Recibos mínimos del piloto: fecha, controles y recorrido. Sin notas libres, PII ni metadatos de proveedores.';copy.append(eyebrow,title,desc);const close=document.createElement('button');close.type='button';close.textContent='Cerrar';close.addEventListener('click',()=>panel.remove());head.append(copy,close);panel.append(head);
    if(state.error){const error=document.createElement('div');error.className='pilot-daily-result error';error.textContent=state.error;panel.append(error)}
    const summary=state.history?.summary;if(summary){const box=document.createElement('div');box.className='pilot-daily-summary';[['Días observados',summary.days_observed],['Días listos',summary.ready_days],['Días con atención',summary.attention_days],['Registros',summary.receipt_count]].forEach(([label,value])=>{const chip=document.createElement('span');chip.textContent=`${label}: ${Number(value)||0}`;box.append(chip)});panel.append(box)}
    const rows=state.history?.receipts||[];if(rows.length){const list=document.createElement('div');list.className='pilot-daily-list';rows.forEach(row=>{const item=document.createElement('article');item.className='pilot-daily-row';const c=document.createElement('div');c.className='pilot-daily-copy';const t=document.createElement('strong');t.textContent=row.local_date;const meta=document.createElement('span');const j=row.gate?.journey||{};meta.textContent=`${Number(row.gate?.passed)||0}/${Number(row.gate?.total)||0} controles · recorrido ${Number(j.pass)||0}/${Number(j.total)||0} · ${dateTime(row.recorded_at)}`;c.append(t,meta);const badge=document.createElement('span');badge.className=`pilot-daily-badge ${row.gate?.ready?'pass':''}`;badge.textContent=row.gate?.ready?'LISTO':'ATENCIÓN';item.append(c,badge);list.append(item)});panel.append(list)}else{const empty=document.createElement('div');empty.className='pilot-daily-empty';empty.textContent=state.history?'Todavía no hay jornadas registradas.':'Cargando historial local…';panel.append(empty)}
    document.body.append(panel);
  }

  async function openHistory(){globalThis.pilotLaunchGateClose?.();renderHistory();await loadHistory();renderHistory()}

  window.addEventListener('post-w99-pilot-launch-gate-rendered',installGateControls);
  globalThis.pilotDailyReceiptHistory=openHistory;
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(installGateControls,0),{once:true});else setTimeout(installGateControls,0);
})();
