/* Экран «Диалоги». */
/* ================= СПИСОК ================= */
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
function renderList(){
  const rows=listRows();
  const q=($('#q')?.value||'').trim().toLowerCase();
  const kinds={all:()=>true,low:r=>r.needsReview,appeal:r=>r.a>0,gross:r=>r.g};
  let v=rows.filter(r=>kinds[fKind](r)&&(!fLang.size||fLang.has(r.lang))&&(!fGroup||r.group===fGroup)
    &&(!q||r.id.toLowerCase().includes(q)||String(r.op).toLowerCase().includes(q)));
  if(sortDir)v.sort((a,b)=>((a.s??-1)-(b.s??-1))*sortDir);
  const all=v.filter(r=>r.s!==null&&r.s!==undefined),avg=all.reduce((s,r)=>s+r.s,0)/all.length;
  $('#avg').textContent=`${v.length} диалогов · средний балл ${fmt(all.length ? Math.round(avg*100)/100 : null)}`;
  const seg=[['all','Все',rows.length],['low','Требуют проверки',rows.filter(kinds.low).length],['appeal','Апелляции',rows.filter(kinds.appeal).length],['gross','Грубые ошибки',rows.filter(kinds.gross).length]];
  const groups=CQA_API.enabled&&BE.groups.length>1?'<span class="sep"></span>'+[['','Все наборы'],...BE.groups.map(g=>[g,g])]
    .map(([g,t])=>`<button class="seg ${fGroup===g?'on':''}" data-group="${esc(g)}">${esc(t)}</button>`).join(''):'';
  $('#filters').innerHTML=seg.map(([k,t,n])=>`<button class="seg ${fKind===k?'on':''}" data-kind="${k}">${t}<small>${n}</small></button>`).join('')
    +'<span class="sep"></span>'+['RU','KZ','EN'].map(l=>`<button class="seg ${fLang.has(l)?'on':''}" data-lang="${l}">${l}</button>`).join('')
    +groups+'<span class="sep"></span><input class="field search" id="q" placeholder="Поиск" aria-label="Поиск" value="'+esc(q)+'">';
  $('#q').oninput=e=>{const pos=e.target.selectionStart;renderList();const n=$('#q');n.focus();n.setSelectionRange(pos,pos)};
  $('#sortScore').textContent='Балл'+(sortDir===1?' ↑':sortDir===-1?' ↓':'');
  $('#rows').innerHTML=v.map(r=>`<tr data-key="${esc(r.key)}"><td class="did">${esc(r.id)}</td><td>${r.lang}</td><td>${r.ch}</td><td>${esc(r.op)}</td>
    <td class="r ${r.s!==null&&r.s<60?'low-score':''}">${fmt(r.s)}</td>
    <td>${r.g?'<span class="fl g">Грубая ошибка</span>':''}${r.a?'<span class="fl">Апелляция</span>':''}${r.needsReview?'<span class="fl">Требует проверки</span>':''}${statusTag(r)}</td></tr>`).join('');
  $('#none').hidden=v.length>0;
  if(!rows.length&&CQA_API.enabled)$('#none').textContent='Диалогов нет. Нажмите «Оценить новые» и загрузите набор по group_id.';
}
$('#filters').onclick=e=>{
  const k=e.target.closest('[data-kind]'),l=e.target.closest('[data-lang]'),g=e.target.closest('[data-group]');
  if(k){fKind=k.dataset.kind;renderList()}
  if(l){const x=l.dataset.lang;fLang.has(x)?fLang.delete(x):fLang.add(x);renderList()}
  if(g){fGroup=g.dataset.group;renderList()}
};
$('#rows').onclick=e=>{
  const tr=e.target.closest('tr');if(!tr)return;
  go('#/card/'+encodeURIComponent(tr.dataset.key));
};
$('#sortScore').onclick=()=>{sortDir=sortDir===1?-1:1;renderList()};
