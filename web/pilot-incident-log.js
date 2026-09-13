(function installPostW99PilotIncidentLog(){
  if(globalThis.POST_W99_PILOT_INCIDENT_LOG)return;
  globalThis.POST_W99_PILOT_INCIDENT_LOG=true;

  const API='/api/pilot/incidents';
  const OPERATOR_HEADER='X-Mercadeo-Operator';
  const OPERATOR_VALUE='pilot-incident-log';
  const MODULES=[
    ['STARTUP','Inicio'],['TODAY','Hoy'],['COMPANIES','Empresas'],['CONTENT','Contenido'],
    ['CALENDAR','Calendario'],['CRM','CRM'],['INBOX','Mensajes'],['CAMPAIGNS','Campañas'],
    ['PAID_MEDIA','Pauta'],['RESULTS','Resultados'],['VIDEO','Video Studio'],['AI','IA'],['BACKUP','Respaldo'],
  ];
  const CATEGORIES=[
    ['UI','Interfaz'],['DATA','Datos'],['WORKFLOW','Flujo de trabajo'],['PERFORMANCE','Rendimiento'],
    ['INTEGRATION','Integración'],['STARTUP','Arranque'],['RECOVERY','Recuperación'],
  ];
  const SEVERITIES=[['LOW','Baja'],['MEDIUM','Media'],['HIGH','Alta'],['BLOCKING','Bloqueante']];
  const labels={module:Object.fromEntries(MODULES),category:Object.fromEntries(CATEGORIES),severity:Object.fromEntries(SEVERITIES)};
  const state={busy:false,history:null,error:null};

  function ensureStyles(){
    if(document.querySelector('#post-w99-pilot-incident-log-style'))return;
    const style=document.createElement('style');style.id='post-w99-pilot-incident-log-style';style.textContent=`
      .pilot-incident-panel{position:fixed;inset:6vh 8vw;z-index:10130;background:#fff;border:1px solid #d8d3ca;border-radius:16px;box-shadow:0 20px 70px rgba(0,0,0,.22);padding:18px;overflow:auto;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}.pilot-incident-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.pilot-incident-head h3{margin:3px 0}.pilot-incident-form{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:14px 0}.pilot-incident-field{display:grid;gap:5px}.pilot-incident-field span{font-size:8px;color:#6e6961}.pilot-incident-field select{width:100%;border:1px solid #d8d3ca;border-radius:8px;background:#fff;padding:9px;font:inherit}.pilot-incident-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}.pilot-incident-summary{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}.pilot-incident-summary span{font-size:9px;background:#f4f1eb;padding:6px 8px;border-radius:999px}.pilot-incident-list{display:grid;gap:8px}.pilot-incident-row{border:1px solid #e1ddd5;border-radius:11px;padding:11px;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px;align-items:center}.pilot-incident-copy{display:grid;gap:4px}.pilot-incident-copy strong{font-size:11px}.pilot-incident-copy span{font-size:9px;color:#6e6961}.pilot-incident-tags{display:flex;gap:5px;flex-wrap:wrap}.pilot-incident-tag{font-size:8px;background:#eeeae3;border-radius:999px;padding:3px 6px}.pilot-incident-tag.blocking{background:#5f2721;color:#fff}.pilot-incident-tag.high{background:#fbefec;color:#5f2721}.pilot-incident-result,.pilot-incident-note,.pilot-incident-error{margin-top:12px;padding:10px 11px;border-radius:10px;font-size:9px;line-height:1.5}.pilot-incident-result,.pilot-incident-note{background:#f4f1eb}.pilot-incident-result.pass{background:#171717;color:#fff}.pilot-incident-error{background:#fbefec;color:#5f2721}.pilot-incident-empty{padding:18px;border:1px dashed #d8d3ca;border-radius:10px;font-size:10px;color:#6e6961}@media(max-width:760px){.pilot-incident-panel{inset:3vh 3vw}.pilot-incident-form{grid-template-columns:1fr}.pilot-incident-row{grid-template-columns:1fr}}
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

  function closePanel(){document.querySelector('#post-w99-pilot-incident-panel')?.remove()}
  function panelHead(titleText,description){
    const head=document.createElement('div');head.className='pilot-incident-head';const copy=document.createElement('div');const eyebrow=document.createElement('p');eyebrow.className='eyebrow';eyebrow.textContent='PILOTO · INCIDENCIAS';const title=document.createElement('h3');title.textContent=titleText;const desc=document.createElement('p');desc.className='muted';desc.textContent=description;copy.append(eyebrow,title,desc);const close=document.createElement('button');close.type='button';close.textContent='Cerrar';close.addEventListener('click',closePanel);head.append(copy,close);return head;
  }
  function selectField(labelText,values,name){const field=document.createElement('label');field.className='pilot-incident-field';const label=document.createElement('span');label.textContent=labelText;const select=document.createElement('select');select.name=name;values.forEach(([value,text])=>{const option=document.createElement('option');option.value=value;option.textContent=text;select.append(option)});field.append(label,select);return field}

  async function submitIncident(panel,button){
    if(state.busy)return;state.busy=true;button.disabled=true;button.textContent='Registrando…';panel.querySelector('.pilot-incident-error')?.remove();
    try{
      const module=panel.querySelector('select[name="module"]')?.value;
      const category=panel.querySelector('select[name="category"]')?.value;
      const severity=panel.querySelector('select[name="severity"]')?.value;
      const incident=await request('POST',API,{local_date:localDate(),module,category,severity});
      const result=document.createElement('div');result.className='pilot-incident-result pass';result.textContent=`INCIDENCIA REGISTRADA · ${labels.module[incident.module]} · ${labels.severity[incident.severity]}`;panel.append(result);state.history=null;
    }catch(error){const node=document.createElement('div');node.className='pilot-incident-error';node.textContent=String(error?.message||error);panel.append(node)}
    finally{state.busy=false;button.disabled=false;button.textContent='Registrar incidencia'}
  }

  function openCreate(){
    globalThis.pilotLaunchGateClose?.();closePanel();ensureStyles();
    const panel=document.createElement('section');panel.id='post-w99-pilot-incident-panel';panel.className='pilot-incident-panel';panel.append(panelHead('Registrar incidencia','Registra solo la clasificación operativa del problema. No se guardan notas, nombres, contactos, URLs, rutas ni datos de proveedores.'));
    const form=document.createElement('div');form.className='pilot-incident-form';form.append(selectField('Módulo',MODULES,'module'),selectField('Categoría',CATEGORIES,'category'),selectField('Severidad',SEVERITIES,'severity'));panel.append(form);
    const actions=document.createElement('div');actions.className='pilot-incident-actions';const submit=document.createElement('button');submit.type='button';submit.textContent='Registrar incidencia';submit.addEventListener('click',()=>submitIncident(panel,submit));const history=document.createElement('button');history.type='button';history.textContent='Ver incidencias';history.addEventListener('click',openHistory);actions.append(submit,history);panel.append(actions);
    const note=document.createElement('div');note.className='pilot-incident-note';note.textContent='Registrar una incidencia no ejecuta acciones correctivas ni modifica módulos de negocio. Solo añade evidencia local estructurada para el piloto.';panel.append(note);document.body.append(panel);
  }

  async function resolveIncident(id,button){
    if(state.busy)return;state.busy=true;button.disabled=true;button.textContent='Resolviendo…';
    try{await request('POST',`${API}/${encodeURIComponent(id)}/resolve`,{local_date:localDate()});await loadHistory();renderHistory()}
    catch(error){state.error=String(error?.message||error);renderHistory()}
    finally{state.busy=false}
  }

  async function loadHistory(){state.error=null;try{state.history=await request('GET',`${API}?status=ALL&limit=100`)}catch(error){state.error=String(error?.message||error);state.history=null}}

  function renderHistory(){
    closePanel();ensureStyles();const panel=document.createElement('section');panel.id='post-w99-pilot-incident-panel';panel.className='pilot-incident-panel';panel.append(panelHead('Incidencias del piloto','Historial local estructurado. Resolver añade un evento nuevo y conserva la apertura original.'));
    if(state.error){const error=document.createElement('div');error.className='pilot-incident-error';error.textContent=state.error;panel.append(error)}
    const summary=state.history?.summary;if(summary){const box=document.createElement('div');box.className='pilot-incident-summary';[['Abiertas',summary.open_count],['Bloqueantes',summary.blocking_open],['Altas',summary.high_open],['Resueltas',summary.resolved_count],['Total',summary.incident_count]].forEach(([label,value])=>{const chip=document.createElement('span');chip.textContent=`${label}: ${Number(value)||0}`;box.append(chip)});panel.append(box)}
    const rows=state.history?.incidents||[];
    if(rows.length){const list=document.createElement('div');list.className='pilot-incident-list';rows.forEach(row=>{const item=document.createElement('article');item.className='pilot-incident-row';const copy=document.createElement('div');copy.className='pilot-incident-copy';const title=document.createElement('strong');title.textContent=`${labels.module[row.module]||row.module} · ${labels.category[row.category]||row.category}`;const tags=document.createElement('div');tags.className='pilot-incident-tags';const severity=document.createElement('span');severity.className=`pilot-incident-tag ${String(row.severity||'').toLowerCase()}`;severity.textContent=labels.severity[row.severity]||row.severity;const status=document.createElement('span');status.className='pilot-incident-tag';status.textContent=row.status==='OPEN'?'ABIERTA':'RESUELTA';tags.append(severity,status);const meta=document.createElement('span');meta.textContent=row.status==='OPEN'?`Registrada ${dateTime(row.opened_at)}`:`Registrada ${dateTime(row.opened_at)} · resuelta ${dateTime(row.resolved_at)}`;copy.append(title,tags,meta);item.append(copy);if(row.status==='OPEN'){const resolve=document.createElement('button');resolve.type='button';resolve.textContent='Marcar resuelta';resolve.addEventListener('click',()=>resolveIncident(row.id,resolve));item.append(resolve)}list.append(item)});panel.append(list)}else{const empty=document.createElement('div');empty.className='pilot-incident-empty';empty.textContent=state.history?'No hay incidencias registradas.':'Cargando incidencias locales…';panel.append(empty)}
    const actions=document.createElement('div');actions.className='pilot-incident-actions';const create=document.createElement('button');create.type='button';create.textContent='Registrar incidencia';create.addEventListener('click',openCreate);actions.append(create);panel.append(actions);document.body.append(panel);
  }

  async function openHistory(){globalThis.pilotLaunchGateClose?.();state.history=null;state.error=null;renderHistory();await loadHistory();renderHistory()}

  function installGateControls(){
    ensureStyles();const panel=document.querySelector('#post-w99-pilot-launch-gate-panel');if(!panel)return;const actions=panel.querySelector('.pilot-launch-actions');if(!actions||actions.querySelector('[data-pilot-incident-create]'))return;
    const create=document.createElement('button');create.type='button';create.dataset.pilotIncidentCreate='1';create.textContent='Registrar incidencia';create.addEventListener('click',openCreate);
    const history=document.createElement('button');history.type='button';history.dataset.pilotIncidentHistory='1';history.textContent='Incidencias';history.addEventListener('click',openHistory);actions.append(create,history);
  }

  window.addEventListener('post-w99-pilot-launch-gate-rendered',installGateControls);
  globalThis.pilotIncidentLogOpen=openHistory;
  globalThis.pilotIncidentLogCreate=openCreate;
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(installGateControls,0),{once:true});else setTimeout(installGateControls,0);
})();
