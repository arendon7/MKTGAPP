const wave70State={companyId:null,data:null,loading:false,baseAugment:typeof wave69Augment==='function'?wave69Augment:null};

function wave70Styles(){
  if(document.querySelector('#wave70-release-evidence-style'))return;
  const style=document.createElement('style');style.id='wave70-release-evidence-style';style.textContent=`
  .w70-panel{padding:13px;border:1px solid #d9d5cc;border-radius:12px;background:#fff;display:grid;gap:10px}.w70-head{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}.w70-head h3{margin:0}.w70-stage{display:inline-flex;padding:5px 8px;border-radius:999px;background:#f3e7df;font-size:8px;white-space:nowrap}.w70-stage.ok{background:#e4efe5}.w70-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px}.w70-card{padding:9px;border:1px solid #e5e1d9;border-radius:9px;display:grid;gap:3px}.w70-card strong{font-size:9px}.w70-card span{font-size:8px;color:#706c65;line-height:1.4}.w70-card.pass{background:#f3f7f3}.w70-card.blocked{background:#faf4ef}.w70-blockers{padding:9px;border-radius:9px;background:#f6f3ed;display:grid;gap:5px}.w70-blockers strong{font-size:9px}.w70-blockers span{font-size:8px;color:#706c65;line-height:1.45}.w70-contract{font-size:8px;color:#706c65;line-height:1.45}.w70-actions{display:flex;gap:7px;flex-wrap:wrap}
  @media(max-width:950px){.w70-grid{grid-template-columns:1fr}}@media(max-width:650px){.w70-head{display:grid}}
  `;document.head.append(style)
}
function wave70Company(){return typeof opsSelectedCompany==='function'?opsSelectedCompany():null}
async function wave70Load(force=false){
  const company=wave70Company();if(!company){wave70State.companyId=null;wave70State.data=null;return null}
  if(wave70State.loading)return wave70State.data;
  if(!force&&wave70State.companyId===company.id&&wave70State.data)return wave70State.data;
  wave70State.loading=true;
  try{const data=await opsApi(`/api/companies/${encodeURIComponent(company.id)}/release-evidence`);wave70State.companyId=company.id;wave70State.data=data;return data}catch(err){opsToast(err.message);return null}finally{wave70State.loading=false}
}
function wave70Panel(data){
  const readiness=data.release_readiness||{},uat=data.physical_uat||{},build=data.current_build||{},panel=opsEl('section','w70-panel'),head=opsEl('div','w70-head'),copy=opsEl('div','');
  copy.append(opsEl('p','eyebrow','RELEASE EVIDENCE · W70'),opsEl('h3','','Puente UAT física → gate de release'),opsEl('p','muted','Una UAT válida solo satisface el blocker físico del build exacto. Versión, tag, firma Developer ID y notarización permanecen gates independientes.'));
  const stage=opsEl('span',`w70-stage ${readiness.production_ready?'ok':''}`,readiness.production_ready?'PRODUCTION READY':readiness.stage||'BLOQUEADO');head.append(copy,stage);panel.append(head);
  const grid=opsEl('div','w70-grid');
  const uatCard=opsEl('div',`w70-card ${uat.accepted_for_current_build?'pass':'blocked'}`);uatCard.append(opsEl('strong','',uat.accepted_for_current_build?'PASS · UAT del build exacto':'BLOQUEADO · UAT del build exacto'),opsEl('span','',uat.accepted_for_current_build?`Sesión ${uat.accepted?.session_id||'—'} · SHA/evidencia/arm64 validados`:(uat.latest_validation?.rejection_reasons||['sin evidencia aceptable']).join(' · ')));
  const buildCard=opsEl('div','w70-card');buildCard.append(opsEl('strong','','BUILD EN EJECUCIÓN'),opsEl('span','',`${String(build.git_sha||'sin SHA').slice(0,12)} · ${build.architecture||'sin arch'} · ${build.product_version||'sin versión'}`));
  const distOk=build.signing_mode==='developer_id'&&build.notarized===true;const dist=opsEl('div',`w70-card ${distOk?'pass':'blocked'}`);dist.append(opsEl('strong','',distOk?'PASS · DISTRIBUCIÓN':'BLOQUEADO · DISTRIBUCIÓN'),opsEl('span','',`${build.signing_mode||'sin firma'} · notarized=${build.notarized===true}`));grid.append(uatCard,buildCard,dist);panel.append(grid);
  const blockers=readiness.blocker_codes||[],box=opsEl('div','w70-blockers');box.append(opsEl('strong','',blockers.length?'Bloqueos vigentes':'Sin bloqueos'),opsEl('span','',blockers.length?blockers.join(' · '):'Todos los gates canónicos están satisfechos.'));panel.append(box);
  panel.append(opsEl('div','w70-contract','Contrato fail-closed: la evidencia UAT debe tener sesión PASSED, Mac Darwin arm64 fuera de CI, escenarios requeridos PASS, digest válido y coincidencia exacta de git SHA + arquitectura + versión. W70 es solo lectura y no cambia RELEASE_READY, tag, firma ni notarización.'));
  const actions=opsEl('div','w70-actions'),refresh=opsEl('button','','Revalidar evidencia');refresh.type='button';refresh.addEventListener('click',async()=>{await wave70Load(true);wave70Augment()});actions.append(refresh);panel.append(actions);return panel
}
function wave70Augment(){
  if(marketingOpsState?.view!=='uat-readiness')return;wave70Styles();const shell=document.querySelector('#wave67-physical-uat .w67-shell'),data=wave70State.data;if(!shell||!data)return;let mount=shell.querySelector('#wave70-release-evidence');if(!mount){mount=opsEl('div','');mount.id='wave70-release-evidence';const preflight=shell.querySelector('#wave69-preflight');if(preflight)preflight.insertAdjacentElement('afterend',mount);else shell.prepend(mount)}mount.replaceChildren(wave70Panel(data))
}
if(wave70State.baseAugment){globalThis.wave69Augment=function(){wave70State.baseAugment();if(marketingOpsState?.view!=='uat-readiness')return;wave70Load().then(wave70Augment)}}
window.addEventListener('marketing-company-change',()=>{wave70State.companyId=null;wave70State.data=null;queueMicrotask(()=>wave70Load(true).then(wave70Augment))});
wave70Styles();queueMicrotask(()=>wave70Load().then(wave70Augment));
