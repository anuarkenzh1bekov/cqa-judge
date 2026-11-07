/* Общие события, окно прогресса, тема, запуск. */
/* ================= ОБЩИЕ СОБЫТИЯ ================= */
document.addEventListener('click',e=>{
  const g=e.target.closest('[data-go-msg]');
  if(g){
    $$('.m.mark').forEach(m=>m.classList.remove('mark'));
    [...g.closest('.ev').querySelectorAll('[data-go-msg]')].forEach(b=>{
      const m=$('#m'+b.dataset.goMsg);m.classList.add('mark');
      motion(m.querySelector('.b')||m,[{transform:'scale(1.025)'},{transform:'none'}],300);
    });
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
    if(!$('#v-card').hidden){const t=total(cur);renderScore(t);renderCrit(t)}else renderAppeals();
    toast(act==='confirm'?'Оценка подтверждена':'Оценка изменена, итог пересчитан');
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

/* Реальная обработка: по диалогу на строку, у каждой свой итог; из готовой строки можно открыть результат. */
function runJobs(title,sub,names,worker){
  $('#runTitle').textContent=title;$('#runSub').textContent=sub;
  $('#runList').innerHTML=names.map(n=>`<div><i></i><span>${esc(n)}</span></div>`).join('');
  const close=$('#runClose');close.disabled=true;close.onclick=()=>$('#runDlg').close();
  $('#runDlg').showModal();
  const els=$$('#runList div');let ok=0;
  (async()=>{
    for(let i=0;i<els.length;i++){
      const el=els[i];el.classList.add('go');
      try{
        const key=await worker(i);ok++;
        el.classList.remove('go');el.classList.add('ok');el.firstChild.innerHTML=CHECK_SVG;
        if(key){
          const b=document.createElement('button');b.className='tx';b.textContent='Открыть';
          b.onclick=()=>{$('#runDlg').close();go('#/card/'+key)};el.append(b);
        }
      }catch(e){
        el.classList.remove('go');el.classList.add('err');el.firstChild.textContent='!';
        const s=document.createElement('span');s.className='ermsg';s.textContent=e.message;el.append(s);
      }
    }
    $('#runSub').textContent=`Обработано ${ok} из ${els.length}`;
    close.disabled=false;
  })();
}

/* Ответ бэкенда: {results:{<id критерия>:{v,ev,why,q,conf}}, gross:{bad,checked}}; ev — номера реплик с 1. */
function addEvaluated(record,resp){
  const base=String(record.conversation_id||'eval').replace(/[^\w-]/g,'')||'eval';
  let key=base,n=1;while(D[key])key=base+'-'+(++n);
  const res={};
  Object.entries(resp.results||{}).forEach(([id,r])=>{
    const c=CRIT.find(x=>String(x.id)===String(id));
    if(c)res[c.id]={v:r.v,ev:r.ev||[],why:r.why||'',q:r.q||'',conf:r.conf??1,sig:sigOf(c)};
  });
  D[key]={id:record.conversation_id||key,lang:String(record.language||'').toUpperCase(),
    channel:record.channel||'agent chat',operator:record.operator||'—',
    msgs:record.transcript.map(m=>[m.speaker,m.timestamp,m.text]),
    res,gross:resp.gross||{bad:false,checked:'—'}};
  appeals[key]={};refreshPick();
  return key;
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
$('#evGo').onclick=()=>{
  const recs=evRecords.slice();$('#evDlg').close();
  if(!CQA_API.enabled){
    runProgress(`Оценка: ${recs.length} диал.`,'Демонстрационный режим: результат не сохраняется',
      CRIT.map(c=>({t:c.name})).concat([{t:'Грубые ошибки'}]),()=>toast('Демо: результат не сохраняется'));
    return;
  }
  runJobs(`Оценка: ${recs.length} диал.`,`Чек-лист v${ver}`,
    recs.map(r=>r.conversation_id||'без ID'),
    async i=>addEvaluated(recs[i],await CQA_API.evaluate(recs[i],{version:ver,criteria:CRIT})));
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
