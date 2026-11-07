/* Роли. Оператор (по умолчанию): только свои диалоги, в карточке можно лишь подать апелляцию, чек-лист только для чтения,
   апелляции списком (открытую можно удалить), своя аналитика. Проверяющий: всё как раньше. Переключатель — в шапке. */
/* ================= РОЛИ ================= */
let me='';
try{me=localStorage.getItem('cqa-me')||''}catch(_){}
try{reviewer=localStorage.getItem('cqa-mode')==='mgr'}catch(_){}
const mine=k=>!!D[k]&&D[k].operator===me;
const visKeys=()=>Object.keys(D).filter(k=>reviewer||mine(k));
function populateMe(){
  const ops=[...new Set(Object.values(D).map(d=>d.operator).filter(o=>o&&o!=='—'))].sort();
  if(!ops.includes(me))me=ops[0]||'';
  const sel=$('#me');
  sel.innerHTML=ops.map(o=>`<option value="${esc(o)}"${o===me?' selected':''}>${esc(o)}</option>`).join('');
  sel.hidden=reviewer||!ops.length;
}
function setNavText(btn,text){const n=[...btn.childNodes].find(x=>x.nodeType===3);if(n)n.nodeValue=text}
function syncRoleUI(){
  document.body.classList.toggle('role-op',!reviewer);
  populateMe();
  setNavText($('#nav [data-r=list]'),reviewer?'Диалоги':'Мои диалоги');
  setNavText($('#nav [data-r=appeals]'),reviewer?'Апелляции':'Мои апелляции');
  setNavText($('#nav [data-r=stats]'),reviewer?'Аналитика':'Моя аналитика');
  $('#v-list .page-h h1').textContent=reviewer?'Диалоги':'Мои диалоги';
  $('#v-stats .page-h h1').textContent=reviewer?'Аналитика':'Моя аналитика';
  $('#v-appeals .page-h h1').textContent=reviewer?'Апелляции':'Мои апелляции';
  $('#rev').textContent=reviewer?'Режим: проверяющий':'Режим: оператор';
  $('#rev').setAttribute('aria-pressed',reviewer);
  if(!reviewer&&fKind==='low')fKind='all';
  /* список для выбора диалога в карточке: оператору только свои */
  $('#pick').innerHTML=visKeys().map(k=>`<option value="${esc(k)}">${D[k].lang} · ${esc(D[k].id)}</option>`).join('');
  if(cur&&visKeys().includes(cur))$('#pick').value=cur;
  syncPick();
}
$('#rev').onclick=()=>{
  reviewer=!reviewer;
  try{localStorage.setItem('cqa-mode',reviewer?'mgr':'op')}catch(_){}
  syncRoleUI();syncCount();
  toast(reviewer?'Режим проверяющего: комментарии, публикация, решения по апелляциям':'Режим оператора: свои диалоги, апелляции, чек-лист для чтения');
  route();
};
$('#me').onchange=e=>{
  me=e.target.value;
  try{localStorage.setItem('cqa-me',me)}catch(_){}
  syncRoleUI();syncCount();route();
};

/* чек-лист оператору — только просмотр */
function lockChecklist(){
  if(reviewer)return;
  $$('#ed input,#ed select,#ed textarea,#ed button').forEach(x=>x.disabled=true);
  $('#verTitle').textContent+=' · только просмотр';
}

/* «Мои апелляции»: список со статусом, открытую можно удалить */
function renderMyAppeals(){
  const items=[];
  visKeys().forEach(d=>Object.keys(appeals[d]||{}).forEach(id=>{
    const c=CRIT.find(x=>x.id==id);
    if(c&&!pending(d,c))items.push({d,c,a:appeals[d][c.id]});
  }));
  items.sort((x,y)=>(!!x.a.decision)-(!!y.a.decision));
  $('#apDetail').innerHTML='';
  $('#apList').innerHTML=items.length?items.map(({d,c,a})=>`<div class="ap-row">
    <div><button class="lk" data-open="${esc(d)}">${esc(D[d].id)}</button> <b>${esc(c.name)}</b>
      <span class="mood ${a.decision?'yes':'warn'}">${a.decision?'решено':'на проверке'}</span>
      <p class="mut">${esc(a.text)}</p>${a.decision?`<div class="st done">${outcomeLine(d,c)}</div>`:''}</div>
    ${a.decision?'':`<button class="tx danger" data-del-ap="${esc(d)}" data-id="${c.id}">Удалить</button>`}</div>`).join('')
    :'<div class="empty">Вы ещё не подавали апелляций. Откройте диалог и нажмите «Оспорить» у критерия</div>';
}
$('#apList').addEventListener('click',async e=>{
  if(reviewer)return;
  const o=e.target.closest('[data-open]');
  if(o){go('#/card/'+encodeURIComponent(o.dataset.open));return}
  const x=e.target.closest('[data-del-ap]');if(!x)return;
  const d=x.dataset.delAp,id=+x.dataset.id;
  if(!confirm('Удалить апелляцию? Её можно будет подать заново.'))return;
  x.disabled=true;
  try{
    if(CQA_API.enabled){await CQA_API.del('/api/appeals/'+appeals[d][id]._id);await beLoadDialog(d,true)}
    else{delete appeals[d][id];persist()}
    syncCount();renderMyAppeals();toast('Апелляция удалена');
  }catch(err){toast('Ошибка: '+err.message);x.disabled=false}
});

/* «Моя аналитика»: мои баллы по критериям и персональный план коучинга */
async function renderMyStats(){
  const box=$('#statsBody');
  if(!CQA_API.enabled){box.innerHTML='<div class="empty">Аналитика доступна при подключённом бэкенде</div>';return}
  if(!me){box.innerHTML='<div class="empty">Нет оценённых диалогов</div>';return}
  box.innerHTML='<div class="empty">Загрузка…</div>';
  let p;
  try{p=await CQA_API.operator(me)}catch(e){box.innerHTML='<div class="empty">Пока нет оценённых диалогов</div>';return}
  opSel=me;
  const crit=p.criteria.filter(c=>c.avg_score_pct!=null);
  box.innerHTML=`<div class="kpis">${kpi('Оценено диалогов',p.evaluations.length)}${kpi('Средний балл',fmt(p.avg_total))}
    ${kpi('Грубые ошибки',p.evaluations.filter(e=>e.gross_error).length)}</div>
    <div class="panel box"><h3>Мои критерии <small class="mut">— средний % балла, слабые сверху</small></h3>
      <table><tbody>${crit.map(c=>`<tr><td>${esc(c.name)}</td><td class="r ${c.avg_score_pct<60?'low-score':''}">${pct(c.avg_score_pct)}</td><td style="width:40%">${bar(c.avg_score_pct,100)}</td></tr>`).join('')}</tbody></table></div>
    <div class="panel box"><div id="coachBox"></div></div>`;
  loadCoaching(me,false);
}
