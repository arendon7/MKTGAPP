const POST_W99_CAMPAIGN_CREATIVE_CREATION_INTENT_SCHEMA='binario.marketing.campaign-creative-creation-intent.v1';
const postW99CampaignCreativeCreationIntentState={active:null};

function creativeIntentText(value){return value===null||value===undefined?'':String(value).trim()}
function creativeIntentCompany(){return typeof opsSelectedCompany==='function'?opsSelectedCompany():null}
function creativeIntentActionKind(item){return creativeIntentText(item?.kind||item?.post_w99_action_kind).toLowerCase()}
function creativeIntentContract(item){
  const resolution=item?.owner_resolution||{},action=item?.action||{},candidates=Array.isArray(resolution.candidates)?resolution.candidates:[];
  const valid=Boolean(
    item?.id&&creativeIntentActionKind(item)==='create_creative'&&
    creativeIntentText(resolution.state)==='OWNER_ONLY'&&
    creativeIntentText(resolution.source_code).toUpperCase()==='CREATE_CREATIVE'&&
    creativeIntentText(resolution.owner_view)==='content'&&
    !creativeIntentText(resolution.target_kind)&&!creativeIntentText(resolution.target_id)&&
    Number(resolution.candidate_count)===0&&candidates.length===0&&
    creativeIntentText(action.view)==='content'&&creativeIntentText(action.campaign_id)
  );
  if(!valid)return null;
  return{campaignId:creativeIntentText(action.campaign_id),resolution};
}
function creativeIntentForget(){
  postW99CampaignCreativeCreationIntentState.active=null;
  document.querySelector('#post-w99-campaign-creative-creation-intent')?.remove();
  document.querySelectorAll('.creative-intent-highlight').forEach(node=>node.classList.remove('creative-intent-highlight'));
}
function creativeIntentActivate(item,contract){
  const company=creativeIntentCompany();if(!company?.id)return null;
  const active={
    schema:POST_W99_CAMPAIGN_CREATIVE_CREATION_INTENT_SCHEMA,
    company_id:String(company.id),action_id:String(item.id),campaign_id:contract.campaignId,
    title:String(item.title||'Crear o vincular creativo'),source_resolution_state:'OWNER_ONLY',source_code:'CREATE_CREATIVE',
    mode:'CHOICE',media_id:null,imported_media_id:null,selection_source:null,opened_at:new Date().toISOString(),persisted:false,
  };
  postW99CampaignCreativeCreationIntentState.active=active;
  if(typeof wave49CreativeState!=='undefined')wave49CreativeState.tab='pipeline';
  return active
}
function creativeIntentCurrent(){
  const active=postW99CampaignCreativeCreationIntentState.active,company=creativeIntentCompany();
  if(!active)return null;
  if(!company?.id||String(company.id)!==String(active.company_id||'')){creativeIntentForget();return null}
  return active
}
function creativeIntentCampaign(active){
  if(typeof wave49CreativeState==='undefined'||!wave49CreativeState.context)return{state:'LOADING'};
  if(String(wave49CreativeState.companyId||'')!==String(active.company_id||''))return{state:'WRONG_COMPANY'};
  const matches=(wave49CreativeState.context.campaigns||[]).filter(row=>String(row?.id||'')===String(active.campaign_id||''));
  if(matches.length!==1)return{state:'NOT_EXACT',count:matches.length};
  return{state:'EXACT',campaign:matches[0]}
}
function creativeIntentMedia(active){
  if(!active.media_id)return{state:'NONE'};
  if(typeof wave49CreativeState==='undefined'||!wave49CreativeState.context)return{state:'LOADING'};
  const matches=(wave49CreativeState.context.items||[]).filter(row=>String(row?.media?.id||'')===String(active.media_id||''));
  if(matches.length!==1)return{state:'NOT_EXACT',count:matches.length};
  return{state:'EXACT',row:matches[0]}
}
function creativeIntentStyles(){
  if(document.querySelector('#post-w99-campaign-creative-creation-intent-style'))return;
  const style=document.createElement('style');style.id='post-w99-campaign-creative-creation-intent-style';style.textContent=`
  .creative-intent-card{border:1px solid #d7d1c8;border-radius:14px;background:#fff;padding:13px;display:grid;gap:9px;margin:0 0 12px}.creative-intent-head{display:grid;gap:4px}.creative-intent-head h3{margin:0;font-size:15px}.creative-intent-head p{margin:0;font-size:8px;color:#716b63;line-height:1.5}.creative-intent-actions{display:flex;gap:7px;flex-wrap:wrap}.creative-intent-note{padding:9px 10px;border-radius:9px;background:#f5f2eb;color:#6f695f;font-size:8px;line-height:1.5}.creative-intent-meta{display:flex;gap:5px;flex-wrap:wrap}.creative-intent-chip{display:inline-flex;padding:3px 6px;border-radius:999px;background:#efebe4;font-size:7px;color:#625c53}.creative-intent-id{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;word-break:break-all}.creative-intent-highlight{outline:2px solid #171717!important;outline-offset:3px}.creative-intent-success{background:#eef4ee}.creative-intent-error{background:#f7f2ec}
  `;document.head.append(style)
}
function creativeIntentCampaignName(campaign){return creativeIntentText(campaign?.name)||'Campaña'}
function creativeIntentRoot(){return document.querySelector('#marketing-ops-view')}
function creativeIntentClearHighlights(){document.querySelectorAll('.creative-intent-highlight').forEach(node=>node.classList.remove('creative-intent-highlight'))}
function creativeIntentButton(label,handler,primary=false){const button=opsEl('button',primary?'primary':'',label);button.type='button';button.addEventListener('click',handler);return button}
function creativeIntentSetMode(mode){
  const active=creativeIntentCurrent();if(!active)return;
  active.mode=mode;active.media_id=null;active.imported_media_id=null;active.selection_source=null;
  if(typeof wave49CreativeState!=='undefined')wave49CreativeState.tab=mode==='IMPORT'?'library':'pipeline';
  if(typeof contentRenderCurrent==='function')contentRenderCurrent();else creativeIntentSchedule()
}
function creativeIntentChooseExistingMedia(mediaId){
  const active=creativeIntentCurrent(),id=creativeIntentText(mediaId);if(!active||active.mode!=='EXISTING'||!id)return;
  active.mode='MEDIA';active.media_id=id;active.selection_source='EXISTING_ITEM_HUMAN_CLICK';active.selected_at=new Date().toISOString();
  creativeIntentSchedule()
}
function creativeIntentContinueImported(){
  const active=creativeIntentCurrent(),id=creativeIntentText(active?.imported_media_id);if(!active||active.mode!=='IMPORT'||!id)return;
  if(typeof wave49CreativeState==='undefined')return;
  active.mode='MEDIA';active.media_id=id;active.selection_source='IMPORTED_MEDIA_HUMAN_CONTINUE';active.selected_at=new Date().toISOString();
  wave49CreativeState.tab='pipeline';wave49CreativeState.selectedId=id;wave49CreativeState.context=null;
  if(typeof contentRenderCurrent==='function')contentRenderCurrent()
}
function creativeIntentForm(active,campaign,media){
  if(String(wave49CreativeState?.selectedId||'')!==String(active.media_id||''))return{state:'WRONG_MEDIA'};
  const forms=[...document.querySelectorAll('#marketing-ops-view form.w49-form')];if(forms.length!==1)return{state:'FORM_NOT_EXACT',count:forms.length};
  const form=forms[0],selects=[...form.querySelectorAll('select')].filter(select=>[...select.options].filter(option=>String(option.value||'')===String(active.campaign_id||'')).length===1);
  if(selects.length!==1)return{state:'CAMPAIGN_SELECT_NOT_EXACT',count:selects.length,form};
  const submits=[...form.querySelectorAll('button[type="submit"]')];if(submits.length!==1)return{state:'SUBMIT_NOT_EXACT',count:submits.length,form,select:selects[0]};
  const select=selects[0],submit=submits[0],linked=String(media?.creative?.campaign_id||'')===String(active.campaign_id||''),selected=String(select.value||'')===String(active.campaign_id||'');
  if(!select.dataset.postW99CreationIntentObserved){select.dataset.postW99CreationIntentObserved='1';select.addEventListener('change',creativeIntentSchedule)}
  return{state:'EXACT',form,select,submit,linked,selected,campaign}
}
function creativeIntentCardBase(active,campaign){
  const card=opsEl('section','creative-intent-card');card.id='post-w99-campaign-creative-creation-intent';
  const head=opsEl('div','creative-intent-head');head.append(opsEl('p','eyebrow','CAMPAÑA · INTENCIÓN DE CREACIÓN'),opsEl('h3','',active.title),opsEl('p','',`Campaña objetivo: ${creativeIntentCampaignName(campaign)}. Esta guía conserva contexto, pero no selecciona piezas, no cambia el selector de campaña y no guarda por ti.`));
  const meta=opsEl('div','creative-intent-meta');meta.append(opsEl('span','creative-intent-chip','OWNER_ONLY'),opsEl('span','creative-intent-chip','CREATE_CREATIVE'),opsEl('span','creative-intent-chip creative-intent-id',active.campaign_id));
  card.append(head,meta);return card
}
function creativeIntentRenderChoice(card,active){
  const note=opsEl('div','creative-intent-note','Elige cómo continuar. W49 puede reutilizar una pieza existente o importar una nueva. Ninguna pieza actualmente seleccionada por defecto se considera una elección humana.');
  const actions=opsEl('div','creative-intent-actions');actions.append(creativeIntentButton('Vincular pieza existente',()=>creativeIntentSetMode('EXISTING'),true),creativeIntentButton('Importar archivo',()=>creativeIntentSetMode('IMPORT')),creativeIntentButton('Cerrar guía',creativeIntentForget));
  card.append(note,actions)
}
function creativeIntentRenderExisting(card,active){
  const lists=[...document.querySelectorAll('#marketing-ops-view .w49-list')];
  const note=opsEl('div','creative-intent-note',lists.length===1?'Haz click en una pieza concreta del pipeline. Solo ese click humano fijará el media_id para esta intención.':'Pipeline no disponible de forma inequívoca; no se elegirá una pieza alternativa.');
  if(lists.length===1)lists[0].classList.add('creative-intent-highlight');
  const actions=opsEl('div','creative-intent-actions');actions.append(creativeIntentButton('Importar en su lugar',()=>creativeIntentSetMode('IMPORT')),creativeIntentButton('Cancelar intención',creativeIntentForget));
  card.append(note,actions)
}
function creativeIntentRenderImport(card,active){
  const actions=opsEl('div','creative-intent-actions');
  if(active.imported_media_id){
    const note=opsEl('div','creative-intent-note creative-intent-success',`El upload humano devolvió el media_id exacto ${active.imported_media_id}. Continuar no guarda campaña: solo abre ese medio exacto en W49 para que elijas la campaña y envíes el formulario.`);card.append(note);actions.append(creativeIntentButton('Continuar con este archivo',creativeIntentContinueImported,true))
  }else{
    const forms=[...document.querySelectorAll('#marketing-ops-view form.company-content-upload')];
    const note=opsEl('div','creative-intent-note',forms.length===1?'Usa el formulario canónico de Biblioteca. El handoff observará únicamente el ID exacto que devuelva ese submit humano.':'Formulario de importación no disponible de forma inequívoca; no se ejecutará un upload alternativo.');card.append(note);if(forms.length===1)forms[0].classList.add('creative-intent-highlight')
  }
  actions.append(creativeIntentButton('Vincular existente',()=>creativeIntentSetMode('EXISTING')),creativeIntentButton('Cancelar intención',creativeIntentForget));card.append(actions)
}
function creativeIntentRenderMedia(card,active,campaign,media){
  const info=creativeIntentForm(active,campaign,media.row);
  if(info.state!=='EXACT'){
    card.append(opsEl('div','creative-intent-note creative-intent-error',`No se puede demostrar un único formulario W49 para el media_id ${active.media_id}. Estado: ${info.state}. No se cambia ningún valor.`));
  }else if(info.linked){
    card.append(opsEl('div','creative-intent-note creative-intent-success',`La pieza exacta ya declara campaign_id=${active.campaign_id}. No se fuerza refresh ni se marca la acción como completada; vuelve al plan para releer Action Center.`));
  }else{
    info.select.classList.add('creative-intent-highlight');
    if(info.selected)info.submit.classList.add('creative-intent-highlight');
    card.append(opsEl('div','creative-intent-note',info.selected?`La campaña ${creativeIntentCampaignName(campaign)} ya está seleccionada por el usuario. El único siguiente cambio permitido es el submit humano “Guardar ficha creativa”.`:`Selecciona manualmente ${creativeIntentCampaignName(campaign)} en el selector resaltado. El handoff no asigna select.value. Después podrás guardar la ficha de forma explícita.`));
  }
  const meta=opsEl('div','creative-intent-meta');meta.append(opsEl('span','creative-intent-chip creative-intent-id',active.media_id),opsEl('span','creative-intent-chip',active.selection_source||'HUMAN_SELECTION'));card.append(meta);
  const actions=opsEl('div','creative-intent-actions');actions.append(creativeIntentButton('Elegir otra vía',()=>creativeIntentSetMode('CHOICE')),creativeIntentButton('Cerrar guía',creativeIntentForget));card.append(actions)
}
function creativeIntentDecorate(){
  creativeIntentStyles();creativeIntentClearHighlights();document.querySelector('#post-w99-campaign-creative-creation-intent')?.remove();
  const active=creativeIntentCurrent();if(!active||typeof marketingOpsState==='undefined'||marketingOpsState.view!=='content')return;
  const root=creativeIntentRoot();if(!root)return;
  const campaignInfo=creativeIntentCampaign(active);
  if(campaignInfo.state==='LOADING'){const card=creativeIntentCardBase(active,null);card.append(opsEl('div','creative-intent-note','Validando campaign_id en el contexto local de W49…'));root.prepend(card);return}
  if(campaignInfo.state!=='EXACT'){const card=creativeIntentCardBase(active,null);card.append(opsEl('div','creative-intent-note creative-intent-error','La campaña objetivo ya no aparece exactamente una vez en W49. La guía queda bloqueada; vuelve a abrir la acción desde el estado actual.'));card.append(creativeIntentButton('Cerrar guía',creativeIntentForget));root.prepend(card);return}
  const campaign=campaignInfo.campaign,card=creativeIntentCardBase(active,campaign);
  if(active.mode==='CHOICE')creativeIntentRenderChoice(card,active);
  else if(active.mode==='EXISTING')creativeIntentRenderExisting(card,active);
  else if(active.mode==='IMPORT')creativeIntentRenderImport(card,active);
  else if(active.mode==='MEDIA'){
    const media=creativeIntentMedia(active);
    if(media.state==='LOADING')card.append(opsEl('div','creative-intent-note','Cargando el media_id exacto mediante el pipeline canónico de W49…'));
    else if(media.state!=='EXACT')card.append(opsEl('div','creative-intent-note creative-intent-error','El media_id elegido ya no aparece exactamente una vez en W49. No se selecciona un sustituto.'));
    else creativeIntentRenderMedia(card,active,campaign,media)
  }
  const tabs=root.querySelector('.w49-tabs');if(tabs)tabs.insertAdjacentElement('afterend',card);else root.prepend(card)
}
function creativeIntentSchedule(){queueMicrotask(creativeIntentDecorate)}

