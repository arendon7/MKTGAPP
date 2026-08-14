(function loadWave38AfterWave37(){
  if(document.querySelector('script[data-audiences-wave37-chain]'))return;
  const wave37=document.createElement('script');
  wave37.src='/audiences-wave37.js';
  wave37.defer=true;
  wave37.dataset.audiencesWave37Chain='1';
  wave37.addEventListener('load',()=>{
    let attempts=0;
    const waitForContactability=()=>{
      if(document.querySelector('#contactability-wave37-style')){
        if(document.querySelector('script[data-analytics-wave38]'))return;
        const analytics=document.createElement('script');
        analytics.src='/analytics.js';
        analytics.defer=true;
        analytics.dataset.analyticsWave38='1';
        document.head.append(analytics);
        return;
      }
      attempts+=1;
      if(attempts<200)setTimeout(waitForContactability,25);
      else console.error('Wave 38 analytics loader: Wave 37 contactability did not finish loading');
    };
    waitForContactability();
  },{once:true});
  document.head.append(wave37);
})();
