/* Сравнение версий чек-листа: одни и те же диалоги, оценённые двумя версиями (оценки ИИ до апелляций). */
/* ================= СРАВНЕНИЕ ВЕРСИЙ ================= */
let cmpState={a:0,b:0,lists:[]};
const CMP_MAX=20;   /* ~$0,016 за диалог: больше за один раз не запускаем */
const sgn=d=>d===null||d===undefined?'—':(d>0?'+':d<0?'−':'')+fmt(Math.abs(d));
const ansTxt=a=>a==='yes'?'Да':a==='no'?'Нет':a==='na'?'N/A':a;
const KIND_TXT={added:'добавлен',removed:'удалён',changed:'изменён'};
const FIELD_TXT={weight:'вес',description:'правило',scale:'шкала',type:'тип',na_allowed:'N/A',na_condition:'условие N/A',guidance:'пояснения',name:'название'};
function cmpOptions(sel,val){
  return cmpState.lists.map(c=>`<option value="${c.id}" ${c.id===val?'selected':''}>${esc(c.name)}${c.is_active?' (активный)':''}</option>`).join('');
}
async function openCompare(){
  $('#cmpOut').innerHTML='<p class="mut">Загрузка…</p>';
  $('#cmpDlg').showModal();
  try{
    const l=await CQA_API.checklists();
    cmpState.lists=l.slice().reverse();
    if(l.length<2){$('#cmpOut').innerHTML='<p class="mut">Нужны минимум две версии. Измените чек-лист и нажмите «Сохранить и применить»: появится новая версия.</p>';$('#cmpGo').disabled=true;return}
    $('#cmpGo').disabled=false;
    const act=l.find(c=>c.is_active)||l[l.length-1],prev=l.filter(c=>c.id<act.id).pop()||l[0];
    cmpState.a=prev.id;cmpState.b=act.id;
    $('#cmpA').innerHTML=cmpOptions('a',prev.id);$('#cmpB').innerHTML=cmpOptions('b',act.id);
    $('#cmpOut').innerHTML='';
    runCompare();
  }catch(e){$('#cmpOut').innerHTML=`<p class="mut">Ошибка: ${esc(e.message)}</p>`}
}
async function runCompare(){
  const a=+$('#cmpA').value,b=+$('#cmpB').value;
  if(a===b){$('#cmpOut').innerHTML='<p class="mut">Выберите две разные версии.</p>';return}
  $('#cmpOut').innerHTML='<p class="mut">Считаем…</p>';
  let r;try{r=await CQA_API.compare(a,b)}catch(e){$('#cmpOut').innerHTML=`<p class="mut">Ошибка: ${esc(e.message)}</p>`;return}
  const s=r.summary,miss=r.missing_b.filter(id=>D[id]),n=Math.min(miss.length,CMP_MAX);
  const run=miss.length?`<div class="cmp-run"><span>«${esc(r.b.name)}» не оценила диалогов: ${miss.length}, а версия «${esc(r.a.name)}» их оценивала.</span>
    <button class="btn ${s.compared?'':'primary'}" id="cmpRun">Прогнать ещё ${n}</button></div>`:'';
  const diff=r.criteria_diff.length?`<div class="cmp-diff">${r.criteria_diff.map(d=>`<span class="chip">${esc(d.name)}: ${KIND_TXT[d.kind]}${d.fields&&d.fields.length?' ('+d.fields.map(f=>FIELD_TXT[f]||f).join(', ')+')':''}</span>`).join('')}</div>`
    :'<p class="mut">Критерии в версиях одинаковые.</p>';
  let body='';
  if(s.compared){
    body=`<div class="kpis cmp-k">
      ${kpi('Сравнено диалогов',s.compared)}
      ${kpi('Средний балл',`${fmt(s.avg_a)} → ${fmt(s.avg_b)}`,`${sgn(s.avg_delta)} в среднем`)}
      ${kpi('Сдвиг по модулю',fmt(s.avg_abs_delta),`вверх ${s.moved_up} · вниз ${s.moved_down} · без изменений ${s.unchanged}`)}
    </div>
    ${r.answer_flips.length?`<div class="tr-h">Где менялись ответы</div><p class="mut">${r.answer_flips.map(f=>`${esc(f.name)}: ${f.count}`).join(' · ')}</p>`:''}
    <div class="tr-h">Диалоги с наибольшим сдвигом</div>
    <table><thead><tr><th>Диалог</th><th class="r">Было</th><th class="r">Стало</th><th class="r">Δ</th><th>Что изменилось</th></tr></thead><tbody>
    ${r.rows.slice(0,10).map(x=>`<tr ${D[x.conversation_id]?`data-cmp-conv="${esc(x.conversation_id)}"`:''}><td class="did">${esc(x.conversation_id)}</td><td class="r">${fmt(x.total_a)}</td><td class="r">${fmt(x.total_b)}</td>
      <td class="r ${x.delta<0?'low-score':x.delta>0?'up':''}">${sgn(x.delta)}</td>
      <td class="mut">${x.changed.map(c=>`${esc(c.name)}: ${esc(ansTxt(c.a))} → ${esc(ansTxt(c.b))}`).join('; ')||'ответы те же, изменились веса'}</td></tr>`).join('')}</tbody></table>`;
  }else body='<p class="mut">Общих диалогов пока нет: ни один диалог не оценён обеими версиями.</p>';
  $('#cmpOut').innerHTML=diff+run+body;
  const rb=$('#cmpRun');
  if(rb)rb.onclick=async()=>{
    rb.disabled=true;
    try{await beRunBatch('Сравнение версий',{conversation_ids:miss.slice(0,n),checklist_id:b})}
    catch(e){toast('Ошибка: '+e.message)}
    runCompare();
  };
}
$('#cmpBtn').onclick=openCompare;
$('#cmpGo').onclick=runCompare;
$('#cmpA').onchange=$('#cmpB').onchange=()=>{$('#cmpOut').innerHTML=''};
$('#cmpClose').onclick=()=>$('#cmpDlg').close();
$('#cmpOut').onclick=e=>{
  const tr=e.target.closest('[data-cmp-conv]');
  if(tr){$('#cmpDlg').close();go('#/card/'+encodeURIComponent(tr.dataset.cmpConv))}
};
if(CQA_API.enabled)$('#cmpBtn').hidden=false;
