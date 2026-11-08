/* Общие события, окно прогресса, тема, запуск. */
/* ================= ОБЩИЕ СОБЫТИЯ ================= */
document.addEventListener('click',async e=>{
  const g=e.target.closest('[data-go-msg]');
  if(g&&$('#m'+g.dataset.goMsg)){
    $$('.m.mark').forEach(m=>m.classList.remove('mark'));
    const grp=g.closest('.ev');
    (grp?[...grp.querySelectorAll('[data-go-msg]')]:[g]).forEach(b=>{
      const m=$('#m'+b.dataset.goMsg);
      if(m){m.classList.add('mark');motion(m.querySelector('.b')||m,[{transform:'scale(1.025)'},{transform:'none'}],300)}
    });
    const tgt=$('#m'+g.dataset.goMsg),sg=tgt.closest('details');if(sg)sg.open=true;
    tgt.scrollIntoView({block:'center'});
    seekTo(+g.dataset.goMsg);
  }
  const sk=e.target.closest('[data-seek]');if(sk&&$('#aud'))seekTo(+sk.dataset.seek);
  const gc=e.target.closest('[data-goto-crit]');
  if(gc){
    const row=$(`.cr[data-id="${gc.dataset.gotoCrit}"]`);
    if(row){
      row.scrollIntoView({block:'center',behavior:reduceMotion()?'auto':'smooth'});
      motion(row,[{backgroundColor:'var(--mark)'},{backgroundColor:'transparent'}],1100);
    }
  }
  const gr=e.target.closest('[data-go-range]');
  if(gr){
    const [a,b]=gr.dataset.goRange.split('-').map(Number);
    $$('.m.mark').forEach(m=>m.classList.remove('mark'));
    for(let n=a;n<=b;n++){
      const m=$('#m'+n);
      if(m){m.classList.add('mark');motion(m.querySelector('.b')||m,[{transform:'scale(1.025)'},{transform:'none'}],300)}
    }
    const first=$('#m'+a);
    if(first){first.scrollIntoView({block:'center'});seekTo(a)}
  }
  const ap=e.target.closest('[data-ap]');if(ap)openAppeal(+ap.dataset.ap);
  const ai=e.target.closest('[data-ai]');
  if(ai){
    const d=ai.dataset.d,a=appeals[d][+ai.dataset.ai];
    ai.disabled=true;ai.textContent='ИИ перепроверяет…';
    try{await CQA_API.aiReview(a._id);await beLoadDialog(d,true);
      if(!$('#v-card').hidden)renderCrit();else renderAppeals()}
    catch(err){toast('Ошибка: '+err.message);ai.disabled=false}
  }
  const ro=e.target.closest('[data-rej-open]');
  if(ro){const p=ro.closest('.decide').nextElementSibling;p.hidden=false;ro.hidden=true;const t=p.querySelector('[data-r]');if(t)t.focus();return}
  const rc=e.target.closest('[data-rej-cancel]');
  if(rc){const p=rc.closest('.rej');p.hidden=true;const b=p.previousElementSibling.querySelector('[data-rej-open]');if(b)b.hidden=false;return}
  const sv=e.target.closest('[data-save]');
  if(sv){
    const id=+sv.dataset.save,d=sv.dataset.d||cur,act=sv.dataset.act||'change',box=sv.closest('.decide');
    const selEl=box.querySelector('[data-v]'),sel=selEl?selEl.value:null,reason=box.querySelector('[data-r]').value.trim();
    const c=CRIT.find(x=>x.id===id);
    if(!reason){toast('Укажите причину');box.querySelector('[data-r]').focus();return}
    if(act==='change'&&String(sel)===String(resOf(d,c).v)){toast('Выберите оценку, отличную от текущей');return}
    sv.disabled=true;
    try{await saveDecision(d,id,sel,reason,act)}catch(err){toast('Ошибка: '+err.message);sv.disabled=false;return}
    syncCount();
    if(!$('#v-card').hidden){const t=total(cur);renderScore(t);renderCrit(t)}else renderAppeals();
    toast(act==='confirm'?'Апелляция отклонена, оператор увидит причину':'Оценка изменена, итог пересчитан');
  }
});

const CHECK_SVG='<svg width="8" height="8" viewBox="0 0 8 8"><path d="M1 4.2 3.2 6.2 7 1.8" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>';

