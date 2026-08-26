function campaignCoordinateActionabilityStyles(){
  if(document.querySelector('#post-w99-campaign-coordinate-actionability-style'))return;
  const style=document.createElement('style');
  style.id='post-w99-campaign-coordinate-actionability-style';
  style.textContent=`
  .cca-observations{border:1px solid #dedad1;border-radius:13px;background:#fff;padding:13px;display:grid;gap:10px}
  .cca-list{display:grid;gap:7px}
  .cca-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;align-items:center;padding:11px;border:1px dashed #d8d2c8;border-radius:10px;background:#faf8f4}
  .cca-copy{display:grid;gap:4px}.cca-copy strong{font-size:10px}.cca-copy p{margin:0;font-size:9px;color:#716b62;line-height:1.45}
  .cca-meta{display:flex;gap:5px;flex-wrap:wrap}.cca-note{font-size:8px;color:#817a70}
  @media(max-width:720px){.cca-row{grid-template-columns:1fr}}
  `;
  document.head.append(style)
}

function campaignCoordinateActionabilityPayload(){
  if(typeof postW99ActionState==='undefined')return null;
  return postW99ActionState.payload||null
}

function campaignCoordinateActionabilityRows(){
  const payload=campaignCoordinateActionabilityPayload();
  return (payload?.observations||[]).filter(row=>
    String(row?.source||'').toUpperCase()==='CAMPAIGN' &&
    String(row?.kind||'').toLowerCase()==='coordinate' &&
    row?.actionability?.state==='NON_ACTIONABLE_COORDINATE'
  )
}

function campaignCoordinateActionabilityChip(row){
  const recovery=String(row?.actionability?.recovery_state||'').toUpperCase();
  if(recovery==='EXACT_EXISTING_OWNER'||recovery==='AMBIGUOUS_EXISTING_OWNER')return 'EN CURSO';
  if(recovery.includes('GAP')||recovery.includes('AMBIGUOUS'))return 'GAP';
  if(recovery==='DIAGNOSTIC_ONLY')return 'DIAGNÓSTICO';
  return 'OBSERVACIÓN'
}

function campaignCoordinateActionabilityOpen(row){
  if(typeof actionCenterOpen==='function'){actionCenterOpen(row);return}
  const campaignId=row?.action?.campaign_id;
  if(typeof campaignState!=='undefined'&&campaignId)campaignState.selectedId=campaignId;
  if(typeof opsShowView==='function')opsShowView(row?.action?.view||'content')
}

function campaignCoordinateActionabilityRow(row){
  const article=opsEl('article','cca-row'),copy=opsEl('div','cca-copy');
  copy.append(
    opsEl('strong','',row.title||'Coordinar distribución'),
    opsEl('p','',row.detail||'El estado se conserva como observación hasta que exista una recuperación exacta.')
  );
  const meta=opsEl('div','cca-meta');
  meta.append(
    opsEl('span','ac-chip low','COORDINATE'),
    opsEl('span','ac-chip',campaignCoordinateActionabilityChip(row)),
    opsEl('span','ac-chip','FUERA DE HOY')
  );
  const state=String(row?.actionability?.coordinate_state||'UNKNOWN');
  const recovery=String(row?.actionability?.recovery_state||'UNKNOWN');
  copy.append(
    meta,
    opsEl('div','cca-note',`Estado: ${state} · recovery: ${recovery}`),
    opsEl(
      'div',
      'cca-note',
      row?.actionability?.reason||
      'Wave64 declaró requires_action=false y no existe un owner de recuperación exacto que autorice una tarea.'
    )
  );
  const open=opsEl('button','','Ver contexto');
  open.type='button';
  open.addEventListener('click',()=>campaignCoordinateActionabilityOpen(row));
  article.append(copy,open);
  return article
}

function campaignCoordinateActionabilityRender(){
  if(typeof marketingOpsState==='undefined'||marketingOpsState.view!=='action-center')return;
  const root=document.querySelector('#marketing-ops-view');
  if(!root)return;
  root.querySelector('#post-w99-campaign-coordinate-observations')?.remove();
  const rows=campaignCoordinateActionabilityRows();
  if(!rows.length)return;
  campaignCoordinateActionabilityStyles();
  const section=opsEl('section','cca-observations');
  section.id='post-w99-campaign-coordinate-observations';
  const head=opsEl('div','ac-toolbar-copy');
  head.append(
    opsEl('p','eyebrow','COORDINACIÓN · OBSERVACIONES'),
    opsEl('h3','','Estados sin acción humana exacta'),
    opsEl(
      'p',
      'muted',
      'Wave64 marcó estos estados como no accionables. Permanecen visibles para contexto, pero no ocupan la cola ni el plan de Hoy salvo que Recovery Guidance pruebe un owner exacto.'
    )
  );
  section.append(head);
  const list=opsEl('div','cca-list');
  rows.forEach(row=>list.append(campaignCoordinateActionabilityRow(row)));
  section.append(list);
  root.append(section)
}

if(typeof actionCenterRender==='function'){
  const campaignCoordinateActionabilityBaseRender=actionCenterRender;
  actionCenterRender=function(){
    campaignCoordinateActionabilityBaseRender();
    campaignCoordinateActionabilityRender()
  }
}

campaignCoordinateActionabilityStyles();
campaignCoordinateActionabilityRender();
