/* Экран «Диалоги». */
/* ================= СПИСОК ================= */
const KINDS={all:()=>true,low:r=>r.needsReview,appeal:r=>r.a>0,gross:r=>r.g};
let rowsCache=[];
function listRows(){
  return Object.entries(D).map(([key,dialog])=>{
    const needsReview=CRIT.some(c=>!pending(key,c)&&dialog.res[c.id].conf<.65);
    return {key,id:dialog.id,lang:dialog.lang,ch:dialog.channel,op:dialog.operator,
      s:total(key).score,g:dialog.gross.bad,a:nAppeals(key),needsReview};
  });
}
/* полный пересчёт: при входе на экран и при смене данных */
function renderList(){rowsCache=listRows();renderListChrome();renderRows()}
/* сводка и фильтры; поле поиска не пересоздаётся */
function renderListChrome(){
  const all=rowsCache.filter(r=>r.s!==null),avg=all.reduce((s,r)=>s+r.s,0)/all.length;
  $('#avg').textContent=`${rowsCache.length} диалогов · средний балл ${fmt(all.length?avg:null)}`;
  const seg=[['all','Все'],['low','Требуют проверки'],['appeal','Апелляции'],['gross','Грубые ошибки']];
  $('#fKinds').innerHTML=seg.map(([k,t])=>`<button class="seg ${fKind===k?'on':''}" data-kind="${k}">${t}<small>${rowsCache.filter(KINDS[k]).length}</small></button>`).join('');
  $('#fLangs').innerHTML=['RU','KZ','EN'].map(l=>`<button class="seg ${fLang.has(l)?'on':''}" data-lang="${l}">${l}</button>`).join('');
}
/* строки таблицы: единственное, что обновляется при вводе в поиск */
function renderRows(){
  const q=$('#q').value.trim().toLowerCase();
  let v=rowsCache.filter(r=>KINDS[fKind](r)&&(!fLang.size||fLang.has(r.lang))&&(!q||r.id.toLowerCase().includes(q)||r.op.toLowerCase().includes(q)));
  if(sortDir)v=v.slice().sort((a,b)=>(a.s-b.s)*sortDir);
  $('#sortScore').textContent='Балл'+(sortDir===1?' ↑':sortDir===-1?' ↓':'');
  $('#rows').innerHTML=v.map(r=>`<tr data-key="${r.key}"><td class="did">${r.id}</td><td>${r.lang}</td><td>${r.ch}</td><td>${esc(r.op)}</td>
    <td class="r ${r.s<60?'low-score':''}">${fmt(r.s)}</td>
    <td>${r.g?'<span class="fl g">Грубая ошибка</span>':''}${r.a?'<span class="fl">Апелляция</span>':''}${r.needsReview?'<span class="fl">Требует проверки</span>':''}</td></tr>`).join('');
  $('#none').hidden=v.length>0;
}
$('#q').oninput=renderRows;
$('#filters').onclick=e=>{
  const k=e.target.closest('[data-kind]'),l=e.target.closest('[data-lang]');
  if(k){fKind=k.dataset.kind;renderListChrome();renderRows()}
  if(l){const x=l.dataset.lang;fLang.has(x)?fLang.delete(x):fLang.add(x);renderListChrome();renderRows()}
};
$('#rows').onclick=e=>{
  const tr=e.target.closest('tr');if(!tr)return;
  go('#/card/'+tr.dataset.key);
};
$('#sortScore').onclick=()=>{sortDir=sortDir===1?-1:1;renderRows()};
