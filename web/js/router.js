/* Маршрутизация между экранами. */
/* ================= РОУТИНГ ================= */
let H=(location.hash&&location.hash.startsWith('#/'))?location.hash:'#/list';
/* История браузера: каждый переход отдельной записью, поэтому стрелка «Назад» идёт по экранам
   приложения и не уводит из него. Прокруткой списка управляем сами (см. restoreListFocus). */
try{history.scrollRestoration='manual';history.replaceState({i:0,from:null},'',H)}catch(_){}
function go(h){
  if(h===H){route();return}
  const prev=H,i=((history.state&&history.state.i)||0)+1;
  H=h;
  try{history.pushState({i,from:prev},'',h)}catch(_){}
  route();
}
let routeSeq=0,curView=null;
async function route(){
  const seq=++routeSeq;
  if(curView==='list'){listUI.scroll=scrollY;listUI.has=true}   /* уходим из списка: запоминаем место */
  syncRoleUI();
  const [,view='list',raw]=H.split('/');
  const arg=raw?decodeURIComponent(raw):raw;
  if(view==='card'&&D[arg])cur=arg;
  /* оператор не открывает чужие диалоги */
  if(view==='card'&&!reviewer&&D[cur]&&!mine(cur)){const k=visKeys()[0];go(k?'#/card/'+encodeURIComponent(k):'#/list');return}
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
  if(view==='list'){renderList();if(CQA_API.enabled&&reviewer)beWarm([...rowsCache.map(r=>r.key),...Object.keys(D)])}
  if(view==='card'){syncPick();if(cur){renderCard();if(CQA_API.enabled&&reviewer){beAutoEvaluate(cur);const ks=Object.keys(D),i=ks.indexOf(cur);beWarm([...ks.slice(i+1),...ks.slice(0,i)])}}else $('#chat').innerHTML='<div class="empty">Диалогов нет. Загрузите набор на экране «Диалоги».</div>'}
  if(view==='checklist'){renderEditor();lockChecklist()}
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
/* стрелки браузера «Назад» и «Вперёд» */
function syncFromUrl(){
  const h=(location.hash&&location.hash.startsWith('#/'))?location.hash:'#/list';
  if(h!==H){H=h;route()}
}
addEventListener('popstate',syncFromUrl);
addEventListener('hashchange',syncFromUrl);
$('#nav').onclick=e=>{const b=e.target.closest('button');if(b)go(b.dataset.r==='card'?'#/card/'+encodeURIComponent(cur):'#/'+b.dataset.r)};
/* «← Диалоги»: если пришли из списка, ведём себя как стрелка браузера (в истории не копятся лишние записи) */
$('#back').onclick=()=>{
  const s=history.state;
  if(s&&s.from&&String(s.from).startsWith('#/list'))history.back();
  else go('#/list');
};
