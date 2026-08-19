const wave63State={companyId:null,data:null,loading:false,attentionOnly:false};
const wave63BaseRenderPipeline=crmRenderPipeline;

function wave63Company(){return typeof opsSelectedCompany==='function'?opsSelectedCompany():null}
function wave63Styles(){
  if(document.querySelector('#wave63-commercial-pipeline-style'))return;
  const s=document.createElement('style');s.id='wave63-commercial-pipeline-style';s.textContent=`
  .w63-shell{display:grid;gap:10px;margin-top:12px}.w63-head{display:flex;justify-content:space-between;gap:10px;align-items:flex-end}.w63-head-copy{display:grid;gap:3px}.w63-head h3{margin:0}.w63-actions{display:flex;gap:6px;flex-wrap:wrap}.w63-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}.w63-metric{padding:10px;border:1px solid #dfdbd2;border-radius:11px;background:#fff;display:grid;gap:3px}.w63-metric span{font-size:8px;color:#716d65}.w63-metric strong{font-size:18px}.w63-board{display:grid;grid-template-columns:repeat(6,minmax(205px,1fr));gap:8px;overflow-x:auto;padding-bottom:7px}.w63-lane{min-height:260px;padding:9px;border:1px solid #dedad1;border-radius:12px;background:#f6f4ef;display:grid;align-content:start;gap:7px}.w63-lane-head{display:grid;gap:4px;padding-bottom:6px;border-bottom:1px solid #e0ddd5}.w63-lane-title{display:flex;justify-content:space-between;gap:6px;align-items:center}.w63-lane-title strong{font-size:10px;text-transform:uppercase}.w63-money{font-size:8px;color:#716d65;line-height:1.35}.w63-card{padding:9px;border:1px solid #dedad1;border-radius:10px;background:#fff;display:grid;gap:7px}.w63-card.attention{border-left:4px solid #171717}.w63-card.closed{opacity:.72}.w63-card-head{display:flex;justify-content:space-between;gap:7px;align-items:flex-start}.w63-card strong{font-size:10px;line-height:1.35}.w63-card p{margin:0;font-size:8px;color:#716d65;line-height:1.45}.w63-chip{display:inline-flex;align-items:center;padding:3px 6px;border-radius:999px;background:#efede7;font-size:7px;white-space:nowrap}.w63-chip.warn{background:#fff0df}.w63-chip.good{background:#e5f0e6}.w63-stage{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:5px}.w63-stage select,.w63-stage button{font-size:9px}.w63-stage button:disabled{opacity:.45;cursor:not-allowed}.w63-card-actions{display:flex;gap:5px;flex-wrap:wrap}.w63-card-actions button{font-size:8px;padding:5px 7px}.w63-note{padding:8px 10px;border:1px dashed #d3cec4;border-radius:9px;background:#fbfaf7;font-size:8px;color:#716d65}.w63-empty{padding:10px;border:1px dashed #d5d0c7;border-radius:9px;color:#716d65;font-size:8px;background:#fff}.w63-refreshing{opacity:.62}
  @media(max-width:950px){.w63-metrics{grid-template-columns:repeat(2,1fr)}.w63-head{align-items:flex-start;flex-direction:column}}@media(max-width:620px){.w63-metrics{grid-template-columns:1fr}.w63-stage{grid-template-columns:1fr}}
  `;document.head.append(s)
}
function wave63FormatAmounts(groups){
  const rows=Array.isArray(groups)?groups:[];if(!rows.length)return 'Sin valor estimado';
  return rows.map(row=>`${row.currency} ${new Intl.NumberFormat('es-CO',{maximumFractionDigits:0}).format(row.value||0)}${row.valued_opportunities<row.opportunities?' + sin valor':''}`).join(' · ')
}
function wave63Metric(title,value,detail){const n=opsEl('div','w63-metric');n.append(opsEl('span','',title),opsEl('strong','',String(value??0)),opsEl('span','',detail));return n}
async function wave63Load(force=false){
  const company=wave63Company();if(!company){wave63State.companyId=null;wave63State.data=null;return null}
  if(wave63State.loading)return wave63State.data;
  if(!force&&wave63State.companyId===company.id&&wave63State.data)return wave63State.data;
  wave63State.loading=true;
  try{const data=await opsApi(`/api/companies/${encodeURIComponent(company.id)}/commercial-pipeline`);wave63State.companyId=company.id;wave63State.data=data;return data}
  catch(err){opsToast(err.message);return null}
  finally{wave63State.loading=false}
}
function wave63AttentionChip(attention){
  const code=attention?.code||'ON_TRACK';const cls=attention?.requires_attention?'w63-chip warn':code==='CLOSED'?'w63-chip':code==='ON_TRACK'?'w63-chip good':'w63-chip';
  return opsEl('span',cls,attention?.label||code)
}
function wave63Open360(contactId){
  if(!contactId)return;
  if(typeof wave62OpenContact==='function'){wave62OpenContact(contactId);return}
  try{wave62State.selectedContactId=contactId}catch(_err){}opsShowView('contact-360')
}
function wave63OpenFollowups(){crmState.tab='followups';crmRenderCurrent()}
async function wave63SaveStage(row,select,button){
  const company=wave63Company(),target=select.value;if(!company||!target||target===row.stage)return;
  if(['WON','LOST'].includes(target)&&!window.confirm(`¿Confirmas mover “${row.title}” a ${crmStageLabel(target)}?`)){select.value=row.stage;button.disabled=true;return}
  button.disabled=true;
  try{
    await opsApi(`/api/companies/${encodeURIComponent(company.id)}/opportunities/${encodeURIComponent(row.id)}`,{method:'PATCH',body:{stage:target}});
    opsToast(`Etapa guardada: ${crmStageLabel(target)}`);wave63State.data=null;
    await crmRefresh(true);await wave63Load(true);crmRenderCurrent()
  }catch(err){select.value=row.stage;button.disabled=false;opsToast(err.message)}
}
function wave63Card(row){
  const attention=row.attention||{},card=opsEl('article',`w63-card${attention.requires_attention?' attention':''}${row.stage==='WON'||row.stage==='LOST'?' closed':''}`),head=opsEl('div','w63-card-head'),copy=opsEl('div','');
  copy.append(opsEl('strong','',row.title),opsEl('p','',[row.contact?.name,row.contact?.organization].filter(Boolean).join(' · ')||'Sin contacto asociado'));head.append(copy,wave63AttentionChip(attention));card.append(head);
  card.append(opsEl('p','',row.value==null?'Sin valor estimado':crmMoney(row.value,row.currency)));
  if(row.next_action)card.append(opsEl('p','',`Siguiente: ${row.next_action}${row.next_action_at?` · ${opsDate(row.next_action_at)}`:''}`));
  else card.append(opsEl('p','','Sin siguiente acción escrita'));
  const follow=row.followup||{};if(follow.pending_activities||follow.overdue_activities||follow.next_due_at)card.append(opsEl('p','',`${follow.pending_activities||0} seguimiento(s) pendiente(s)${follow.overdue_activities?` · ${follow.overdue_activities} vencido(s)`:''}${follow.next_due_at?` · próximo ${opsDate(follow.next_due_at)}`:''}`));
  const stage=opsEl('div','w63-stage'),select=document.createElement('select');select.setAttribute('aria-label',`Etapa de ${row.title}`);crmStages.forEach(([value,label])=>{const o=opsEl('option','',label);o.value=value;o.selected=value===row.stage;select.append(o)});const save=opsEl('button','primary','Guardar etapa');save.type='button';save.disabled=true;select.addEventListener('change',()=>{save.disabled=select.value===row.stage});save.addEventListener('click',()=>wave63SaveStage(row,select,save));stage.append(select,save);card.append(stage);
  const actions=opsEl('div','w63-card-actions');if(row.contact?.id){const c360=opsEl('button','','Contacto 360');c360.type='button';c360.addEventListener('click',()=>wave63Open360(row.contact.id));actions.append(c360)}if(attention.requires_attention){const followBtn=opsEl('button','','Seguimientos');followBtn.type='button';followBtn.addEventListener('click',wave63OpenFollowups);actions.append(followBtn)}if(actions.children.length)card.append(actions);
  return card
}
function wave63Draw(shell,data){
  shell.replaceChildren();if(!data){shell.append(opsEl('div','w63-empty','No fue posible cargar el pipeline local.'));return}
  const head=opsEl('div','w63-head'),copy=opsEl('div','w63-head-copy');copy.append(opsEl('p','eyebrow','PIPELINE OPERATIVO'),opsEl('h3','','Pipeline comercial operativo'),opsEl('p','muted','Prioriza seguimientos y permite mover etapas de forma explícita. Valores separados por moneda; nunca se suman monedas distintas.'));const actions=opsEl('div','w63-actions');const attention=opsEl('button',wave63State.attentionOnly?'primary':'','Solo requieren atención');attention.type='button';attention.addEventListener('click',()=>{wave63State.attentionOnly=!wave63State.attentionOnly;wave63Draw(shell,data)});const refresh=opsEl('button','','Actualizar local');refresh.type='button';refresh.addEventListener('click',async()=>{shell.classList.add('w63-refreshing');const next=await wave63Load(true);shell.classList.remove('w63-refreshing');wave63Draw(shell,next)});actions.append(attention,refresh);head.append(copy,actions);shell.append(head);
  const summary=data.summary||{},metrics=opsEl('div','w63-metrics');metrics.append(wave63Metric('ABIERTAS',summary.open_opportunities,'oportunidades activas'),wave63Metric('ATENCIÓN',summary.requires_attention,'requieren siguiente paso'),wave63Metric('PROPUESTAS',summary.proposals,'en negociación'),wave63Metric('GANADAS',summary.won,'cierres registrados'));shell.append(metrics);
  shell.append(opsEl('div','w63-note',`Valor abierto por moneda: ${wave63FormatAmounts(summary.amounts_by_currency)}. El board es local; abrirlo no consulta Meta ni ejecuta mensajes.`));
  const board=opsEl('div','w63-board');for(const lane of data.lanes||[]){const col=opsEl('section','w63-lane'),laneHead=opsEl('div','w63-lane-head'),title=opsEl('div','w63-lane-title');const rows=(lane.opportunities||[]).filter(row=>!wave63State.attentionOnly||row.attention?.requires_attention);title.append(opsEl('strong','',lane.label||lane.stage),opsEl('span','marketing-ops-badge',rows.length));laneHead.append(title,opsEl('div','w63-money',wave63FormatAmounts(lane.amounts_by_currency)));col.append(laneHead);for(const row of rows)col.append(wave63Card(row));if(!rows.length)col.append(opsEl('div','w63-empty',wave63State.attentionOnly?'Sin casos que requieran atención.':'Sin oportunidades en esta etapa.'));board.append(col)}shell.append(board)
}
function wave63RenderPipeline(root){
  wave63Styles();wave63BaseRenderPipeline(root);const legacy=root.querySelector('.crm-pipeline');if(legacy)legacy.remove();const shell=opsEl('section','w63-shell');root.append(shell);const company=wave63Company();if(!company){wave63Draw(shell,null);return}if(wave63State.companyId===company.id&&wave63State.data)wave63Draw(shell,wave63State.data);else shell.append(opsEl('div','w63-empty','Preparando pipeline comercial local…'));wave63Load(true).then(data=>{if(shell.isConnected&&wave63Company()?.id===company.id)wave63Draw(shell,data)})
}

crmRenderPipeline=wave63RenderPipeline;
wave63Styles();
if(marketingOpsState?.view==='crm'&&crmState?.tab==='pipeline')crmRenderCurrent();
