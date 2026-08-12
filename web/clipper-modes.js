function ensureClipperModeControls(){
  let root=$('#clipper-mode-controls');if(root)return root;
  const run=$('#clipper-run');const form=run?.closest('.inline-form');if(!form)return null;
  root=el('div','clipper-mode-controls');root.id='clipper-mode-controls';root.style.display='grid';root.style.gridTemplateColumns='minmax(140px,1fr) minmax(110px,1fr)';root.style.gap='8px';root.style.marginTop='10px';
  const modeLabel=el('label','','');modeLabel.append(document.createTextNode('Modo'));const mode=document.createElement('select');mode.id='clipper-mode';for(const [value,label] of [['natural','Natural · idea completa'],['objective','Duración objetivo']]){const option=el('option','',label);option.value=value;mode.append(option)}modeLabel.append(mode);
  const targetLabel=el('label','','');targetLabel.append(document.createTextNode('Objetivo por clip (s)'));const target=document.createElement('input');target.id='clipper-target-duration';target.type='number';target.min='3';target.max='180';target.step='1';target.value='30';target.disabled=true;targetLabel.append(target);
  mode.addEventListener('change',()=>{target.disabled=mode.value!=='objective';renderClipperModeHelp()});target.addEventListener('change',()=>renderClipperModeHelp());root.append(modeLabel,targetLabel);form.parentElement.insertBefore(root,form.nextSibling);
  const help=el('p','muted','');help.id='clipper-mode-help';help.style.marginTop='7px';root.parentElement.insertBefore(help,root.nextSibling);renderClipperModeHelp();return root;
}
function renderClipperModeHelp(){const help=$('#clipper-mode-help'),mode=$('#clipper-mode');if(!help||!mode)return;help.textContent=mode.value==='objective'?`Busca cortes cercanos a ${Number($('#clipper-target-duration')?.value||30)}s, pero conserva límites narrativos y evita solapamientos.`:'Prioriza hook + idea autocontenida + cierre/acción; la duración puede variar dentro del mínimo y máximo.'}
function clipperModePayload(){ensureClipperModeControls();const mode=$('#clipper-mode')?.value||'natural';const payload={mode};if(mode==='objective')payload.target_duration=Number($('#clipper-target-duration')?.value||30);return payload}
function decorateNarrativeClipResults(){
  const rows=[...document.querySelectorAll('#clipper-results .result-item')];if(!rows.length)return;
  rows.forEach(node=>{if(node.querySelector('.narrative-meta'))return;const strong=node.querySelector('strong');if(!strong)return;const match=strong.textContent.match(/score\s+([\d.]+)/i);if(!match)return})
}
ensureClipperModeControls();