/* Демонстрационный прогресс: шаг 120 мс, весь список около секунды. */
function runProgress(title,sub,rows,done,step=120){
  $('#runTitle').textContent=title;$('#runSub').textContent=sub;
  $('#runList').innerHTML=rows.map(r=>`<div ${r.cache?'class="cache"':''}><i></i><span>${esc(r.t)}</span></div>`).join('');
  $('#runClose').disabled=true;$('#runDlg').showModal();
  const els=$$('#runList div');
  (async()=>{
    for(const el of els){
      if(el.classList.contains('cache')){await new Promise(r=>setTimeout(r,step/2));continue}
      el.classList.add('go');await new Promise(r=>setTimeout(r,step));
      el.classList.remove('go');el.classList.add('ok');el.firstChild.innerHTML=CHECK_SVG;
    }
    $('#runClose').disabled=false;
  })();
  $('#runClose').onclick=()=>{$('#runDlg').close();done&&done()};
}
/* окно «Оценить диалог»: загрузка транскрипта или набора по group_id и выбор чек-листа */
let evRecords=[],evGroupName=null;
function parseRecords(text){
  const j=JSON.parse(text);
  /* ответ API организаторов целиком ({isSuccess, data:{dataset_group_id, records}}) или файл набора: берём его имя */
  const box=j&&!Array.isArray(j)?(j.data&&j.data.records?j.data:j.records?j:null):null;
  evGroupName=box&&box.dataset_group_id?String(box.dataset_group_id):null;
  const arr=Array.isArray(j)?j:(box?box.records:[j]);
  arr.forEach(r=>{if(!r||!Array.isArray(r.transcript))throw new Error('нет поля transcript')});
  return arr;
}
function evCheck(){
  const t=$('#evText').value.trim(),info=$('#evInfo'),grp=($('#evGroup')?.value||'').trim();
  const aud=$('#evAudio')&&$('#evAudio').files[0];
  if(!t){evRecords=[];evGroupName=null;info.textContent=grp?`Набор «${grp}» будет загружен из API организаторов и оценён`:'';$('#evGo').disabled=!(grp||aud);return}
  try{
    evRecords=parseRecords(t);
    info.textContent=evRecords.slice(0,3).map(r=>`${r.conversation_id||'без ID'} · ${r.language||'?'} · ${r.transcript.length} реплик`).join('; ')+(evRecords.length>3?` и ещё ${evRecords.length-3}`:'');
    $('#evGo').disabled=false;
  }catch(e){evRecords=[];evGroupName=null;info.textContent='Не удалось прочитать: '+e.message;$('#evGo').disabled=true}
}
$('#runNew').onclick=async()=>{
  $('#evText').value='';$('#evFile').value='';$('#evAudio').value='';audioHint();if($('#evGroup'))$('#evGroup').value='';
  if(CQA_API.enabled){
    $('#evChk').innerHTML='<option>Загрузка…</option>';
    CQA_API.checklists().then(list=>{
      $('#evChk').innerHTML=list.slice().reverse().map(c=>`<option value="${c.id}" ${c.is_active?'selected':''}>${esc(c.name)}${c.is_active?' (активный)':''}</option>`).join('')||'<option value="">Активный чек-лист</option>';
    }).catch(err=>{$('#evChk').innerHTML='<option value="">Активный чек-лист</option>';toast('Ошибка: '+err.message)});
  }else $('#evChk').innerHTML=`<option>Текущий, v${ver} · ${CRIT.length} критериев</option>`;
  evCheck();$('#evDlg').showModal();
};
/* Аудио звонка: с бэкендом запись распознаётся (Gemini), сохраняется для плеера и оценивается как звонок. */
const AUDIO_HINT=()=>CQA_API.enabled?'MP3, WAV, OGG, FLAC, AAC до 15 МБ. Запись распознаётся (роли, время, персональные данные скрыты) и оценивается как звонок.'
  :'В демо-режиме запись не распознаётся: нужен бэкенд.';
function audioHint(){
  const f=$('#evAudio').files[0];
  $('#evAudioInfo').textContent=f?`${f.name} · ${(f.size/1048576).toFixed(1)} МБ. `+(CQA_API.enabled?'Будет распознана и оценена.':'Демо-режим: не распознаётся.'):AUDIO_HINT();
  evCheck();
}
$('#evAudio').onchange=audioHint;
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
      /* сначала набор по group_id: если его нет, ничего не сохраняем и ничего не оцениваем */
      if(grp){toast('Загружаем набор '+grp+'…');ids=ids.concat((await CQA_API.importGroup(grp)).conversation_ids)}
      if(recs.length)ids=ids.concat((await CQA_API.upload(recs,evGroupName)).conversation_ids);
      const aud=$('#evAudio').files[0];
      if(aud){
        $('#evInfo').textContent='Распознаём запись… обычно 20–60 секунд';
        const t=await CQA_API.transcribe(aud);
        toast(`Запись распознана: ${t.turns} реплик, язык ${t.language}, ${(t.duration_ms/1000).toFixed(0)} с, $${t.cost_usd.toFixed(3)}`);
        ids.push(t.conversation_id);
      }
      $('#evDlg').close();
      /* итог показывает само окно: «Готово N из N», открытие каждого, повтор неудавшихся */
      await beRunBatch(`Оценка: ${ids.length} диал.`,{conversation_ids:ids,checklist_id:+$('#evChk').value||null});
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
  /* пока грузятся данные с сервера, вместо пустого экрана — индикатор загрузки */
  const boot=document.createElement('div');
  boot.className='boot';boot.setAttribute('role','status');
  boot.innerHTML='<i></i><span>Загружаем диалоги и оценки…</span>';
  $('.wrap').appendChild(boot);
  if(CQA_API.enabled){try{await beLoadAll()}catch(e){err=e}}
  else{const n=$('#navStats');if(n)n.hidden=true}
  await route();
  boot.remove();
  if(err){
    toast('Бэкенд недоступен: '+err.message);
    $('#none').hidden=false;
    $('#none').innerHTML=`Не удалось подключиться к бэкенду <b>${esc(CQA_CONFIG.apiBase)}</b>. Запустите его или откройте демо: <a href="?demo=1">?demo=1</a>`;
  }
})();
