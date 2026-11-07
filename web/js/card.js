/* Экран «Карточка диалога»: транскрипт, плеер, критерии, апелляция. */
/* ================= КАРТОЧКА ================= */
function renderCard(){
  $('#pick').value=cur;renderChat();renderScore();renderFeedback();renderCrit();
}
function bubble(d,i,opt={}){
  const [who,t,text]=D[d].msgs[i],n=i+1;
  const tm=`<span class="tm" data-seek="${n}">${mm(secOf(d,n))}</span>`;
  const id=opt.noId?'':`id="m${n}"`,mk=opt.mark?' mark':'';
  if(who==='system')return `<div class="m system${mk}" ${id}>${esc(text)}<span class="mf">${tm} · #${n}</span></div>`;
  return `<div class="m ${who}${mk}" ${id}><div class="b">${esc(text)}<div class="mf">${tm} · #${n}</div></div></div>`;
}
/* реплики подряд от одного говорящего: подпись показываем один раз */
function msgList(d,idx,opt={}){
  const names={client:'Клиент',operator:'Оператор',bot:'Бот'};
  let last='',out='';
  idx.forEach(i=>{
    const who=D[d].msgs[i][0];
    if(who!=='system'&&who!==last)out+=`<div class="gl ${who}">${names[who]||esc(who)}</div>`;
    last=who==='system'?'':who;
    out+=bubble(d,i,{noId:opt.noId,mark:(opt.marks||[]).includes(i+1)});
  });
  return out;
}
function renderChat(){
  const d=D[cur];
  const player=CQA_API.enabled&&d.audio
    ?`<div class="player"><audio id="aud" controls preload="none" src="${CQA_API.audioUrl(d.id)}"></audio><small>Нажмите на время реплики или ссылку на реплику — запись перемотается к этому месту</small></div>`:'';
  const chat=$('#chat');
  chat.innerHTML=player+msgList(cur,d.msgs.map((_,i)=>i));
  /* реплики появляются по очереди: шаг 50 мс, весь каскад не дольше секунды */
  chat.classList.remove('in');void chat.offsetWidth;
  [...chat.children].filter(el=>!el.classList.contains('player')).forEach((el,i)=>el.style.setProperty('--d',Math.min(i*50,1000)+'ms'));
  chat.classList.add('in');
  $('#cardTitle').textContent=d.id;
  $('#meta').innerHTML=`<span>${d.lang}</span><span>${d.channel}</span><span>${esc(d.operator)}</span>`
    +(d.checklistName?`<span title="Чек-лист оценки">${esc(d.checklistName)}</span>`:'');
}
const mm=s=>String(Math.floor(s/60)).padStart(2,'0')+':'+String(Math.floor(s%60)).padStart(2,'0');
/* время реплики в секундах от начала: чаты дают MM:SS, звонки — ISO 8601 с часовым поясом */
const secOf=(d,n)=>{
  const ms=D[d].msgs,ts=ms[n-1][1];
  if(ts.includes('T'))return Math.max(0,Math.round((Date.parse(ts)-Date.parse(ms[0][1]))/1000));
  const [m,s]=ts.split(':').map(Number);return m*60+s;
};
function seekTo(n){
  const a=$('#aud');if(!a||!D[cur].msgs[n-1])return;
  a.currentTime=secOf(cur,n);a.play().catch(()=>{});
}

