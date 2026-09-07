(function installPostW99AIRecommendationHandoff(){
  if(globalThis.POST_W99_AI_RECOMMENDATION_HANDOFF)return;
  globalThis.POST_W99_AI_RECOMMENDATION_HANDOFF=true;

  const state={companyId:null,payload:null,loading:false,busy:new Set()};
  let activeHandoff=null;

  function company(){return typeof opsSelectedCompany==='function'?opsSelectedCompany():(typeof wave65Company==='function'?wave65Company():null)}
  function handoffs(){return state.payload?.handoffs||[]}
  function gaps(){return state.payload?.owner_gaps||[]}
  function actionFor(row){const route=row?.route||{};return{label:'Abrir módulo responsable',view:route.view,tab:'ai-accepted-handoff',entity_id:row.recommendation_id||null,lead_id:null,contact_id:null,opportunity_id:null,campaign_id:route.campaign_id||null,media_id:route.media_id||null}}

  function styles(){
    if(document.querySelector('#post-w99-ai-handoff-style'))return;
    const s=document.createElement('style');s.id='post-w99-ai-handoff-style';s.textContent=`
      .ai-handoff-section,.ai-handoff-owner{border:1px solid #d8d2c8;border-radius:13px;background:#fff;padding:12px;display:grid;gap:10px}.ai-handoff-section{border-left:4px solid #171717}.ai-handoff-head{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}.ai-handoff-head h3,.ai-handoff-head h4{margin:0}.ai-handoff-list{display:grid;gap:8px}.ai-handoff-row{border:1px solid #e5e0d8;border-radius:10px;padding:9px;display:grid;gap:6px;background:#faf9f6}.ai-handoff-row strong{font-size:10px}.ai-handoff-row p{margin:0;font-size:8px;color:#706a61;line-height:1.45}.ai-handoff-meta{display:flex;gap:5px;flex-wrap:wrap}.ai-handoff-chip{font-size:7px;padding:4px 6px;border-radius:999px;background:#efede7}.ai-handoff-actions{display:flex;gap:6px;flex-wrap:wrap}.ai-handoff-owner{margin:0 0 12px;border-left:4px solid #171717}.ai-handoff-safety{font-size:8px;color:#716b62;line-height:1.45}.ai-handoff-empty{padding:10px;border:1px dashed #d8d2c8;border-radius:9px;font-size:8px;color:#716b62}@media(max-width:700px){.ai-handoff-head{display:grid}}
    `;document.head.append(s)
  }

  async function load(force=false){
    const current=company();if(!current){state.companyId=null;state.payload=null;return null}
    if(state.loading)return state.payload;
    if(!force&&state.companyId===current.id&&state.payload)return state.payload;
    state.loading=true;
    try{state.payload=await opsApi(`/api/companies/${encodeURIComponent(current.id)}/ai/recommendation-handoffs`);state.companyId=current.id;return state.payload}
    catch(err){state.payload=null;opsToast(err.message);return null}
    finally{state.loading=false}
  }

  async function refreshLocalQueues(){
    const jobs=[];
    if(typeof globalThis.actionCenterLoad==='function')jobs.push(globalThis.actionCenterLoad(true));
    if(typeof globalThis.portfolioLoad==='function')jobs.push(globalThis.portfolioLoad());
    if(typeof globalThis.todayPortfolioLoad==='function')jobs.push(globalThis.todayPortfolioLoad(true));
    if(jobs.length)await Promise.allSettled(jobs)
  }

  function capture(companyId,item){
    const action=item?.action||item||{},kind=String(item?.kind||'').toLowerCase();
    if(kind!=='ai_accepted_handoff'||action.tab!=='ai-accepted-handoff'||!action.entity_id||!action.view)return;
    activeHandoff={companyId:String(companyId||'').trim()||null,recommendationId:String(action.entity_id),ownerView:String(action.view)};
  }

  async function openOwner(row){
    const current=company();if(!current||!row?.recommendation_id)return;
    const action=actionFor(row);activeHandoff={companyId:current.id,recommendationId:row.recommendation_id,ownerView:action.view};
    if(typeof globalThis.portfolioNavigate==='function'){await globalThis.portfolioNavigate(current.id,action);return}
    if(typeof globalThis.actionCenterOpen==='function'){globalThis.actionCenterOpen({kind:'ai_accepted_handoff',action});return}
    opsToast('No está disponible la navegación canónica al owner.');
  }

  async function resolve(row,outcome,button){
    const current=company();if(!current||!row?.recommendation_id)return;
    const verb=outcome==='APPLIED'?'marcar como aplicada':'marcar como no aplicada';
    if(!window.confirm(`Vas a ${verb} esta recomendación aceptada. Esto registra únicamente tu evidencia local de cierre; no ejecuta, revierte ni modifica ninguna acción de marketing. ¿Continuar?`))return;
    const key=String(row.recommendation_id);if(state.busy.has(key))return;state.busy.add(key);if(button)button.disabled=true;
    try{
      const result=await opsApi(`/api/companies/${encodeURIComponent(current.id)}/ai/recommendation-handoffs`,{method:'POST',body:{recommendation_id:key,outcome}});
      state.payload=result.projection||null;state.companyId=current.id;activeHandoff=null;
      await refreshLocalQueues();
      opsToast(outcome==='APPLIED'?'Handoff cerrado como aplicado; la app no ejecutó la recomendación':'Handoff cerrado como no aplicado; la app no ejecutó cambios');
      renderOwnerContext();if(marketingOpsState.view==='intelligence'&&typeof wave65Render==='function')wave65Render();
    }catch(err){opsToast(err.message);if(button)button.disabled=false}
    finally{state.busy.delete(key)}
  }

  function handoffRow(row,withOpen=true){
    const card=opsEl('article','ai-handoff-row'),route=row.route||{},meta=opsEl('div','ai-handoff-meta');
    meta.append(opsEl('span','ai-handoff-chip',row.area||'STRATEGY'),opsEl('span','ai-handoff-chip',route.owner||route.state||'OWNER GAP'));
    card.append(meta,opsEl('strong','',row.title||'Recomendación aceptada'),opsEl('p','',row.why||''),opsEl('p','',`Siguiente paso sugerido: ${row.next_step||'Revisar manualmente.'}`));
    if(withOpen&&route.state==='OWNER_RESOLVED'){
      const actions=opsEl('div','ai-handoff-actions'),open=opsEl('button','primary','Abrir módulo responsable');open.type='button';open.addEventListener('click',()=>openOwner(row));actions.append(open);card.append(actions)
    }
    return card
  }

  function renderIntelligencePanel(){
    if(marketingOpsState.view!=='intelligence')return;styles();const root=document.querySelector('#marketing-ops-view');if(!root||root.querySelector('#post-w99-ai-handoffs'))return;
    const current=company();if(!current)return;const section=opsEl('section','ai-handoff-section');section.id='post-w99-ai-handoffs';
    const head=opsEl('div','ai-handoff-head'),copy=opsEl('div','');copy.append(opsEl('p','eyebrow','ASTRA / IA · HANDOFF HUMANO'),opsEl('h3','','Recomendaciones aceptadas pendientes de aplicar'),opsEl('p','muted','Aceptar una recomendación no la ejecuta. Esta capa sólo la transfiere a un owner estructurado cuando existe identidad exacta.'));const refresh=opsEl('button','','Actualizar handoffs');refresh.type='button';refresh.addEventListener('click',async()=>{await load(true);if(typeof wave65Render==='function')wave65Render()});head.append(copy,refresh);section.append(head);
    const payload=state.companyId===current.id?state.payload:null;if(!payload){section.append(opsEl('div','ai-handoff-empty',state.loading?'Cargando handoffs locales…':'Cargando recomendaciones aceptadas…'));const anchor=root.querySelector('#post-w99-ai-review')||root.querySelector('.w65-hero');anchor?.insertAdjacentElement('afterend',section);if(!state.loading)load(true).then(()=>{if(marketingOpsState.view==='intelligence'&&typeof wave65Render==='function')wave65Render()});return}
    const summary=payload.summary||{},meta=opsEl('div','ai-handoff-meta');meta.append(opsEl('span','ai-handoff-chip',`${summary.open_handoffs||0} handoff(s) abiertos`),opsEl('span','ai-handoff-chip',`${summary.owner_gaps||0} sin owner exacto`),opsEl('span','ai-handoff-chip',`${summary.resolved_current||0} resueltos`));section.append(meta);
    const list=opsEl('div','ai-handoff-list');for(const row of handoffs())list.append(handoffRow(row,true));for(const row of gaps()){
      const card=handoffRow(row,false);card.append(opsEl('div','ai-handoff-safety','OWNER GAP · No se eligió CRM, campaña, creativo u otro módulo por similitud textual. Se requiere una identidad estructurada antes de crear un handoff.'));list.append(card)
    }if(!handoffs().length&&!gaps().length)list.append(opsEl('div','ai-handoff-empty','No hay recomendaciones aceptadas actuales pendientes de handoff.'));section.append(list,opsEl('div','ai-handoff-safety','Contrato: navegación local y cierre manual. No llama al proveedor IA, no consulta Meta, no crea contenido, no modifica CRM, no activa pauta y no ejecuta la recomendación.'));
    const anchor=root.querySelector('#post-w99-ai-review')||root.querySelector('.w65-hero');if(anchor)anchor.insertAdjacentElement('afterend',section);else root.prepend(section)
  }

  function activeRow(){
    const current=company();if(!activeHandoff||!current||activeHandoff.companyId!==current.id||activeHandoff.ownerView!==marketingOpsState.view)return null;
    return handoffs().find(row=>row.recommendation_id===activeHandoff.recommendationId)||null
  }

  function renderOwnerContext(){
    styles();document.querySelector('#post-w99-ai-handoff-owner')?.remove();const row=activeRow();if(!row)return;const root=document.querySelector('#marketing-ops-view');if(!root)return;
    const route=row.route||{},card=opsEl('section','ai-handoff-owner');card.id='post-w99-ai-handoff-owner';card.dataset.aiHandoffRecommendationId=row.recommendation_id||'';
    const head=opsEl('div','ai-handoff-head'),copy=opsEl('div','');copy.append(opsEl('p','eyebrow','ASTRA · RECOMENDACIÓN ACEPTADA'),opsEl('h4','',row.title||'Handoff de Astra'),opsEl('p','muted',`Owner estructurado: ${route.owner||route.view||'—'}. Abrir este módulo no marcó la recomendación como aplicada.`));head.append(copy,opsEl('span','ai-handoff-chip',row.area||'STRATEGY'));card.append(head,opsEl('p','ai-handoff-safety',row.next_step||'Revisar manualmente.'));
    const actions=opsEl('div','ai-handoff-actions'),applied=opsEl('button','primary','Marcar aplicada'),skip=opsEl('button','','No aplicar');applied.type=skip.type='button';applied.addEventListener('click',()=>resolve(row,'APPLIED',applied));skip.addEventListener('click',()=>resolve(row,'NOT_APPLIED',skip));actions.append(applied,skip);card.append(actions,opsEl('div','ai-handoff-safety','Estos botones sólo cierran el handoff como evidencia humana. No disparan ningún control del módulo propietario.'));
    const context=root.querySelector('#post-w99-contextual-control-handoff')||root.querySelector('#post-w99-contextual-deep-link-context');if(context)context.insertAdjacentElement('afterend',card);else root.prepend(card)
  }

  if(typeof globalThis.actionCenterSourceLabel==='function'){
    const baseLabel=globalThis.actionCenterSourceLabel;globalThis.actionCenterSourceLabel=function postW99AIHandoffSourceLabel(value){return value==='AI_HANDOFF'?'Astra · aceptada':baseLabel(value)};
  }
  if(typeof globalThis.actionCenterOpen==='function'){
    const baseOpen=globalThis.actionCenterOpen;globalThis.actionCenterOpen=function postW99AIHandoffOpen(item){capture(company()?.id,item);const value=baseOpen.apply(this,arguments);queueMicrotask(renderOwnerContext);return value};
  }
  if(typeof globalThis.portfolioNavigate==='function'){
    const baseNavigate=globalThis.portfolioNavigate;globalThis.portfolioNavigate=async function postW99AIHandoffPortfolioNavigate(companyId,action){if(action?.tab==='ai-accepted-handoff')capture(companyId,{kind:'ai_accepted_handoff',action});const value=await baseNavigate.apply(this,arguments);queueMicrotask(renderOwnerContext);return value};
  }
  if(typeof globalThis.actionCenterLoad==='function'){
    const baseLoad=globalThis.actionCenterLoad;globalThis.actionCenterLoad=async function postW99AIHandoffActionCenterLoad(){const value=await baseLoad.apply(this,arguments);await load(true);return value};
  }

  if(typeof wave65Render==='function'){
    const baseWave65Render=wave65Render;wave65Render=function postW99AIHandoffWave65Render(){baseWave65Render();renderIntelligencePanel();renderOwnerContext()};
  }
  const baseRender=globalThis.renderMarketingOps;if(typeof baseRender==='function')globalThis.renderMarketingOps=function postW99AIHandoffRenderMarketingOps(){const value=baseRender.apply(this,arguments);queueMicrotask(renderOwnerContext);return value};
  ['campaignRenderCurrent','contentRenderCurrent','wave64Render'].forEach(name=>{const base=globalThis[name];if(typeof base!=='function')return;globalThis[name]=function postW99AIHandoffOwnerRender(){const value=base.apply(this,arguments);queueMicrotask(renderOwnerContext);return value}});
  window.addEventListener('marketing-ops-refreshed',()=>{const current=company();if(!current){state.payload=null;state.companyId=null;activeHandoff=null}else if(current.id!==state.companyId){state.payload=null;state.companyId=null;if(activeHandoff&&activeHandoff.companyId!==current.id)activeHandoff=null}load(true).then(()=>{renderOwnerContext();if(marketingOpsState.view==='intelligence'&&typeof wave65Render==='function')wave65Render()})});
  styles();load();if(marketingOpsState.view==='intelligence'&&typeof wave65Render==='function')wave65Render();
})();