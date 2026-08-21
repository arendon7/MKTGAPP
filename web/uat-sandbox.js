const wave75SandboxState={data:null,loading:false,mutating:false};

function wave75Styles(){
  if(document.querySelector('#wave75-uat-sandbox-style'))return;
  const style=document.createElement('style');style.id='wave75-uat-sandbox-style';style.textContent=`
  .w75-sandbox{margin-top:12px;padding:14px;border:1px solid #d7d2c8;border-radius:13px;background:#fff;display:grid;gap:10px}.w75-head{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}.w75-head h3{margin:0}.w75-warning{padding:10px;border-radius:10px;background:#fff0df;font-size:9px;line-height:1.5}.w75-ok{padding:10px;border-radius:10px;background:#e8f1e8;font-size:9px;line-height:1.5}.w75-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px}.w75-cell{padding:9px;border:1px solid #e4e0d7;border-radius:9px;display:grid;gap:3px}.w75-cell strong{font-size:10px}.w75-cell span{font-size:8px;color:#706c65}.w75-actions{display:flex;gap:7px;flex-wrap:wrap}.w75-contract{font-size:8px;color:#706c65;line-height:1.5}.w75-badge{display:inline-flex;padding:4px 7px;border-radius:999px;background:#171717;color:#fff;font-size:8px;white-space:nowrap}@media(max-width:760px){.w75-head{display:grid}.w75-grid{grid-template-columns:1fr}}
  `;document.head.append(style)
}

async function wave75Load(force=false){
  if(wave75SandboxState.loading)return wave75SandboxState.data;
  if(!force&&wave75SandboxState.data)return wave75SandboxState.data;
  wave75SandboxState.loading=true;
  try{wave75SandboxState.data=await opsApi('/api/uat-sandbox');return wave75SandboxState.data}
  catch(err){opsToast(err.message);return null}
  finally{wave75SandboxState.loading=false}
}

function wave75SelectedCompanyId(){return String(marketingOpsState?.selectedCompanyId||'')}

async function wave75OpenSandbox(){
  const data=wave75SandboxState.data,company=data?.company;if(!company?.id)return;
  marketingOpsState.selectedCompanyId=company.id;
  try{localStorage.setItem('marketingOpsCompany',company.id)}catch(_err){}
  if(typeof fillCompanyFilter==='function')fillCompanyFilter();
  window.dispatchEvent(new CustomEvent('marketing-company-change',{detail:{companyId:company.id,source:'uat-sandbox'}}));
  if(typeof refreshMarketingOps==='function')await refreshMarketingOps(false);
  opsShowView('uat-readiness')
}

async function wave75Create(reset=false){
  if(wave75SandboxState.mutating)return;
  const copy=reset?'Se desactivará únicamente el sandbox UAT registrado y se creará una generación nueva. Los datos reales no se tocarán. ¿Continuar?':'Se creará una empresa aislada con datos sintéticos locales. No se consultará Meta, no se generarán resultados y este sandbox no podrá certificar UAT física. ¿Continuar?';
  if(!window.confirm(copy))return;
  wave75SandboxState.mutating=true;wave75RenderPanel();
  try{
    wave75SandboxState.data=await opsApi(reset?'/api/uat-sandbox/reset':'/api/uat-sandbox',{method:'POST',body:reset?{confirm:true}:{}});
    opsToast(reset?'Sandbox UAT recreado':'Sandbox UAT creado');wave75RenderPanel()
  }catch(err){opsToast(err.message)}
  finally{wave75SandboxState.mutating=false;wave75RenderPanel()}
}

function wave75Cell(title,value,copy){const node=opsEl('div','w75-cell');node.append(opsEl('strong','',value),opsEl('span','',title),opsEl('span','',copy));return node}

