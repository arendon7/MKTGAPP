const wave76JourneyState={data:null,loading:false};

const W76_STATUS_LABELS={VERIFIED:'Verificado',READY_TO_TEST:'Listo para probar',OPTIONAL_READY:'Opcional · listo',EXTERNAL_OPTIONAL:'Externo · opcional',NEEDS_REVIEW:'Revisar',BROKEN:'Bloqueado'};

function wave76Styles(){
  if(document.querySelector('#wave76-functional-journey-style'))return;
  const style=document.createElement('style');style.id='wave76-functional-journey-style';style.textContent=`
  .w76-journey{margin-top:12px;padding:14px;border:1px solid #d7d2c8;border-radius:13px;background:#fff;display:grid;gap:11px}.w76-head{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}.w76-head h3{margin:0}.w76-progress{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px}.w76-metric{padding:10px;border:1px solid #e4e0d7;border-radius:9px;display:grid;gap:3px}.w76-metric strong{font-size:18px}.w76-metric span{font-size:8px;color:#706c65}.w76-next{padding:10px;border-radius:10px;background:#f4f1e9;display:flex;justify-content:space-between;gap:10px;align-items:center}.w76-next strong{font-size:10px}.w76-next span{display:block;font-size:8px;color:#706c65;margin-top:2px}.w76-list{display:grid;gap:7px}.w76-row{padding:10px;border:1px solid #e4e0d7;border-radius:10px;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;align-items:center}.w76-row.verified{background:#eef4ee}.w76-row.broken,.w76-row.needs_review{background:#fff0df}.w76-copy{display:grid;gap:3px}.w76-copy strong{font-size:10px}.w76-copy span{font-size:8px;color:#706c65;line-height:1.45}.w76-side{display:flex;gap:6px;align-items:center;flex-wrap:wrap;justify-content:flex-end}.w76-chip{display:inline-flex;padding:4px 7px;border-radius:999px;background:#efede7;font-size:8px;white-space:nowrap}.w76-chip.verified{background:#dfece0}.w76-chip.broken,.w76-chip.needs_review{background:#ffe6ca}.w76-note{font-size:8px;color:#706c65;line-height:1.5;padding:9px;border:1px dashed #d7d2c8;border-radius:9px}.w76-actions{display:flex;gap:7px;flex-wrap:wrap}@media(max-width:760px){.w76-head,.w76-next,.w76-row{display:grid;grid-template-columns:1fr}.w76-progress{grid-template-columns:1fr}.w76-side{justify-content:flex-start}}
  `;document.head.append(style)
}

function wave76SandboxSelected(data){return Boolean(data?.sandbox?.company?.id&&String(marketingOpsState?.selectedCompanyId||'')===String(data.sandbox.company.id))}

async function wave76Load(force=false){
  if(wave76JourneyState.loading)return wave76JourneyState.data;
  if(!force&&wave76JourneyState.data)return wave76JourneyState.data;
  wave76JourneyState.loading=true;
  try{wave76JourneyState.data=await opsApi('/api/uat-sandbox/journey');return wave76JourneyState.data}
  catch(err){opsToast(err.message);return null}
  finally{wave76JourneyState.loading=false}
}

function wave76Go(row){
  if(!row?.view)return;
  if(row.view==='crm'&&row.tab&&typeof crmState!=='undefined')crmState.tab=row.tab;
  opsShowView(row.view)
}

function wave76Metric(value,label,copy){const node=opsEl('div','w76-metric');node.append(opsEl('strong','',String(value)),opsEl('span','',label),opsEl('span','',copy));return node}

function wave76Row(row){
  const node=opsEl('div',`w76-row ${String(row.status||'').toLowerCase()}`),copy=opsEl('div','w76-copy');copy.append(opsEl('strong','',row.label),opsEl('span','',row.detail),opsEl('span','',`Esperado: ${row.expected}`));
  const side=opsEl('div','w76-side'),chip=opsEl('span',`w76-chip ${String(row.status||'').toLowerCase()}`,W76_STATUS_LABELS[row.status]||row.status);side.append(chip);
  if(!['VERIFIED','EXTERNAL_OPTIONAL'].includes(row.status)){const open=opsEl('button',row.required?'primary':'','Abrir paso');open.type='button';open.addEventListener('click',()=>wave76Go(row));side.append(open)}
  node.append(copy,side);return node
}

