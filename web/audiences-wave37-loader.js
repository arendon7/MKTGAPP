(function loadWave37AfterAudiences(){
  if(document.querySelector('script[data-audiences-wave36-base]'))return;
  const base=document.createElement('script');
  base.src='/audiences-base.js';
  base.defer=true;
  base.dataset.audiencesWave36Base='1';
  base.addEventListener('load',()=>{
    if(document.querySelector('script[data-contactability-wave37]'))return;
    const extension=document.createElement('script');
    extension.src='/contactability.js';
    extension.defer=true;
    extension.dataset.contactabilityWave37='1';
    document.head.append(extension);
  },{once:true});
  document.head.append(base);
})();
