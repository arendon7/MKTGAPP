const wave67State={companyId:null,overview:null,loading:false,busy:false};

function wave67Styles(){
  if(document.querySelector('#wave67-physical-uat-style'))return;
  const style=document.createElement('style');style.id='wave67-physical-uat-style';style.textContent=`
  .w67-shell{display:grid;gap:10px}.w67-hero{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(280px,.7fr);gap:10px}.w67-panel,.w67-machine,.w67-scenario{padding:13px;border:1px solid #ddd8cf;border-radius:12px;background:#fff;display:grid;gap:8px}.w67-panel h3,.w67-scenario h4{margin:0}.w67-machine strong{font-size:12px}.w67-machine span,.w67-note{font-size:8px;color:#6f6a62;line-height:1.45}.w67-chip{display:inline-flex;width:max-content;padding:4px 7px;border-radius:999px;background:#efede7;font-size:8px}.w67-chip.pass{background:#e5f0e6}.w67-chip.fail{background:#f7e4df}.w67-chip.blocked{background:#171717;color:#fff}.w67-chip.pending,.w67-chip.skipped{background:#f0eee8}.w67-actions{display:flex;gap:6px;flex-wrap:wrap}.w67-start{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.5fr) auto;gap:6px}.w67-start input{min-width:0}.w67-list{display:grid;gap:8px}.w67-scenario{grid-template-columns:minmax(0,1fr) minmax(240px,.7fr);align-items:start}.w67-scenario-copy{display:grid;gap:5px}.w67-scenario-controls{display:grid;gap:6px}.w67-scenario-controls textarea{width:100%;min-height:62px;resize:vertical}.w67-session-head{display:flex;justify-content:space-between;gap:8px;align-items:flex-start}.w67-report{padding:9px;border-radius:9px;background:#f6f3ed;font-size:8px;line-height:1.5;word-break:break-word}.w67-warning{padding:10px;border-left:4px solid #171717;background:#f6f3ed;font-size:9px;line-height:1.5}.w67-history{display:grid;gap:5px}.w67-history-row{display:flex;justify-content:space-between;gap:8px;padding:7px 0;border-bottom:1px solid #eeeae2;font-size:8px}.w67-history-row:last-child{border-bottom:0}
  @media(max-width:900px){.w67-hero,.w67-scenario{grid-template-columns:1fr}.w67-start{grid-template-columns:1fr}.w67-session-head{display:grid}}
  `;document.head.append(style)
}

function wave67Company(){return typeof opsSelectedCompany==='function'?opsSelectedCompany():null}
function wave67Chip(status){return opsEl('span',`w67-chip ${String(status||'PENDING').toLowerCase()}`,status||'PENDING')}
function wave67RequiredPending(session){return (session?.scenarios||[]).filter(row=>row.required&&row.status==='PENDING').length}

async function wave67Load(force=false){
  const company=wave67Company();if(!company){wave67State.companyId=null;wave67State.overview=null;return null}
  if(wave67State.loading)return wave67State.overview;
  if(!force&&wave67State.companyId===company.id&&wave67State.overview)return wave67State.overview;
  wave67State.loading=true;
  try{const data=await opsApi(`/api/companies/${encodeURIComponent(company.id)}/physical-uat`);wave67State.companyId=company.id;wave67State.overview=data;return data}catch(err){opsToast(err.message);return null}finally{wave67State.loading=false}
}

async function wave67Start(operator,notes){
  const company=wave67Company();if(!company||wave67State.busy)return;
  if(!confirm('Iniciar una nueva sesión UAT física. Cada resultado deberá marcarse manualmente y CI nunca podrá satisfacer el gate físico. ¿Continuar?'))return;
  wave67State.busy=true;
  try{
    await opsApi(`/api/companies/${encodeURIComponent(company.id)}/physical-uat`,{method:'POST',body:{operator:operator||null,notes:notes||null}});
    await wave67Load(true);opsToast('Sesión UAT iniciada; ningún escenario se marca automáticamente');wave67Inject()
  }catch(err){opsToast(err.message)}finally{wave67State.busy=false}
}

async function wave67Record(session,scenario,status,note){
  const company=wave67Company();if(!company||wave67State.busy)return;
  const verb=status==='PASS'?'aprobar':status==='FAIL'?'marcar como fallo':status==='BLOCKED'?'marcar como bloqueado':'omitir';
  if(!confirm(`¿Confirmas ${verb} el escenario “${scenario.label}”?`))return;
  wave67State.busy=true;
  try{
    await opsApi(`/api/companies/${encodeURIComponent(company.id)}/physical-uat/${encodeURIComponent(session.id)}/scenarios/${encodeURIComponent(scenario.id)}`,{method:'PATCH',body:{status,note:note||null}});
    await wave67Load(true);wave67Inject()
  }catch(err){opsToast(err.message)}finally{wave67State.busy=false}
}

