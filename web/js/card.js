/* Экран «Карточка диалога»: транскрипт, плеер, критерии, апелляция. */
/* ================= КАРТОЧКА ================= */
function renderCard(){
  const t=total(cur);   /* итог считаем один раз на обновление карточки */
  $('#pick').value=cur;renderChat();renderScore(t);renderCrit(t);
}
function bubble(d,i,opt={}){
  const [who,t,text]=D[d].msgs[i],n=i+1;
  const tm=`<span class="tm">${mm(secOf(d,n))}</span>`;
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
    if(who!=='system'&&who!==last)out+=`<div class="gl ${who}">${names[who]}</div>`;
    last=who==='system'?'':who;
    out+=bubble(d,i,{noId:opt.noId,mark:(opt.marks||[]).includes(i+1)});
  });
  return out;
}
function renderChat(){
  const d=D[cur];
  const chat=$('#chat');
  chat.innerHTML=msgList(cur,d.msgs.map((_,i)=>i));
  /* реплики появляются по очереди: шаг 50 мс, весь каскад не дольше секунды */
  [...chat.children].forEach((el,i)=>el.style.setProperty('--d',Math.min(i*50,1000)+'ms'));
  chat.classList.add('in');
  $('#cardTitle').textContent=d.id;
  $('#meta').innerHTML=`<span>${d.lang}</span><span>${d.channel}</span><span>${esc(d.operator)}</span>`;
}
const mm=s=>String(Math.floor(s/60)).padStart(2,'0')+':'+String(Math.floor(s%60)).padStart(2,'0');
/* время реплики в секундах от начала: чаты дают MM:SS, звонки — ISO 8601 с часовым поясом */
const secOf=(d,n)=>{
  const ms=D[d].msgs,ts=ms[n-1][1];
  if(ts.includes('T'))return Math.max(0,Math.round((Date.parse(ts)-Date.parse(ms[0][1]))/1000));
  const [m,s]=ts.split(':').map(Number);return m*60+s;
};

