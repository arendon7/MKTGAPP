const instagramLocalState={bound:false,userSelectedSource:false};

function instagramLocalEligibleRenders(){
  return (state.current?.renders||[]).filter(row=>{
    const width=Number(row.width),height=Number(row.height),duration=Number(row.end)-Number(row.start),bytes=Number(row.bytes||0),name=String(row.output_name||'').toLowerCase();
    return row.status==='PASS'&&width>0&&height>0&&width*16===height*9&&width<=1920&&duration>=3&&duration<=60&&(!bytes||bytes<=1000000000)&&(name.endsWith('.mp4')||name.endsWith('.mov'));
  });
}

function ensureInstagramLocalControls(){
  const form=$('#social-publication-form'),renderWrap=$('#social-render-wrap');if(!form||!renderWrap)return null;
  let wrap=$('#instagram-reel-source-wrap');if(wrap)return wrap;
  wrap=document.createElement('label');wrap.id='instagram-reel-source-wrap';wrap.className='hidden';wrap.innerHTML='Origen del Reel<select id="instagram-reel-source"><option value="local">Render local certificado</option><option value="url">URL pública</option></select>';
  renderWrap.insertAdjacentElement('beforebegin',wrap);
  const source=$('#instagram-reel-source');source.addEventListener('change',()=>{instagramLocalState.userSelectedSource=true;renderInstagramLocalVisibility()});
  $('#social-channel')?.addEventListener('change',()=>setTimeout(renderInstagramLocalVisibility,0));
  $('#social-kind')?.addEventListener('change',()=>setTimeout(renderInstagramLocalVisibility,0));
  return wrap;
}

function fillInstagramLocalRenders(){
  const select=$('#social-render-id');if(!select)return;const previous=select.value,rows=instagramLocalEligibleRenders();select.replaceChildren();
  if(!rows.length){select.append(socialOption('','Genera primero un render 9:16 PASS de 3–60 s'));select.disabled=true;return}
  select.disabled=false;
  for(const row of rows){const duration=(Number(row.end)-Number(row.start)).toFixed(1);select.append(socialOption(row.id,`${row.output_name||row.id} · ${row.width}×${row.height} · ${duration}s`))}
  if(rows.some(row=>row.id===previous))select.value=previous;
}

function renderInstagramLocalVisibility(){
  ensureInstagramLocalControls();const channel=$('#social-channel')?.value,kind=$('#social-kind')?.value,wrap=$('#instagram-reel-source-wrap');if(!wrap)return;
  const instagramReel=channel==='instagram'&&kind==='reel';wrap.classList.toggle('hidden',!instagramReel);
  if(!instagramReel)return;
  const source=$('#instagram-reel-source');if(!instagramLocalState.userSelectedSource&&instagramLocalEligibleRenders().length)source.value='local';
  const local=source.value==='local';
  $('#social-render-wrap').classList.toggle('hidden',!local);$('#social-render-note').classList.toggle('hidden',!local);
  $('#social-media-wrap').classList.toggle('hidden',local);$('#social-media-note').classList.toggle('hidden',local);
  if(local){
    const renderLabel=$('#social-render-wrap');if(renderLabel)renderLabel.childNodes[0].textContent='Render local 9:16';
    $('#social-render-note').textContent='Instagram Reel local se envía desde el MP4/MOV administrado del proyecto mediante upload resumable de Meta. El backend vuelve a validar proyecto, PASS, duración, tamaño y SHA-256 antes de transmitirlo.';
    fillInstagramLocalRenders();
  }else{
    $('#social-media-note').textContent='URL pública: Meta descargará el Reel desde Internet. Usa esta alternativa sólo cuando el archivo ya esté alojado públicamente.';
  }
}

async function createInstagramLocalPublication({publishNow=false}={}){
  const projectId=socialProjectId();if(!projectId)return;const target=$('#social-target');if(!target?.value){toast('Selecciona una cuenta Meta');return}
  const renderId=$('#social-render-id')?.value||'';if(!renderId){toast('Selecciona un render local 9:16 PASS de 3–60 s');return}
  if(!instagramLocalEligibleRenders().some(row=>row.id===renderId)){toast('Ese render ya no cumple el gate local de Instagram; actualiza el proyecto');return}
  const scheduled=socialJsonDate($('#social-scheduled-for').value),selected=target.options[target.selectedIndex];
  const payload={channel:'instagram',target_id:target.value,target_name:selected?.textContent||target.value,kind:'reel',message:$('#social-message').value.trim(),link_url:null,media_url:null,render_id:renderId,...(!publishNow&&scheduled?{scheduled_for:scheduled}:{})};
  try{
    const row=await api(`/api/projects/${projectId}/publications`,{method:'POST',body:payload});
    if(publishNow)await api(`/api/projects/${projectId}/publications/${row.id}/publish-now`,{method:'POST',body:{}});
    $('#social-message').value='';if(!publishNow)$('#social-scheduled-for').value='';
    toast(publishNow?'Instagram Reel local enviado a Meta':scheduled?'Instagram Reel local programado':'Borrador local de Instagram guardado');
    await refreshSocialProject();if(typeof refreshTimeline==='function')refreshTimeline();renderInstagramLocalVisibility();
  }catch(err){toast(err.message)}
}

