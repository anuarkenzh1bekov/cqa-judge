/* Экран «Аналитика» (для администратора): по последней оценке каждого диалога, финальные баллы после апелляций. */
/* ================= АНАЛИТИКА ================= */
let opSel=null;
const pct=v=>v==null?'—':fmt(v)+'%';
function kpi(t,v,sub){return `<div class="panel kpi"><small>${t}</small><b>${v}</b>${sub?`<span>${sub}</span>`:''}</div>`}
function bar(v,max){const w=max?Math.max(2,Math.round(v/max*100)):0;return `<span class="bar"><i style="width:${w}%"></i></span>`}
function groupTable(title,obj){
  const rows=Object.entries(obj).sort((a,b)=>(b[1].avg_total??0)-(a[1].avg_total??0));
  return `<div class="panel tbl st-t"><div class="tr-h">${title}</div><table><thead><tr><th></th><th class="r">Диалогов</th><th class="r">Средний балл</th><th class="r">Грубые ошибки</th></tr></thead><tbody>
    ${rows.map(([k,v])=>`<tr><td>${esc(k)}</td><td class="r">${v.count}</td><td class="r ${v.avg_total!==null&&v.avg_total<60?'low-score':''}">${fmt(v.avg_total)}</td><td class="r">${v.gross_errors||''}</td></tr>`).join('')}</tbody></table></div>`;
}
async function renderStats(){
  const box=$('#statsBody');
  if(!CQA_API.enabled){box.innerHTML='<div class="empty">Аналитика доступна при подключённом бэкенде</div>';return}
  box.innerHTML='<div class="empty">Загрузка…</div>';
  let s;try{s=await CQA_API.stats()}catch(e){box.innerHTML=`<div class="empty">Ошибка: ${esc(e.message)}</div>`;return}
  const o=s.overview,dist=s.score_distribution,maxD=Math.max(1,...Object.values(dist));
    box.innerHTML=`
  <div class="kpis">
    ${kpi('Оценено диалогов',o.evaluated_conversations)}
    ${kpi('Средний балл',fmt(o.avg_total),o.avg_initial_total!==o.avg_total?`до апелляций ${fmt(o.avg_initial_total)}`:'')}
    ${kpi('С грубыми ошибками',o.gross_error_conversations)}
    ${kpi('Критериев на проверку',o.criteria_needing_review,'нужен взгляд проверяющего')}
    ${kpi('Апелляции',s.appeals.total||0,s.appeals.total?`изменено ${s.appeals.changed||0} · ${pct(s.appeals.change_rate_pct)} решений`:'')}
  </div>
  <div class="st-grid">
    <div class="panel box"><h3>Распределение баллов</h3>
      ${['85-100','70-84','50-69','0-49','n/a'].filter(k=>dist[k]).map(k=>`<div class="wl"><span class="t">${k}</span>${bar(dist[k],maxD)}<span>${dist[k]}</span></div>`).join('')}</div>
  </div>
  <div class="panel tbl st-t"><div class="tr-h">Критерии — от самых проблемных</div><table><thead><tr><th>Критерий</th><th class="r">Средний % балла</th><th class="r">N/A</th><th>Ответы</th></tr></thead><tbody>
    ${s.by_criterion.map(c=>`<tr><td>${esc(c.name||c.key)}</td><td class="r ${c.avg_score_pct!==null&&c.avg_score_pct<60?'low-score':''}">${pct(c.avg_score_pct)}</td><td class="r">${pct(c.na_rate)}</td>
      <td class="mut">${Object.entries(c.answers).map(([a,n])=>`${a==='yes'?'Да':a==='no'?'Нет':a==='na'?'N/A':a}: ${n}`).join(' · ')}</td></tr>`).join('')}</tbody></table></div>
  <div class="st-grid">${groupTable('По языкам',s.by_language)}${groupTable('По каналам',s.by_channel)}</div>
  <div class="st-grid">
    <div class="panel tbl st-t"><div class="tr-h">Операторы <small class="mut">— нажмите, чтобы открыть рекомендации</small></div><table><thead><tr><th>Оператор</th><th class="r">Диалогов</th><th class="r">Средний балл</th><th class="r">Грубые</th></tr></thead><tbody id="opRows">
      ${Object.entries(s.by_operator).sort((a,b)=>(a[1].avg_total??999)-(b[1].avg_total??999)).map(([k,v])=>`<tr data-op="${esc(k)}" class="${opSel===k?'on':''}"><td>${esc(k)}</td><td class="r">${v.count}</td><td class="r ${v.avg_total!==null&&v.avg_total<60?'low-score':''}">${fmt(v.avg_total)}</td><td class="r">${v.gross_errors||''}</td></tr>`).join('')}</tbody></table></div>
    <div id="opCard"></div>
  </div>
  <div class="st-grid">
    <div class="panel tbl st-t"><div class="tr-h">Самые низкие баллы</div><table><tbody>
      ${s.lowest.map(x=>`<tr data-conv="${esc(x.conversation_id)}"><td class="did">${esc(x.conversation_id)}</td><td class="r low-score">${fmt(x.total)}</td><td>${x.gross_error?'<span class="fl g">Грубая ошибка</span>':''}</td></tr>`).join('')}</tbody></table></div>
    <div class="panel tbl st-t"><div class="tr-h">Грубые ошибки</div><table><tbody>
      ${s.gross_errors.map(x=>`<tr data-conv="${esc(x.conversation_id)}"><td class="did">${esc(x.conversation_id)}</td><td>${esc(x.explanation||'')}</td></tr>`).join('')||'<tr><td class="mut">Не выявлено</td></tr>'}</tbody></table></div>
  </div>`;
  if(opSel)renderOperator(opSel);
}
async function renderOperator(name){
  opSel=name;$$('#opRows tr').forEach(t=>t.classList.toggle('on',t.dataset.op===name));
  const box=$('#opCard');box.innerHTML='<div class="panel box">Загрузка…</div>';
  let p;try{p=await CQA_API.operator(name)}catch(e){box.innerHTML=`<div class="panel box">Ошибка: ${esc(e.message)}</div>`;return}
  const areas=p.most_frequent_improvement_areas.map(([k,n])=>{const c=p.criteria.find(x=>x.key===k);return `${esc(c?c.name:k)} (${n})`}).join(', ');
  box.innerHTML=`<div class="panel box op-card"><h3>Оператор</h3><h2>${esc(p.operator)} · ${fmt(p.avg_total)}</h2>
    ${areas?`<p class="mut">Чаще всего зоны роста: ${areas}</p>`:''}
    <ul class="fbl">${p.improvements.slice(0,12).map(i=>`<li class="ev"><button class="lk" data-conv="${esc(i.conversation_id)}">${esc(i.conversation_id)}</button> ${esc(i.text)}${i.example_phrase?`<span class="q">Можно сказать: «${esc(i.example_phrase)}»</span>`:''}</li>`).join('')||'<li class="mut">Рекомендаций нет</li>'}</ul></div>`;
}
$('#v-stats').addEventListener('click',e=>{
  const op=e.target.closest('[data-op]');if(op){renderOperator(op.dataset.op);return}
  const cv=e.target.closest('[data-conv]');if(cv&&D[cv.dataset.conv])go('#/card/'+encodeURIComponent(cv.dataset.conv));
});
