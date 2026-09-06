(function postW99CloudSocialBridge(){
  'use strict';
  if(window.__postW99CloudSocialBridgeLoaded)return;
  window.__postW99CloudSocialBridgeLoaded=true;

  const originalStatus=window.opsStatusLabel;
  if(typeof originalStatus==='function'){
    window.opsStatusLabel=function(value){
      if(value==='DELEGATED')return 'Delegada a cloud';
      return originalStatus(value);
    };
  }

  function selectedRows(){
    const rows=Array.isArray(window.marketingOpsState?.calendar)?[...window.marketingOpsState.calendar]:[];
    return rows.sort((a,b)=>String(a.scheduled_for||a.created_at).localeCompare(String(b.scheduled_for||b.created_at)));
  }

  function route(row,action){
    return `/api/companies/${encodeURIComponent(row.company_id)}/publications/${encodeURIComponent(row.id)}/cloud/${action}`;
  }

  async function readOverview(row){
    return window.opsApi(route(row,'status'));
  }

  async function act(row,action){
    return window.opsApi(route(row,action),{method:'POST',body:{}});
  }

  function button(label){
    const node=document.createElement('button');
    node.type='button';
    node.className='post-w99-cloud-social-action';
    node.textContent=label;
    return node;
  }

  function describe(result){
    const delegation=result?.delegation||{};
    if(result?.requires_manual_reconciliation)return 'Estado cloud ambiguo: revisar Meta manualmente antes de cualquier reintento.';
    if(result?.local_status==='PUBLISHED')return 'Publicación cloud confirmada y reconciliada localmente.';
    if(result?.local_status==='FAILED')return 'Cloud confirmó fallo sin resultado remoto ambiguo. Revisa antes de volver a programar.';
    if(delegation.status==='PREPARED')return 'Autoridad local retirada. El enqueue cloud aún no está confirmado.';
    if(delegation.remote_status==='LEASED')return 'Cloud está procesando esta publicación.';
    if(delegation.status==='CONFIRMED')return 'Publicación confirmada en la cola cloud.';
    return 'Estado cloud actualizado.';
  }

  async function delegatedControl(row,node){
    node.disabled=true;
    try{
      const current=await readOverview(row);
      const delegation=current?.delegation||{};
      if(delegation.status==='PREPARED'){
        node.textContent='Reintentar cloud';
        node.disabled=false;
        node.onclick=async()=>{
          node.disabled=true;
          try{
            const retried=await act(row,'retry');
            window.opsToast?.(describe(retried));
            await window.refreshMarketingOps?.(true);
          }catch(err){window.opsToast?.(err.message)}finally{node.disabled=false}
        };
        window.opsToast?.(describe(current));
        return;
      }
      const refreshed=await act(row,'refresh');
      window.opsToast?.(describe(refreshed));
      await window.refreshMarketingOps?.(true);
    }catch(err){
      window.opsToast?.(err.message);
    }finally{
      if(node.textContent!=='Reintentar cloud')node.disabled=false;
    }
  }

  function decorateCalendar(){
    const table=document.querySelector('.marketing-ops-calendar');
    if(!table)return;
    const domRows=[...table.querySelectorAll('.marketing-ops-calendar-row')];
    const rows=selectedRows();
    domRows.forEach((line,index)=>{
      const row=rows[index];
      if(!row||!row.company_id||!row.id||line.querySelector('[data-cloud-social-control]'))return;
      const stateCell=line.lastElementChild;
      if(!stateCell)return;
      const holder=document.createElement('span');
      holder.dataset.cloudSocialControl='1';
      holder.style.display='block';
      holder.style.marginTop='6px';
      if(row.status==='QUEUED'){
        const control=button('Delegar a cloud');
        control.onclick=async()=>{
          const confirmed=window.confirm('Delegar esta publicación a cloud retira primero la autoridad del programador local. Si la red falla quedará detenida hasta reintentar explícitamente. ¿Continuar?');
          if(!confirmed)return;
          control.disabled=true;
          try{
            const result=await act(row,'delegate');
            window.opsToast?.(describe(result));
            await window.refreshMarketingOps?.(true);
          }catch(err){window.opsToast?.(err.message)}finally{control.disabled=false}
        };
        holder.append(control);
      }else if(row.status==='DELEGATED'){
        const control=button('Estado cloud');
        control.onclick=()=>delegatedControl(row,control);
        holder.append(control);
      }else{
        return;
      }
      stateCell.append(holder);
    });
  }

  const originalRender=window.renderOpsCalendar;
  if(typeof originalRender==='function'){
    window.renderOpsCalendar=function(root){
      originalRender(root);
      decorateCalendar();
    };
  }

  // Current view may already be calendar when this additive bundle arrives.
  if(window.marketingOpsState?.view==='calendar'&&typeof window.renderMarketingOps==='function'){
    window.renderMarketingOps();
  }
})();
