(function loadWave39AfterWave38(){
  if(document.querySelector('script[data-audiences-wave38-chain]'))return;
  const ready=(selector)=>Boolean(document.querySelector(selector));
  const loadCrmCsv=()=>{
    if(document.querySelector('script[data-crm-csv-wave45]'))return;
    const csv=document.createElement('script');
    csv.src='/crm-csv.js';
    csv.defer=true;
    csv.dataset.crmCsvWave45='1';
    document.head.append(csv);
  };
  const loadDailyActions=()=>{
    const existing=document.querySelector('script[data-daily-actions-wave44]');
    if(existing){if(ready('#daily-actions-wave44-style'))loadCrmCsv();else existing.addEventListener('load',loadCrmCsv,{once:true});return}
    const actions=document.createElement('script');
    actions.src='/daily-actions.js';
    actions.defer=true;
    actions.dataset.dailyActionsWave44='1';
    actions.addEventListener('load',loadCrmCsv,{once:true});
    document.head.append(actions);
  };
  const loadDaily=()=>{
    const existing=document.querySelector('script[data-daily-ops-wave43]');
    if(existing){if(ready('#daily-ops-wave43-style'))loadDailyActions();else existing.addEventListener('load',loadDailyActions,{once:true});return}
    const daily=document.createElement('script');
    daily.src='/daily-ops.js';
    daily.defer=true;
    daily.dataset.dailyOpsWave43='1';
    daily.addEventListener('load',loadDailyActions,{once:true});
    document.head.append(daily);
  };
  const loadEditorial=()=>{
    const existing=document.querySelector('script[data-editorial-wave42]');
    if(existing){if(ready('#editorial-wave42-style'))loadDaily();else existing.addEventListener('load',loadDaily,{once:true});return}
    const editorial=document.createElement('script');
    editorial.src='/editorial-management.js';
    editorial.defer=true;
    editorial.dataset.editorialWave42='1';
    editorial.addEventListener('load',loadDaily,{once:true});
    document.head.append(editorial);
  };
  const loadReplies=()=>{
    const existing=document.querySelector('script[data-inbox-replies-wave41]');
    if(existing){if(ready('#inbox-replies-wave41-style'))loadEditorial();else existing.addEventListener('load',loadEditorial,{once:true});return}
    const replies=document.createElement('script');
    replies.src='/inbox-replies.js';
    replies.defer=true;
    replies.dataset.inboxRepliesWave41='1';
    replies.addEventListener('load',loadEditorial,{once:true});
    document.head.append(replies);
  };
  const loadInbox=()=>{
    const existing=document.querySelector('script[data-inbox-wave39]');
    if(existing){if(ready('#inbox-wave39-style'))loadReplies();else existing.addEventListener('load',loadReplies,{once:true});return}
    const inbox=document.createElement('script');
    inbox.src='/inbox.js';
    inbox.defer=true;
    inbox.dataset.inboxWave39='1';
    inbox.addEventListener('load',loadReplies,{once:true});
    document.head.append(inbox);
  };
  const wave38=document.createElement('script');
  wave38.src='/audiences-wave38.js';
  wave38.defer=true;
  wave38.dataset.audiencesWave38Chain='1';
  wave38.addEventListener('load',()=>{
    let attempts=0;
    const waitForAnalytics=()=>{
      if(ready('#analytics-wave38-style')){loadInbox();return}
      attempts+=1;
      if(attempts<200)setTimeout(waitForAnalytics,25);
      else console.error('Wave 45 loader: Wave 38 analytics did not finish loading');
    };
    waitForAnalytics();
  },{once:true});
  document.head.append(wave38);
})();