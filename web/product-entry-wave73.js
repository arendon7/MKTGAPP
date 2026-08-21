const wave73EntryState={ready:false,error:null};
function wave73EntryNotice(text,state=''){
  let box=document.querySelector('#wave73-entry-notice');if(!box){box=document.createElement('div');box.id='wave73-entry-notice';box.style.cssText='position:fixed;right:14px;bottom:14px;z-index:10000;padding:9px 12px;border:1px solid #d8d3ca;background:#fff;border-radius:10px;box-shadow:0 8px 30px rgba(0,0,0,.08);font:11px/1.35 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#5f5a52';document.body.append(box)}box.textContent=text;if(state==='fail')box.style.borderColor='#e3b7ad';if(state==='ok')box.style.borderColor='#b8d8bf';return box
}
async function wave73Wait(check,timeout=20000){const started=Date.now();while(Date.now()-started<timeout){try{if(check())return true}catch(_err){}await new Promise(resolve=>setTimeout(resolve,40))}throw new Error('timeout de entrada Wave 73')}
async function wave73Entry(){
  wave73EntryNotice('Verificando módulos de MERCADEO APP…');
  try{
    await globalThis.wave73BootstrapPromise;
    await globalThis.wave73EnsureScript('/product-entry.js');
    await wave73Wait(()=>typeof globalThis.wave72ProductIntegrity==='function'&&Boolean(document.querySelector('#marketing-ops-shell')));
    await wave73Wait(()=>globalThis.wave73BootstrapState?.ready===true);
    const integrity=await globalThis.wave72ProductIntegrity();if(!integrity.ready)throw new Error('integridad de producto incompleta');
    wave73EntryState.ready=true;wave73EntryNotice(`MERCADEO APP lista · bootstrap ${globalThis.wave73BootstrapState.loaded.length}/${WAVE73_CHAIN.length}`,'ok');
    window.dispatchEvent(new CustomEvent('wave73-entry-ready',{detail:{loaded:globalThis.wave73BootstrapState.loaded.length}}));
    setTimeout(()=>document.querySelector('#wave73-entry-notice')?.remove(),3000)
  }catch(err){wave73EntryState.error=String(err?.message||err);const box=wave73EntryNotice(`Entrada incompleta · ${wave73EntryState.error}`,'fail');const retry=document.createElement('button');retry.type='button';retry.textContent='Reintentar';retry.style.marginLeft='8px';retry.addEventListener('click',()=>location.reload());box.append(retry)}
}
globalThis.wave73EntryState=wave73EntryState;globalThis.wave73Entry=wave73Entry;if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',wave73Entry,{once:true});else wave73Entry();
