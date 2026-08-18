const wave59State={navQueued:false};

const WAVE59_LABELS={
  home:'Hoy',inbox:'Inbox', 'lead-intake':'Leads',crm:'CRM',campaigns:'Campañas',
  content:'Creative Studio',video:'Video Studio',calendar:'Calendario',publish:'Publicar',
  pauta:'Pauta',analytics:'Resultados',audiences:'Audiencias',companies:'Empresas & Meta',
  'public-gateway':'Recepción web 24/7','capture-bridge':'Captura web',attribution:'Atribución',
  learning:'Aprendizaje','ai-copilot':'IA Copilot',ai:'IA Copilot'
};
const WAVE59_GROUPS=[
  ['TRABAJO DIARIO',['home','inbox','lead-intake','crm']],
  ['CREAR Y DISTRIBUIR',['campaigns','content','video','calendar','publish','pauta']],
  ['MEDIR Y MEJORAR',['analytics','learning','ai-copilot','ai']],
  ['CONFIGURACIÓN',['audiences','companies']],
];
const WAVE59_ADVANCED=new Set(['attribution','capture-bridge','public-gateway']);

function wave59Styles(){
  if(document.querySelector('#wave59-local-product-style'))return;
  const style=document.createElement('style');style.id='wave59-local-product-style';style.textContent=`
  .marketing-ops-rail{padding:16px 11px;gap:13px}.marketing-ops-brand{padding:4px 6px 8px}.marketing-ops-brand strong{font-size:15px}.marketing-ops-brand span{font-size:9px;line-height:1.45}.w59-nav-group{display:grid;gap:4px}.w59-nav-label{padding:8px 7px 3px;font-size:7px;letter-spacing:.13em;color:#8a857c}.w59-nav-group button{width:100%;text-align:left}.w59-nav-optional{border-top:1px solid #e4e0d8;margin-top:4px;padding-top:7px}.w59-nav-optional summary{cursor:pointer;list-style:none;padding:7px;font-size:8px;color:#777269}.w59-nav-optional summary::-webkit-details-marker{display:none}.w59-nav-optional summary:after{content:'+';float:right}.w59-nav-optional[open] summary:after{content:'−'}.w59-nav-optional .w59-nav-group{padding-top:3px}.w59-local-chip{display:inline-flex;align-items:center;gap:5px;padding:5px 8px;border:1px solid #d8d3c9;border-radius:999px;background:#f8f6f1;font-size:8px;color:#5f5b54}.w59-local-dot{width:6px;height:6px;border-radius:999px;background:#171717}.w59-home-intro{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(260px,.7fr);gap:12px}.w59-home-card{padding:15px;border:1px solid #dcd8cf;border-radius:14px;background:#fff;display:grid;gap:9px}.w59-home-card h3{margin:0;font-size:20px}.w59-home-card p{margin:0}.w59-home-actions{display:flex;gap:7px;flex-wrap:wrap}.w59-home-actions button{min-height:34px}.w59-mode-list{display:grid;gap:6px}.w59-mode-row{display:grid;grid-template-columns:10px minmax(0,1fr);gap:7px;align-items:start;padding:7px 0;border-bottom:1px solid #eeeae2}.w59-mode-row:last-child{border-bottom:0}.w59-mode-row i{width:7px;height:7px;margin-top:3px;border-radius:999px;background:#171717}.w59-mode-row strong{font-size:9px}.w59-mode-row span{display:block;font-size:8px;color:#706c65;margin-top:2px;line-height:1.4}.w59-journey{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:7px}.w59-journey button{padding:10px;border:1px solid #e2ded6;border-radius:11px;background:#fff;text-align:left;display:grid;gap:3px;min-height:76px}.w59-journey button:hover{border-color:#bdb7ac}.w59-journey .step{font-size:7px;color:#777269;letter-spacing:.08em}.w59-journey strong{font-size:18px}.w59-journey span{font-size:8px;color:#706c65}.w59-cloud-note{font-size:8px;color:#706c65;padding:6px 7px 2px;line-height:1.4}.w59-home-intro+.w50-command{margin-top:0}.w50-kicker{letter-spacing:.1em}.marketing-ops-top h2{letter-spacing:-.02em}
  @media(max-width:1100px){.w59-journey{grid-template-columns:repeat(3,1fr)}}@media(max-width:760px){.w59-home-intro{grid-template-columns:1fr}.w59-journey{grid-template-columns:1fr 1fr}}@media(max-width:480px){.w59-journey{grid-template-columns:1fr}}
  `;document.head.append(style)
}

