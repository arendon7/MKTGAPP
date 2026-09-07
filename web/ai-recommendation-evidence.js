(function installPostW99AIRecommendationEvidence(){
  if(globalThis.POST_W99_AI_RECOMMENDATION_EVIDENCE)return;
  globalThis.POST_W99_AI_RECOMMENDATION_EVIDENCE=true;

  const state={companyId:null,payload:null,loading:false};
  let activeRecommendationId=null;

  function company(){return typeof opsSelectedCompany==='function'?opsSelectedCompany():(typeof wave65Company==='function'?wave65Company():null)}
  function rows(){return state.payload?.recommendations||[]}
  function stateLabel(value){return({EVIDENCE_AVAILABLE:'Evidencia posterior disponible',CAPTURE_DUE:'Captura pendiente',OBSERVATION_WINDOW:'Ventana de observación',POST_SNAPSHOT_NO_TARGET_SIGNAL:'Snapshot posterior sin señal exacta',IDENTITY_GAP:'Identidad histórica incompleta',INVALID_APPLIED_TIME:'Cronología no verificable'})[value]||value||'Estado desconocido'}

  function styles(){
    if(document.querySelector('#post-w99-ai-evidence-style'))return;
    const s=document.createElement('style');s.id='post-w99-ai-evidence-style';s.textContent=`
      .ai-evidence-section{border:1px solid #d8d2c8;border-left:4px solid #171717;border-radius:13px;background:#fff;padding:12px;display:grid;gap:10px}.ai-evidence-head{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}.ai-evidence-head h3{margin:0}.ai-evidence-list{display:grid;gap:8px}.ai-evidence-row{border:1px solid #e5e0d8;border-radius:10px;padding:9px;display:grid;gap:6px;background:#faf9f6}.ai-evidence-row strong{font-size:10px}.ai-evidence-row p{margin:0;font-size:8px;color:#706a61;line-height:1.45}.ai-evidence-meta{display:flex;gap:5px;flex-wrap:wrap}.ai-evidence-chip{font-size:7px;padding:4px 6px;border-radius:999px;background:#efede7}.ai-evidence-samples{display:grid;gap:4px}.ai-evidence-sample{font-size:8px;padding:6px;border-radius:8px;background:#f3f1ec}.ai-evidence-actions{display:flex;gap:6px;flex-wrap:wrap}.ai-evidence-safety,.ai-evidence-empty{font-size:8px;color:#716b62;line-height:1.45}.ai-evidence-empty{padding:10px;border:1px dashed #d8d2c8;border-radius:9px}@media(max-width:700px){.ai-evidence-head{display:grid}}
    `;document.head.append(s)
  }

  async function load(force=false){
    const current=company();if(!current){state.companyId=null;state.payload=null;return null}
    if(state.loading)return state.payload;
    if(!force&&state.companyId===current.id&&state.payload)return state.payload;
    state.loading=true;
    try{state.payload=await opsApi(`/api/companies/${encodeURIComponent(current.id)}/ai/recommendation-evidence`);state.companyId=current.id;return state.payload}
    catch(err){state.payload=null;opsToast(err.message);return null}
    finally{state.loading=false}
  }

  function capture(item){
    const action=item?.action||item||{},kind=String(item?.kind||'').toLowerCase();
    if(kind!=='ai_recommendation_evidence_capture'||action.tab!=='ai-recommendation-evidence'||!action.entity_id)return;
    activeRecommendationId=String(action.entity_id);
  }

  function openResults(row){
    const action={label:'Actualizar resultados',view:'analytics',tab:'ai-recommendation-evidence',entity_id:row.recommendation_id||null,campaign_id:row.target?.campaign_id||null,media_id:row.target?.media_id||null,lead_id:null,contact_id:null,opportunity_id:null};
    activeRecommendationId=String(row.recommendation_id||'')||null;
    const current=company();
    if(current&&typeof globalThis.portfolioNavigate==='function'){globalThis.portfolioNavigate(current.id,action);return}
    if(typeof globalThis.actionCenterOpen==='function'){globalThis.actionCenterOpen({kind:'ai_recommendation_evidence_capture',action});return}
    opsToast('No está disponible la navegación canónica a Resultados.');
  }

  function metricText(sample){
    const metrics=sample?.metrics||{};return Object.entries(metrics).slice(0,6).map(([key,value])=>`${key}: ${value}`).join(' · ')
  }

  function card(row){
    const node=opsEl('article','ai-evidence-row');if(activeRecommendationId&&row.recommendation_id===activeRecommendationId)node.dataset.aiEvidenceActive='1';
    const meta=opsEl('div','ai-evidence-meta');meta.append(opsEl('span','ai-evidence-chip',stateLabel(row.state)),opsEl('span','ai-evidence-chip',row.target?.kind||'UNKNOWN'));
    node.append(meta,opsEl('strong','',row.title||'Recomendación aplicada'),opsEl('p','',row.state_reason||''));
    if(row.applied_at)node.append(opsEl('p','',`Marcada como aplicada: ${row.applied_at}`));
    const observation=row.post_application_snapshot;
    if(observation){
      node.append(opsEl('p','',`Snapshot capturado después: ${observation.created_at||'sin fecha'} · ${observation.organic_observations||0} observación(es) orgánicas · ${observation.paid_observations||0} de pauta.`));
      node.append(opsEl('div','ai-evidence-safety',`Ventana del snapshot: ${observation.date_preset||'no especificada'}. La captura es posterior al cierre, pero sus métricas pueden incluir tiempo anterior a la aplicación.`));
      const samples=opsEl('div','ai-evidence-samples');
      for(const sample of [...(observation.organic_samples||[]),...(observation.paid_samples||[])].slice(0,4)){
        const text=metricText(sample);if(text)samples.append(opsEl('div','ai-evidence-sample',text));
      }
      if(samples.childNodes.length)node.append(samples)
    }
    if(row.state==='CAPTURE_DUE'){
      const actions=opsEl('div','ai-evidence-actions'),button=opsEl('button','primary','Abrir Resultados para actualizar');button.type='button';button.addEventListener('click',()=>openResults(row));actions.append(button);node.append(actions)
    }
    node.append(opsEl('div','ai-evidence-safety','Lectura observacional: que una métrica esté en un snapshot capturado después no demuestra que ocurriera después ni que Astra o la recomendación la hayan causado.'));
    return node
  }

  function render(){
    if(marketingOpsState.view!=='intelligence'&&marketingOpsState.view!=='analytics')return;styles();const root=document.querySelector('#marketing-ops-view');if(!root)return;root.querySelector('#post-w99-ai-recommendation-evidence')?.remove();
    const current=company();if(!current)return;const section=opsEl('section','ai-evidence-section');section.id='post-w99-ai-recommendation-evidence';
    const head=opsEl('div','ai-evidence-head'),copy=opsEl('div','');copy.append(opsEl('p','eyebrow','ASTRA / IA · EVIDENCIA POSTERIOR'),opsEl('h3','','Qué se capturó después de recomendaciones marcadas como aplicadas'),opsEl('p','muted','La app conserva cronología de captura y evidencia observada; no convierte correlación temporal ni ventanas solapadas en causalidad.'));const refresh=opsEl('button','','Actualizar evidencia local');refresh.type='button';refresh.addEventListener('click',async()=>{await load(true);render()});head.append(copy,refresh);section.append(head);
    const payload=state.companyId===current.id?state.payload:null;if(!payload){section.append(opsEl('div','ai-evidence-empty',state.loading?'Cargando evidencia local…':'Cargando seguimiento…'));const anchor=root.querySelector('#post-w99-ai-handoffs')||root.querySelector('.w65-hero');anchor?.insertAdjacentElement('afterend',section);if(!state.loading)load(true).then(render);return}
    const summary=payload.summary||{},meta=opsEl('div','ai-evidence-meta');meta.append(opsEl('span','ai-evidence-chip',`${summary.tracked_applied||0} aplicadas rastreadas`),opsEl('span','ai-evidence-chip',`${summary.evidence_available||0} con evidencia posterior`),opsEl('span','ai-evidence-chip',`${summary.capture_due||0} captura(s) pendientes`));section.append(meta);
    const list=opsEl('div','ai-evidence-list');for(const row of rows())list.append(card(row));if(!rows().length)list.append(opsEl('div','ai-evidence-empty','Todavía no hay recomendaciones aceptadas y marcadas como aplicadas para observar.'));section.append(list,opsEl('div','ai-evidence-safety','Contrato: endpoint GET local, snapshots ya existentes y navegación humana. No refresca proveedores, no genera IA, no ejecuta marketing y no atribuye resultados a Astra.'));
    const anchor=root.querySelector('#post-w99-ai-handoffs')||root.querySelector('#post-w99-ai-review')||root.querySelector('.w65-hero');if(anchor)anchor.insertAdjacentElement('afterend',section);else root.prepend(section)
  }

  if(typeof globalThis.actionCenterSourceLabel==='function'){
    const baseLabel=globalThis.actionCenterSourceLabel;globalThis.actionCenterSourceLabel=function postW99AIEvidenceSourceLabel(value){return value==='AI_EVIDENCE'?'Astra · evidencia':baseLabel(value)};
  }
  if(typeof globalThis.actionCenterOpen==='function'){
    const baseOpen=globalThis.actionCenterOpen;globalThis.actionCenterOpen=function postW99AIEvidenceOpen(item){capture(item);const value=baseOpen.apply(this,arguments);queueMicrotask(render);return value};
  }
  if(typeof globalThis.portfolioNavigate==='function'){
    const baseNavigate=globalThis.portfolioNavigate;globalThis.portfolioNavigate=async function postW99AIEvidencePortfolioNavigate(companyId,action){if(action?.tab==='ai-recommendation-evidence'&&action?.entity_id)activeRecommendationId=String(action.entity_id);const value=await baseNavigate.apply(this,arguments);queueMicrotask(render);return value};
  }
  if(typeof globalThis.actionCenterLoad==='function'){
    const baseLoad=globalThis.actionCenterLoad;globalThis.actionCenterLoad=async function postW99AIEvidenceActionCenterLoad(){const value=await baseLoad.apply(this,arguments);await load(true);return value};
  }
  if(typeof wave65Render==='function'){
    const baseWave65Render=wave65Render;wave65Render=function postW99AIEvidenceWave65Render(){baseWave65Render();render()};
  }
  const baseRender=globalThis.renderMarketingOps;if(typeof baseRender==='function')globalThis.renderMarketingOps=function postW99AIEvidenceRenderMarketingOps(){const value=baseRender.apply(this,arguments);queueMicrotask(render);return value};
  window.addEventListener('marketing-ops-refreshed',()=>{const current=company();if(!current){state.payload=null;state.companyId=null;activeRecommendationId=null}else if(current.id!==state.companyId){state.payload=null;state.companyId=null;activeRecommendationId=null}load(true).then(render)});
  styles();load();queueMicrotask(render);
})();
