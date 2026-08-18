const wave49State={summary:null,loading:false,busy:new Set(),preferredPaidMediaId:null};

function wave49Styles(){
  if(document.querySelector('#wave49-creative-studio-style'))return;
  const style=document.createElement('style');style.id='wave49-creative-studio-style';style.textContent=`
  .wave49-shell{display:grid;gap:12px}.wave49-hero{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(300px,.65fr);gap:12px}.wave49-card{padding:15px;border:1px solid #dedbd2;border-radius:13px;background:#fff;display:grid;gap:10px}.wave49-actions{display:flex;gap:7px;flex-wrap:wrap}.wave49-actions button{min-height:34px}.wave49-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:7px}.wave49-metrics>div{padding:9px;border:1px solid #e5e1d9;border-radius:9px;display:grid;gap:2px}.wave49-metrics strong{font-size:17px}.wave49-metrics span{font-size:8px;color:#706c65}.wave49-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:12px}.wave49-list{display:grid;gap:8px}.wave49-source{padding:10px;border:1px solid #e3dfd7;border-radius:10px;display:grid;gap:7px;background:#fff}.wave49-source-head{display:flex;justify-content:space-between;gap:8px;align-items:start}.wave49-source strong{font-size:10px}.wave49-meta{font-size:8px;color:#706c65}.wave49-chip{font-size:8px;padding:4px 6px;border-radius:999px;background:#efede7;white-space:nowrap}.wave49-chip.good{background:#e5f0e6}.wave49-chip.warn{background:#f8e8d2}.wave49-library{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.wave49-media{border:1px solid #dedbd2;border-radius:10px;padding:8px;background:#fff;display:grid;gap:6px;min-width:0}.wave49-media-preview{width:100%;aspect-ratio:1.25;border-radius:7px;background:#efede8;overflow:hidden;display:grid;place-items:center}.wave49-media-preview img,.wave49-media-preview video{width:100%;height:100%;object-fit:cover}.wave49-media-preview span{font-size:10px;color:#706c65}.wave49-media strong{font-size:9px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.wave49-media select{min-width:0;width:100%;font-size:9px}.wave49-promoted{padding:8px 10px;border-radius:9px;background:#eef5ef;font-size:9px}.wave49-lineage{font-size:8px;color:#706c65;word-break:break-all}.wave49-empty{padding:13px;border:1px dashed #ccc6ba;border-radius:10px;color:#706c65;font-size:9px}.wave49-safety{padding:10px;border:1px solid #d9d5cc;border-radius:10px;background:#f5f2eb;font-size:9px;color:#625f58}
  @media(max-width:1000px){.wave49-hero,.wave49-grid{grid-template-columns:1fr}.wave49-library{grid-template-columns:1fr 1fr}}@media(max-width:650px){.wave49-metrics{grid-template-columns:1fr 1fr}.wave49-library{grid-template-columns:1fr}}
  `;document.head.append(style)
}

function wave49El(tag,className='',text=''){return opsEl(tag,className,text)}
function wave49Status(status){return status==='PASS'?'good':status==='FAIL'?'warn':''}

async function wave49LoadSummary(force=false){
  const company=wave47Company();if(!company)return null;
  if(wave49State.summary&&!force&&wave49State.summary.company_id===company.id)return wave49State.summary;
  wave49State.summary=await opsApi(`/api/companies/${encodeURIComponent(company.id)}/creative-studio`);return wave49State.summary
}

async function wave49Promote(sourceType,sourceId,button){
  const company=wave47Company();if(!company||wave49State.busy.has(`${sourceType}:${sourceId}`))return;
  wave49State.busy.add(`${sourceType}:${sourceId}`);if(button)button.disabled=true;
  try{const result=await opsApi(`/api/companies/${encodeURIComponent(company.id)}/creative-studio/promote`,{method:'POST',body:{source_type:sourceType,source_id:sourceId}});opsToast(result.reused?'Asset ya estaba disponible en biblioteca':'Guardado en biblioteca de la empresa');wave49State.summary=null;renderMarketingOps()}catch(err){opsToast(err.message)}finally{wave49State.busy.delete(`${sourceType}:${sourceId}`);if(button)button.disabled=false}
}

