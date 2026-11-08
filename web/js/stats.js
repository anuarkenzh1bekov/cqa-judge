/* Экран «Аналитика» (для администратора): по последней оценке каждого диалога, финальные баллы после апелляций. */
/* ================= АНАЛИТИКА ================= */
let opSel=null;
const pct=v=>v==null?'—':fmt(v)+'%';
function kpi(t,v,sub){return `<div class="panel kpi"><small>${t}</small><b>${v}</b>${sub?`<span>${sub}</span>`:''}</div>`}
function bar(v,max){const w=max?Math.max(2,Math.round(v/max*100)):0;return `<span class="bar"><i style="width:${w}%"></i></span>`}
/* Тепловая карта: слабые места видны сразу — красное = критерий проседает у оператора */
function heatmapHtml(h){
  if(!h||!h.operators.length||!h.criteria.length)return '';
  const cell=v=>v==null?'<td class="c nil">—</td>':`<td class="c" style="--v:${Math.max(0,Math.min(1,v/100)).toFixed(2)}" title="${fmt(v)}%">${Math.round(v)}</td>`;
  return `<div class="panel box hm"><h3>Карта слабых мест: оператор × критерий <small class="mut">— средний % балла, нажмите на оператора, чтобы открыть его диалоги</small></h3>
    <table><thead><tr><th></th>${h.criteria.map(c=>`<th title="${esc(c.name)}">${esc(c.name.length>22?c.name.slice(0,21)+'…':c.name)}</th>`).join('')}<th>Итого</th></tr></thead><tbody>
    ${h.operators.map(o=>`<tr><td class="op" data-op="${esc(o.operator)}">${esc(o.operator)} <small class="mut">· ${o.count}</small></td>${h.criteria.map(c=>cell(o.cells[c.key])).join('')}${cell(o.avg)}</tr>`).join('')}</tbody></table>
    <div class="leg"><span>слабо</span><i></i><span>хорошо</span></div></div>`;
}
function groupTable(title,obj){
  const rows=Object.entries(obj).sort((a,b)=>(b[1].avg_total??0)-(a[1].avg_total??0));
  return `<div class="panel tbl st-t"><div class="tr-h">${title}</div><table><thead><tr><th></th><th class="r">Диалогов</th><th class="r">Средний балл</th><th class="r">Грубые ошибки</th></tr></thead><tbody>
    ${rows.map(([k,v])=>`<tr><td>${esc(k)}</td><td class="r">${v.count}</td><td class="r ${v.avg_total!==null&&v.avg_total<60?'low-score':''}">${fmt(v.avg_total)}</td><td class="r">${v.gross_errors||''}</td></tr>`).join('')}</tbody></table></div>`;
}
/* Калибровка: насколько проверяющие соглашаются с ИИ и учится ли ИИ на их решениях */
function trendSvg(tr){
  if(tr.length<2)return '';
  const W=220,H=48,pts=tr.map((x,i)=>`${(i/(tr.length-1)*W).toFixed(1)},${(H-(x.agreement_pct||0)/100*H).toFixed(1)}`).join(' ');
  return `<svg class="trend" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="Согласие проверяющих с ИИ по мере решений"><polyline points="${pts}" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/></svg>`;
}
function calibrationHtml(c){
  if(!c)return '';
  const o=c.overall,l=c.learning;
  if(!o.decided)return `<div class="panel box cal"><h3>Калибровка по решениям проверяющих</h3><p class="mut">Решений по апелляциям пока нет. Каждое исправление ответа ИИ станет поправкой в промпте этого критерия: ${l.enabled?`до ${l.per_criterion} последних на критерий`:'сейчас отключено в настройках'}.</p></div>`;
  const kinds={agree:'модели согласны',minor:'соседние ступени',disputed:'модели спорили, ответ перепроверен',review:'модели расходились, но не уверены',gemini_only:'только Gemini'};
  return `<div class="panel box cal"><h3>Калибровка по решениям проверяющих</h3>
    <p class="mut">Люди смотрят только спорные случаи, поэтому цифры показывают, где ИИ слабее всего, а не общую точность.</p>
    <div class="kpis">
      ${kpi('Проверяющие согласны с ИИ',pct(o.agreement_pct),`${o.confirmed} из ${o.decided} решений`)}
      ${kpi('Исправлено ответов ИИ',o.changed,'это уже поправки в промпте')}
      ${kpi('Оценок с поправками',l.evaluations_using_examples,l.enabled?`доступно поправок: ${l.examples_available}`:'обучение отключено')}
    </div>
    ${c.trend.length>1?`<div class="cal-tr"><span class="mut">Согласие с ИИ по мере решений</span>${trendSvg(c.trend)}</div>`:''}
    <table><thead><tr><th>Критерий</th><th class="r">Апелляций</th><th class="r">Исправлено</th><th class="r">Согласие</th></tr></thead><tbody>
    ${c.by_criterion.map(x=>`<tr><td>${esc(x.name)}</td><td class="r">${x.appealed}</td><td class="r">${x.changed}</td><td class="r ${x.agreement_pct!==null&&x.agreement_pct<60?'low-score':''}">${pct(x.agreement_pct)}</td></tr>`).join('')}</tbody></table>
    ${c.by_model_agreement.length?`<p class="mut cal-m">Как часто проверяющий менял ответ в зависимости от согласия моделей: ${c.by_model_agreement.map(x=>`${kinds[x.agreement]||x.agreement} — ${pct(x.changed_pct)} (${x.changed}/${x.decided})`).join('; ')}.</p>`:''}</div>`;
}
async function renderStats(){
  if(!reviewer)return renderMyStats();
  const box=$('#statsBody');
  if(!CQA_API.enabled){box.innerHTML='<div class="empty">Аналитика доступна при подключённом бэкенде</div>';return}
  const xb=$('#xlsBtn');xb.href=CQA_API.url('/api/export/stats.xlsx');xb.hidden=false;
  box.innerHTML='<div class="empty">Загрузка…</div>';
  $('#expCsv').href=CQA_API.exportUrl('csv');$('#expCsv').hidden=false;
  let s,cal=null;
  try{[s,cal]=await Promise.all([CQA_API.stats(),CQA_API.calibration().catch(()=>null)])}
  catch(e){box.innerHTML=`<div class="empty">Ошибка: ${esc(e.message)}</div>`;return}
  const o=s.overview,dist=s.score_distribution,maxD=Math.max(1,...Object.values(dist));
    box.innerHTML=`
  <div class="kpis">
    ${kpi('Оценено диалогов',o.evaluated_conversations)}
    ${kpi('Средний балл',fmt(o.avg_total),o.avg_initial_total!==o.avg_total?`до апелляций ${fmt(o.avg_initial_total)}`:'')}
    ${kpi('С грубыми ошибками',o.gross_error_conversations)}
    ${kpi('Оценены уверенно',`${o.confident_conversations} из ${o.evaluated_conversations}`,o.needs_human_conversations?`${o.needs_human_conversations} просят взгляд человека`:'человек не нужен')}
    ${kpi('Критериев на проверку',o.criteria_needing_review,'нужен взгляд проверяющего')}
    ${kpi('Апелляции',s.appeals.total||0,s.appeals.total?`изменено ${s.appeals.changed||0} · ${pct(s.appeals.change_rate_pct)} решений`:'')}
  </div>
  ${heatmapHtml(s.heatmap)}
  ${calibrationHtml(cal)}
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
    <ul class="fbl">${p.improvements.slice(0,12).map(i=>`<li class="ev"><button class="lk" data-conv="${esc(i.conversation_id)}">${esc(i.conversation_id)}</button> ${esc(i.text)}${i.example_phrase?`<span class="q">Можно сказать: «${esc(i.example_phrase)}»</span>`:''}</li>`).join('')||'<li class="mut">Рекомендаций нет</li>'}</ul><div id="coachBox"></div></div>`;
  loadCoaching(name,false);
}
const plural=(n,a,b,c)=>{const m=n%100,k=n%10;return m>10&&m<20?c:k===1?a:k>1&&k<5?b:c};
const LVL=p=>p>=85?'yes':p>=60?'warn':'no';
function coachHtml(c){
  const pct=v=>v==null?'—':Math.round(v)+'%';
  const quote=q=>q?`<span class="q">«${esc(q.text)}»</span>`:'';
  const go=id=>`<button class="lk" data-conv="${esc(id)}">${esc(id)}</button>`;
  return `<div class="coach">
    <div class="tr-h">План коучинга <small>· ${c.source==='ai'?'составлен ИИ по реальным диалогам':'по правилам критериев (ИИ недоступен)'}${c.cached?' · из кэша':''}</small>
      <button class="lk" id="coachRefresh">Обновить</button></div>
    <p class="why">${esc(c.summary)}</p>
    <p class="mut">${c.basis&&c.basis.reviewer_notes?`План опирается на ${c.basis.reviewer_notes} ${plural(c.basis.reviewer_notes,'комментарий','комментария','комментариев')} проверяющего и на цифры по диалогам. Он пересчитывается при каждом новом диалоге и комментарии.`:'Комментариев проверяющего пока нет: план строится по оценкам. Он пересчитывается при каждом новом диалоге.'}</p>
    <p class="mut">Оценено диалогов: ${c.evaluated} · средний балл ${pct(c.avg_total)} (команда ${pct(c.team_avg)})${c.trend!=null?` · динамика ${c.trend>0?'+':''}${c.trend}`:''}${c.injection_dialogs?` · попыток повлиять на оценку: ${c.injection_dialogs}`:''}</p>
    ${c.strengths.length?`<p class="why">Сильные стороны: ${c.strengths.map(s=>`<span class="mood yes">${esc(s.name)} ${pct(s.avg_pct)}</span>`).join(' ')}</p>`:''}
    ${c.focus.map((f,i)=>`<div class="coach-f"><h4>${i+1}. ${esc(f.name)} <span class="mood ${LVL(f.avg_pct)}">${pct(f.avg_pct)}</span> <small>команда ${pct(f.team_pct)}</small></h4>
      ${f.reviewer_notes&&f.reviewer_notes.length?`<ul class="fbl rn">${f.reviewer_notes.map(n=>`<li class="ev"><small>${n.source==='comment'?'Проверяющий':'Решение'} · </small>${go(n.conversation_id)} ${esc(n.text)}</li>`).join('')}</ul>`:''}
      ${f.tip?`<p class="why"><b>Что делать:</b> ${esc(f.tip)}</p>`:''}
      ${f.practice_phrase?`<span class="say"><small>Фраза для тренировки</small>«${esc(f.practice_phrase)}»</span>`:''}
      ${f.mistakes.length?`<ul class="fbl">${f.mistakes.map(m=>`<li class="ev">${go(m.conversation_id)} <small>${m.score_pct}%</small> ${esc(m.explanation||'')}${quote(m.quote)}</li>`).join('')}</ul>`:''}
      ${f.exemplar?`<p class="why"><b>Как сделал ${esc(f.exemplar.operator)}:</b> ${go(f.exemplar.conversation_id)}${quote(f.exemplar.quote)}</p>`:''}</div>`).join('')}
    ${c.weekly_plan.length?`<h4>План на неделю</h4><ol class="coach-w">${c.weekly_plan.map(x=>`<li>${esc(x)}</li>`).join('')}</ol>`:''}</div>`;
}
async function loadCoaching(name,refresh){
  const box=$('#coachBox');if(!box)return;
  box.innerHTML='<p class="mut">Составляю план коучинга…</p>';
  try{const c=await CQA_API.coaching(name,refresh);if(opSel!==name)return;box.innerHTML=coachHtml(c);
    $('#coachRefresh').onclick=()=>loadCoaching(name,true)}
  catch(e){box.innerHTML=`<p class="mut">План коучинга недоступен: ${esc(e.message)}</p>`}
}
/* клик по оператору в карте: один диалог — сразу карточка, несколько — список его диалогов, худшие сверху */
function openOperatorDialogs(name){
  const keys=Object.keys(D).filter(k=>D[k].operator===name);
  if(keys.length===1){go('#/card/'+encodeURIComponent(keys[0]));return}
  $('#q').value=name;sortDir=1;fKind='all';fLang.clear();fGroup='';listUI.has=false;go('#/list');
}
$('#v-stats').addEventListener('click',e=>{
  const hm=e.target.closest('.hm [data-op]');if(hm){openOperatorDialogs(hm.dataset.op);return}
  const op=e.target.closest('[data-op]');if(op){renderOperator(op.dataset.op);return}
  const cv=e.target.closest('[data-conv]');if(cv&&D[cv.dataset.conv])go('#/card/'+encodeURIComponent(cv.dataset.conv));
});
