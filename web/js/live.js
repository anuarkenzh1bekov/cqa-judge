/* Живая оценка: события с сервера (SSE) заполняют карточку и окно оценки, пока модель ещё пишет.
   Сервер присылает снимки: по каждому критерию ответ и текст, написанный к этому моменту. */
/* ================= ЖИВАЯ ОЦЕНКА ================= */
let liveES=null,liveCid=null,liveSnap=null,liveRaf=0;

function liveStart(cid){
  if(!CQA_API.enabled||!window.EventSource||(liveES&&liveCid===cid))return;
  liveStop();
  liveCid=cid;
  const es=new EventSource(CQA_API.url('/api/conversations/'+encodeURIComponent(cid)+'/live'));
  liveES=es;
  es.onmessage=e=>{
    let ev;try{ev=JSON.parse(e.data)}catch(_){return}
    if(ev.type==='partial'){liveSnap=ev;liveSchedule()}
    else if(ev.type==='done'||ev.type==='idle')liveStop(false);   /* итоговую карточку перерисует обычный поток */
  };
  es.onerror=()=>liveStop(false);   /* без бесконечных переподключений: останется обычное ожидание */
}
function liveStop(clear=true){
  if(liveES)liveES.close();
  liveES=null;liveCid=null;
  if(clear){liveSnap=null;cancelAnimationFrame(liveRaf)}
}
/* перерисовка не чаще одного раза за кадр */
function liveSchedule(){cancelAnimationFrame(liveRaf);liveRaf=requestAnimationFrame(liveRender)}
function liveRender(){liveRows();liveModal()}

const liveCrit=key=>{const id=BE.keyId&&BE.keyId[key];return id?CRIT.find(c=>c.id===id):null};
/* название критерия или флага грубой ошибки (флагов нет среди CRIT) */
const liveName=(key,c)=>c?c.name:((BE.flags||[]).find(f=>f.key===key)||{}).name||key;
const liveAns=(c,a)=>{try{return label(c,ansToFront(c,a))}catch(_){return String(a)}};

/* строки критериев в карточке: пока идёт оценка там «скелетоны», вместо них пишется ответ и текст модели */
function liveRows(){
  if(!liveSnap||!liveCid||liveCid!==cur||$('#v-card').hidden)return;
  const keys=Object.keys(liveSnap.criteria);
  keys.forEach((k,i)=>{
    const c=liveCrit(k),s=liveSnap.criteria[k];if(!c||!s)return;
    const row=$(`.cr.loading[data-id="${c.id}"]`);if(!row)return;
    const chip=row.querySelector('.v');
    if(s.answer&&chip){const v=ansToFront(c,s.answer);chip.className='v '+kind(c,v);chip.textContent=label(c,v)}
    const body=row.querySelector('.cr-b');
    if(body&&s.text){
      const last=!s.done&&i===keys.length-1;
      body.innerHTML=`<p class="live-t">${esc(s.text)}${last?'<i class="caret"></i>':''}</p>`;
    }
  });
}

/* окно «Оценка диалога»: лента критериев по мере написания */
function liveModal(){
  const box=$('#runLive');
  if(!box||box.hidden||!liveSnap)return;
  const keys=Object.keys(liveSnap.criteria);
  const stick=box.scrollTop+box.clientHeight>=box.scrollHeight-24;
  box.innerHTML=(liveSnap.request?`<div class="lv-req"><small>Запрос клиента</small>${esc(liveSnap.request)}</div>`:'')
    +keys.map((k,i)=>{
      const c=liveCrit(k),s=liveSnap.criteria[k],last=!s.done&&i===keys.length-1;
      const v=s.answer&&c?ansToFront(c,s.answer):null;
      return `<div class="lv-i"><div class="lv-h"><span>${esc(liveName(k,c))}</span>${v!==null?`<span class="v ${kind(c,v)}">${esc(label(c,v))}</span>`:''}</div>
        ${s.text?`<p class="live-t">${esc(s.text)}${last?'<i class="caret"></i>':''}</p>`:''}</div>`;
    }).join('');
  if(stick)box.scrollTop=box.scrollHeight;
}
