const wave74ListenerMap=new WeakMap();
const wave74OriginalAddEventListener=EventTarget.prototype.addEventListener;
function wave74RememberListener(target,type){
  if(!target||!type)return;
  let types=wave74ListenerMap.get(target);if(!types){types=new Set();wave74ListenerMap.set(target,types)}types.add(String(type));
}
EventTarget.prototype.addEventListener=function(type,listener,options){wave74RememberListener(this,type);return wave74OriginalAddEventListener.call(this,type,listener,options)};
function wave74HasDirectListener(target,type){return Boolean(wave74ListenerMap.get(target)?.has(String(type))||typeof target?.[`on${type}`]==='function')}
function wave74HasAncestorListener(target,type){let node=target?.parentNode;while(node){if(wave74HasDirectListener(node,type))return true;node=node.parentNode}return wave74HasDirectListener(document,type)||wave74HasDirectListener(window,type)}
function wave74DescribeControl(el){const tag=String(el?.tagName||'').toLowerCase();const type=String(el?.getAttribute?.('type')||'').toLowerCase();const id=String(el?.id||'');const name=String(el?.getAttribute?.('name')||'');const text=String(el?.textContent||el?.getAttribute?.('aria-label')||el?.getAttribute?.('title')||'').replace(/\s+/g,' ').trim().slice(0,80);return {tag,type,id,name,text}}
function wave74ClassifyControl(el){
  const meta=wave74DescribeControl(el);const tag=meta.tag;
  if(el?.disabled||el?.getAttribute?.('aria-disabled')==='true')return {...meta,status:'DISABLED',mechanism:'disabled'};
  if(tag==='a'){
    const href=String(el.getAttribute('href')||'').trim();if(href&&href!=='#')return {...meta,status:'WIRED',mechanism:'href'};if(wave74HasDirectListener(el,'click'))return {...meta,status:'WIRED',mechanism:'direct-click'};if(wave74HasAncestorListener(el,'click'))return {...meta,status:'DELEGATED',mechanism:'ancestor-click'};return {...meta,status:'UNWIRED',mechanism:'none'};
  }
  if(tag==='form'){
    const action=String(el.getAttribute('action')||'').trim();if(wave74HasDirectListener(el,'submit'))return {...meta,status:'WIRED',mechanism:'submit-listener'};if(action)return {...meta,status:'WIRED',mechanism:'form-action'};return {...meta,status:'UNWIRED',mechanism:'none'};
  }
  if(tag==='select'){
    if(el.form)return {...meta,status:'WIRED',mechanism:'form-field'};if(wave74HasDirectListener(el,'change')||wave74HasDirectListener(el,'input'))return {...meta,status:'WIRED',mechanism:'direct-change'};if(wave74HasAncestorListener(el,'change'))return {...meta,status:'DELEGATED',mechanism:'ancestor-change'};return {...meta,status:'UNWIRED',mechanism:'none'};
  }
  if(tag==='button'||el?.getAttribute?.('role')==='button'){
    const type=meta.type||'submit';if(type==='submit'&&el.form){const form=el.form;if(wave74HasDirectListener(form,'submit')||String(form.getAttribute('action')||'').trim())return {...meta,status:'WIRED',mechanism:'handled-form'}}
    if(wave74HasDirectListener(el,'click'))return {...meta,status:'WIRED',mechanism:'direct-click'};if(wave74HasAncestorListener(el,'click'))return {...meta,status:'DELEGATED',mechanism:'ancestor-click'};return {...meta,status:'UNWIRED',mechanism:'none'};
  }
  return {...meta,status:'IGNORED',mechanism:'non-action'};
}
function wave74IsVisible(el){if(!el||!el.isConnected)return false;const style=getComputedStyle(el);if(style.display==='none'||style.visibility==='hidden')return false;return el.getClientRects().length>0}
function wave74AuditScope(scope){const controls=[...scope.querySelectorAll('button,a[href],form,select,[role="button"]')].filter(wave74IsVisible);const rows=controls.map(wave74ClassifyControl);return {total:rows.length,wired:rows.filter(row=>row.status==='WIRED').length,delegated:rows.filter(row=>row.status==='DELEGATED').length,disabled:rows.filter(row=>row.status==='DISABLED').length,unwired:rows.filter(row=>row.status==='UNWIRED'),controls:rows}}
globalThis.wave74InteractionProbe={auditScope:wave74AuditScope,classify:wave74ClassifyControl,hasDirect:wave74HasDirectListener,describe:wave74DescribeControl,listenerMap:wave74ListenerMap};