function renderScore(t=total(cur)){
  renderScoreHtml(t);
  countUp($('#score .n'),t.score,cur);
}
function renderScoreHtml(t){
  /* исходный итог нужен только для сравнения после решения проверяющего */
  const decided=Object.values(appeals[cur]).some(a=>a.decision);
  const o=decided?total(cur,true):t,d=D[cur];
  const act=CRIT.filter(c=>!pending(cur,c)),nas=act.filter(c=>value(cur,c)==='na');
  const diff=t.score!==null&&o.score!==null?Math.round((t.score-o.score)*100)/100:0;
  const notes=[];
  if(diff)notes.push(`<span class="up">${diff>0?'+':''}${fmt(diff)} после решения</span>, было ${fmt(o.score)}`);
  if(nas.length)notes.push(`N/A: вес ${nas.reduce((a,c)=>a+c.w,0)} перераспределён`);
  if(act.length<CRIT.length)notes.push(`ожидают оценки: ${CRIT.length-act.length}`);
  const g=d.gross;
  $('#score').innerHTML=`<div class="sc-top"><span class="n">${fmt(t.score)}</span><span class="of">из 100</span><div class="sc-side">${notes.join('<br>')}</div></div>
   <div class="gross ${g.bad?'bad':''}"><span class="gt">Грубые ошибки: ${g.bad?'выявлены':'не выявлены'}</span><span class="m2">проверено ${g.checked}</span></div>`;
}
function decideForm(d,c,ap){
  const r=resOf(d,c);
  const opts=(c.type==='yn'?['yes','no',...(c.na?['na']:[])]:[...c.steps,...(c.na?['na']:[])]).map(o=>`<option value="${o}" ${o==r.v?'selected':''}>${label(c,o)}</option>`).join('');
  return `<div class="decide"><div class="cmt">${esc(ap.text)}</div>
    <div class="f"><label class="fi">Новая оценка<select class="field" data-v="${c.id}">${opts}</select></label><label class="fi">Причина решения<input class="field" data-r="${c.id}"></label></div>
    <div class="f"><button class="btn primary" data-save="${c.id}" data-d="${d}" data-act="confirm">Подтвердить оценку</button><button class="btn" data-save="${c.id}" data-d="${d}" data-act="change">Изменить на выбранную</button></div></div>`;
}
function renderCrit(t=total(cur)){
  const secs=sectionScores(cur);let lastSec=null;
  $('#crit').innerHTML=CRIT.map((c,i)=>{
    let head='';
    if(c.section&&c.section!==lastSec){
      lastSec=c.section;const sc=secs.find(x=>x.name===c.section);
      head=`<div class="sec"><span>${esc(c.section)}</span><span>${sc&&sc.score!==null?fmt(sc.score):'—'}</span></div>`;
    }
    return head+critRow(c,i,t);
  }).join('');
}
function critRow(c,i,t){
    if(pending(cur,c))return `<div class="cr" data-id="${c.id}"><div class="cr-h"><span class="cr-n">${i+1}</span><span class="cr-t">${esc(c.name)}</span><span class="v na">Ожидает оценки</span><span></span></div><div class="cr-b why">Критерий изменён. Примените чек-лист, чтобы оценить его в этом диалоге.</div></div>`;
    const r=resOf(cur,c),v=value(cur,c),ap=appeals[cur][c.id];
    const p=points(c,v),eff=v==='na'||!t.den?null:c.w/t.den*100;
    const evs=r.ev.map(n=>`<button class="lk" data-go-msg="${n}">#${n}</button>`).join('');
    let state='';
    if(ap&&!ap.decision)state=`<div class="st">Апелляция на проверке: ${esc(ap.text)}</div>`;
    if(ap&&ap.decision)state=ap.decision.act==='confirm'
      ?`<div class="st done">Оценка подтверждена. ${esc(ap.decision.reason)}</div>`
      :`<div class="st done"><s>${label(c,r.v)}</s> → <b>${label(c,ap.decision.v)}</b>. ${esc(ap.decision.reason)}</div>`;
    const dec=reviewer&&ap&&!ap.decision?decideForm(cur,c,ap):'';
    return `<div class="cr k-${kind(c,v)}" data-id="${c.id}">
      <div class="cr-h"><span class="cr-n">${i+1}</span><span class="cr-t">${esc(c.name)}</span><span class="v ${kind(c,v)}">${label(c,v)}</span><span class="cr-p">${p===null?'—':fmt(Math.round(p*100)/100)} / ${c.w}</span></div>
      ${eff!==null&&Math.abs(eff-c.w)>.05?`<div class="cr-w">вес ${c.w} → ${fmt(Math.round(eff*100)/100)} с учётом N/A</div>`:''}
      <div class="cr-b"><p class="why">${esc(r.why)}</p>
        ${evs?`<div class="ev">Реплики: ${evs}${r.q?`<span class="q">${esc(r.q)}</span>`:''}</div>`:''}
        <div class="cr-f">${r.conf<.65?`<span class="conf low">Сверьте оценку с диалогом</span>`:''}${ap?'':`<button class="tx" data-ap="${c.id}">Оспорить</button>`}</div>
        ${state}${dec}</div></div>`;
}
function saveDecision(d,id,sel,reason,act){
  const c=CRIT.find(x=>x.id===id),r=resOf(d,c);
  const v=act==='confirm'?r.v:(c.type==='scale'&&sel!=='na'?Number(sel):sel);
  appeals[d][id].decision={v,reason,act};persist();
}
function refreshPick(){
  $('#pick').innerHTML=Object.entries(D).map(([k,d])=>`<option value="${k}">${d.lang} · ${d.id}</option>`).join('');
}
refreshPick();
$('#pick').onchange=e=>go('#/card/'+e.target.value);
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
$('#dlgYes').onclick=()=>{
  const t=$('#dlgText').value.trim();
  if(!t){toast('Добавьте комментарий');return}
  appeals[cur][apId]={text:t};persist();$('#dlg').close();renderCrit();syncCount();
  toast('Апелляция отправлена');
};
