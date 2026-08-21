const wave72EntryState={started:false,ready:false,lastCompanyId:null,integrity:null,error:null};

function wave72EntryStyles(){
  if(document.querySelector('#wave72-entry-style'))return;
  const style=document.createElement('style');style.id='wave72-entry-style';style.textContent=`
  .w72-boot{position:fixed;right:14px;bottom:14px;z-index:9999;display:flex;gap:8px;align-items:center;padding:9px 12px;border:1px solid #ddd7cc;background:rgba(255,255,255,.96);box-shadow:0 8px 30px rgba(0,0,0,.08);border-radius:10px;font:11px/1.3 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#5f5a52}
  .w72-boot.ok{border-color:#b8d8bf}.w72-boot.fail{border-color:#e3b7ad}.w72-boot button{border:1px solid #d5d0c6;background:#fff;border-radius:7px;padding:5px 8px;cursor:pointer}
  .w72-company-action{margin-left:7px;white-space:nowrap}.w72-company-action button{border:1px solid #d8d3ca;background:#fff;border-radius:7px;padding:7px 9px;cursor:pointer;font:inherit}
  `;document.head.append(style)
}
function wave72BootNotice(text,state=''){wave72EntryStyles();let box=document.querySelector('#wave72-boot');if(!box){box=document.createElement('div');box.id='wave72-boot';box.className='w72-boot';document.body.append(box)}box.className=`w72-boot ${state}`;box.replaceChildren(document.createTextNode(text));return box}
function wave72WaitFor(check,timeout=15000){return new Promise((resolve,reject)=>{const start=Date.now();const tick=()=>{try{if(check()){resolve(true);return}}catch(_err){}if(Date.now()-start>=timeout){reject(new Error('timeout de arranque'));return}setTimeout(tick,40)};tick()})}
function wave72EnsureScript(src,datasetKey,ready){
  if(ready())return Promise.resolve();
  return new Promise((resolve,reject)=>{
    let script=document.querySelector(`script[data-${datasetKey}]`);
    const done=()=>wave72WaitFor(ready,10000).then(resolve,reject);
    if(script){script.addEventListener('load',done,{once:true});script.addEventListener('error',()=>reject(new Error(`No se pudo cargar ${src}`)),{once:true});done();return}
    script=document.createElement('script');script.src=src;script.defer=true;script.dataset[datasetKey.replace(/-([a-z])/g,(_m,c)=>c.toUpperCase())]='1';script.addEventListener('load',done,{once:true});script.addEventListener('error',()=>reject(new Error(`No se pudo cargar ${src}`)),{once:true});document.head.append(script)
  })
}
function wave72CompanyId(){return typeof marketingOpsState!=='undefined'?marketingOpsState.selectedCompanyId||null:null}
function wave72Companies(){return typeof marketingOpsState!=='undefined'?marketingOpsState.companies||[]:[]}
function wave72EmitContext(forceRefresh=false){
  const current=wave72CompanyId(),changed=current!==wave72EntryState.lastCompanyId;
  if(changed){const previous=wave72EntryState.lastCompanyId;wave72EntryState.lastCompanyId=current;window.dispatchEvent(new CustomEvent('marketing-company-change',{detail:{companyId:current,previousCompanyId:previous}}))}
  if(forceRefresh)window.dispatchEvent(new CustomEvent('marketing-ops-refreshed',{detail:{companyId:current}}));
}
function wave72BroadcastContext(){
  const current=wave72CompanyId();wave72EntryState.lastCompanyId=current;
  window.dispatchEvent(new CustomEvent('marketing-company-change',{detail:{companyId:current,previousCompanyId:current,rebroadcast:true}}));
  window.dispatchEvent(new CustomEvent('marketing-ops-refreshed',{detail:{companyId:current,rebroadcast:true}}));
}
function wave72InstallContextEvents(){
  if(globalThis.__wave72ContextEventsInstalled)return;globalThis.__wave72ContextEventsInstalled=true;wave72EntryState.lastCompanyId=null;
  const baseRefresh=globalThis.refreshMarketingOps;
  if(typeof baseRefresh==='function')globalThis.refreshMarketingOps=async function(...args){const result=await baseRefresh(...args);wave72EmitContext(true);return result};
}
function wave72EnsureCompanyAction(){
  const header=document.querySelector('.marketing-ops-top');if(!header||header.querySelector('.w72-company-action'))return;
  const wrap=document.createElement('div');wrap.className='w72-company-action';const button=document.createElement('button');button.type='button';button.textContent='+ Empresa';button.addEventListener('click',()=>globalThis.opsShowView?.('companies'));wrap.append(button);header.append(wrap)
}
async function wave72Integrity(){
  const companyId=wave72CompanyId(),url=companyId?`/api/product-integrity?company_id=${encodeURIComponent(companyId)}`:'/api/product-integrity';
  const response=await fetch(url,{headers:{Accept:'application/json'},cache:'no-store'});const data=await response.json();if(!response.ok)throw new Error(data.error||`HTTP ${response.status}`);wave72EntryState.integrity=data;return data
}
async function wave72FinishOnboarding(){
  await globalThis.refreshMarketingOps?.(true);wave72EmitContext(true);wave72EnsureCompanyAction();
  const companies=wave72Companies();
  if(!companies.length){globalThis.opsShowView?.('companies');setTimeout(()=>document.querySelector('#marketing-ops-view input[required]')?.focus(),0);return}
  if(!wave72CompanyId()&&typeof globalThis.wave47EnsureCompanySelection==='function'){globalThis.wave47EnsureCompanySelection();await globalThis.refreshMarketingOps?.(true)}
}
async function wave72Boot(){
  if(wave72EntryState.started)return;wave72EntryState.started=true;wave72BootNotice('Preparando MERCADEO APP…');
  try{
    await wave72EnsureScript('/marketing-ops.js','marketing-ops',()=>typeof globalThis.refreshMarketingOps==='function'&&Boolean(document.querySelector('#marketing-ops-shell')));
    wave72InstallContextEvents();await wave72FinishOnboarding();
    await wave72EnsureScript('/crm.js','crm-wave32',()=>typeof globalThis.renderOpsCrm==='function');
    await wave72EnsureScript('/company-content.js','company-content-wave34',()=>typeof globalThis.submitOpsPublication==='function');
    await wave72EnsureScript('/campaigns.js','campaigns-wave35',()=>Boolean(document.querySelector('[data-ops-view="campaigns"]')));
    await wave72EnsureScript('/audiences.js','audiences-wave36',()=>Boolean(document.querySelector('script[data-audiences-wave38-chain]'))||Boolean(document.querySelector('#audience-wave36-style')));
    await wave72WaitFor(()=>Boolean(document.querySelector('#wave47-product-shell-style')),15000);
    await wave72WaitFor(()=>Boolean(document.querySelector('#wave71-dossier-style')),20000);
    await wave72FinishOnboarding();wave72BroadcastContext();
    const integrity=await wave72Integrity();if(!integrity.ready)throw new Error(`Integridad incompleta: ${[...(integrity.missing?.web_assets||[]),...(integrity.missing?.runtime_methods||[]),...(integrity.missing?.failed_company_projections||[])].join(', ')||'revisar diagnóstico'}`);
    wave72EntryState.ready=true;wave72BootNotice(`Producto listo · ${integrity.inventory.present_web_assets}/${integrity.inventory.required_web_assets} superficies · ${integrity.inventory.registered_apps} apps`,'ok');
    setTimeout(()=>document.querySelector('#wave72-boot')?.remove(),3500)
  }catch(err){wave72EntryState.error=String(err?.message||err);const box=wave72BootNotice(`Arranque incompleto · ${wave72EntryState.error}`,'fail'),retry=document.createElement('button');retry.type='button';retry.textContent='Reintentar';retry.addEventListener('click',()=>{wave72EntryState.started=false;wave72EntryState.error=null;wave72Boot()});box.append(retry)}
}

globalThis.wave72Boot=wave72Boot;globalThis.wave72ProductIntegrity=wave72Integrity;
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',wave72Boot,{once:true});else wave72Boot();