function wave59ButtonLabel(button,view){
  const label=WAVE59_LABELS[view];if(!label)return;
  if(button.textContent.trim()===label)return;
  button.replaceChildren(document.createTextNode(label));
}
function wave59NavGroup(label,buttons){const group=opsEl('div','w59-nav-group');group.dataset.w59Group=label;group.append(opsEl('div','w59-nav-label',label));buttons.forEach(button=>group.append(button));return group}

function wave59RebuildNavigation(){
  const nav=document.querySelector('.marketing-ops-nav');if(!nav)return;
  const buttons=[...nav.querySelectorAll('button[data-ops-view]')];if(!buttons.length)return;
  const unique=new Map();for(const button of buttons){const view=button.dataset.opsView;if(view&&!unique.has(view))unique.set(view,button)}
  for(const [view,button] of unique)wave59ButtonLabel(button,view);
  nav.replaceChildren();const used=new Set();
  for(const [label,views] of WAVE59_GROUPS){const rows=[];for(const view of views){const button=unique.get(view);if(button){rows.push(button);used.add(view)}}if(rows.length)nav.append(wave59NavGroup(label,rows))}
  const advanced=[];const other=[];for(const [view,button] of unique){if(used.has(view))continue;if(WAVE59_ADVANCED.has(view))advanced.push(button);else other.push(button)}
  if(other.length)nav.append(wave59NavGroup('MÁS HERRAMIENTAS',other));
  if(advanced.length){const details=document.createElement('details');details.className='w59-nav-optional';const summary=document.createElement('summary');summary.textContent='Avanzado · opcional';details.append(summary,opsEl('div','w59-cloud-note','Atribución avanzada y recepción web 24/7. No son necesarias para operar la app local.'));details.append(wave59NavGroup('INTEGRACIONES',advanced));nav.append(details)}
  const active=marketingOpsState?.view;nav.querySelectorAll('button[data-ops-view]').forEach(button=>button.classList.toggle('active',button.dataset.opsView===active));
  const brand=document.querySelector('.marketing-ops-brand');if(brand){brand.querySelector('.eyebrow')?.replaceChildren(document.createTextNode('BINARIO MARKETING IA'));brand.querySelector('strong')?.replaceChildren(document.createTextNode('Marketing OS local'));brand.querySelector('span')?.replaceChildren(document.createTextNode('Opera cada empresa desde un solo flujo: atender, convertir, planear, crear, distribuir y aprender.'))}
}

function wave59TopMode(){
  const top=document.querySelector('.marketing-ops-top');if(!top)return;let chip=top.querySelector('.w59-local-chip');if(!chip){chip=opsEl('span','w59-local-chip');chip.append(opsEl('i','w59-local-dot'),document.createTextNode('Modo local · datos en este Mac'));const selector=top.querySelector('.marketing-ops-company-select');if(selector)selector.insertAdjacentElement('beforebegin',chip);else top.append(chip)}
  const title=document.querySelector('.topbar h1');if(title&&document.querySelector('#marketing-ops-shell:not(.marketing-ops-hidden)'))title.textContent='BINARIO Marketing IA';
}

