(function installPostW99PilotRecoveryRehearsal(){
  if(globalThis.POST_W99_PILOT_RECOVERY_REHEARSAL)return;
  globalThis.POST_W99_PILOT_RECOVERY_REHEARSAL=true;

  const API='/api/pilot-data-safety/snapshots';
  const OPERATOR_HEADER={'X-Mercadeo-Operator':'pilot-data-safety'};
  let busy=false;

  function ensureStyles(){
    if(document.querySelector('#post-w99-pilot-recovery-rehearsal-style'))return;
    const style=document.createElement('style');
    style.id='post-w99-pilot-recovery-rehearsal-style';
    style.textContent=`
      .pilot-recovery-rehearsal-note{margin-top:9px;padding:10px 11px;border:1px solid #ded9d0;border-radius:10px;background:#faf9f6;font-size:9px;line-height:1.5;color:#5f5a52}
      .pilot-recovery-rehearsal-result{margin-top:9px;padding:10px 11px;border-radius:10px;background:#f2f0eb;font-size:10px;line-height:1.5}
      .pilot-recovery-rehearsal-result.pass{background:#171717;color:#fff}
      .pilot-recovery-rehearsal-result.error{background:#fbefec;color:#5f2721}
    `;
    document.head.append(style);
  }

  async function request(method,path){
    const options={method,cache:'no-store',headers:method==='POST'?OPERATOR_HEADER:{}};
    const response=await fetch(path,options);
    const payload=await response.json().catch(()=>({error:'Respuesta local inválida'}));
    if(!response.ok)throw new Error(payload.error||`Error local ${response.status}`);
    return payload;
  }

  function resultNode(panel){
    let node=panel.querySelector('#post-w99-pilot-recovery-rehearsal-result');
    if(!node){
      node=document.createElement('div');
      node.id='post-w99-pilot-recovery-rehearsal-result';
      node.className='pilot-recovery-rehearsal-result';
      const actions=Array.from(panel.children).find(child=>child.classList?.contains('pilot-data-safety-actions'));
      (actions||panel).insertAdjacentElement('afterend',node);
    }
    return node;
  }

  function show(panel,message,kind=''){
    const node=resultNode(panel);
    node.className=`pilot-recovery-rehearsal-result ${kind}`.trim();
    node.textContent=message;
  }

  async function rehearse(panel,button){
    if(busy)return;
    busy=true;
    button.disabled=true;
    button.textContent='Probando…';
    show(panel,'Verificando el respaldo y preparando un espacio temporal aislado. Los datos activos no se reemplazan.');
    try{
      const listing=await request('GET',API);
      const snapshot=Array.isArray(listing.snapshots)?listing.snapshots[0]:null;
      if(!snapshot?.id){
        show(panel,'No hay un respaldo disponible. Crea primero un respaldo verificado y vuelve a probar.','error');
        return;
      }
      const outcome=await request('POST',`${API}/${encodeURIComponent(snapshot.id)}/rehearse`);
      const files=Number(outcome?.readability?.files_checked)||0;
      if(outcome.status!=='PASS'||!outcome.active_data_unchanged||!outcome.workspace_cleaned){
        throw new Error('El ensayo no pudo demostrar una recuperación aislada segura.');
      }
      show(panel,`RECUPERACIÓN VERIFICADA · ${files} archivos comprobados · datos activos sin cambios · espacio temporal eliminado.`,'pass');
    }catch(error){
      show(panel,String(error?.message||'No fue posible completar el ensayo local de recuperación.'),'error');
    }finally{
      busy=false;
      button.disabled=false;
      button.textContent='Probar recuperación';
    }
  }

  function installControl(){
    ensureStyles();
    const panel=document.querySelector('#post-w99-pilot-data-safety-panel');
    if(!panel||panel.querySelector('[data-pilot-recovery-rehearsal]'))return;
    const actions=Array.from(panel.children).find(child=>child.classList?.contains('pilot-data-safety-actions'));
    if(!actions)return;
    const button=document.createElement('button');
    button.type='button';
    button.dataset.pilotRecoveryRehearsal='1';
    button.textContent='Probar recuperación';
    button.addEventListener('click',()=>rehearse(panel,button));
    actions.append(button);
    const note=document.createElement('div');
    note.className='pilot-recovery-rehearsal-note';
    note.dataset.pilotRecoveryRehearsal='1';
    note.textContent='Prueba el respaldo más reciente en un espacio temporal separado. No restaura, borra ni reemplaza los datos activos y no inicia conexiones externas.';
    actions.insertAdjacentElement('afterend',note);
  }

  document.addEventListener('click',event=>{
    if(event.target?.closest?.('.pilot-data-safety-action, #post-w99-pilot-data-safety-panel')){
      setTimeout(installControl,0);
    }
  });
  window.addEventListener('marketing-ops-refreshed',()=>setTimeout(installControl,0));
  window.addEventListener('wave73-entry-ready',()=>setTimeout(installControl,0));
  window.addEventListener('wave73-bootstrap-ready',()=>setTimeout(installControl,0));
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(installControl,0),{once:true});
  else setTimeout(installControl,0);
})();
