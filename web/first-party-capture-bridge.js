(function BinarioFirstPartyCaptureBridge(){
  'use strict';
  const VERSION='1.0.0';
  const STORAGE_KEY='binario.marketing.first-party-capture.v1';
  const TRACKING_KEYS=['utm_source','utm_medium','utm_campaign','utm_id','utm_content','utm_term','utm_source_platform'];
  const CODE_RE=/^bm_[0-9a-f]{24}$/;
  const UTM_RE=/^[A-Za-z0-9._~+\-]{1,160}$/;

  function safePageUrl(raw){
    try{
      const url=new URL(raw,window.location.href);
      if(!/^https?:$/.test(url.protocol))return '';
      return `${url.origin}${url.pathname}`;
    }catch(_err){return ''}
  }
  function readStorage(){
    try{
      const raw=sessionStorage.getItem(STORAGE_KEY);
      if(!raw)return null;
      const value=JSON.parse(raw);
      if(!value||!CODE_RE.test(String(value.bm_tid||'')))return null;
      return value;
    }catch(_err){return null}
  }
  function writeStorage(value){
    try{sessionStorage.setItem(STORAGE_KEY,JSON.stringify(value))}catch(_err){}
  }
  function clearStorage(){
    try{sessionStorage.removeItem(STORAGE_KEY)}catch(_err){}
  }
  function captureFromLocation(){
    const params=new URL(window.location.href).searchParams;
    const hasCode=params.has('bm_tid');
    const rawCode=String(params.get('bm_tid')||'').trim();
    if(hasCode&&!CODE_RE.test(rawCode)){
      clearStorage();
      return null;
    }
    if(!hasCode)return readStorage();
    const captured={
      bm_tid:rawCode,
      bm_client_captured_at:new Date().toISOString(),
      bm_landing_url:safePageUrl(window.location.href),
      bm_referrer_url:safePageUrl(document.referrer||''),
      bm_bridge_version:VERSION,
    };
    for(const key of TRACKING_KEYS){
      const value=String(params.get(key)||'').trim();
      if(value&&UTM_RE.test(value))captured[key]=value;
    }
    writeStorage(captured);
    return captured;
  }
  function upsertHidden(form,name,value){
    if(!value)return;
    let input=form.querySelector(`input[type="hidden"][name="${name}"]`);
    if(!input){
      input=document.createElement('input');
      input.type='hidden';
      input.name=name;
      input.dataset.binarioAttribution='1';
      form.appendChild(input);
    }
    input.value=String(value);
  }
  function instrumentForm(form,captured){
    if(!(form instanceof HTMLFormElement)||form.dataset.binarioAttribution==='off'||!captured)return;
    upsertHidden(form,'bm_tid',captured.bm_tid);
    for(const key of TRACKING_KEYS)upsertHidden(form,key,captured[key]);
    upsertHidden(form,'bm_client_captured_at',captured.bm_client_captured_at);
    upsertHidden(form,'bm_landing_url',captured.bm_landing_url);
    upsertHidden(form,'bm_referrer_url',captured.bm_referrer_url);
    upsertHidden(form,'bm_bridge_version',captured.bm_bridge_version);
    form.dataset.binarioAttributionInstrumented='1';
  }
  function instrumentAll(){
    const captured=captureFromLocation();
    if(!captured)return;
    document.querySelectorAll('form').forEach(form=>instrumentForm(form,captured));
    document.dispatchEvent(new CustomEvent('binario:attribution-captured',{detail:{version:VERSION,tracking:true}}));
  }
  function start(){
    instrumentAll();
    const observer=new MutationObserver(records=>{
      const captured=readStorage();
      if(!captured)return;
      for(const record of records){
        for(const node of record.addedNodes){
          if(!(node instanceof Element))continue;
          if(node.matches('form'))instrumentForm(node,captured);
          node.querySelectorAll?.('form').forEach(form=>instrumentForm(form,captured));
        }
      }
    });
    observer.observe(document.documentElement,{childList:true,subtree:true});
  }

  window.BinarioFirstPartyCapture=Object.freeze({
    version:VERSION,
    read(){const value=readStorage();return value?Object.assign({},value):null},
    clear(){clearStorage()},
    instrument(){instrumentAll()},
  });

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});
  else start();
})();
