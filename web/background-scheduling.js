const backgroundState={status:null,error:null,busy:false,timer:null};

function backgroundEnsureStyles(){
  if(document.querySelector('#background-scheduling-style'))return;
  const style=document.createElement('style');style.id='background-scheduling-style';style.textContent=`
    .background-scheduling{margin-top:14px}.background-scheduling-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}
    .background-scheduling-state{display:inline-flex;align-items:center;padding:6px 9px;border-radius:999px;background:#efede7;font-size:10px;font-weight:900;text-transform:uppercase}.background-scheduling-state.enabled{background:#171717;color:#fff}.background-scheduling-state.attention{border:1px solid #171717;background:#fff}
    .background-scheduling-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:11px 0}.background-scheduling-grid div{padding:10px;border:1px solid #e1ded5;border-radius:11px;background:#fff}.background-scheduling-grid span,.background-scheduling-grid strong{display:block}.background-scheduling-grid span{font-size:9px;color:#77736b;text-transform:uppercase}.background-scheduling-grid strong{margin-top:3px;font-size:12px;overflow-wrap:anywhere}
    .background-scheduling-copy{margin:7px 0;color:#6f6c65;font-size:11px;line-height:1.45}.background-scheduling-error{color:#8a3329}
    @media(max-width:700px){.background-scheduling-head{display:block}.background-scheduling-grid{grid-template-columns:1fr}.background-scheduling .marketing-ops-actions button{width:100%}}
  `;document.head.append(style)
}

function backgroundLabel(status){
  if(!status)return ['VERIFICANDO',''];
  if(!status.supported)return ['SOLO CON APP ABIERTA','attention'];
  if(status.registration==='enabled')return ['ACTIVO','enabled'];
  if(status.registration==='requires-approval')return ['REQUIERE APROBACIÓN','attention'];
  if(status.registration==='not-registered')return ['INACTIVO',''];
  if(status.registration==='not-found')return ['REVISAR INSTALACIÓN','attention'];
  if(status.registration==='helper-unavailable')return ['NO DISPONIBLE','attention'];
  if(status.registration==='error')return ['ERROR','attention'];
  return ['INACTIVO',''];
}

function backgroundLastRun(status){const row=status?.last_agent_run;if(!row)return 'Todavía sin ejecución en segundo plano';if(row.error)return row.error;return row.last_run_at?opsDate(row.last_run_at):'Sin fecha registrada'}
function backgroundQueue(status){const q=status?.queue||{};return `${q.queued||0} programadas · ${q.failed||0} con error`}

function renderBackgroundScheduling(root){
  backgroundEnsureStyles();const status=backgroundState.status;const [label,stateClass]=backgroundLabel(status);const section=opsEl('section','marketing-ops-section background-scheduling');const head=opsEl('div','background-scheduling-head');const copy=opsEl('div','');copy.append(opsEl('p','eyebrow','PROGRAMACIÓN EN SEGUNDO PLANO'),opsEl('h3','','Que tus publicaciones no dependan de la ventana abierta'));const badge=opsEl('span',`background-scheduling-state ${stateClass}`,label);head.append(copy,badge);section.append(head);
  const description=status?.supported?'Cuando está activo, macOS revisa aproximadamente cada minuto la misma cola que ves en Calendario, dentro de tu sesión de usuario. Si el Mac duerme o está apagado, la ejecución puede retrasarse.':'En este Mac la cola se procesa mientras MERCADEO APP esté abierta. La ejecución con la ventana cerrada requiere macOS 13 o posterior.';section.append(opsEl('p','background-scheduling-copy',description));
  const grid=opsEl('div','background-scheduling-grid');grid.append(backgroundInfo('Última ejecución',backgroundLastRun(status)),backgroundInfo('Cola',backgroundQueue(status)),backgroundInfo('Cadencia',status?.supported?'≈ 1 minuto · best effort':'Mientras la app esté abierta'));section.append(grid);
  if(status?.requires_approval)section.append(opsEl('p','background-scheduling-copy','macOS requiere tu aprobación en Ajustes del Sistema → General → Ítems de inicio antes de dejar el agente activo.'));
  if(backgroundState.error||status?.error)section.append(opsEl('p','background-scheduling-copy background-scheduling-error',backgroundState.error||status.error));
  const actions=opsEl('div','marketing-ops-actions');const refresh=backgroundButton('Actualizar',()=>refreshBackgroundScheduling(true));actions.append(refresh);
  if(status?.supported&&status.registration!=='enabled'){actions.prepend(backgroundButton(backgroundState.busy?'Activando…':'Activar',()=>backgroundMutate('register'),true,backgroundState.busy));}
  if(status?.supported&&status.registration==='enabled'){actions.prepend(backgroundButton(backgroundState.busy?'Desactivando…':'Desactivar',()=>backgroundMutate('unregister'),false,backgroundState.busy));}
  if(status?.supported&&(status.requires_approval||status.registration==='enabled'))actions.append(backgroundButton('Abrir Login Items',()=>backgroundMutate('open-settings')));
  section.append(actions);root.append(section)
}
function backgroundInfo(label,value){const node=opsEl('div','');node.append(opsEl('span','',label),opsEl('strong','',value));return node}
function backgroundButton(label,action,primary=false,disabled=false){const button=opsEl('button',primary?'primary':'',label);button.type='button';button.disabled=disabled;button.addEventListener('click',action);return button}

async function refreshBackgroundScheduling(rerender=false){
  try{backgroundState.status=await opsApi('/api/background-scheduling');backgroundState.error=null}catch(err){backgroundState.error=err.message;backgroundState.status=null}
  if(rerender&&marketingOpsState.view==='home'&&typeof renderMarketingOps==='function')renderMarketingOps()
}

async function backgroundMutate(action){
  if(backgroundState.busy)return;backgroundState.busy=true;backgroundState.error=null;if(marketingOpsState.view==='home')renderMarketingOps();
  try{
    if(action==='unregister')backgroundState.status=await opsApi('/api/background-scheduling',{method:'DELETE'});
    else backgroundState.status=await opsApi(`/api/background-scheduling/${action}`,{method:'POST',body:{}});
    opsToast(action==='register'?'Programación en segundo plano solicitada':action==='unregister'?'Programación en segundo plano desactivada':'Ajustes de Login Items abiertos');
  }catch(err){backgroundState.error=err.message;opsToast(err.message)}finally{backgroundState.busy=false;await refreshBackgroundScheduling(false);if(marketingOpsState.view==='home')renderMarketingOps()}
}

const backgroundBaseRenderHome=globalThis.renderOpsHome;
if(typeof backgroundBaseRenderHome==='function')globalThis.renderOpsHome=function(root){backgroundBaseRenderHome(root);renderBackgroundScheduling(root)};
backgroundEnsureStyles();refreshBackgroundScheduling(true);
clearInterval(backgroundState.timer);backgroundState.timer=setInterval(()=>{if(marketingOpsState.view==='home')refreshBackgroundScheduling(true)},30000);
window.addEventListener('beforeunload',()=>clearInterval(backgroundState.timer));
globalThis.refreshBackgroundScheduling=refreshBackgroundScheduling;
