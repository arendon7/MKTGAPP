function campaignAttentionActionabilityStyles(){
  if(document.querySelector('#post-w99-campaign-attention-actionability-style'))return;
  const style=document.createElement('style');
  style.id='post-w99-campaign-attention-actionability-style';
  style.textContent=`
  .caa-observations{border:1px solid #dedad1;border-radius:13px;background:#fff;padding:13px;display:grid;gap:10px}
  .caa-list{display:grid;gap:7px}
  .caa-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;align-items:center;padding:11px;border:1px dashed #d8d2c8;border-radius:10px;background:#faf8f4}
  .caa-copy{display:grid;gap:4px}.caa-copy strong{font-size:10px}.caa-copy p{margin:0;font-size:9px;color:#716b62;line-height:1.45}
  .caa-meta{display:flex;gap:5px;flex-wrap:wrap}.caa-note{font-size:8px;color:#817a70}
  @media(max-width:720px){.caa-row{grid-template-columns:1fr}}
  `;
  document.head.append(style)
}

function campaignAttentionActionabilityPayload(){
  if(typeof postW99ActionState==='undefined')return null;
  return postW99ActionState.payload||null
}

function campaignAttentionActionabilityRows(){
  const payload=campaignAttentionActionabilityPayload();
  return (payload?.observations||[]).filter(row=>
    String(row?.source||'').toUpperCase()==='CAMPAIGN' &&
    row?.actionability?.state==='NON_REQUIRED_CAMPAIGN_ATTENTION'
  )
}

function campaignAttentionActionabilityChip(row){
  const kind=String(row?.kind||'').toUpperCase();
  if(kind==='OPTIONAL_AI')return 'OPCIONAL';
  if(kind==='REVIEW_RESULTS')return 'REVISIÓN';
  if(kind==='CALENDAR')return 'SEGUIMIENTO';
  return 'OBSERVACIÓN'
}

function campaignAttentionActionabilityOpen(row){
  if(typeof actionCenterOpen==='function'){actionCenterOpen(row);return}
  const campaignId=row?.action?.campaign_id;
  if(typeof campaignState!=='undefined'&&campaignId)campaignState.selectedId=campaignId;
  if(typeof opsShowView==='function')opsShowView(row?.action?.view||'campaigns')
}

function campaignAttentionActionabilityRow(row){
  const article=opsEl('article','caa-row'),copy=opsEl('div','caa-copy');
  copy.append(
    opsEl('strong','',row.title||'Contexto de campaña'),
    opsEl('p','',row.detail||'La fuente canónica no exige acción humana en este estado.')
  );
  const meta=opsEl('div','caa-meta');
  meta.append(
    opsEl('span','ac-chip low',String(row?.kind||'CAMPAIGN').toUpperCase()),
    opsEl('span','ac-chip',campaignAttentionActionabilityChip(row)),
    opsEl('span','ac-chip','FUERA DE HOY')
  );
  const lineage=row?.actionability?.lineage||{};
  copy.append(
    meta,
    opsEl('div','caa-note',`Fuente: ${String(lineage.source||'UNKNOWN')} · campaña: ${String(lineage.campaign_id||'UNKNOWN')}`),
    opsEl(
      'div',
      'caa-note',
      row?.actionability?.reason||
      'La fuente canónica declaró que este estado no requiere acción; se conserva solo como contexto navegable.'
    )
  );
  const open=opsEl('button','','Ver contexto');
  open.type='button';
  open.addEventListener('click',()=>campaignAttentionActionabilityOpen(row));
  article.append(copy,open);
  return article
}

function campaignAttentionActionabilityRender(){
  if(typeof marketingOpsState==='undefined'||marketingOpsState.view!=='action-center')return;
  const root=document.querySelector('#marketing-ops-view');
  if(!root)return;
  root.querySelector('#post-w99-campaign-attention-observations')?.remove();
  const rows=campaignAttentionActionabilityRows();
  if(!rows.length)return;
  campaignAttentionActionabilityStyles();
  const section=opsEl('section','caa-observations');
  section.id='post-w99-campaign-attention-observations';
  const head=opsEl('div','ac-toolbar-copy');
  head.append(
    opsEl('p','eyebrow','CAMPAÑAS · CONTEXTO NO REQUERIDO'),
    opsEl('h3','','Estados visibles que no son tareas de Hoy'),
    opsEl(
      'p',
      'muted',
      'Estas superficies siguen disponibles para consulta u operación voluntaria, pero Wave64/Wave65 no las marcan como atención requerida y por eso no ocupan la cola.'
    )
  );
  section.append(head);
  const list=opsEl('div','caa-list');
  rows.forEach(row=>list.append(campaignAttentionActionabilityRow(row)));
  section.append(list);
  root.append(section)
}

if(typeof actionCenterRender==='function'){
  const campaignAttentionActionabilityBaseRender=actionCenterRender;
  actionCenterRender=function(){
    campaignAttentionActionabilityBaseRender();
    campaignAttentionActionabilityRender()
  }
}

campaignAttentionActionabilityStyles();
campaignAttentionActionabilityRender();
