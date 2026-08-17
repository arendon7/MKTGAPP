const editorialState={selectedId:null,busy:false};

function editorialStyles(){
  if(document.querySelector('#editorial-wave42-style'))return;
  const style=document.createElement('style');style.id='editorial-wave42-style';style.textContent=`
  .editorial-calendar .marketing-ops-calendar-head,.editorial-calendar .marketing-ops-calendar-row{grid-template-columns:150px 130px 110px minmax(0,1fr) 105px 100px}.editorial-manage{font-size:10px;min-height:32px}.editorial-panel{display:grid;gap:10px;margin:0 0 12px;padding:14px;border:1px solid #171717;border-radius:14px;background:#fff}.editorial-panel-head{display:flex;justify-content:space-between;gap:12px}.editorial-panel textarea{min-height:100px;resize:vertical}.editorial-panel .two{display:grid;grid-template-columns:1fr 1fr;gap:10px}.editorial-meta{font-size:10px;color:#6f6b64}.editorial-danger{border-color:#9b2f2f;color:#8a2020}@media(max-width:700px){.editorial-calendar .marketing-ops-calendar-row{grid-template-columns:1fr}.editorial-panel .two{grid-template-columns:1fr}}
  `;document.head.append(style)
}
function editorialCanManage(row){return ['DRAFT','QUEUED','FAILED'].includes(String(row?.status||''))}
function editorialLocalInput(value){if(!value)return'';const date=new Date(value);if(Number.isNaN(date.getTime()))return'';const pad=n=>String(n).padStart(2,'0');return`${date.getFullYear()}-${pad(date.getMonth()+1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`}
function editorialSelected(){return marketingOpsState.calendar.find(row=>row.id===editorialState.selectedId)||null}

async function editorialCancel(row){
  if(editorialState.busy||!editorialCanManage(row))return;
  if(!window.confirm(`Cancelar esta publicación de ${row.company_name||'la empresa'}?`))return;
  editorialState.busy=true;
  try{await opsApi(`/api/companies/${encodeURIComponent(row.company_id)}/publications/${encodeURIComponent(row.id)}`,{method:'DELETE'});opsToast('Publicación cancelada');editorialState.selectedId=null;await refreshMarketingOps(true);renderMarketingOps()}catch(err){opsToast(err.message)}finally{editorialState.busy=false}
}

async function editorialReplace(row,message,dateValue){
  if(editorialState.busy||!editorialCanManage(row))return;
  const payload={message:String(message||'').trim(),scheduled_for:null};
  if(dateValue){const date=new Date(dateValue);if(Number.isNaN(date.getTime())){opsToast('Fecha inválida');return}payload.scheduled_for=date.toISOString()}
  editorialState.busy=true;
  try{const result=await opsApi(`/api/companies/${encodeURIComponent(row.company_id)}/publications/${encodeURIComponent(row.id)}/replace`,{method:'POST',body:payload});opsToast(result.replacement?.status==='QUEUED'?'Publicación reprogramada':'Nueva versión guardada como borrador');editorialState.selectedId=result.replacement?.id||null;await refreshMarketingOps(true);renderMarketingOps()}catch(err){opsToast(err.message)}finally{editorialState.busy=false}
}

function editorialPanel(root,row){
  const panel=opsEl('section','editorial-panel');const head=opsEl('div','editorial-panel-head');const copy=opsEl('div','');copy.append(opsEl('p','eyebrow','GESTIONAR PUBLICACIÓN'),opsEl('strong','',`${row.company_name||'Empresa'} · ${row.channel==='instagram'?'Instagram':'Facebook'}`),opsEl('div','editorial-meta',`Formato ${row.kind} · Estado ${opsStatusLabel(row.status)} · ID ${row.id.slice(0,8)}…`));const close=opsEl('button','','Cerrar');close.type='button';close.addEventListener('click',()=>{editorialState.selectedId=null;renderMarketingOps()});head.append(copy,close);panel.append(head);
  const note=opsEl('div','marketing-ops-note','Puedes corregir copy y fecha. Canal, formato, cuenta y archivo permanecen inmutables. Guardar crea una nueva versión y cancela la anterior para conservar trazabilidad.');panel.append(note);
  if(row.error)panel.append(opsEl('div','marketing-ops-note',`Último error: ${row.error}`));
  const fields=opsEl('div','two');const messageLabel=opsEl('label','','Copy / caption');const message=document.createElement('textarea');message.value=row.message||'';message.maxLength=20000;messageLabel.append(message);const dateLabel=opsEl('label','','Programar para');const date=document.createElement('input');date.type='datetime-local';date.value=editorialLocalInput(row.status==='QUEUED'?row.scheduled_for:null);dateLabel.append(date,opsEl('span','editorial-meta','Déjalo vacío para guardar la nueva versión como borrador. Una reprogramación debe quedar al menos 60 segundos en el futuro.'));fields.append(messageLabel,dateLabel);panel.append(fields);
  const actions=opsEl('div','marketing-ops-actions');const save=opsEl('button','primary','Guardar nueva versión');save.type='button';save.addEventListener('click',()=>editorialReplace(row,message.value,date.value));const cancel=opsEl('button','editorial-danger','Cancelar publicación');cancel.type='button';cancel.addEventListener('click',()=>editorialCancel(row));actions.append(save,cancel);panel.append(actions);root.append(panel)
}

renderOpsCalendar=function(root){
  editorialStyles();const section=opsEl('section','marketing-ops-section');const head=opsEl('div','marketing-ops-section-head');const copy=opsEl('div','');copy.append(opsEl('p','eyebrow','CALENDARIO EDITORIAL'),opsEl('h3','','Publicaciones'),opsEl('p','muted','Corrige, reprograma o cancela borradores y publicaciones todavía no enviadas.'));head.append(copy);const add=opsEl('button','primary','+ Programar');add.type='button';add.addEventListener('click',()=>opsShowView('publish'));head.append(add);section.append(head);
  const selected=editorialSelected();if(selected&&editorialCanManage(selected))editorialPanel(section,selected);
  if(!marketingOpsState.calendar.length){section.append(opsEmpty('Todavía no hay publicaciones para este filtro.'));root.append(section);return}
  const table=opsEl('div','marketing-ops-calendar editorial-calendar');const header=opsEl('div','marketing-ops-calendar-head');['Fecha','Empresa','Canal','Contenido','Estado','Acciones'].forEach(text=>header.append(opsEl('span','',text)));table.append(header);
  [...marketingOpsState.calendar].sort((a,b)=>String(a.scheduled_for||a.created_at).localeCompare(String(b.scheduled_for||b.created_at))).forEach(row=>{const line=opsEl('div','marketing-ops-calendar-row');line.append(opsEl('span','',opsDate(row.scheduled_for||row.created_at)),opsEl('span','',row.company_name||'—'),opsEl('span','',row.channel==='instagram'?'Instagram':'Facebook'),opsEl('p','',row.message||'(sin copy)'),opsEl('span','status',opsStatusLabel(row.status)));const action=opsEl('div','');if(editorialCanManage(row)){const manage=opsEl('button','editorial-manage','Gestionar');manage.type='button';manage.addEventListener('click',()=>{editorialState.selectedId=row.id;renderMarketingOps()});action.append(manage)}else action.append(opsEl('span','editorial-meta','Sólo lectura'));line.append(action);table.append(line)});section.append(table);root.append(section)
};

editorialStyles();if(marketingOpsState.view==='calendar')renderMarketingOps();