function wave59FlowValue(data,key){return Number(data?.flow?.[key]||0)}
function wave59JourneyCard(step,title,value,copy,view){const button=opsEl('button','','');button.type='button';button.append(opsEl('span','step',step),opsEl('strong','',String(value)),opsEl('span','',`${title} · ${copy}`));button.addEventListener('click',()=>opsShowView(view));return button}
function wave59HomeIntro(root){
  if(root.querySelector('.w59-home-intro'))return;const company=typeof wave47Company==='function'?wave47Company():typeof opsSelectedCompany==='function'?opsSelectedCompany():null;if(!company)return;
  const data=(typeof wave50CommandState!=='undefined'&&wave50CommandState.companyId===company.id)?wave50CommandState.data:null;
  const intro=opsEl('div','w59-home-intro'),main=opsEl('section','w59-home-card'),mode=opsEl('section','w59-home-card');main.append(opsEl('p','eyebrow','HOY'),opsEl('h3','',`Trabaja ${company.name} desde aquí`),opsEl('p','muted','La app funciona localmente. Meta y los proveedores de IA se consultan solo cuando una acción del módulo correspondiente lo requiere; el cloud de recepción 24/7 es opcional.'));
  const actions=opsEl('div','w59-home-actions');[['Nueva campaña','campaigns',true],['Crear pieza','content',false],['Revisar Inbox','inbox',false],['Abrir CRM','crm',false],['Preparar pauta','pauta',false]].forEach(([label,view,primary])=>{const b=opsEl('button',primary?'primary':'',label);b.type='button';b.addEventListener('click',()=>opsShowView(view));actions.append(b)});main.append(actions);
  mode.append(opsEl('p','eyebrow','ARQUITECTURA'),opsEl('h3','','Local primero'));const list=opsEl('div','w59-mode-list');[['Core local','Empresas, campañas, CRM, creativos, video, calendario, datos y trazabilidad viven en este Mac.'],['Conexiones explícitas','Meta e IA salen a Internet únicamente cuando usas sus funciones.'],['Cloud opcional','Gateway/Supabase/Vercel quedan fuera del camino crítico y solo sirven para recepción pública 24/7.']].forEach(([a,b])=>{const row=opsEl('div','w59-mode-row');row.append(document.createElement('i'));const copy=opsEl('div','');copy.append(opsEl('strong','',a),opsEl('span','',b));row.append(copy);list.append(row)});mode.append(list);intro.append(main,mode);root.prepend(intro);
  const journey=opsEl('div','w59-journey');const attention=Number(data?.attention?.total||0),crm=wave59FlowValue(data,'crm_open_opportunities'),campaigns=wave59FlowValue(data,'campaigns_active'),creative=wave59FlowValue(data,'creatives_production')+wave59FlowValue(data,'creatives_ready'),scheduled=wave59FlowValue(data,'scheduled')+wave59FlowValue(data,'paid_plans'),published=Number(data?.publications?.published||0);journey.append(wave59JourneyCard('01 · ATENDER','Inbox / prioridades',attention,'requieren atención','inbox'),wave59JourneyCard('02 · CONVERTIR','CRM',crm,'oportunidades abiertas','crm'),wave59JourneyCard('03 · PLANEAR','Campañas',campaigns,'activas','campaigns'),wave59JourneyCard('04 · CREAR','Creativos',creative,'en flujo','content'),wave59JourneyCard('05 · DISTRIBUIR','Calendario + pauta',scheduled,'preparadas','calendar'),wave59JourneyCard('06 · APRENDER','Resultados',published,'publicadas observadas','analytics'));intro.insertAdjacentElement('afterend',journey)
}
function wave59PolishHome(){
  if(marketingOpsState?.view!=='home')return;const root=document.querySelector('#marketing-ops-view');if(!root)return;document.querySelector('#marketing-ops-eyebrow')?.replaceChildren(document.createTextNode('CENTRO DE TRABAJO'));const company=typeof wave47Company==='function'?wave47Company():null;document.querySelector('#marketing-ops-title')?.replaceChildren(document.createTextNode(company?`Hoy · ${company.name}`:'Hoy'));document.querySelector('#marketing-ops-subtitle')?.replaceChildren(document.createTextNode('Prioridades, flujo de marketing y siguiente acción desde el estado local de la empresa.'));wave59HomeIntro(root);
  root.querySelectorAll('.w50-kicker').forEach(node=>{if(node.textContent.trim()==='MARKETING COMMAND CENTER')node.textContent='OPERACIÓN INTEGRADA';if(node.textContent.trim()==='CAMPAIGN COCKPIT')node.textContent='CAMPAÑAS ACTIVAS'});
}
function wave59Apply(){wave59Styles();wave59RebuildNavigation();wave59TopMode();wave59PolishHome()}
function wave59QueueApply(){if(wave59State.navQueued)return;wave59State.navQueued=true;queueMicrotask(()=>{wave59State.navQueued=false;wave59Apply()})}

const wave59BaseRenderMarketingOps=globalThis.renderMarketingOps;
if(typeof wave59BaseRenderMarketingOps==='function')globalThis.renderMarketingOps=function(){const result=wave59BaseRenderMarketingOps();wave59QueueApply();return result};
const wave59BaseOpsShowView=globalThis.opsShowView;
if(typeof wave59BaseOpsShowView==='function')globalThis.opsShowView=function(view){const result=wave59BaseOpsShowView(view);wave59QueueApply();return result};
window.addEventListener('marketing-company-change',wave59QueueApply);
wave59Apply();
