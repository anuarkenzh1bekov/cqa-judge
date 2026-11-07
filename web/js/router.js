/* Маршрутизация между экранами. */
/* ================= РОУТИНГ ================= */
let H=(location.hash&&location.hash.startsWith('#/'))?location.hash:'#/list';
function go(h){H=h;try{history.replaceState(null,'',h)}catch(_){}route()}
function route(){
  const [,view='list',arg]=H.split('/');
  if(view==='card'&&D[arg])cur=arg;
  ['list','card','checklist','appeals'].forEach(v=>$('#v-'+v).hidden=v!==view);
  $$('#nav button').forEach(t=>t.classList.toggle('on',t.dataset.r===view));
  syncCount();
  if(view==='list')renderList();
  if(view==='card')renderCard();
  if(view==='checklist')renderEditor();
  if(view==='appeals')renderAppeals();
  scrollTo(0,0);
}
addEventListener('hashchange',()=>{if(location.hash.startsWith('#/')&&location.hash!==H){H=location.hash;route()}});
$('#nav').onclick=e=>{const b=e.target.closest('button');if(b)go(b.dataset.r==='card'?'#/card/'+cur:'#/'+b.dataset.r)};
$('#back').onclick=()=>go('#/list');
