/* Общие события, окно прогресса, тема, запуск. */
/* ================= ОБЩИЕ СОБЫТИЯ ================= */
document.addEventListener('click',async e=>{
  const g=e.target.closest('[data-go-msg]');
  if(g&&$('#m'+g.dataset.goMsg)){
    $$('.m.mark').forEach(m=>m.classList.remove('mark'));
    void document.body.offsetWidth;
    const grp=g.closest('.ev');
    (grp?[...grp.querySelectorAll('[data-go-msg]')]:[g]).forEach(b=>{const m=$('#m'+b.dataset.goMsg);if(m)m.classList.add('mark')});
    $('#m'+g.dataset.goMsg).scrollIntoView({block:'center'});
    seekTo(+g.dataset.goMsg);
  }
  const sk=e.target.closest('[data-seek]');if(sk&&$('#aud'))seekTo(+sk.dataset.seek);
  const ap=e.target.closest('[data-ap]');if(ap)openAppeal(+ap.dataset.ap);
  const ai=e.target.closest('[data-ai]');
  if(ai){
    const d=ai.dataset.d,a=appeals[d][+ai.dataset.ai];
    ai.disabled=true;ai.textContent='ИИ перепроверяет…';
    try{await CQA_API.aiReview(a._id);await beLoadDialog(d,true);
      if(!$('#v-card').hidden)renderCrit();else renderAppeals()}
    catch(err){toast('Ошибка: '+err.message);ai.disabled=false}
  }
  const sv=e.target.closest('[data-save]');
  if(sv){
    const id=+sv.dataset.save,d=sv.dataset.d||cur,act=sv.dataset.act||'change',box=sv.closest('.decide');
    const sel=box.querySelector('[data-v]').value,reason=box.querySelector('[data-r]').value.trim();
    const c=CRIT.find(x=>x.id===id);
    if(!reason){toast('Укажите причину');box.querySelector('[data-r]').focus();return}
    if(act==='change'&&String(sel)===String(resOf(d,c).v)){toast('Выберите оценку, отличную от текущей');return}
    sv.disabled=true;
    try{await saveDecision(d,id,sel,reason,act)}catch(err){toast('Ошибка: '+err.message);sv.disabled=false;return}
    syncCount();
    if(!$('#v-card').hidden){renderScore();renderCrit()}else renderAppeals();
    toast(act==='confirm'?'Оценка подтверждена':'Оценка изменена, итог пересчитан');
  }
});

