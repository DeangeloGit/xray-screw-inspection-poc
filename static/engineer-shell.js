(()=>{
 const buttons=[...document.querySelectorAll('[data-engineer-tab]')],panels=[...document.querySelectorAll('[data-engineer-panel]')];
 function select(tab){if(!buttons.some(b=>b.dataset.engineerTab===tab))tab='machines';for(const b of buttons){const active=b.dataset.engineerTab===tab;b.classList.toggle('active',active);b.setAttribute('aria-current',active?'page':'false')}for(const p of panels)p.hidden=p.dataset.engineerPanel!==tab;const url=new URL(location);url.searchParams.set('tab',tab);history.replaceState(null,'',url);window.dispatchEvent(new CustomEvent('engineering-panel',{detail:tab}));}
 for(const b of buttons)b.onclick=()=>select(b.dataset.engineerTab);
 const params=new URLSearchParams(location.search);select(params.get('tab')||(params.get('sample')?'tuning':document.body.dataset.initialTab||'machines'));
})();