function wave76Render(){
  if(marketingOpsState?.view!=='uat-readiness')return;wave76Styles();const root=document.querySelector('#marketing-ops-view');if(!root)return;root.querySelector('.w76-journey')?.remove();
  const panel=opsEl('section','w76-journey'),head=opsEl('div','w76-head'),copy=opsEl('div','');copy.append(opsEl('p','eyebrow','FUNCTIONAL JOURNEY VALIDATOR · W76'),opsEl('h3','','Recorrido funcional observado'),opsEl('p','muted','No ejecuta acciones ni autoasigna PASS. Solo observa el estado que dejaron tus acciones explícitas sobre el sandbox sintético.'));head.append(copy);panel.append(head);
  const data=wave76JourneyState.data;
  if(!data&&!wave76JourneyState.loading){panel.append(opsEl('div','w76-note','Leyendo estado local del recorrido…'));root.append(panel);wave76Load().then(wave76Render);return}
  if(wave76JourneyState.loading&&!data){panel.append(opsEl('div','w76-note','Actualizando evidencia funcional local…'));root.append(panel);return}
  if(!data?.sandbox?.exists){panel.append(opsEl('div','w76-note','Primero crea el sandbox W75. W76 nunca crea datos por sí solo.'));root.append(panel);return}
  if(!data?.sandbox?.active){panel.append(opsEl('div','w76-note','El sandbox registrado está inactivo. Recréalo desde el panel W75 para iniciar un recorrido nuevo.'));root.append(panel);return}
  const summary=data.summary||{},progress=opsEl('div','w76-progress');progress.append(
    wave76Metric(`${summary.core_verified||0}/${summary.core_required||0}`,'CORE VERIFICADO',summary.core_complete?'Recorrido funcional mínimo completo':'Faltan acciones explícitas'),
    wave76Metric(summary.optional_verified||0,'EXTENDIDO VERIFICADO',`${summary.optional_total||0} checkpoints opcionales`),
    wave76Metric(data.sandbox.generation||'—','GENERACIÓN','Sandbox sintético · nunca release')
  );panel.append(progress);
  if(!wave76SandboxSelected(data)){const note=opsEl('div','w76-next'),nc=opsEl('div','');nc.append(opsEl('strong','','Abre el sandbox antes de ejecutar el recorrido'),opsEl('span','',data.sandbox.company?.name||'Empresa sintética'));const b=opsEl('button','primary','Abrir sandbox');b.type='button';b.addEventListener('click',()=>typeof wave75OpenSandbox==='function'?wave75OpenSandbox():null);note.append(nc,b);panel.append(note)}
  else if(data.next_checkpoint){const next=opsEl('div','w76-next'),nc=opsEl('div','');nc.append(opsEl('strong','',`Siguiente checkpoint · ${data.next_checkpoint.label}`),opsEl('span','',data.next_checkpoint.detail));const b=opsEl('button','primary','Ir al paso');b.type='button';b.addEventListener('click',()=>wave76Go(data.next_checkpoint));next.append(nc,b);panel.append(next)}
  else panel.append(opsEl('div','w76-next',summary.core_complete?'Core funcional verificado. Los pasos externos/opcionales no alteran esta conclusión.':'No hay siguiente checkpoint disponible.'));
  const list=opsEl('div','w76-list');for(const row of data.checkpoints||[])list.append(wave76Row(row));panel.append(list);
  const actions=opsEl('div','w76-actions'),refresh=opsEl('button','','Verificar cambios');refresh.type='button';refresh.addEventListener('click',async()=>{await wave76Load(true);wave76Render()});actions.append(refresh);if(typeof wave75Create==='function'){const reset=opsEl('button','','Nuevo recorrido limpio');reset.type='button';reset.addEventListener('click',()=>wave75Create(true));actions.append(reset)}panel.append(actions);
  panel.append(opsEl('div','w76-note','Contrato: W76 es read-only. No convierte leads, no cambia etapas, no completa seguimientos, no crea creativos/publicaciones/pauta, no consulta providers y no registra evidencia física. Resultados e IA siguen siendo externos/opcionales porque W75 deliberadamente no siembra evidencia falsa.'));
  root.append(panel)
}

const wave76BaseRender=globalThis.renderMarketingOps;
if(typeof wave76BaseRender==='function')globalThis.renderMarketingOps=function(){const result=wave76BaseRender();queueMicrotask(wave76Render);return result};
window.addEventListener('marketing-company-change',()=>{wave76JourneyState.data=null;if(marketingOpsState?.view==='uat-readiness')wave76Load(true).then(wave76Render)});
wave76Render();