function bindInstagramLocalSubmitInterceptors(){
  if(instagramLocalState.bound)return;const form=$('#social-publication-form'),publish=$('#social-publish-now');if(!form||!publish)return;instagramLocalState.bound=true;
  form.addEventListener('submit',event=>{
    if($('#social-channel')?.value!=='instagram'||$('#social-kind')?.value!=='reel'||$('#instagram-reel-source')?.value!=='local')return;
    event.preventDefault();event.stopImmediatePropagation();createInstagramLocalPublication();
  },true);
  publish.addEventListener('click',event=>{
    if($('#social-channel')?.value!=='instagram'||$('#social-kind')?.value!=='reel'||$('#instagram-reel-source')?.value!=='local')return;
    event.preventDefault();event.stopImmediatePropagation();createInstagramLocalPublication({publishNow:true});
  },true);
}

function instagramLocalWatch(){
  ensureInstagramLocalControls();bindInstagramLocalSubmitInterceptors();renderInstagramLocalVisibility();
  for(const selector of ['#active-project-name','#render-count']){const target=$(selector);if(target)new MutationObserver(()=>setTimeout(renderInstagramLocalVisibility,0)).observe(target,{childList:true,characterData:true,subtree:true})}
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',instagramLocalWatch,{once:true});else instagramLocalWatch();
globalThis.renderInstagramLocalVisibility=renderInstagramLocalVisibility;

(function loadOperationalReadinessExtension(){
  if(!document.querySelector('script[data-operational-readiness]')){const script=document.createElement('script');script.src='/operational-readiness.js';script.defer=true;script.dataset.operationalReadiness='1';document.head.append(script)}
})();

(function loadMarketingOperationsExtension(){
  const loadCrm=()=>{if(!document.querySelector('script[data-crm-wave32]')){const crm=document.createElement('script');crm.src='/crm.js';crm.defer=true;crm.dataset.crmWave32='1';document.head.append(crm)}};
  const existing=document.querySelector('script[data-marketing-ops]');
  if(existing){if(globalThis.refreshMarketingOps)loadCrm();else existing.addEventListener('load',loadCrm,{once:true});return}
  const script=document.createElement('script');script.src='/marketing-ops.js';script.defer=true;script.dataset.marketingOps='1';script.addEventListener('load',loadCrm,{once:true});document.head.append(script);
})();

(function loadCompanyContentExtension(){
  const load=()=>{if(document.querySelector('script[data-company-content-wave34]'))return;const script=document.createElement('script');script.src='/company-content.js';script.defer=true;script.dataset.companyContentWave34='1';document.head.append(script)};
  const waitForCrm=()=>{const crm=document.querySelector('script[data-crm-wave32]');if(globalThis.renderCrm){load();return}if(crm){crm.addEventListener('load',load,{once:true});return}setTimeout(waitForCrm,50)};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',waitForCrm,{once:true});else waitForCrm();
})();

(function loadCampaignCenterExtension(){
  const load=()=>{if(document.querySelector('script[data-campaigns-wave35]'))return;const script=document.createElement('script');script.src='/campaigns.js';script.defer=true;script.dataset.campaignsWave35='1';document.head.append(script)};
  const waitForContent=()=>{const content=document.querySelector('script[data-company-content-wave34]');if(globalThis.contentRenderCurrent){load();return}if(content){content.addEventListener('load',load,{once:true});return}setTimeout(waitForContent,50)};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',waitForContent,{once:true});else waitForContent();
})();

(function loadCrmAudiencesExtension(){
  const load=()=>{if(document.querySelector('script[data-audiences-wave36]'))return;const script=document.createElement('script');script.src='/audiences.js';script.defer=true;script.dataset.audiencesWave36='1';document.head.append(script)};
  const waitForCampaigns=()=>{const campaigns=document.querySelector('script[data-campaigns-wave35]');if(globalThis.campaignForm){load();return}if(campaigns){campaigns.addEventListener('load',load,{once:true});return}setTimeout(waitForCampaigns,50)};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',waitForCampaigns,{once:true});else waitForCampaigns();
})();