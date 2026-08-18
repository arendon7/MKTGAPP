(function loadWave39AfterWave38(){
  if(document.querySelector('script[data-audiences-wave38-chain]'))return;
  const ready=(selector)=>Boolean(document.querySelector(selector));
  const loadCreativeStudio=()=>{
    if(document.querySelector('script[data-creative-studio-wave49]'))return;
    const creative=document.createElement('script');
    creative.src='/creative-studio.js';
    creative.defer=true;
    creative.dataset.creativeStudioWave49='1';
    document.head.append(creative);
  };
  const loadPaidMediaCenter=()=>{
    const existing=document.querySelector('script[data-paid-media-wave48]');
    if(existing){if(ready('#wave48-paid-media-style'))loadCreativeStudio();else existing.addEventListener('load',loadCreativeStudio,{once:true});return}
    const paid=document.createElement('script');
    paid.src='/paid-media-center.js';
    paid.defer=true;
    paid.dataset.paidMediaWave48='1';
    paid.addEventListener('load',loadCreativeStudio,{once:true});
    document.head.append(paid);
  };
  const loadProductShell=()=>{
    const existing=document.querySelector('script[data-product-shell-wave47]');
    if(existing){if(ready('#wave47-product-shell-style'))loadPaidMediaCenter();else existing.addEventListener('load',loadPaidMediaCenter,{once:true});return}
    const shell=document.createElement('script');
    shell.src='/product-shell.js';
    shell.defer=true;
    shell.dataset.productShellWave47='1';
    shell.addEventListener('load',loadPaidMediaCenter,{once:true});
    document.head.append(shell);
  };
  const loadFollowupReschedule=()=>{
    const existing=document.querySelector('script[data-followup-reschedule-wave45]');
    if(existing){if(ready('#followup-reschedule-wave45-style'))loadProductShell();else existing.addEventListener('load',loadProductShell,{once:true});return}
    const reschedule=document.createElement('script');
    reschedule.src='/followup-reschedule.js';
    reschedule.defer=true;
    reschedule.dataset.followupRescheduleWave45='1';
    reschedule.addEventListener('load',loadProductShell,{once:true});
    document.head.append(reschedule);
  };
  const loadDailyActions=()=>{
    const existing=document.querySelector('script[data-daily-actions-wave44]');
    if(existing){if(ready('#daily-actions-wave44-style'))loadFollowupReschedule();else existing.addEventListener('load',loadFollowupReschedule,{once:true});return}
    const actions=document.createElement('script');
    actions.src='/daily-actions.js';
    actions.defer=true;
    actions.dataset.dailyActionsWave44='1';
    actions.addEventListener('load',loadFollowupReschedule,{once:true});
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
      else console.error('Wave 49 loader: Wave 38 analytics did not finish loading');
    };
    waitForAnalytics();
  },{once:true});
  document.head.append(wave38);
})();