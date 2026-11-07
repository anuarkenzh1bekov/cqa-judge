/* Экран «Апелляции»: очередь и решение проверяющего. */
/* ================= АПЕЛЛЯЦИИ ================= */
function renderAppeals(){
  const items=[];
  Object.keys(D).forEach(d=>Object.keys(appeals[d]).forEach(id=>{const c=CRIT.find(x=>x.id==id);if(c&&!pending(d,c))items.push({d,c})}));
  if(!items.length){$('#apList').innerHTML='<div class="empty">Апелляций нет</div>';$('#apDetail').innerHTML='';return}
  if(!apSel||!items.some(i=>i.d===apSel.d&&i.c.id===apSel.id))apSel={d:items[0].d,id:items[0].c.id};
  $('#apList').innerHTML=items.map(({d,c})=>{
    const a=appeals[d][c.id],on=apSel.d===d&&apSel.id===c.id;
    return `<button class="ap-item ${on?'on':''}" data-d="${d}" data-id="${c.id}"><b>${D[d].id}</b><span>${esc(c.name)} · ${a.decision?'решено':'на проверке'}</span></button>`;
  }).join('');
  const d=apSel.d,c=CRIT.find(x=>x.id===apSel.id),a=appeals[d][c.id],r=resOf(d,c);
  const idx=new Set();r.ev.forEach(n=>[n-1,n,n+1].forEach(k=>{if(k>=1&&k<=D[d].msgs.length)idx.add(k)}));
  const frag=msgList(d,[...idx].sort((x,y)=>x-y).map(n=>n-1),{noId:true,marks:r.ev});
  $('#apDetail').innerHTML=`<div class="panel ap-d">
    <div class="meta"><span>${D[d].id}</span><span>${D[d].lang}</span><span>${esc(D[d].operator)}</span></div>
    <h2>${esc(c.name)}</h2>
    <div class="cmp"><div><small>Оценка модели</small><b>${label(c,r.v)}</b></div><div><small>${a.decision?'Решение':'Итог сейчас'}</small><b>${label(c,a.decision?a.decision.v:r.v)}</b></div></div>
    <div class="st">${esc(a.text)}</div>
    <p class="why" style="margin-top:12px">${esc(r.why)}</p>
    <div class="frag">${frag}</div>
    ${a.decision?`<div class="hist"><div class="st done">${a.decision.act==='confirm'?'Оценка подтверждена':'Оценка изменена'}. ${esc(a.decision.reason)}</div><div>Итог диалога: ${fmt(total(d,true).score)} → <b>${fmt(total(d).score)}</b></div></div>`:decideForm(d,c,a)}
    <div style="margin-top:16px"><button class="tx" data-open="${d}">Открыть диалог</button></div>
  </div>`;
}
$('#apList').onclick=e=>{const b=e.target.closest('.ap-item');if(!b)return;apSel={d:b.dataset.d,id:+b.dataset.id};renderAppeals()};
$('#apDetail').onclick=e=>{const o=e.target.closest('[data-open]');if(o)go('#/card/'+o.dataset.open)};
