const wave69State={companyId:null,data:null,loading:false,baseStart:typeof wave67Start==='function'?wave67Start:null,baseInject:typeof wave67Inject==='function'?wave67Inject:null};

function wave69Styles(){
  if(document.querySelector('#wave69-physical-uat-preflight-style'))return;
  const style=document.createElement('style');style.id='wave69-physical-uat-preflight-style';style.textContent=`
  .w69-preflight{padding:13px;border:1px solid #d9d5cc;border-radius:12px;background:#fff;display:grid;gap:10px}.w69-head{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}.w69-head h3{margin:0}.w69-status{display:inline-flex;padding:5px 8px;border-radius:999px;background:#f3e7df;font-size:8px;white-space:nowrap}.w69-status.ready{background:#e4efe5}.w69-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px}.w69-check{padding:8px;border:1px solid #e5e1d9;border-radius:9px;display:grid;gap:3px}.w69-check.pass{background:#f3f7f3}.w69-check.blocked{background:#faf4ef}.w69-check strong{font-size:9px}.w69-check span{font-size:8px;color:#706c65;line-height:1.4}.w69-footer{display:flex;justify-content:space-between;gap:10px;align-items:center;padding:9px;border-radius:9px;background:#f6f3ed}.w69-footer strong{font-size:9px}.w69-footer span{display:block;font-size:8px;color:#706c65;margin-top:2px}.w69-blockers{font-size:8px;color:#706c65;line-height:1.45}
  @media(max-width:1050px){.w69-grid{grid-template-columns:1fr 1fr}}@media(max-width:650px){.w69-grid{grid-template-columns:1fr}.w69-head,.w69-footer{display:grid}}
  `;document.head.append(style)
}
function wave69Company(){return typeof opsSelectedCompany==='function'?opsSelectedCompany():null}
async function wave69Load(force=false){
  const company=wave69Company();if(!company){wave69State.companyId=null;wave69State.data=null;return null}
  if(wave69State.loading)return wave69State.data;
  if(!force&&wave69State.companyId===company.id&&wave69State.data)return wave69State.data;
  wave69State.loading=true;
  try{const data=await opsApi(`/api/companies/${encodeURIComponent(company.id)}/physical-uat/preflight`);wave69State.companyId=company.id;wave69State.data=data;return data}catch(err){opsToast(err.message);return null}finally{wave69State.loading=false}
}
function wave69Panel(data){
  const panel=opsEl('section','w69-preflight'),head=opsEl('div','w69-head'),copy=opsEl('div','');copy.append(opsEl('p','eyebrow','PHYSICAL UAT PREFLIGHT · W69'),opsEl('h3','','Preflight técnico del Mac y del bundle'),opsEl('p','muted','Comprueba elegibilidad y componentes antes de iniciar evidencia manual. No ejecuta escenarios, no consulta providers y no abre el release.'));const status=opsEl('span',`w69-status ${data.ready_to_begin_physical_uat?'ready':''}`,data.ready_to_begin_physical_uat?'LISTO PARA INICIAR':'PREFLIGHT BLOQUEADO');head.append(copy,status);panel.append(head);
  const grid=opsEl('div','w69-grid');for(const row of data.checks||[]){const card=opsEl('div',`w69-check ${row.passed?'pass':'blocked'}`);card.append(opsEl('strong','',`${row.passed?'PASS':'BLOQUEADO'} · ${row.label}`),opsEl('span','',row.detail));grid.append(card)}panel.append(grid);
  if((data.blockers||[]).length)panel.append(opsEl('div','w69-blockers',`Bloqueos: ${data.blockers.join(' · ')}. La sesión física no debe iniciarse desde este entorno.`));
  const footer=opsEl('div','w69-footer'),footerCopy=opsEl('div','');footerCopy.append(opsEl('strong','',data.next_action?.label||'Revisar preflight'),opsEl('span','',`${data.scenario_contract?.required||0} escenarios requeridos · ${data.scenario_contract?.optional||0} opcional(es) · evidencia siempre manual`));const refresh=opsEl('button','','Revalidar preflight');refresh.type='button';refresh.addEventListener('click',async()=>{await wave69Load(true);wave69Augment()});footer.append(footerCopy,refresh);panel.append(footer);return panel
}
function wave69Augment(){
  if(marketingOpsState?.view!=='uat-readiness')return;wave69Styles();const shell=document.querySelector('#wave67-physical-uat .w67-shell'),data=wave69State.data;if(!shell||!data)return;let mount=shell.querySelector('#wave69-preflight');if(!mount){mount=opsEl('div','');mount.id='wave69-preflight';shell.prepend(mount)}mount.replaceChildren(wave69Panel(data));
  shell.querySelectorAll('.w67-start button.primary').forEach(button=>{button.disabled=!data.ready_to_begin_physical_uat;button.title=data.ready_to_begin_physical_uat?'Preflight listo':'Resuelve el preflight antes de iniciar una nueva sesión física'});
}
if(wave69State.baseStart){
  globalThis.wave67Start=async function(operator,notes){const data=await wave69Load(true);if(!data?.ready_to_begin_physical_uat){opsToast('Preflight físico bloqueado: usa el .app arm64 certificado en un Mac real, fuera de CI');wave69Augment();return}return wave69State.baseStart(operator,notes)};
}
if(wave69State.baseInject){
  globalThis.wave67Inject=async function(){await wave69State.baseInject();if(marketingOpsState?.view!=='uat-readiness')return;await wave69Load();wave69Augment()};
}
window.addEventListener('marketing-company-change',()=>{wave69State.companyId=null;wave69State.data=null;queueMicrotask(()=>globalThis.wave67Inject?.())});
wave69Styles();queueMicrotask(()=>globalThis.wave67Inject?.());
