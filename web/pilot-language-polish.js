(function installPostW99PilotLanguagePolish(){
  if(globalThis.POST_W99_PILOT_LANGUAGE_POLISH)return;
  globalThis.POST_W99_PILOT_LANGUAGE_POLISH=true;

  function replaceText(node,replacements){
    if(!node)return;
    let value=node.textContent||'';
    for(const [from,to] of replacements)value=value.replace(from,to);
    if(value!==node.textContent)node.textContent=value;
  }

  function polishNavigation(){
    const inbox=document.querySelector('[data-ops-view="inbox"]');
    if(inbox&&inbox.tagName==='BUTTON')inbox.textContent='Mensajes';
    const more=document.querySelector('.post-w99-more');
    if(more){
      const labels={
        'executive-cockpit':'Panel ejecutivo',
        'action-center':'Centro de acciones',
      };
      for(const option of more.options||[])if(labels[option.value])option.textContent=labels[option.value];
    }
  }

  function polishBootstrapFailure(){
    const box=document.querySelector('[data-post-w99-pilot-failure]');if(!box)return;
    const paragraphs=box.querySelectorAll('p');
    if(paragraphs[0])paragraphs[0].textContent='La aplicación local sigue protegida. Recarga la página; si persiste, reinicia MERCADEO APP antes de operar cuentas o publicaciones.';
    if(paragraphs[1])paragraphs[1].textContent='El detalle técnico permanece disponible en el entorno local de desarrollo.';
  }

  function polishGuidance(){
    for(const node of document.querySelectorAll('.pilot-guide-copy p')){
      const current=node.textContent||'';
      if(current.startsWith('No se pudo leer el estado local de W50.')){
        node.textContent='No se pudo leer el estado de preparación de esta empresa. Reintenta la lectura local.';
        continue;
      }
      replaceText(node,[
        ['W50 no pudo componer el estado local de esta empresa.','No fue posible componer el estado local de esta empresa.'],
        ['Los ocho pasos de readiness reportados por W50 están completos.','Los pasos de preparación de la empresa están completos.'],
        ['W50 reporta preparación incompleta.','La preparación de la empresa está incompleta.'],
      ]);
    }
  }

  function polishCompanies(){
    if(!document.querySelector('.pco-hero'))return;
    const eyebrow=document.querySelector('#marketing-ops-eyebrow');if(eyebrow)eyebrow.textContent='EMPRESAS / TODAS';
    const heroEyebrow=document.querySelector('.pco-hero .eyebrow');if(heroEyebrow)heroEyebrow.textContent='CONFIGURACIÓN · ESTADO';
    const heroCopy=document.querySelector('.pco-hero .muted');if(heroCopy)heroCopy.textContent='Resumen de preparación por empresa. Esta vista no consulta Meta ni cambia cuentas.';
    for(const label of document.querySelectorAll('.pco-stat span'))replaceText(label,[['PROMEDIO READINESS','PREPARACIÓN PROM.']]);
    for(const detail of document.querySelectorAll('.pco-next p'))if((detail.textContent||'').trim())detail.textContent='Siguiente acción recomendada';
    const note=document.querySelector('.pco-note');if(note)note.textContent='Los pasos y porcentajes reflejan la preparación de cada empresa. Esta vista no muestra credenciales ni identificadores técnicos de Meta.';
    for(const empty of document.querySelectorAll('.pco-empty'))replaceText(empty,[
      ['Componiendo readiness local de todas las empresas…','Revisando preparación local de todas las empresas…'],
      ['desde el módulo propietario','desde Empresas'],
    ]);
    const owner=document.querySelector('.pco-owner span');if(owner)owner.textContent='Configurando la empresa activa. Las verificaciones y cambios se realizan únicamente dentro de esta empresa.';
  }

  function polishJourney(){
    for(const node of document.querySelectorAll('.pilot-journey-copy span,.pilot-journey-summary,.pilot-journey-meta .pilot-journey-chip'))replaceText(node,[
      ['shell empresarial','área de trabajo'],
      ['renderizadas','mostradas'],
      ['el smoke registra','la verificación registra'],
      ['modo portfolio','todas las empresas'],
      [' PASS',' VERIFICADAS'],
    ]);
    for(const status of document.querySelectorAll('.pilot-journey-status'))if(status.textContent==='PASS')status.textContent='VERIFICADO';
    for(const title of document.querySelectorAll('.pilot-journey-copy strong'))if(title.textContent==='Inbox')title.textContent='Mensajes';
  }

  function polishDataSafety(){
    const description=document.querySelector('.pilot-data-safety-head .muted');if(description)description.textContent='Copias verificables del estado local de MERCADEO APP. No suben datos a la nube ni incluyen credenciales Meta/IA.';
    const notice=document.querySelector('.pilot-data-safety-notice');if(notice)notice.textContent='Este bloque sólo crea y verifica copias locales. Restaurar o borrar respaldos no está habilitado durante esta fase del piloto. Los archivos temporales, registros técnicos y escrituras incompletas se excluyen deliberadamente.';
    for(const badge of document.querySelectorAll('.pilot-data-safety-badge'))if(badge.textContent==='SNAPSHOT LOCAL')badge.textContent='COPIA LOCAL';
    for(const button of document.querySelectorAll('.pilot-data-safety-actions button'))replaceText(button,[['Crear snapshot verificado','Crear respaldo verificado']]);
    for(const empty of document.querySelectorAll('.pilot-data-safety-empty'))replaceText(empty,[['snapshots locales','respaldos locales'],['snapshot','respaldo']]);
  }

  function polishSession(){
    const description=document.querySelector('.pilot-session-head .muted');if(description)description.textContent='Estado operativo local bajo demanda. No consulta Meta ni ejecuta acciones externas. La preparación de cada empresa se revisa por separado.';
    for(const title of document.querySelectorAll('.pilot-session-card strong'))if(title.textContent==='Backend local')title.textContent='Aplicación local';
    for(const copy of document.querySelectorAll('.pilot-session-card p'))replaceText(copy,[
      [/([0-9]+)\/([0-9]+) stores legibles\./g,'$1/$2 fuentes de datos disponibles.'],
      ['modo portfolio','todas las empresas'],
      ['snapshot local','respaldo local'],
      ['snapshots','respaldos'],
    ]);
    const note=document.querySelector('.pilot-session-note');if(note)note.textContent='“LISTO” aquí significa que la aplicación y sus fuentes locales base están operativas. No acredita conexión Meta, publicación remota, validación física ni producción. La preparación de cada empresa se revisa desde Empresas.';
    for(const chip of document.querySelectorAll('.pilot-session-chip')){
      if(chip.textContent==='READY')chip.textContent='LISTO';
      else if(chip.textContent==='PASS')chip.textContent='VERIFICADO';
      else if(chip.textContent==='AVAILABLE')chip.textContent='DISPONIBLE';
      else if(chip.textContent==='NONE')chip.textContent='SIN RESPALDO';
      else if(chip.textContent==='ERROR')chip.textContent='REVISAR';
    }
  }

  function polish(){
    document.title='MERCADEO APP · Centro de operaciones';
    polishNavigation();
    polishBootstrapFailure();
    polishGuidance();
    polishCompanies();
    polishJourney();
    polishDataSafety();
    polishSession();
  }

  function schedule(){setTimeout(polish,0);setTimeout(polish,450);setTimeout(polish,1400)}
  const baseRender=globalThis.renderMarketingOps;
  if(typeof baseRender==='function'&&!baseRender.__postW99LanguagePolish){
    const wrapped=function(){const result=baseRender.apply(this,arguments);schedule();return result};
    wrapped.__postW99LanguagePolish=true;globalThis.renderMarketingOps=wrapped;
  }
  document.addEventListener('click',schedule);
  window.addEventListener('marketing-ops-refreshed',schedule);
  window.addEventListener('wave73-entry-ready',schedule);
  window.addEventListener('wave73-bootstrap-ready',schedule);
  window.addEventListener('wave73-bootstrap-failed',schedule);
  window.addEventListener('post-w99-pilot-journey-observed',schedule);
  globalThis.pilotLanguagePolish=polish;
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',schedule,{once:true});else schedule();
})();
