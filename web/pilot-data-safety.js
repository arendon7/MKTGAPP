(function installPostW99PilotDataSafety(){
  if(globalThis.POST_W99_PILOT_DATA_SAFETY)return;
  globalThis.POST_W99_PILOT_DATA_SAFETY=true;

  const API='/api/pilot-data-safety/snapshots';
  const OPERATOR_HEADER={'X-Mercadeo-Operator':'pilot-data-safety'};
  const state={open:false,busy:false,payload:null,error:null,verified:{}};

  function ensureStyles(){
    if(document.querySelector('#post-w99-pilot-data-safety-style'))return;
    const style=document.createElement('style');style.id='post-w99-pilot-data-safety-style';style.textContent=`
      .pilot-data-safety-action{margin-left:7px}.pilot-data-safety-action button{border:1px solid #d8d3ca;background:#fff;border-radius:7px;padding:7px 9px;cursor:pointer;font:inherit}.pilot-data-safety-panel{position:fixed;inset:8vh 12vw;z-index:10040;background:#fff;border:1px solid #d8d3ca;border-radius:16px;box-shadow:0 20px 70px rgba(0,0,0,.18);padding:18px;overflow:auto;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}.pilot-data-safety-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.pilot-data-safety-head h3{margin:3px 0}.pilot-data-safety-notice{margin:12px 0;padding:11px;border-radius:10px;background:#f4f1eb;font-size:10px;line-height:1.5}.pilot-data-safety-actions{display:flex;gap:7px;align-items:center;flex-wrap:wrap}.pilot-data-safety-list{display:grid;gap:8px;margin-top:12px}.pilot-data-safety-row{border:1px solid #e1ddd5;border-radius:11px;padding:11px;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;align-items:center}.pilot-data-safety-row strong{font-size:11px}.pilot-data-safety-row span{font-size:9px;color:#6e6961}.pilot-data-safety-copy{display:grid;gap:4px}.pilot-data-safety-badge{font-size:8px;width:max-content;border-radius:999px;padding:4px 7px;background:#eeeae3}.pilot-data-safety-badge.pass{background:#171717;color:#fff}.pilot-data-safety-error{background:#fbefec;padding:10px;border-radius:9px;margin-top:10px;font-size:10px}.pilot-data-safety-empty{padding:18px;border:1px dashed #d8d3ca;border-radius:10px;margin-top:12px;font-size:10px;color:#6e6961}@media(max-width:760px){.pilot-data-safety-panel{inset:3vh 3vw}.pilot-data-safety-row{grid-template-columns:1fr}}
    `;document.head.append(style);
  }

  async function request(method,path){
    const options={method,headers:method==='GET'?{}:OPERATOR_HEADER,cache:'no-store'};
    const response=await fetch(path,options);
    const payload=await response.json().catch(()=>({error:'Respuesta local inválida'}));
    if(!response.ok)throw new Error(payload.error||`Error local ${response.status}`);
    return payload;
  }

  function bytes(value){
    let n=Number(value)||0;const units=['B','KB','MB','GB','TB'];let i=0;
    while(n>=1024&&i<units.length-1){n/=1024;i+=1}
    return `${n>=10||i===0?n.toFixed(0):n.toFixed(1)} ${units[i]}`;
  }

  function date(value){
    const d=new Date(value);return Number.isNaN(d.getTime())?String(value||'—'):d.toLocaleString();
  }

  async function refresh(){
    state.error=null;
    try{state.payload=await request('GET',API)}catch(error){state.error=String(error?.message||error)}
    if(state.open)render();
  }

  async function createSnapshot(){
    if(state.busy)return;state.busy=true;state.error=null;render();
    try{
      const created=await request('POST',API);state.verified[created.id]=true;await refresh();
    }catch(error){state.error=String(error?.message||error)}finally{state.busy=false;if(state.open)render()}
  }

  async function verifySnapshot(id){
    if(state.busy)return;state.busy=true;state.error=null;render();
    try{const result=await request('POST',`${API}/${encodeURIComponent(id)}/verify`);state.verified[id]=Boolean(result.verified)}catch(error){state.error=String(error?.message||error)}finally{state.busy=false;if(state.open)render()}
  }

  function snapshotRow(row){
    const item=document.createElement('article');item.className='pilot-data-safety-row';
    const copy=document.createElement('div');copy.className='pilot-data-safety-copy';
    const title=document.createElement('strong');title.textContent=date(row.created_at);
    const meta=document.createElement('span');meta.textContent=`${Number(row.file_count)||0} archivos · ${bytes(row.total_bytes)}`;
    const badge=document.createElement('span');badge.className=`pilot-data-safety-badge ${state.verified[row.id]?'pass':''}`;badge.textContent=state.verified[row.id]?'VERIFICADO EN ESTA SESIÓN':'SNAPSHOT LOCAL';
    copy.append(title,meta,badge);
    const actions=document.createElement('div');actions.className='pilot-data-safety-actions';
    const verify=document.createElement('button');verify.type='button';verify.disabled=state.busy;verify.textContent='Verificar integridad';verify.addEventListener('click',()=>verifySnapshot(row.id));actions.append(verify);
    item.append(copy,actions);return item;
  }

  function render(){
    ensureStyles();document.querySelector('#post-w99-pilot-data-safety-panel')?.remove();
    const panel=document.createElement('section');panel.id='post-w99-pilot-data-safety-panel';panel.className='pilot-data-safety-panel';state.open=true;
    const head=document.createElement('div');head.className='pilot-data-safety-head';const copy=document.createElement('div');const eyebrow=document.createElement('p');eyebrow.className='eyebrow';eyebrow.textContent='PILOTO · SEGURIDAD DE DATOS';const title=document.createElement('h3');title.textContent='Respaldo local';const desc=document.createElement('p');desc.className='muted';desc.textContent='Snapshots verificables del estado local de MERCADEO APP. No suben datos a la nube ni incluyen credenciales Meta/IA.';copy.append(eyebrow,title,desc);
    const close=document.createElement('button');close.type='button';close.textContent='Cerrar';close.addEventListener('click',()=>{state.open=false;panel.remove()});head.append(copy,close);panel.append(head);
    const notice=document.createElement('div');notice.className='pilot-data-safety-notice';notice.textContent='Este bloque sólo crea y verifica copias. Restaurar o borrar snapshots no está habilitado durante esta fase del piloto. Temp, logs y archivos parciales se excluyen deliberadamente.';panel.append(notice);
    const actions=document.createElement('div');actions.className='pilot-data-safety-actions';const create=document.createElement('button');create.type='button';create.disabled=state.busy;create.textContent=state.busy?'Procesando…':'Crear snapshot verificado';create.addEventListener('click',()=>createSnapshot());const reload=document.createElement('button');reload.type='button';reload.disabled=state.busy;reload.textContent='Actualizar lista';reload.addEventListener('click',()=>refresh());actions.append(create,reload);panel.append(actions);
    if(state.error){const error=document.createElement('div');error.className='pilot-data-safety-error';error.textContent=state.error;panel.append(error)}
    const rows=state.payload?.snapshots||[];if(rows.length){const list=document.createElement('div');list.className='pilot-data-safety-list';rows.forEach(row=>list.append(snapshotRow(row)));panel.append(list)}else{const empty=document.createElement('div');empty.className='pilot-data-safety-empty';empty.textContent=state.payload?'Todavía no hay snapshots locales.':'Pulsa “Actualizar lista” o crea el primer snapshot para consultar el estado.';panel.append(empty)}
    document.body.append(panel);
  }

  function installAction(){
    ensureStyles();const top=document.querySelector('.marketing-ops-top');if(!top||top.querySelector('.pilot-data-safety-action'))return;
    const wrap=document.createElement('div');wrap.className='pilot-data-safety-action';const button=document.createElement('button');button.type='button';button.textContent='Respaldo local';button.addEventListener('click',async()=>{render();await refresh()});wrap.append(button);top.append(wrap);
  }

  window.addEventListener('marketing-ops-refreshed',installAction);
  window.addEventListener('wave73-entry-ready',installAction);
  window.addEventListener('wave73-bootstrap-ready',installAction);
  globalThis.pilotDataSafetyOpen=()=>{render();return refresh()};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(installAction,0),{once:true});else setTimeout(installAction,0);
})();
