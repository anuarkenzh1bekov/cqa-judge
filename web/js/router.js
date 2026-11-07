/* Маршрутизация между экранами. */
/* ================= РОУТИНГ ================= */
let H=(location.hash&&location.hash.startsWith('#/'))?location.hash:'#/list';
function go(h){H=h;try{history.replaceState(null,'',h)}catch(_){}route()}
let routeSeq=0,curView=null;
async function route(){
  const seq=++routeSeq;
  if(curView==='list'){listUI.scroll=scrollY;listUI.has=true}   /* уходим из списка: запоминаем место */
  const [,view='list',raw]=H.split('/');
  const arg=raw?decodeURIComponent(raw):raw;
  if(view==='card'&&D[arg])cur=arg;
  ['list','card','checklist','appeals','stats'].forEach(v=>{const el=$('#v-'+v);if(el)el.hidden=v!==view});
  $$('#nav button').forEach(t=>t.classList.toggle('on',t.dataset.r===view));
  syncCount();
  try{
    if(CQA_API.enabled&&view==='card'&&cur&&!D[cur].loaded){
      $('#chat').innerHTML='<div class="empty">Загрузка…</div>';$('#crit').innerHTML='';$('#score').innerHTML='';
      await beLoadDialog(cur);
    }
    if(CQA_API.enabled&&view==='appeals')await beLoadAppealDialogs();
  }catch(e){toast('Ошибка загрузки: '+e.message)}
  if(seq!==routeSeq)return;  // пользователь уже ушёл на другой экран
  if(view==='list')renderList();
  if(view==='card'){if(cur)renderCard();else $('#chat').innerHTML='<div class="empty">Диалогов нет. Загрузите набор на экране «Диалоги».</div>'}
  if(view==='checklist')renderEditor();
  if(view==='appeals')renderAppeals();
  if(view==='stats')renderStats();
  syncCount();
  if(view==='list'&&listUI.has){scrollTo(0,listUI.scroll);restoreListFocus()}else scrollTo(0,0);
  curView=view;
  motion($('#v-'+view),[{opacity:0,transform:'translateY(6px)'},{opacity:1,transform:'none'}],180);
}
/* для очереди апелляций нужны карточки всех диалогов, где есть апелляции */
async function beLoadAppealDialogs(){
  const list=await CQA_API.appeals();
  const ids=[...new Set(list.map(a=>a.conversation_id))].filter(id=>D[id]);
  await Promise.all(ids.map(id=>beLoadDialog(id)));
}
addEventListener('hashchange',()=>{if(location.hash.startsWith('#/')&&location.hash!==H){H=location.hash;route()}});
$('#nav').onclick=e=>{const b=e.target.closest('button');if(b)go(b.dataset.r==='card'?'#/card/'+encodeURIComponent(cur):'#/'+b.dataset.r)};
$('#back').onclick=()=>go('#/list');
