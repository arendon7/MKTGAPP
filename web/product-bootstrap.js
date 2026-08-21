const wave73BootstrapState={started:false,ready:false,loaded:[],error:null};
const WAVE73_CHAIN=[
  '/instagram-local-reel.js','/operational-readiness.js','/marketing-ops.js','/crm.js','/company-content.js',
  '/campaigns.js','/audiences.js','/contactability.js','/analytics.js','/inbox.js','/inbox-replies.js',
  '/editorial-management.js','/daily-ops.js','/daily-actions.js','/followup-reschedule.js','/product-shell.js',
  '/paid-media-center.js','/creative-studio.js','/command-center.js','/ai-copilot.js','/learning-loop.js',
  '/attribution-foundation.js','/capture-bridge.js','/lead-intake.js','/public-gateway.js',
  '/local-product-integration.js','/workdesk.js','/commercial-desk.js','/contact-360.js',
  '/commercial-pipeline.js','/execution-workspace.js','/results-intelligence.js','/uat-readiness.js',
  '/physical-uat.js','/guided-physical-uat.js','/physical-uat-preflight.js','/release-evidence.js',
  '/candidate-certification-dossier.js','/product-journey.js'
];

function wave73ResourceLoaded(src){
  try{const absolute=new URL(src,location.href).href;return performance.getEntriesByName(absolute).some(row=>Number(row.responseEnd)>0)}catch(_err){return false}
}
function wave73ScriptFor(src){
  return [...document.scripts].find(script=>{try{return new URL(script.src,location.href).pathname===src}catch(_err){return false}})||null
}
function wave73EnsureScript(src,timeout=12000){
  return new Promise((resolve,reject)=>{
    let settled=false,script=wave73ScriptFor(src);const finish=()=>{if(settled)return;settled=true;clearTimeout(timer);if(script)script.dataset.wave73Loaded='1';wave73BootstrapState.loaded.push(src);resolve(src)};const fail=()=>{if(settled)return;settled=true;clearTimeout(timer);reject(new Error(`No se pudo cargar ${src}`))};const timer=setTimeout(()=>{if(wave73ResourceLoaded(src))finish();else fail()},timeout);
    if(script&&(script.dataset.wave73Loaded==='1'||wave73ResourceLoaded(src))){finish();return}
    if(!script){script=document.createElement('script');script.src=src;script.async=false;script.defer=true;script.dataset.wave73Managed='1';document.head.append(script)}
    script.addEventListener('load',finish,{once:true});script.addEventListener('error',fail,{once:true});
    queueMicrotask(()=>{if(wave73ResourceLoaded(src))finish()})
  })
}
async function wave73Bootstrap(){
  if(wave73BootstrapState.started)return globalThis.wave73BootstrapPromise;wave73BootstrapState.started=true;
  try{for(const src of WAVE73_CHAIN)await wave73EnsureScript(src);wave73BootstrapState.ready=true;window.dispatchEvent(new CustomEvent('wave73-bootstrap-ready',{detail:{loaded:[...wave73BootstrapState.loaded]}}));return wave73BootstrapState}catch(err){wave73BootstrapState.error=String(err?.message||err);window.dispatchEvent(new CustomEvent('wave73-bootstrap-failed',{detail:{error:wave73BootstrapState.error,loaded:[...wave73BootstrapState.loaded]}}));throw err}
}
globalThis.wave73BootstrapState=wave73BootstrapState;globalThis.wave73EnsureScript=wave73EnsureScript;globalThis.wave73BootstrapPromise=wave73Bootstrap();
