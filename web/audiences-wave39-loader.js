(function loadWave39AfterWave38(){
  if(document.querySelector('script[data-audiences-wave38-chain]'))return;
  const loadEditorial=()=>{
    if(document.querySelector('script[data-editorial-wave42]'))return;
    const editorial=document.createElement('script');
    editorial.src='/editorial-management.js';
    editorial.defer=true;
    editorial.dataset.editorialWave42='1';
    document.head.append(editorial);
  };
  const wave38=document.createElement('script');
  wave38.src='/audiences-wave38.js';
  wave38.defer=true;
  wave38.dataset.audiencesWave38Chain='1';
  wave38.addEventListener('load',()=>{
    let attempts=0;
    const waitForAnalytics=()=>{
      if(document.querySelector('#analytics-wave38-style')){
        if(document.querySelector('script[data-inbox-wave39]'))return;
        const inbox=document.createElement('script');
        inbox.src='/inbox.js';
        inbox.defer=true;
        inbox.dataset.inboxWave39='1';
        inbox.addEventListener('load',()=>{
          if(document.querySelector('script[data-inbox-replies-wave41]')){loadEditorial();return}
          const replies=document.createElement('script');
          replies.src='/inbox-replies.js';
          replies.defer=true;
          replies.dataset.inboxRepliesWave41='1';
          replies.addEventListener('load',loadEditorial,{once:true});
          document.head.append(replies);
        },{once:true});
        document.head.append(inbox);
        return;
      }
      attempts+=1;
      if(attempts<200)setTimeout(waitForAnalytics,25);
      else console.error('Wave 39 inbox loader: Wave 38 analytics did not finish loading');
    };
    waitForAnalytics();
  },{once:true});
  document.head.append(wave38);
})();