/* прогресс оценки (демо-режим) */
function runProgress(title,sub,rows,done){
  $('#runTitle').textContent=title;$('#runSub').textContent=sub;
  $('#runList').innerHTML=rows.map(r=>`<div ${r.cache?'class="cache"':''}><i></i>${esc(r.t)}</div>`).join('');
  $('#runClose').disabled=true;$('#runDlg').showModal();
  const els=$$('#runList div');
  (async()=>{
    for(const el of els){
      if(el.classList.contains('cache')){await new Promise(r=>setTimeout(r,200));continue}
      el.classList.add('go');await new Promise(r=>setTimeout(r,500));el.classList.remove('go');el.classList.add('ok');el.firstChild.innerHTML='<svg width="8" height="8" viewBox="0 0 8 8"><path d="M1 4.2 3.2 6.2 7 1.8" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>';
    }
    $('#runClose').disabled=false;
  })();
  $('#runClose').onclick=()=>{$('#runDlg').close();done&&done()};
}
/* окно «Оценить диалог»: загрузка транскрипта или набора по group_id и выбор чек-листа */
let evRecords=[];
function parseRecords(text){
  const j=JSON.parse(text);
  const arr=Array.isArray(j)?j:(j.data&&j.data.records?j.data.records:[j]);
  arr.forEach(r=>{if(!r||!Array.isArray(r.transcript))throw new Error('нет поля transcript')});
  return arr;
}
function evCheck(){
  const t=$('#evText').value.trim(),info=$('#evInfo'),grp=($('#evGroup')?.value||'').trim();
  if(!t){evRecords=[];info.textContent=grp?`Набор «${grp}» будет загружен из API организаторов и оценён`:'';$('#evGo').disabled=!grp;return}
  try{
    evRecords=parseRecords(t);
    info.textContent=evRecords.slice(0,3).map(r=>`${r.conversation_id||'без ID'} · ${r.language||'?'} · ${r.transcript.length} реплик`).join('; ')+(evRecords.length>3?` и ещё ${evRecords.length-3}`:'');
    $('#evGo').disabled=false;
  }catch(e){evRecords=[];info.textContent='Не удалось прочитать: '+e.message;$('#evGo').disabled=true}
}
$('#runNew').onclick=async()=>{
  $('#evText').value='';$('#evFile').value='';if($('#evGroup'))$('#evGroup').value='';
  if(CQA_API.enabled){
    $('#evChk').innerHTML='<option>Загрузка…</option>';
    CQA_API.checklists().then(list=>{
      $('#evChk').innerHTML=list.slice().reverse().map(c=>`<option value="${c.id}" ${c.is_active?'selected':''}>${esc(c.name)}${c.is_active?' (активный)':''}</option>`).join('');
    }).catch(err=>toast('Ошибка: '+err.message));
  }else $('#evChk').innerHTML=`<option>Текущий, v${ver} · ${CRIT.length} критериев</option>`;
  evCheck();$('#evDlg').showModal();
};
$('#evFile').onchange=async e=>{const f=e.target.files[0];if(f){$('#evText').value=await f.text();evCheck()}};
$('#evText').oninput=evCheck;
if($('#evGroup'))$('#evGroup').oninput=evCheck;
$('#evNo').onclick=()=>$('#evDlg').close();
$('#evGo').onclick=async()=>{
  const recs=evRecords.slice(),grp=($('#evGroup')?.value||'').trim();
  if(CQA_API.enabled){
    $('#evGo').disabled=true;
    try{
      let ids=[];
      if(recs.length)ids=ids.concat((await CQA_API.upload(recs)).conversation_ids);
      if(grp){toast('Загружаем набор '+grp+'…');ids=ids.concat((await CQA_API.importGroup(grp)).conversation_ids)}
      $('#evDlg').close();
      const s=await beRunBatch(`Оценка: ${ids.length} диал.`,{conversation_ids:ids,checklist_id:+$('#evChk').value||null});
      await beRefreshAfterBatch();
      toast(`Готово: ${s.done} из ${s.total}`+(s.error?`, ошибок ${s.error}`:''));
    }catch(err){toast('Ошибка: '+err.message)}
    finally{$('#evGo').disabled=false}
    return;
  }
  $('#evDlg').close();
  runProgress(`Оценка: ${recs.length} диал.`,'Демонстрационный режим: бэкенд не подключён',
    CRIT.map(c=>({t:c.name})).concat([{t:'Грубые ошибки'}]),()=>toast('Демо: результат не сохраняется'));
};

function syncTheme(){
  const cur=document.documentElement.dataset.theme;
  $$('[data-theme-set]').forEach(b=>b.setAttribute('aria-pressed',b.dataset.themeSet===cur));
}
$$('[data-theme-set]').forEach(b=>b.onclick=()=>{
  document.documentElement.dataset.theme=b.dataset.themeSet;
  syncTheme();
  try{localStorage.setItem('cqa-theme',b.dataset.themeSet)}catch(_){}
});
try{const s=localStorage.getItem('cqa-theme');if(s)document.documentElement.dataset.theme=s}catch(_){}
if(CQA_CONFIG.theme)document.documentElement.dataset.theme=CQA_CONFIG.theme;
if(CQA_CONFIG.embed)document.body.classList.add('embed');
syncTheme();
(async()=>{
  let err=null;
  if(CQA_API.enabled){try{await beLoadAll()}catch(e){err=e}}
  else{const n=$('#navStats');if(n)n.hidden=true}
  await route();
  if(err){
    toast('Бэкенд недоступен: '+err.message);
    $('#none').hidden=false;
    $('#none').innerHTML=`Не удалось подключиться к бэкенду <b>${esc(CQA_CONFIG.apiBase)}</b>. Запустите его или откройте демо: <a href="?demo=1">?demo=1</a>`;
  }
})();
