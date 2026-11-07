/* Экран «Диалоги». */
/* ================= СПИСОК ================= */
const KINDS={all:()=>true,low:r=>r.needsReview,appeal:r=>r.a>0,gross:r=>r.g};
let rowsCache=[];
let fGroup='';
function listRows(){
  return Object.entries(D).map(([key,dialog])=>{
    const s=dialog.summary;
    if(!dialog.loaded&&CQA_API.enabled){
      const done=s&&s.status==='done';
      return {key,id:dialog.id,lang:dialog.lang,ch:dialog.channel,op:dialog.operator,group:dialog.group,
        s:done?s.final_total:null,g:!!(done&&s.gross_error),a:(s&&s.open_appeals)||0,needsReview:!!(done&&s.needs_review),
        status:s?s.status:'none'};
    }
    const needsReview=CRIT.some(c=>!pending(key,c)&&dialog.res[c.id].conf<.65);
    const anyRes=CRIT.some(c=>!pending(key,c));
    return {key,id:dialog.id,lang:dialog.lang,ch:dialog.channel,op:dialog.operator,group:dialog.group,
      s:total(key).score,g:dialog.gross.bad,a:nAppeals(key),needsReview,
      status:dialog.running?'running':(anyRes||!CQA_API.enabled?'done':(s?s.status:'none'))};
  });
}
const statusTag=r=>r.status==='running'||r.status==='pending'?'<span class="fl">Оценивается</span>'
  :r.status==='error'?'<span class="fl g">Ошибка оценки</span>':r.status==='none'?'<span class="fl">Не оценён</span>':'';
/* полный пересчёт: при входе на экран и при смене данных */
function renderList(){rowsCache=listRows();renderListChrome();renderRows()}
/* фильтры и счётчики; поле поиска не пересоздаётся */
function renderListChrome(){
  const seg=[['all','Все'],['low','Требуют проверки'],['appeal','Апелляции'],['gross','Грубые ошибки']];
  $('#fKinds').innerHTML=seg.map(([k,t])=>`<button class="seg ${fKind===k?'on':''}" data-kind="${k}">${t}<small>${rowsCache.filter(KINDS[k]).length}</small></button>`).join('');
  $('#fLangs').innerHTML=['RU','KZ','EN'].map(l=>`<button class="seg ${fLang.has(l)?'on':''}" data-lang="${l}">${l}</button>`).join('');
  $('#fGroups').innerHTML=CQA_API.enabled&&BE.groups.length>1?'<span class="sep"></span>'+[['','Все наборы'],...BE.groups.map(g=>[g,g])]
    .map(([g,t])=>`<button class="seg ${fGroup===g?'on':''}" data-group="${esc(g)}">${esc(t)}</button>`).join(''):'';
}
/* строки таблицы: единственное, что обновляется при вводе в поиск */
function renderRows(){
  const rows=rowsCache;
  const q=$('#q').value.trim().toLowerCase();
  let v=rows.filter(r=>KINDS[fKind](r)&&(!fLang.size||fLang.has(r.lang))&&(!fGroup||r.group===fGroup)
    &&(!q||r.id.toLowerCase().includes(q)||String(r.op).toLowerCase().includes(q)));
  if(sortDir)v=v.slice().sort((a,b)=>((a.s??-1)-(b.s??-1))*sortDir);
  const all=v.filter(r=>r.s!==null&&r.s!==undefined),avg=all.reduce((s,r)=>s+r.s,0)/all.length;
  $('#avg').textContent=`${v.length} диалогов · средний балл ${fmt(all.length ? Math.round(avg*100)/100 : null)}`;
  $('#sortScore').textContent='Балл'+(sortDir===1?' ↑':sortDir===-1?' ↓':'');
  $('#rows').innerHTML=v.map(r=>`<tr data-key="${esc(r.key)}"><td class="did">${esc(r.id)}</td><td>${r.lang}</td><td>${r.ch}</td><td>${esc(r.op)}</td>
    <td class="r ${r.s!==null&&r.s<60?'low-score':''}">${fmt(r.s)}</td>
    <td>${r.g?'<span class="fl g">Грубая ошибка</span>':''}${r.a?'<span class="fl">Апелляция</span>':''}${r.needsReview?'<span class="fl">Требует проверки</span>':''}${statusTag(r)}</td></tr>`).join('');
  $('#none').hidden=v.length>0;
  if(!rows.length&&CQA_API.enabled)$('#none').textContent='Диалогов нет. Нажмите «Оценить новые» и загрузите набор по group_id.';
}
$('#q').oninput=renderRows;
$('#filters').onclick=e=>{
  const k=e.target.closest('[data-kind]'),l=e.target.closest('[data-lang]'),g=e.target.closest('[data-group]');
  if(k){fKind=k.dataset.kind;renderListChrome();renderRows()}
  if(l){const x=l.dataset.lang;fLang.has(x)?fLang.delete(x):fLang.add(x);renderListChrome();renderRows()}
  if(g){fGroup=g.dataset.group;renderListChrome();renderRows()}
};
$('#rows').onclick=e=>{
  const tr=e.target.closest('tr');if(!tr)return;
  go('#/card/'+encodeURIComponent(tr.dataset.key));
};
$('#sortScore').onclick=()=>{sortDir=sortDir===1?-1:1;renderRows()};
