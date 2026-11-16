"use strict";
(() => {
  const overview=document.querySelector('#overview-view'),terminal=document.querySelector('#terminal-view');
  let active='overview',scroll=0;
  function navigate(){
    const next=location.hash==='#/terminal'?'terminal':'overview';
    if(active==='overview'&&next==='terminal')scroll=window.scrollY;
    overview.hidden=next==='terminal';overview.inert=overview.hidden;
    terminal.hidden=next!=='terminal';terminal.inert=terminal.hidden;
    document.documentElement.dataset.screen=next;
    const terminalLink=document.querySelector('.terminal-nav');
    if(next==='terminal'){document.querySelectorAll('.nav-link').forEach(link=>link.removeAttribute('aria-current'));terminalLink.setAttribute('aria-current','page');}else terminalLink.removeAttribute('aria-current');
    if(next!==active){
      if(next==='terminal'){window.scrollTo({top:0,behavior:'instant'});document.querySelector('#terminal-input').focus({preventScroll:true});}
      else {const anchor=document.getElementById(location.hash.slice(1));if(anchor)anchor.scrollIntoView({behavior:'instant'});else window.scrollTo({top:scroll,behavior:'instant'});}
      active=next;window.dispatchEvent(new CustomEvent('dnssec:screen',{detail:{route:next}}));
    }
  }
  addEventListener('hashchange',navigate);navigate();
})();

