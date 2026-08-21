const wave71State={companyId:null,data:null,loading:false};

function wave71Styles(){
  if(document.querySelector('#wave71-dossier-style'))return;
  const s=document.createElement('style');s.id='wave71-dossier-style';s.textContent=`
  .w71-panel{padding:13px;border:1px solid #d9d5cc;border-radius:12px;background:#fff;display:grid;gap:10px}.w71-head{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}.w71-head h3{margin:0}.w71-stage{padding:5px 8px;border-radius:999px;background:#f3e7df;font-size:8px}.w71-stage.ok{background:#e4efe5}.w71-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:7px}.w71-card{padding:9px;border:1px solid #e5e1d9;border-radius:9px;display:grid;gap:3px}.w71-card strong{font-size:9px}.w71-card span{font-size:8px;color:#706c65;line-height:1.4}.w71-next{padding:10px;border-radius:9px;background:#f6f3ed;display:grid;gap:4px}.w71-next strong{font-size:9px}.w71-next span{font-size:8px;color:#706c65}.w71-actions{display:flex;gap:7px;flex-wrap:wrap}.w71-hash{font-family:monospace;font-size:8px;color:#706c65;word-break:break-all}@media(max-width:980px){.w71-grid{grid-template-columns:1fr 1fr}}@media(max-width:650px){.w71-grid{grid-template-columns:1fr}.w71-head{display:grid}}
  `;document.head.append(s)
}
function wave71Company(){return typeof opsSelectedCompany==='function'?opsSelectedCompany():null}
async function wave71Load(force=false){
  const c=wave71Company();if(!c){wave71State.companyId=null;wave71State.data=null;return null}
  if(wave71State.loading)return wave71State.data;
  if(!force&&wave71State.companyId===c.id&&wave71State.data)return wave71State.data;
  wave71State.loading=true;try{wave71State.data=await opsApi(`/api/companies/${encodeURIComponent(c.id)}/certification-dossier`);wave71State.companyId=c.id;return wave71State.data}catch(err){opsToast(err.message);return null}finally{wave71State.loading=false}
}
function wave71Export(data){
  const text=JSON.stringify(data,null,2),blob=new Blob([text],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');
  a.href=url;a.download=`BINARIO-UAT-CERTIFICATION-${String(data.company?.name||'company').replace(/[^A-Za-z0-9_-]+/g,'_')}-${String(data.candidate?.git_sha||'unknown').slice(0,12)}.json`;document.body.append(a);a.click();a.remove();URL.revokeObjectURL(url);opsToast('Expediente exportado como snapshot local')
}
function wave71Panel(data){
  const panel=opsEl('section','w71-panel'),head=opsEl('div','w71-head'),copy=opsEl('div','');copy.append(opsEl('p','eyebrow','CANDIDATE CERTIFICATION · W71'),opsEl('h3','','Expediente del candidato físico'),opsEl('p','muted','Consolida identidad del build, preflight, escenarios, evidencia UAT y bloqueos de release. No concede autoridad de release.'));
  const good=data.stage==='PHYSICAL_UAT_PASSED_FOR_BUILD';head.append(copy,opsEl('span',`w71-stage ${good?'ok':''}`,data.stage));panel.append(head);
  const build=data.candidate||{},uat=data.uat||{},release=data.release||{},session=uat.latest_session||{},grid=opsEl('div','w71-grid');
  [['BUILD',`${String(build.git_sha||'—').slice(0,12)} · ${build.architecture||'—'} · ${build.product_version||'—'}`],['PREFLIGHT',data.preflight?.ready?'PASS · listo para UAT física':`BLOQUEADO · ${(data.preflight?.blockers||[]).length} blocker(s)`],['SESIÓN UAT',session.id?`${session.status} · ${session.required_pass||0}/${session.required_total||0} requeridos PASS`:'Sin sesión registrada'],['RELEASE',release.production_ready?'PRODUCTION READY':`${release.stage||'BLOQUEADO'} · ${(release.blocker_codes||[]).length} blocker(s)`]].forEach(([title,text])=>{const card=opsEl('div','w71-card');card.append(opsEl('strong','',title),opsEl('span','',text));grid.append(card)});panel.append(grid);
  const next=opsEl('div','w71-next');next.append(opsEl('strong','','Siguiente acción canónica'),opsEl('span','',data.next_action||'—'));panel.append(next,opsEl('div','w71-hash',`dossier_sha256 · ${data.dossier_sha256||'—'}`));
  const actions=opsEl('div','w71-actions'),refresh=opsEl('button','','Recalcular expediente'),exportBtn=opsEl('button','primary','Exportar expediente JSON');refresh.type=exportBtn.type='button';refresh.addEventListener('click',async()=>{await wave71Load(true);wave71Augment()});exportBtn.addEventListener('click',()=>wave71Export(data));actions.append(refresh,exportBtn);panel.append(actions);return panel
}
function wave71Augment(){
  if(marketingOpsState?.view!=='uat-readiness')return;wave71Styles();const shell=document.querySelector('#wave67-physical-uat .w67-shell'),data=wave71State.data;if(!shell||!data)return;let mount=shell.querySelector('#wave71-certification-dossier');if(!mount){mount=opsEl('div','');mount.id='wave71-certification-dossier';const evidence=shell.querySelector('#wave70-release-evidence');if(evidence)evidence.insertAdjacentElement('afterend',mount);else shell.append(mount)}mount.replaceChildren(wave71Panel(data))
}
window.addEventListener('marketing-company-change',()=>{wave71State.companyId=null;wave71State.data=null;queueMicrotask(()=>wave71Load(true).then(wave71Augment))});
wave71Styles();queueMicrotask(()=>wave71Load().then(wave71Augment));