async function wave49AttachCampaign(mediaId,campaignId,button){
  const company=wave47Company();if(!company||!campaignId)return;
  const key=`campaign:${mediaId}:${campaignId}`;if(wave49State.busy.has(key))return;wave49State.busy.add(key);if(button)button.disabled=true;
  try{const result=await opsApi(`/api/companies/${encodeURIComponent(company.id)}/creative-studio/media/${encodeURIComponent(mediaId)}/campaigns/${encodeURIComponent(campaignId)}`,{method:'POST',body:{}});opsToast(result.changed?'Asset vinculado a la campaña':'El asset ya estaba vinculado a esa campaña');wave49State.summary=null;renderMarketingOps()}catch(err){opsToast(err.message)}finally{wave49State.busy.delete(key);if(button)button.disabled=false}
}

function wave49UseInPauta(mediaId){
  wave49State.preferredPaidMediaId=mediaId;try{localStorage.setItem('binarioPreferredPaidMedia',mediaId)}catch(_err){}opsShowView('pauta')
}

if(typeof wave48LoadContext==='function'){
  const wave49BasePaidContext=wave48LoadContext;
  wave48LoadContext=async function(force=false){
    const context=await wave49BasePaidContext(force);let preferred=wave49State.preferredPaidMediaId;try{preferred=preferred||localStorage.getItem('binarioPreferredPaidMedia')||null}catch(_err){}
    if(context&&preferred&&Array.isArray(context.images)){
      const index=context.images.findIndex(row=>row.id===preferred);if(index>0){const images=[...context.images];const [item]=images.splice(index,1);images.unshift(item);context.images=images}
      if(index>=0){wave49State.preferredPaidMediaId=null;try{localStorage.removeItem('binarioPreferredPaidMedia')}catch(_err){}}
    }
    return context
  }
}

function wave49WorkspaceHero(company,summary){
  const hero=wave49El('div','wave49-hero'),main=wave49El('section','wave49-card'),side=wave49El('section','wave49-card');main.append(wave49El('p','eyebrow','CREATIVE STUDIO'),wave49El('h3','',`Studio · ${company.name}`),wave49El('p','muted','Crea, edita y finaliza piezas dentro del workspace de la empresa. Cuando una pieza está lista, promuévela una vez a la biblioteca y úsala en todo el sistema.'));const actions=wave49El('div','wave49-actions');const open=wave49El('button','primary','Abrir editor completo');open.type='button';open.addEventListener('click',()=>wave47OpenStudio(false));const upload=wave49El('button','','Cargar video / media');upload.type='button';upload.addEventListener('click',()=>wave47OpenStudio(true));const content=wave49El('button','','Abrir biblioteca');content.type='button';content.addEventListener('click',()=>opsShowLegacy());actions.append(open,upload,content);main.append(actions,wave49El('div','wave49-safety','Los motores siguen siendo los certificados: ProjectStore + FFmpeg + Whisper. Wave 49 no duplica edición ni render; consolida outputs y provenance.'));
  const metrics=wave49El('div','wave49-metrics');[['Assets',summary.assets.length],['Renders',summary.renders.length],['Biblioteca',summary.library.length],['Promociones',summary.bridge_count]].forEach(([label,value])=>{const box=wave49El('div');box.append(wave49El('strong','',String(value)),wave49El('span','',label));metrics.append(box)});side.append(wave49El('p','eyebrow','WORKSPACE'),wave49El('h3','',summary.workspace?'Conectado a la empresa':'Aún no creado'),wave49El('p','muted',summary.workspace?`Project ${summary.workspace.project_id}`:'Se crea al abrir Creative Studio por primera vez.'),metrics);hero.append(main,side);return hero
}

function wave49SourceRow(row,sourceType){
  const card=wave49El('article','wave49-source'),head=wave49El('div','wave49-source-head'),copy=wave49El('div');copy.append(wave49El('strong','',sourceType==='render'?row.output_name:row.name),wave49El('div','wave49-meta',sourceType==='render'?`${row.width}×${row.height} · ${row.duration?.toFixed?.(2)||row.duration||'—'} s`:`${row.kind} · ${row.bytes?new Intl.NumberFormat('es-CO').format(row.bytes):'—'} bytes`));const chip=row.promoted?wave49El('span','wave49-chip good','En biblioteca'):wave49El('span',`wave49-chip ${wave49Status(row.status)}`,sourceType==='render'?row.status:'Studio');head.append(copy,chip);card.append(head);if(row.promoted)card.append(wave49El('div','wave49-lineage',`→ ${row.promoted.company_media_id} · SHA ${row.promoted.source_sha256.slice(0,12)}…`));const actions=wave49El('div','wave49-actions');if(!row.promoted&&row.promotable){const promote=wave49El('button','primary','Guardar en biblioteca');promote.type='button';promote.addEventListener('click',()=>wave49Promote(sourceType,row.id,promote));actions.append(promote)}if(sourceType==='render'&&row.status!=='PASS')actions.append(wave49El('span','wave49-meta','Solo los renders PASS pueden convertirse en asset reutilizable.'));if(actions.childElementCount)card.append(actions);return card
}