function renderScore(){
  renderScoreHtml();
  countUp($('#score .n'),total(cur).score,cur);
}
function renderScoreHtml(){
  const t=total(cur),o=total(cur,true),d=D[cur];
  const act=CRIT.filter(c=>!pending(cur,c)),nas=act.filter(c=>value(cur,c)==='na');
  const diff=t.score!==null&&o.score!==null?Math.round((t.score-o.score)*100)/100:0;
  const notes=[];
  if(diff)notes.push(`<span class="up">${diff>0?'+':''}${fmt(diff)} после решения</span>, было ${fmt(o.score)}`);
  if(nas.length)notes.push(`N/A: вес ${nas.reduce((a,c)=>a+c.w,0)} перераспределён`);
  if(act.length&&act.length<CRIT.length)notes.push(`ожидают оценки: ${CRIT.length-act.length}`);
  if(CQA_API.enabled&&d.models)notes.push(`<span class="mdl">${esc(d.models.gemini||'')}${d.models.jev?' + '+esc(d.models.jev):''}${d.cost!=null?` · $${d.cost.toFixed(4)}`:''}</span>`);
  const g=d.gross;
  const btn=CQA_API.enabled?`<div class="sc-act"><button class="btn ${d.evalId?'':'primary'}" id="evalNow">${d.running?'Оценивается…':d.evalId?'Переоценить':'Оценить диалог'}</button>`
    +(d.evalId?`<a class="tx" href="${CQA_API.url('/api/evaluations/'+d.evalId+'/export')}" target="_blank" rel="noopener">Экспорт для CRM</a>`:'')+'</div>':'';
  if(CQA_API.enabled&&!d.evalId){
    $('#score').innerHTML=`<div class="sc-top"><span class="n">—</span><span class="of">из 100</span><div class="sc-side">${d.running?'Оценка выполняется, обновите через минуту':'Диалог ещё не оценён'}</div></div>${btn}`;
  }else{
    $('#score').innerHTML=`<div class="sc-top"><span class="n">${fmt(t.score)}</span><span class="of">из 100</span><div class="sc-side">${notes.join('<br>')}</div></div>
     <div class="gross ${g.bad?'bad':''}"><span class="gt">Грубые ошибки: ${g.bad?'выявлены':'не выявлены'}</span><span class="m2">${CQA_API.enabled?'':'проверено '}${linkify(g.checked)}</span>
     ${g.ev&&g.ev.length?`<span class="ev">${g.ev.map(n=>`<button class="lk" data-go-msg="${n}">#${n}</button>`).join('')}</span>`:''}</div>${btn}`;
  }
  const b=$('#evalNow');
  if(b)b.onclick=async()=>{
    if(d.running){toast('Оценка уже выполняется');return}
    try{
      await beRunBatch('Оценка диалога '+d.id,{conversation_ids:[d.id]});
      await beRefreshAfterBatch();toast('Оценка готова');
    }catch(e){toast('Ошибка: '+e.message)}
  };
}
function renderFeedback(){
  const box=$('#fb');if(!box)return;
  const f=CQA_API.enabled&&D[cur].feedback;
  if(!f){box.hidden=true;box.innerHTML='';return}
  const link=x=>x.turn!=null?`<button class="lk" data-go-msg="${x.turn+1}">#${x.turn+1}</button>`:'';
  const nameOf=k=>{const id=BE.keyId[k];const c=CRIT.find(x=>x.id===id);return c?c.name:''};
  box.hidden=false;
  box.innerHTML=`<div class="tr-h">Рекомендации оператору</div>
    <p class="why">${linkify(f.summary||'')}</p>
    ${f.improvements&&f.improvements.length?`<h4>Что улучшить</h4><ul class="fbl">${f.improvements.map(x=>`<li class="ev">${link(x)} ${linkify(x.text)}${x.criterion_key&&nameOf(x.criterion_key)?` <small>· ${esc(nameOf(x.criterion_key))}</small>`:''}${x.example_phrase?`<span class="q">Можно сказать: «${esc(x.example_phrase)}»</span>`:''}</li>`).join('')}</ul>`:''}
    ${f.strengths&&f.strengths.length?`<h4>Что получилось хорошо</h4><ul class="fbl">${f.strengths.map(x=>`<li class="ev">${link(x)} ${linkify(x.text)}</li>`).join('')}</ul>`:''}`;
}
function decideForm(d,c,ap){
  const r=resOf(d,c);
  const opts=(c.type==='yn'?['yes','no',...(c.na?['na']:[])]:[...c.steps,...(c.na?['na']:[])]).map(o=>`<option value="${o}" ${o==r.v?'selected':''}>${label(c,o)}</option>`).join('');
  const ai=ap.ai?`<div class="st ai">ИИ-проверка: ${ap.ai.appeal_justified?'апелляция обоснована':'апелляция не обоснована'}, предлагает «${esc(label(c,ansToFront(c,ap.ai.suggested_answer)))}». ${linkify(ap.ai.explanation||'')}</div>`
    :(CQA_API.enabled&&ap._id?`<div class="f"><button class="tx" data-ai="${c.id}" data-d="${esc(d)}">Попросить ИИ перепроверить</button></div>`:'');
  return `<div class="decide"><div class="cmt">${esc(ap.text)}</div>${ai}
    <div class="f"><label class="fi">Новая оценка<select class="field" data-v="${c.id}">${opts}</select></label><label class="fi">Причина решения<input class="field" data-r="${c.id}"></label></div>
    <div class="f"><button class="btn primary" data-save="${c.id}" data-d="${esc(d)}" data-act="confirm">Подтвердить оценку</button><button class="btn" data-save="${c.id}" data-d="${esc(d)}" data-act="change">Изменить на выбранную</button></div></div>`;
}
function renderCrit(){
  const t=total(cur),secs=sectionScores(cur);let lastSec=null;
  $('#crit').innerHTML=CRIT.map((c,i)=>{
    let head='';
    if(c.section&&c.section!==lastSec){
      lastSec=c.section;const sc=secs.find(x=>x.name===c.section);
      head=`<div class="sec"><span>${esc(c.section)}</span><span>${sc&&sc.score!==null?fmt(sc.score):'—'}</span></div>`;
    }
    return head+critRow(c,i,t);
  }).join('');
}
const AGREE={agree:'модели согласны',minor:'соседние ступени шкалы',disputed:'модели разошлись — Gemini перепроверил',
  review:'модели разошлись, проверьте',gemini_only:'Jev недоступен'};
