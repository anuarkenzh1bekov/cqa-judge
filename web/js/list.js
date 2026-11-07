/* Экран «Диалоги». */
/* ================= СПИСОК ================= */
function listRows(){
  return Object.entries(D).map(([key,dialog])=>{
    const needsReview=CRIT.some(c=>!pending(key,c)&&dialog.res[c.id].conf<.65);
    return {key,id:dialog.id,lang:dialog.lang,ch:dialog.channel,op:dialog.operator,
      s:total(key).score,g:dialog.gross.bad,a:nAppeals(key),needsReview};
  });
}
function renderList(){
  const rows=listRows();
  const q=($('#q')?.value||'').trim().toLowerCase();
  const kinds={all:()=>true,low:r=>r.needsReview,appeal:r=>r.a>0,gross:r=>r.g};
  let v=rows.filter(r=>kinds[fKind](r)&&(!fLang.size||fLang.has(r.lang))&&(!q||r.id.includes(q)||r.op.toLowerCase().includes(q)));
  if(sortDir)v.sort((a,b)=>(a.s-b.s)*sortDir);
  const all=rows.filter(r=>r.s!==null),avg=all.reduce((s,r)=>s+r.s,0)/all.length;
  $('#avg').textContent=`${rows.length} диалогов · средний балл ${fmt(all.length ? avg : null)}`;
  const seg=[['all','Все',rows.length],['low','Требуют проверки',rows.filter(kinds.low).length],['appeal','Апелляции',rows.filter(kinds.appeal).length],['gross','Грубые ошибки',rows.filter(kinds.gross).length]];
  $('#filters').innerHTML=seg.map(([k,t,n])=>`<button class="seg ${fKind===k?'on':''}" data-kind="${k}">${t}<small>${n}</small></button>`).join('')
    +'<span class="sep"></span>'+['RU','KZ','EN'].map(l=>`<button class="seg ${fLang.has(l)?'on':''}" data-lang="${l}">${l}</button>`).join('')
    +'<span class="sep"></span><input class="field search" id="q" placeholder="Поиск" aria-label="Поиск" value="'+esc(q)+'">';
  $('#q').oninput=e=>{const pos=e.target.selectionStart;renderList();const n=$('#q');n.focus();n.setSelectionRange(pos,pos)};
  $('#sortScore').textContent='Балл'+(sortDir===1?' ↑':sortDir===-1?' ↓':'');
  $('#rows').innerHTML=v.map(r=>`<tr data-key="${r.key}"><td class="did">${r.id}</td><td>${r.lang}</td><td>${r.ch}</td><td>${esc(r.op)}</td>
    <td class="r ${r.s<60?'low-score':''}">${fmt(r.s)}</td>
    <td>${r.g?'<span class="fl g">Грубая ошибка</span>':''}${r.a?'<span class="fl">Апелляция</span>':''}${r.needsReview?'<span class="fl">Требует проверки</span>':''}</td></tr>`).join('');
  $('#none').hidden=v.length>0;
}
$('#filters').onclick=e=>{
  const k=e.target.closest('[data-kind]'),l=e.target.closest('[data-lang]');
  if(k){fKind=k.dataset.kind;renderList()}
  if(l){const x=l.dataset.lang;fLang.has(x)?fLang.delete(x):fLang.add(x);renderList()}
};
$('#rows').onclick=e=>{
  const tr=e.target.closest('tr');if(!tr)return;
  go('#/card/'+tr.dataset.key);
};
$('#sortScore').onclick=()=>{sortDir=sortDir===1?-1:1;renderList()};
