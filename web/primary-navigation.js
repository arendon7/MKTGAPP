const POST_W99_PRIMARY_NAVIGATION=[
  ['today-execution','Hoy'],
  ['companies','Empresas'],
  ['content','Contenido'],
  ['calendar','Calendario'],
  ['crm','CRM'],
  ['inbox','Inbox'],
  ['intelligence','Resultados'],
];
const POST_W99_SECONDARY_NAVIGATION=[
  ['executive-cockpit','Cockpit'],
  ['action-center','Action Center'],
  ['campaigns','Campañas'],
  ['pauta','Pauta'],
  ['publish','Publicar'],
  ['video','Video Studio'],
  ['audiences','Audiencias'],
  ['analytics','Analítica'],
];
const POST_W99_SECONDARY_VIEWS=new Set(POST_W99_SECONDARY_NAVIGATION.map(([view])=>view));

function primaryNavigationStyles(){
  if(document.querySelector('#post-w99-primary-navigation-style'))return;
  const style=document.createElement('style');
  style.id='post-w99-primary-navigation-style';
  style.textContent=`
    .marketing-ops-nav[data-post-w99-primary-navigation="1"]{display:flex;align-items:center;gap:5px;overflow:auto;padding-bottom:2px}
    .marketing-ops-nav[data-post-w99-primary-navigation="1"]>button{white-space:nowrap}
    .post-w99-more{min-width:94px;border:1px solid #d9d4ca;background:#fff;border-radius:9px;padding:7px 26px 7px 9px;font:inherit;font-size:9px;color:#5e5a53;cursor:pointer}
    .post-w99-more.active{background:#171717;color:#fff;border-color:#171717}
    .post-w99-astra{margin-left:auto!important;background:#171717!important;color:#fff!important;border-color:#171717!important;white-space:nowrap}
    @media(max-width:800px){.post-w99-astra{margin-left:0!important}}
  `;
  document.head.append(style);
}

function primaryNavigationGo(view){
  if(view==='content'){
    if(typeof opsShowLegacy==='function')opsShowLegacy();
    return;
  }
  if(typeof opsShowView==='function')opsShowView(view);
}

function primaryNavigationOpenAstra(){
  const reveal=()=>{
    const panel=document.querySelector('.w51-ai');
    if(panel){panel.scrollIntoView({block:'start',behavior:'smooth'});return true}
    return false;
  };
  if(marketingOpsState?.view==='home'&&reveal())return;
  if(typeof opsShowView==='function')opsShowView('home');
  requestAnimationFrame(()=>requestAnimationFrame(()=>{if(!reveal()&&typeof wave51Load==='function')wave51Load(false).then(()=>{if(typeof renderMarketingOps==='function')renderMarketingOps();requestAnimationFrame(reveal)})}));
}

function primaryNavigationButton(view,label){
  const button=opsEl('button','',label);
  button.type='button';
  button.dataset.opsView=view;
  button.addEventListener('click',()=>primaryNavigationGo(view));
  button.classList.toggle('active',marketingOpsState?.view===view);
  return button;
}

function primaryNavigationMore(){
  const select=document.createElement('select');
  select.className=`post-w99-more ${POST_W99_SECONDARY_VIEWS.has(marketingOpsState?.view)?'active':''}`;
  select.setAttribute('aria-label','Más módulos');
  const placeholder=opsEl('option','','Más');
  placeholder.value='';
  select.append(placeholder);
  for(const [view,label] of POST_W99_SECONDARY_NAVIGATION){
    const option=opsEl('option','',label);
    option.value=view;
    option.selected=marketingOpsState?.view===view;
    select.append(option);
  }
  select.addEventListener('change',()=>{const view=select.value;if(view)primaryNavigationGo(view)});
  return select;
}

function primaryNavigationEnsure(){
  primaryNavigationStyles();
  const nav=document.querySelector('.marketing-ops-nav');
  if(!nav)return;
  nav.dataset.postW99PrimaryNavigation='1';
  nav.replaceChildren();
  for(const [view,label] of POST_W99_PRIMARY_NAVIGATION)nav.append(primaryNavigationButton(view,label));
  nav.append(primaryNavigationMore());
  const astra=opsEl('button','post-w99-astra','✦ Astra / IA');
  astra.type='button';
  astra.dataset.postW99Astra='1';
  astra.addEventListener('click',primaryNavigationOpenAstra);
  nav.append(astra);
}

const postW99PrimaryNavigationBaseRender=globalThis.renderMarketingOps;
globalThis.renderMarketingOps=function(){
  postW99PrimaryNavigationBaseRender();
  primaryNavigationEnsure();
};
window.addEventListener('marketing-ops-refreshed',primaryNavigationEnsure);
primaryNavigationEnsure();