function wave49LibraryCard(media,campaigns){
  const card=wave49El('article','wave49-media'),preview=wave49El('div','wave49-media-preview');if(media.kind==='image'){const img=document.createElement('img');img.src=media.file_url;img.alt=media.original_name;img.loading='lazy';preview.append(img)}else if(media.kind==='video'){const video=document.createElement('video');video.src=media.file_url;video.muted=true;video.preload='metadata';video.playsInline=true;preview.append(video)}else preview.append(wave49El('span','','Media'));card.append(preview,wave49El('strong','',media.original_name),wave49El('div','wave49-meta',`${media.kind}${media.width&&media.height?` · ${media.width}×${media.height}`:''}${media.duration!==null&&media.duration!==undefined?` · ${Number(media.duration).toFixed(1)} s`:''}`));
  const select=document.createElement('select'),placeholder=wave49El('option','','Vincular a campaña…');placeholder.value='';select.append(placeholder);for(const campaign of campaigns){const option=wave49El('option','',`${campaign.name} · ${campaign.status}${campaign.media_ids.includes(media.id)?' ✓':''}`);option.value=campaign.id;select.append(option)}card.append(select);const actions=wave49El('div','wave49-actions');const attach=wave49El('button','','Usar en campaña');attach.type='button';attach.disabled=!campaigns.length;attach.addEventListener('click',()=>{if(!select.value){opsToast('Selecciona una campaña');return}wave49AttachCampaign(media.id,select.value,attach)});actions.append(attach);if(media.kind==='image'){const paid=wave49El('button','primary','Usar en Pauta');paid.type='button';paid.addEventListener('click',()=>wave49UseInPauta(media.id));actions.append(paid)}const publish=wave49El('button','','Abrir Publicar');publish.type='button';publish.addEventListener('click',()=>opsShowView('publish'));actions.append(publish);card.append(actions);return card
}

renderWave47Video=async function(root){
  const company=wave47Company();const shell=wave49El('div','wave49-shell');root.append(shell);if(!company){shell.append(wave49El('section','wave49-card','Selecciona o crea una empresa primero.'));return}let summary;try{summary=await wave49LoadSummary(true)}catch(err){shell.append(wave49El('div','wave49-empty',err.message));return}shell.append(wave49WorkspaceHero(company,summary));
  const grid=wave49El('div','wave49-grid'),renders=wave49El('section','wave49-card'),assets=wave49El('section','wave49-card');renders.append(wave49El('p','eyebrow','OUTPUTS'),wave49El('h3','','Renders terminados'),wave49El('p','muted','Solo PASS + SHA verificado pueden pasar a biblioteca.'));const renderList=wave49El('div','wave49-list');for(const row of [...summary.renders].reverse().slice(0,12))renderList.append(wave49SourceRow(row,'render'));if(!summary.renders.length)renderList.append(wave49El('div','wave49-empty','Todavía no hay renders. Abre el editor y crea la primera pieza.'));renders.append(renderList);assets.append(wave49El('p','eyebrow','FUENTES'),wave49El('h3','','Assets del Studio'),wave49El('p','muted','Promueve imágenes o videos de trabajo que quieras reutilizar fuera del editor.'));const assetList=wave49El('div','wave49-list');for(const row of [...summary.assets].reverse().slice(0,12))assetList.append(wave49SourceRow(row,'project_asset'));if(!summary.assets.length)assetList.append(wave49El('div','wave49-empty','El workspace aún no tiene assets.'));assets.append(assetList);grid.append(renders,assets);shell.append(grid);
  const library=wave49El('section','wave49-card');library.append(wave49El('p','eyebrow','BIBLIOTECA DE EMPRESA'),wave49El('h3','','Una salida, múltiples usos'),wave49El('p','muted','Los assets de esta biblioteca son reutilizables por Campañas y Pauta; no necesitas exportar y volver a subir.'));const mediaGrid=wave49El('div','wave49-library');for(const media of summary.library)mediaGrid.append(wave49LibraryCard(media,summary.campaigns));if(!summary.library.length)mediaGrid.append(wave49El('div','wave49-empty','Promueve un render o asset para construir la biblioteca reusable de esta empresa.'));library.append(mediaGrid);shell.append(library)
};

wave49Styles();if(marketingOpsState.view==='video')renderMarketingOps();