async function wave67Finish(session){
  const company=wave67Company();if(!company||wave67State.busy)return;
  const pending=wave67RequiredPending(session);if(pending){opsToast(`${pending} escenario(s) requerido(s) siguen pendientes`);return}
  if(!confirm('Cerrar esta sesión UAT. El resultado se calculará desde la evidencia registrada y no cambiará RELEASE_READY. ¿Continuar?'))return;
  wave67State.busy=true;
  try{
    const result=await opsApi(`/api/companies/${encodeURIComponent(company.id)}/physical-uat/${encodeURIComponent(session.id)}/finish`,{method:'POST',body:{}});
    await wave67Load(true);opsToast(result.physical_uat_complete?'UAT física registrada como PASS elegible':'Sesión cerrada; el gate físico no quedó satisfecho');wave67Inject()
  }catch(err){opsToast(err.message)}finally{wave67State.busy=false}
}

async function wave67Download(session){
  const company=wave67Company();if(!company)return;
  try{
    const report=await opsApi(`/api/companies/${encodeURIComponent(company.id)}/physical-uat/${encodeURIComponent(session.id)}/report`);
    const blob=new Blob([JSON.stringify(report,null,2)+'\n'],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`BINARIO-UAT-${session.id}.json`;document.body.append(a);a.click();a.remove();URL.revokeObjectURL(url)
  }catch(err){opsToast(err.message)}
}

function wave67Scenario(session,row){
  const card=opsEl('article','w67-scenario'),copy=opsEl('div','w67-scenario-copy'),head=opsEl('div','w67-session-head'),title=opsEl('div','');title.append(opsEl('p','eyebrow',row.required?'REQUERIDO':'OPCIONAL'),opsEl('h4','',row.label));head.append(title,wave67Chip(row.status));copy.append(head,opsEl('span','w67-note',row.updated_at?`Última evidencia: ${opsDate(row.updated_at)}`:'Aún no ejecutado en esta sesión.'));
  const controls=opsEl('div','w67-scenario-controls'),note=document.createElement('textarea');note.placeholder='Nota breve de evidencia, comportamiento observado o bloqueo';note.value=row.note||'';note.disabled=session.status!=='IN_PROGRESS';controls.append(note);
  const actions=opsEl('div','w67-actions');for(const [status,label,cls] of [['PASS','PASS','primary'],['FAIL','FAIL',''],['BLOCKED','BLOQUEADO','']]){const button=opsEl('button',cls,label);button.type='button';button.disabled=session.status!=='IN_PROGRESS'||wave67State.busy;button.addEventListener('click',()=>wave67Record(session,row,status,note.value.trim()));actions.append(button)}if(!row.required){const skip=opsEl('button','','OMITIR OPCIONAL');skip.type='button';skip.disabled=session.status!=='IN_PROGRESS'||wave67State.busy;skip.addEventListener('click',()=>wave67Record(session,row,'SKIPPED',note.value.trim()));actions.append(skip)}controls.append(actions);card.append(copy,controls);return card
}

function wave67History(overview){
  const panel=opsEl('section','w67-panel');panel.append(opsEl('p','eyebrow','HISTORIAL LOCAL'),opsEl('h3','','Sesiones UAT'));const list=opsEl('div','w67-history');for(const row of (overview.sessions||[]).slice(0,8)){const item=opsEl('div','w67-history-row'),left=opsEl('div','');left.append(opsEl('strong','',row.id),opsEl('span','w67-note',`${row.operator||'Sin operador'} · ${opsDate(row.created_at)}`));const right=opsEl('div','w67-actions');right.append(wave67Chip(row.status));const report=opsEl('button','','Reporte');report.type='button';report.addEventListener('click',()=>wave67Download(row));right.append(report);item.append(left,right);list.append(item)}if(!(overview.sessions||[]).length)list.append(opsEl('div','w67-note','Aún no hay sesiones físicas registradas.'));panel.append(list);return panel
}

function wave67Panel(overview){
  const shell=opsEl('section','w67-shell'),session=overview.active_session||overview.latest_session,hero=opsEl('div','w67-hero'),intro=opsEl('section','w67-panel');intro.append(opsEl('p','eyebrow','PHYSICAL UAT EVIDENCE · W67'),opsEl('h3','','Evidencia de prueba en Mac físico'),opsEl('p','muted','Este harness registra lo que una persona ejecuta y observa. No prueba escenarios solo, no consulta proveedores y no cambia el estado de release.'));
  if(!session){const form=opsEl('div','w67-start'),operator=document.createElement('input'),notes=document.createElement('input'),start=opsEl('button','primary','Iniciar UAT física');operator.placeholder='Operador / responsable';notes.placeholder='Notas de sesión (opcional)';start.type='button';start.addEventListener('click',()=>wave67Start(operator.value.trim(),notes.value.trim()));form.append(operator,notes,start);intro.append(form)}else{intro.append(opsEl('div','w67-report',`Última sesión: ${session.id} · ${session.status}${session.evidence_sha256?` · SHA ${session.evidence_sha256}`:''}`));if(session.status!=='IN_PROGRESS'){const fresh=opsEl('button','','Iniciar nueva sesión');fresh.type='button';fresh.addEventListener('click',()=>wave67Start('',`Repetición posterior a ${session.id}`));intro.append(fresh)}}
  const machine=opsEl('section','w67-machine'),m=session?.machine;machine.append(opsEl('p','eyebrow','ELEGIBILIDAD DEL GATE'),opsEl('strong','',m?(m.physical_gate_eligible?'Mac arm64 físico elegible':'Sesión no elegible para gate físico'):'Se captura al iniciar la sesión'));
  if(m)machine.append(opsEl('span','',`${m.system} · ${m.machine} · macOS ${m.macos_version||'—'} · CI=${m.is_ci}`));machine.append(opsEl('span','',overview.physical_uat_complete?'Existe una sesión PASS elegible. RELEASE_READY sigue bloqueado por gates posteriores.':'No existe todavía una sesión PASS elegible; CI y máquinas no arm64 nunca satisfacen este gate.'));hero.append(intro,machine);shell.append(hero);
  if(session){const panel=opsEl('section','w67-panel'),head=opsEl('div','w67-session-head'),copy=opsEl('div','');copy.append(opsEl('p','eyebrow','SESIÓN ACTUAL / ÚLTIMA'),opsEl('h3','',session.id),opsEl('span','w67-note',`${session.operator||'Sin operador'} · ${session.status}`));const actions=opsEl('div','w67-actions'),download=opsEl('button','','Exportar JSON');download.type='button';download.addEventListener('click',()=>wave67Download(session));actions.append(download);if(session.status==='IN_PROGRESS'){const finish=opsEl('button','primary','Cerrar sesión');finish.type='button';finish.disabled=wave67RequiredPending(session)>0||wave67State.busy;finish.addEventListener('click',()=>wave67Finish(session));actions.append(finish)}head.append(copy,actions);panel.append(head);
    if(session.status==='IN_PROGRESS'&&wave67RequiredPending(session))panel.append(opsEl('div','w67-warning',`${wave67RequiredPending(session)} escenario(s) requerido(s) siguen pendientes. El cierre permanece bloqueado hasta registrar PASS, FAIL o BLOCKED explícitamente.`));
    const list=opsEl('div','w67-list');for(const row of session.scenarios||[])list.append(wave67Scenario(session,row));panel.append(list);shell.append(panel)}
  shell.append(wave67History(overview));return shell
}

async function wave67Inject(){
  if(marketingOpsState?.view!=='uat-readiness')return;wave67Styles();const root=document.querySelector('#marketing-ops-view');if(!root)return;let mount=root.querySelector('#wave67-physical-uat');if(!mount){mount=opsEl('div','');mount.id='wave67-physical-uat';root.append(mount)}
  const company=wave67Company();if(!company){mount.replaceChildren();return}const overview=await wave67Load();if(!overview||marketingOpsState?.view!=='uat-readiness'||wave67Company()?.id!==company.id)return;mount.replaceChildren(wave67Panel(overview))
}

const wave67BaseRenderMarketingOps=globalThis.renderMarketingOps;
if(typeof wave67BaseRenderMarketingOps==='function')globalThis.renderMarketingOps=function(){const result=wave67BaseRenderMarketingOps();queueMicrotask(wave67Inject);return result};
window.addEventListener('marketing-company-change',()=>{wave67State.companyId=null;wave67State.overview=null;queueMicrotask(wave67Inject)});
wave67Styles();queueMicrotask(wave67Inject);
