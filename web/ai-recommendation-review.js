(function installPostW99AIRecommendationReview(){
  if(globalThis.POST_W99_AI_RECOMMENDATION_REVIEW)return;
  globalThis.POST_W99_AI_RECOMMENDATION_REVIEW=true;
  if(typeof wave65Render!=='function')return;

  const state={companyId:null,payload:null,loading:false,busy:new Set()};
  let exactSessionTarget=null;

  function company(){return typeof wave65Company==='function'?wave65Company():null}
  function styles(){
    if(document.querySelector('#post-w99-ai-review-style'))return;
    const s=document.createElement('style');s.id='post-w99-ai-review-style';s.textContent=`
      .ai-review-section{border-left:4px solid #171717}.ai-review-summary{display:flex;gap:6px;flex-wrap:wrap}.ai-review-groups{display:grid;gap:9px}.ai-review-group{border:1px solid #ddd8cf;border-radius:12px;padding:11px;display:grid;gap:9px;background:#fff}.ai-review-group.target{box-shadow:0 0 0 2px #171717 inset}.ai-review-group-head{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}.ai-review-group-head h4{margin:0;font-size:12px}.ai-review-list{display:grid;gap:7px}.ai-review-card{border:1px solid #e7e2d9;border-radius:10px;padding:9px;background:#faf9f6;display:grid;gap:6px}.ai-review-card strong{font-size:10px}.ai-review-card p{margin:0;font-size:9px;color:#625d55;line-height:1.45}.ai-review-next{padding:7px 8px;border-radius:8px;background:#f1eee8;font-size:9px}.ai-review-actions{display:flex;gap:6px;flex-wrap:wrap}.ai-review-chip{display:inline-flex;padding:4px 7px;border-radius:999px;background:#efede7;font-size:8px}.ai-review-chip.warning{background:#f5eee1}.ai-review-safety{font-size:8px;color:#756f66;line-height:1.45}.ai-review-empty{padding:12px;border:1px dashed #d9d3c9;border-radius:9px;font-size:9px;color:#756f66}
    `;document.head.append(s)
  }

  function captureTarget(companyId,action){
    if(!action||action.view!=='intelligence'||action.tab!=='ai-recommendation-review'||!action.entity_id)return;
    exactSessionTarget={companyId:String(companyId||'').trim()||null,sessionId:String(action.entity_id||'').trim()};
  }

  async function load(force=false){
    const current=company();if(!current){state.companyId=null;state.payload=null;return null}
    if(state.loading)return state.payload;
    if(!force&&state.companyId===current.id&&state.payload)return state.payload;
    state.loading=true;
    try{state.payload=await opsApi(`/api/companies/${encodeURIComponent(current.id)}/ai/recommendation-review`);state.companyId=current.id;return state.payload}
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

  async function decide(rec,decision,button){
    const current=company();if(!current||!rec?.recommendation_id)return;
    const label=decision==='ACCEPTED'?'aceptar':'descartar';
    if(!window.confirm(`Vas a ${label} esta recomendación de Astra. Esto sólo registra tu revisión local: no publica, no activa pauta, no crea contenido y no modifica CRM. ¿Continuar?`))return;
    const key=String(rec.recommendation_id);if(state.busy.has(key))return;state.busy.add(key);if(button)button.disabled=true;
    try{
      const result=await opsApi(`/api/companies/${encodeURIComponent(current.id)}/ai/recommendation-review`,{method:'POST',body:{recommendation_id:key,decision}});
      state.payload=result.projection||null;state.companyId=current.id;
      await refreshLocalQueues();
      const stillTarget=(state.payload?.groups||[]).some(group=>group.session_id===exactSessionTarget?.sessionId);if(!stillTarget)exactSessionTarget=null;
      opsToast(decision==='ACCEPTED'?'Recomendación aceptada para criterio humano; no se ejecutó ninguna acción':'Recomendación descartada; no se ejecutó ninguna acción');
      if(marketingOpsState.view==='intelligence')wave65Render();
    }catch(err){opsToast(err.message);if(button)button.disabled=false}
    finally{state.busy.delete(key)}
  }

  function recommendationCard(rec){
    const card=opsEl('article','ai-review-card'),chips=opsEl('div','ai-review-summary');
    chips.append(opsEl('span','ai-review-chip warning',`Sugerencia IA · ${rec.priority||'MEDIUM'} · no autoritativa`),opsEl('span','ai-review-chip',rec.area||'STRATEGY'));
    card.append(chips,opsEl('strong','',rec.title||'Recomendación'),opsEl('p','',rec.why||'Sin justificación adicional.'),opsEl('div','ai-review-next',`Próximo paso sugerido: ${rec.next_step||'Revisar manualmente.'}`));
    const actions=opsEl('div','ai-review-actions'),accept=opsEl('button','primary','Aceptar recomendación'),dismiss=opsEl('button','','Descartar');accept.type=dismiss.type='button';
    accept.addEventListener('click',()=>decide(rec,'ACCEPTED',accept));dismiss.addEventListener('click',()=>decide(rec,'DISMISSED',dismiss));actions.append(accept,dismiss);card.append(actions);return card
  }

  function groupCard(group,currentCompanyId){
    const target=Boolean(exactSessionTarget&&exactSessionTarget.sessionId===group.session_id&&(!exactSessionTarget.companyId||exactSessionTarget.companyId===currentCompanyId));
    const card=opsEl('article',`ai-review-group ${target?'target':''}`);card.dataset.aiReviewSessionId=group.session_id||'';
    const head=opsEl('div','ai-review-group-head'),copy=opsEl('div','');copy.append(opsEl('p','eyebrow',`${group.task||'AI'} · REVISIÓN HUMANA`),opsEl('h4','',group.target_label||'Astra / IA'),opsEl('div','ai-review-safety',`${group.pending_count||0} pendiente(s) · áreas ${(group.areas||[]).join(', ')||'—'} · prioridad del modelo no altera Hoy`));head.append(copy,opsEl('span','ai-review-chip',group.session_created_at?opsDate(group.session_created_at):'Sesión IA'));card.append(head);
    const list=opsEl('div','ai-review-list');for(const rec of group.recommendations||[])list.append(recommendationCard(rec));card.append(list);
    if(target)card.scrollIntoView({block:'center',behavior:'smooth'});return card
  }

  function renderPanel(){
    if(marketingOpsState.view!=='intelligence')return;styles();const root=document.querySelector('#marketing-ops-view');if(!root||root.querySelector('#post-w99-ai-review'))return;
    const current=company();if(!current)return;const section=opsEl('section','marketing-ops-section ai-review-section');section.id='post-w99-ai-review';
    const head=opsEl('div','marketing-ops-section-head'),copy=opsEl('div','');copy.append(opsEl('p','eyebrow','ASTRA / IA · CONTROL HUMANO'),opsEl('h3','','Recomendaciones pendientes de revisión'),opsEl('p','muted','Astra puede sugerir. Tú decides qué aceptar o descartar. Aceptar no ejecuta el siguiente paso ni cambia la prioridad determinística de Hoy.'));const refresh=opsEl('button','','Actualizar revisión');refresh.type='button';refresh.addEventListener('click',async()=>{await load(true);wave65Render()});head.append(copy,refresh);section.append(head);
    const payload=state.companyId===current.id?state.payload:null;if(!payload){section.append(opsEl('div','ai-review-empty',state.loading?'Cargando revisión local…':'Cargando recomendaciones ya generadas…'));root.querySelector('.w65-hero')?.insertAdjacentElement('afterend',section);if(!state.loading)load(true).then(()=>{if(marketingOpsState.view==='intelligence')wave65Render()});return}
    const summary=payload.summary||{},summaryRow=opsEl('div','ai-review-summary');summaryRow.append(opsEl('span','ai-review-chip',`${summary.current_sessions_with_pending_review||0} sesión(es) pendientes`),opsEl('span','ai-review-chip',`${summary.pending_recommendations||0} recomendación(es)`),opsEl('span','ai-review-chip',`${summary.accepted||0} aceptadas históricas`),opsEl('span','ai-review-chip',`${summary.dismissed||0} descartadas históricas`));section.append(summaryRow);
    let groups=[...(payload.groups||[])];if(exactSessionTarget){const index=groups.findIndex(group=>group.session_id===exactSessionTarget.sessionId);if(index>0)groups.unshift(groups.splice(index,1)[0])}
    const list=opsEl('div','ai-review-groups');for(const group of groups)list.append(groupCard(group,current.id));if(!groups.length)list.append(opsEl('div','ai-review-empty','No hay recomendaciones de la sesión IA actual pendientes de revisión.'));section.append(list,opsEl('div','ai-review-safety','Contrato: esta superficie sólo lee sesiones IA ya generadas y registra ACCEPTED/DISMISSED localmente. No llama al proveedor de IA, no consulta Meta, no publica, no pauta, no crea tareas CRM y no ejecuta recomendaciones.'));
    const hero=root.querySelector('.w65-hero');if(hero)hero.insertAdjacentElement('afterend',section);else root.prepend(section)
  }

  if(typeof globalThis.actionCenterSourceLabel==='function'){
    const baseLabel=globalThis.actionCenterSourceLabel;globalThis.actionCenterSourceLabel=function postW99AIReviewSourceLabel(value){return value==='AI_REVIEW'?'Astra / IA':baseLabel(value)};
  }
  if(typeof globalThis.actionCenterOpen==='function'){
    const baseOpen=globalThis.actionCenterOpen;globalThis.actionCenterOpen=function postW99AIReviewActionOpen(item){captureTarget(company()?.id,item?.action||{});return baseOpen(item)};
  }
  if(typeof globalThis.portfolioNavigate==='function'){
    const baseNavigate=globalThis.portfolioNavigate;globalThis.portfolioNavigate=async function postW99AIReviewPortfolioNavigate(companyId,action){captureTarget(companyId,action||{});return baseNavigate(companyId,action)};
  }

  const baseRender=wave65Render;wave65Render=function postW99AIRecommendationReviewRender(){baseRender();renderPanel()};
  if(typeof wave65Analyze==='function'){
    const baseAnalyze=wave65Analyze;wave65Analyze=async function postW99AIRecommendationAnalyze(row){await baseAnalyze(row);await load(true);if(marketingOpsState.view==='intelligence')wave65Render()};
  }
  window.addEventListener('marketing-ops-refreshed',()=>{const current=company();if(!current||current.id!==state.companyId){state.payload=null;state.companyId=null}load(true).then(()=>{if(marketingOpsState.view==='intelligence')wave65Render()})});
  styles();load();if(marketingOpsState.view==='intelligence')wave65Render();
})();