function modelsLine(c,r){
  if(!r.gemini)return '';
  const j=r.jev?`Jev: ${esc(label(c,ansToFront(c,r.jev.answer)))} (${Math.round(r.jev.probability*100)}%)`:'';
  const adj=r.adjudication&&r.adjudication.changed?' · ответ изменён после перепроверки':'';
  return `<div class="mdl">Gemini: ${esc(label(c,ansToFront(c,r.gemini.answer)))}${j?' · '+j:''} · ${AGREE[r.agreement]||''}${adj}</div>`;
}
function critRow(c,i,t){
    if(pending(cur,c)){
      const msg=CQA_API.enabled&&!D[cur].evalId?'Диалог ещё не оценён.':'Критерий изменён. Примените чек-лист, чтобы оценить его в этом диалоге.';
      return `<div class="cr" data-id="${c.id}"><div class="cr-h"><span class="cr-n">${i+1}</span><span class="cr-t">${esc(c.name)}</span><span class="v na">Ожидает оценки</span><span></span></div><div class="cr-b why">${msg}</div></div>`;
    }
    const r=resOf(cur,c),v=value(cur,c),ap=appeals[cur][c.id];
    const p=points(c,v),eff=v==='na'||!t.den?null:c.w/t.den*100;
    const evs=r.ev.map(n=>`<button class="lk" data-go-msg="${n}">#${n}</button>`).join('');
    const rng=!evs&&r.range?`<div class="ev">Проверенный участок: <button class="lk" data-go-msg="${r.range[0]+1}">#${r.range[0]+1}</button>–<button class="lk" data-go-msg="${r.range[1]+1}">#${r.range[1]+1}</button></div>`:'';
    let state='';
    if(ap&&!ap.decision)state=`<div class="st">Апелляция на проверке: ${esc(ap.text)}</div>`;
    if(ap&&ap.decision)state=ap.decision.act==='confirm'
      ?`<div class="st done">Оценка подтверждена. ${esc(ap.decision.reason)}</div>`
      :`<div class="st done"><s>${label(c,r.v)}</s> → <b>${label(c,ap.decision.v)}</b>. ${esc(ap.decision.reason)}</div>`;
    const dec=reviewer&&ap&&!ap.decision?decideForm(cur,c,ap):'';
    const canAppeal=!ap||ap.decision;
    return `<div class="cr k-${kind(c,v)}" data-id="${c.id}">
      <div class="cr-h"><span class="cr-n">${i+1}</span><span class="cr-t">${esc(c.name)}</span><span class="v ${kind(c,v)}">${label(c,v)}</span><span class="cr-p">${p===null?'—':fmt(Math.round(p*100)/100)} / ${c.w}</span></div>
      ${eff!==null&&Math.abs(eff-c.w)>.05?`<div class="cr-w">вес ${c.w} → ${fmt(Math.round(eff*100)/100)} с учётом N/A</div>`:''}
      <div class="cr-b"><p class="why">${linkify(r.why)}</p>
        ${evs?`<div class="ev">Реплики: ${evs}${r.q?`<span class="q">${esc(r.q)}</span>`:''}</div>`:rng}
        ${modelsLine(c,r)}
        <div class="cr-f">${r.conf<.65?`<span class="conf low">Сверьте оценку с диалогом</span>`:''}${canAppeal?`<button class="tx" data-ap="${c.id}">Оспорить</button>`:''}</div>
        ${state}${dec}</div></div>`;
}
async function saveDecision(d,id,sel,reason,act){
  if(CQA_API.enabled){await beDecide(d,id,sel,reason,act);return}
  const c=CRIT.find(x=>x.id===id),r=resOf(d,c);
  const v=act==='confirm'?r.v:(c.type==='scale'&&sel!=='na'?Number(sel):sel);
  appeals[d][id].decision={v,reason,act};persist();
}
if(!CQA_API.enabled)$('#pick').innerHTML=Object.entries(D).map(([k,d])=>`<option value="${k}">${d.lang} · ${d.id}</option>`).join('');
$('#pick').onchange=e=>go('#/card/'+encodeURIComponent(e.target.value));
$('#rev').onclick=function(){
  reviewer=!reviewer;this.setAttribute('aria-pressed',reviewer);
  if(!$('#v-card').hidden)renderCrit();
};
let apId=null;
function openAppeal(id){
  apId=id;const c=CRIT.find(x=>x.id===id);
  $('#dlgSub').textContent=`${c.name}: сейчас ${label(c,value(cur,c))}`;
  $('#dlgText').value='';$('#dlg').showModal();$('#dlgText').focus();
}
$('#dlgNo').onclick=()=>$('#dlg').close();
$('#dlgYes').onclick=async()=>{
  const t=$('#dlgText').value.trim();
  if(!t){toast('Добавьте комментарий');return}
  if(CQA_API.enabled){
    $('#dlgYes').disabled=true;
    try{await beSendAppeal(cur,apId,t);$('#dlg').close();renderCrit();syncCount();toast('Апелляция отправлена')}
    catch(e){toast('Ошибка: '+e.message)}
    finally{$('#dlgYes').disabled=false}
    return;
  }
  appeals[cur][apId]={text:t};persist();$('#dlg').close();renderCrit();syncCount();
  toast('Апелляция отправлена');
};