function wave75RenderPanel(){
  if(marketingOpsState?.view!=='uat-readiness')return;wave75Styles();const root=document.querySelector('#marketing-ops-view');if(!root)return;
  root.querySelector('.w75-sandbox')?.remove();const panel=opsEl('section','w75-sandbox');
  const head=opsEl('div','w75-head'),copy=opsEl('div','');copy.append(opsEl('p','eyebrow','CONTROLLED FUNCTIONAL UAT · W75'),opsEl('h3','','Sandbox UAT controlado'),opsEl('p','muted','Crea un caso repetible para recorrer Leads, CRM, Pipeline y Campañas sin contaminar empresas reales ni fabricar evidencia de providers.'));head.append(copy,opsEl('span','w75-badge','SINTÉTICO · NO RELEASE'));panel.append(head);
  const data=wave75SandboxState.data;
  if(!data&&!wave75SandboxState.loading){panel.append(opsEl('div','w75-warning','Consultando únicamente el manifiesto local del sandbox…'));root.append(panel);wave75Load().then(wave75RenderPanel);return}
  if(wave75SandboxState.loading&&!data){panel.append(opsEl('div','w75-warning','Cargando estado local…'));root.append(panel);return}
  if(!data?.exists){
    panel.append(opsEl('div','w75-warning','No existe sandbox. Crearlo es una acción explícita: genera solo datos locales .invalid y nunca registra evidencia física de release.'));
    const actions=opsEl('div','w75-actions'),create=opsEl('button','primary',wave75SandboxState.mutating?'Creando…':'Crear sandbox UAT');create.type='button';create.disabled=wave75SandboxState.mutating;create.addEventListener('click',()=>wave75Create(false));actions.append(create);panel.append(actions);root.append(panel);return
  }
  const selected=wave75SelectedCompanyId()===data.company?.id;
  panel.append(opsEl('div',selected?'w75-warning':'w75-ok',selected?'Estás operando sobre datos sintéticos. La ruta de UAT física está bloqueada por backend para esta empresa y nunca puede quitar el blocker physical_uat_missing.':`Generación ${data.generation} disponible y aislada. Ábrela solo cuando quieras recorrer el flujo funcional.`));
  const grid=opsEl('div','w75-grid');grid.append(
    wave75Cell('EMPRESA',data.company?.name||'—',data.active?'Activa y aislada':'Inactiva'),
    wave75Cell('FIXTURE',data.functional_ready?'Completo':'Incompleto',`${Object.values(data.entity_checks||{}).filter(Boolean).length}/${Object.keys(data.entity_checks||{}).length} entidades verificadas`),
    wave75Cell('RELEASE','Prohibido','Sin evidencia provider, sin métricas sembradas, sin UAT física')
  );panel.append(grid);
  const actions=opsEl('div','w75-actions'),open=opsEl('button','primary','Abrir sandbox'),reset=opsEl('button','',wave75SandboxState.mutating?'Recreando…':'Recrear sandbox'),refresh=opsEl('button','','Actualizar estado');open.type=reset.type=refresh.type='button';open.disabled=!data.active;reset.disabled=wave75SandboxState.mutating;open.addEventListener('click',wave75OpenSandbox);reset.addEventListener('click',()=>wave75Create(true));refresh.addEventListener('click',async()=>{await wave75Load(true);wave75RenderPanel()});actions.append(open,reset,refresh);panel.append(actions);
  panel.append(opsEl('div','w75-contract','Fixture: contacto sintético + lead con coincidencia exacta + lead nuevo + oportunidad COP + seguimiento + campaña LEADS. No crea publicaciones, pauta, resultados, atribución, IA ni llamadas a providers. Reset solo desactiva el sandbox previamente registrado; nunca borra ni modifica una empresa real.'));
  root.append(panel)
}

const wave75BaseRender=globalThis.renderMarketingOps;
if(typeof wave75BaseRender==='function')globalThis.renderMarketingOps=function(){const result=wave75BaseRender();queueMicrotask(wave75RenderPanel);return result};
window.addEventListener('marketing-company-change',()=>{if(marketingOpsState?.view==='uat-readiness')wave75RenderPanel()});
wave75RenderPanel();
