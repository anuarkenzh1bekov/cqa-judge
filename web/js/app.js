/* Общие события, окно прогресса, тема, запуск. */
/* ================= ОБЩИЕ СОБЫТИЯ ================= */
document.addEventListener('click',e=>{
  const g=e.target.closest('[data-go-msg]');
  if(g){
    $$('.m.mark').forEach(m=>m.classList.remove('mark'));
    [...g.closest('.ev').querySelectorAll('[data-go-msg]')].forEach(b=>$('#m'+b.dataset.goMsg).classList.add('mark'));
    $('#m'+g.dataset.goMsg).scrollIntoView({block:'center'});
  }
  const ap=e.target.closest('[data-ap]');if(ap)openAppeal(+ap.dataset.ap);
  const sv=e.target.closest('[data-save]');
  if(sv){
    const id=+sv.dataset.save,d=sv.dataset.d||cur,act=sv.dataset.act||'change',box=sv.closest('.decide');
    const sel=box.querySelector('[data-v]').value,reason=box.querySelector('[data-r]').value.trim();
    const c=CRIT.find(x=>x.id===id);
    if(!reason){toast('Укажите причину');box.querySelector('[data-r]').focus();return}
    if(act==='change'&&String(sel)===String(resOf(d,c).v)){toast('Выберите оценку, отличную от текущей');return}
    saveDecision(d,id,sel,reason,act);syncCount();
    if(!$('#v-card').hidden){renderScore();renderCrit()}else renderAppeals();
    toast(act==='confirm'?'Оценка подтверждена':'Оценка изменена, итог пересчитан');
  }
});

/* прогресс оценки */
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
/* окно «Оценить диалог»: загрузка транскрипта и выбор чек-листа */
let evRecords=[];
function parseRecords(text){
  const j=JSON.parse(text);
  const arr=Array.isArray(j)?j:(j.data&&j.data.records?j.data.records:[j]);
  arr.forEach(r=>{if(!r||!Array.isArray(r.transcript))throw new Error('нет поля transcript')});
  return arr;
}
function evCheck(){
  const t=$('#evText').value.trim(),info=$('#evInfo');
  if(!t){evRecords=[];info.textContent='';$('#evGo').disabled=true;return}
  try{
    evRecords=parseRecords(t);
    info.textContent=evRecords.slice(0,3).map(r=>`${r.conversation_id||'без ID'} · ${r.language||'?'} · ${r.transcript.length} реплик`).join('; ')+(evRecords.length>3?` и ещё ${evRecords.length-3}`:'');
    $('#evGo').disabled=false;
  }catch(e){evRecords=[];info.textContent='Не удалось прочитать: '+e.message;$('#evGo').disabled=true}
}
$('#runNew').onclick=()=>{
  $('#evChk').innerHTML=`<option>Текущий, v${ver} · ${CRIT.length} критериев</option>`;
  $('#evText').value='';$('#evFile').value='';evCheck();$('#evDlg').showModal();
};
$('#evFile').onchange=async e=>{const f=e.target.files[0];if(f){$('#evText').value=await f.text();evCheck()}};
$('#evText').oninput=evCheck;
$('#evNo').onclick=()=>$('#evDlg').close();
$('#evGo').onclick=async()=>{
  const recs=evRecords.slice();$('#evDlg').close();
  if(CQA_API.enabled){
    try{await CQA_API.evaluate(recs[0],{version:ver,criteria:CRIT});toast('Ответ бэкенда получен')}
    catch(e){toast('Ошибка бэкенда: '+e.message)}
    return;
  }
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
route();
