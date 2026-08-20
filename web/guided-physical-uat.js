const wave68State={baseScenario:typeof wave67Scenario==='function'?wave67Scenario:null};

function wave68Styles(){
  if(document.querySelector('#wave68-guided-uat-style'))return;
  const s=document.createElement('style');s.id='wave68-guided-uat-style';s.textContent=`
  .w68-guide{display:grid;gap:6px;padding:9px;border:1px solid #e3ded4;border-radius:9px;background:#faf8f4}.w68-guide-row{display:grid;grid-template-columns:92px minmax(0,1fr);gap:7px;font-size:8px;line-height:1.45}.w68-guide-row strong{font-size:7px;letter-spacing:.08em;color:#777269}.w68-open{width:max-content}.w68-progress{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px;padding:10px;border:1px solid #ddd8cf;border-radius:11px;background:#fff}.w68-progress div{display:grid;gap:2px}.w68-progress strong{font-size:16px}.w68-progress span{font-size:7px;color:#706c65}.w68-order{font-size:7px;color:#777269;letter-spacing:.08em}
  @media(max-width:760px){.w68-progress{grid-template-columns:1fr 1fr}.w68-guide-row{grid-template-columns:1fr}}
  `;document.head.append(s)
}
function wave68Contract(id){return (wave67State.overview?.readiness?.manual_scenarios||[]).find(row=>row.id===id)||null}
function wave68Open(contract){if(!contract)return;if(contract.tab&&typeof crmState!=='undefined')crmState.tab=contract.tab;opsShowView(contract.view||'uat-readiness')}
function wave68Guide(contract,index,total){
  const box=opsEl('div','w68-guide');box.append(opsEl('span','w68-order',`ESCENARIO ${index+1} DE ${total}`));
  for(const [label,value] of [['PRECONDICIÓN',contract?.precondition],['RESULTADO ESPERADO',contract?.expected]]){const row=opsEl('div','w68-guide-row');row.append(opsEl('strong','',label),opsEl('span','',value||'Sin instrucción adicional.'));box.append(row)}
  const open=opsEl('button','','Abrir módulo');open.type='button';open.className='w68-open';open.addEventListener('click',()=>wave68Open(contract));box.append(open);return box
}
function wave68Progress(session){
  const rows=session?.scenarios||[],required=rows.filter(row=>row.required),pass=required.filter(row=>row.status==='PASS').length,fail=required.filter(row=>row.status==='FAIL').length,blocked=required.filter(row=>row.status==='BLOCKED').length,pending=required.filter(row=>row.status==='PENDING').length;
  const box=opsEl('div','w68-progress');for(const [value,label] of [[pass,'PASS'],[fail,'FAIL'],[blocked,'BLOQUEADOS'],[pending,'PENDIENTES']]){const n=opsEl('div','');n.append(opsEl('strong','',String(value)),opsEl('span','',label));box.append(n)}return box
}
if(wave68State.baseScenario){
  globalThis.wave67Scenario=function(session,row){const card=wave68State.baseScenario(session,row),rows=session?.scenarios||[],index=Math.max(0,rows.findIndex(item=>item.id===row.id)),copy=card.querySelector('.w67-scenario-copy');if(copy)copy.append(wave68Guide(wave68Contract(row.id),index,rows.length));return card};
}
const wave68BasePanel=typeof wave67Panel==='function'?wave67Panel:null;
if(wave68BasePanel){
  globalThis.wave67Panel=function(overview){const shell=wave68BasePanel(overview),session=overview.active_session||overview.latest_session;if(session){const hero=shell.querySelector('.w67-hero');if(hero)hero.insertAdjacentElement('afterend',wave68Progress(session))}return shell};
}
wave68Styles();
if(marketingOpsState?.view==='uat-readiness')queueMicrotask(wave67Inject);