const creativeIntentBaseOpen=globalThis.actionCenterOpen;
if(typeof creativeIntentBaseOpen==='function')globalThis.actionCenterOpen=function(item){
  const contract=creativeIntentContract(item);
  if(contract)creativeIntentActivate(item,contract);
  else if(item?.id&&postW99CampaignCreativeCreationIntentState.active&&String(item.id)!==String(postW99CampaignCreativeCreationIntentState.active.action_id))creativeIntentForget();
  const value=creativeIntentBaseOpen.apply(this,arguments);creativeIntentSchedule();return value
};

const creativeIntentBaseItemCard=globalThis.wave49ItemCard;
if(typeof creativeIntentBaseItemCard==='function')globalThis.wave49ItemCard=function(row){
  const node=creativeIntentBaseItemCard.apply(this,arguments),mediaId=creativeIntentText(row?.media?.id);
  if(mediaId)node.addEventListener('click',()=>creativeIntentChooseExistingMedia(mediaId));
  return node
};

const creativeIntentBaseUpload=globalThis.contentUpload;
if(typeof creativeIntentBaseUpload==='function')globalThis.contentUpload=async function(){
  const result=await creativeIntentBaseUpload.apply(this,arguments),active=creativeIntentCurrent(),id=creativeIntentText(result?.id);
  if(active&&active.mode==='IMPORT'&&id){active.imported_media_id=id;active.imported_at=new Date().toISOString();active.import_source='CANONICAL_UPLOAD_RETURN'}
  return result
};

const creativeIntentBaseContentRender=globalThis.contentRenderCurrent;
if(typeof creativeIntentBaseContentRender==='function')globalThis.contentRenderCurrent=function(){const value=creativeIntentBaseContentRender.apply(this,arguments);creativeIntentSchedule();return value};
const creativeIntentBasePipelineRender=globalThis.wave49RenderPipeline;
if(typeof creativeIntentBasePipelineRender==='function')globalThis.wave49RenderPipeline=async function(){const value=await creativeIntentBasePipelineRender.apply(this,arguments);creativeIntentDecorate();return value};

window.addEventListener('marketing-ops-refreshed',()=>{creativeIntentCurrent();creativeIntentSchedule()});
window.addEventListener('pageshow',creativeIntentSchedule);window.addEventListener('pagehide',creativeIntentForget);
creativeIntentStyles();creativeIntentSchedule();
