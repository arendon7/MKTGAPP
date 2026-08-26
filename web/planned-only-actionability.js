function plannedOnlyActionabilityStyles(){
  if(document.querySelector('#post-w99-planned-only-actionability-style'))return;
  const style=document.createElement('style');
  style.id='post-w99-planned-only-actionability-style';
  style.textContent=`
  .po-observations{border:1px solid #dedad1;border-radius:13px;background:#fff;padding:13px;display:grid;gap:10px}
  .po-observation-list{display:grid;gap:7px}
  .po-observation{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;align-items:center;padding:11px;border:1px dashed #d8d2c8;border-radius:10px;background:#faf8f4}
  .po-observation-copy{display:grid;gap:4px}.po-observation-copy strong{font-size:10px}.po-observation-copy p{margin:0;font-size:9px;color:#716b62;line-height:1.45}
  .po-observation-meta{display:flex;gap:5px;flex-wrap:wrap}.po-observation-note{font-size:8px;color:#817a70}
  @media(max-width:720px){.po-observation{grid-template-columns:1fr}}
  `;
  document.head.append(style)
}

function plannedOnlyActionabilityPayload(){
  if(typeof postW99ActionState==='undefined')return null;
  return postW99ActionState.payload||null
}

function plannedOnlyActionabilityRows(){
  const payload=plannedOnlyActionabilityPayload();
  return (payload?.observations||[]).filter(row=>
    String(row?.source||'').toUpperCase()==='CAMPAIGN' &&
    String(row?.kind||'').toLowerCase()==='planned_only' &&
    row?.actionability?.state==='NON_ACTIONABLE'
  )
}

function plannedOnlyActionabilityOpenCampaign(row){
  if(typeof actionCenterOpen==='function'){actionCenterOpen(row);return}
  if(typeof campaignState!=='undefined'&&row?.action?.campaign_id)campaignState.selectedId=row.action.campaign_id;
  if(typeof opsShowView==='function')opsShowView('campaigns')
}

function plannedOnlyActionabilityObservation(row){
  const article=opsEl('article','po-observation'),copy=opsEl('div','po-observation-copy');
  copy.append(
    opsEl('strong','',row.title||'Canal todavía planificado'),
    opsEl('p','',row.detail||'Este estado no tiene una acción ejecutable desde el gate actual.')
  );
  const meta=opsEl('div','po-observation-meta');
  meta.append(
    opsEl('span','ac-chip low','OBSERVACIÓN'),
    opsEl('span','ac-chip','PLANNED_ONLY'),
    opsEl('span','ac-chip','FUERA DE HOY')
  );
  copy.append(
    meta,
    opsEl(
      'div',
      'po-observation-note',
      row.actionability?.reason||'Wave64 conserva este estado como no accionable y no se inventa un provider para ejecutarlo.'
    )
  );
  const open=opsEl('button','','Ver campaña');
  open.type='button';
  open.addEventListener('click',()=>plannedOnlyActionabilityOpenCampaign(row));
  article.append(copy,open);
  return article
}

function plannedOnlyActionabilityRender(){
  if(typeof marketingOpsState==='undefined'||marketingOpsState.view!=='action-center')return;
  const root=document.querySelector('#marketing-ops-view');
  if(!root)return;
  root.querySelector('#post-w99-planned-only-observations')?.remove();
  const rows=plannedOnlyActionabilityRows();
  if(!rows.length)return;
  plannedOnlyActionabilityStyles();
  const section=opsEl('section','po-observations');
  section.id='post-w99-planned-only-observations';
  const head=opsEl('div','ac-toolbar-copy');
  head.append(
    opsEl('p','eyebrow','OBSERVACIONES · NO EJECUTABLES'),
    opsEl('h3','','Canales todavía planificados'),
    opsEl('p','muted','Se conservan visibles sin ocupar la cola de acciones ni el plan de Hoy. Abrir la campaña solo navega al owner; no habilita ni simula un provider.')
  );
  section.append(head);
  const list=opsEl('div','po-observation-list');
  rows.forEach(row=>list.append(plannedOnlyActionabilityObservation(row)));
  section.append(list);
  root.append(section)
}

if(typeof actionCenterRender==='function'){
  const plannedOnlyActionabilityBaseRender=actionCenterRender;
  actionCenterRender=function(){
    plannedOnlyActionabilityBaseRender();
    plannedOnlyActionabilityRender()
  }
}

plannedOnlyActionabilityStyles();
plannedOnlyActionabilityRender();
