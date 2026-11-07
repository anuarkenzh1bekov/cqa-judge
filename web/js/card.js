/* Экран «Карточка диалога»: транскрипт, плеер, критерии, апелляция. */
/* ================= КАРТОЧКА ================= */
function renderCard(){
  const t=total(cur);   /* итог считаем один раз на обновление карточки */
  $('#pick').value=cur;renderChat();renderScore(t);renderMood();renderFeedback();renderCrit(t);
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
  /* служебные реплики в самом начале (смена языка, «чат начат») сворачиваем в одну строку: они не часть разговора */
  let lead=0;
  if(!opt.noId)while(lead<idx.length&&D[d].msgs[idx[lead]][0]==='system')lead++;
  if(lead>=2){
    const hit=(opt.marks||[]).some(n=>idx.slice(0,lead).includes(n-1));
    out+=`<details class="sysgrp"${hit?' open':''}><summary>Служебные сообщения: ${lead}</summary>`
      +idx.slice(0,lead).map(i=>bubble(d,i,{noId:opt.noId,mark:(opt.marks||[]).includes(i+1)})).join('')+'</details>';
    idx=idx.slice(lead);
  }
  idx.forEach(i=>{
    const who=D[d].msgs[i][0];
    if(who!=='system'&&who!==last)out+=`<div class="gl ${who}">${names[who]||esc(who)}</div>`;
    last=who==='system'?'':who;
    out+=bubble(d,i,{noId:opt.noId,mark:(opt.marks||[]).includes(i+1)});
  });
  return out;
}
const AP_ICON={
  play:'<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5.5v13a1 1 0 0 0 1.5.86l10.5-6.5a1 1 0 0 0 0-1.72L9.5 4.64A1 1 0 0 0 8 5.5z"/></svg>',
  pause:'<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/></svg>',
  vol:'<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M11 5 6 9H3v6h3l5 4z"/><path d="M15.5 8.5a5 5 0 0 1 0 7M18.5 5.5a9 9 0 0 1 0 13"/></svg>',
  low:'<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M11 5 6 9H3v6h3l5 4z"/><path d="M15.5 8.5a5 5 0 0 1 0 7"/></svg>',
  mute:'<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M11 5 6 9H3v6h3l5 4z"/><path d="m16 9 5 6M21 9l-5 6"/></svg>'
};
/* плеер собственный: <audio> скрыт, им управляют кнопки; seekTo() работает с тем же элементом */
function initPlayer(){
  const a=$('#aud');if(!a)return;
  const play=$('#apPlay'),seek=$('#apSeek'),cur_=$('#apCur'),dur=$('#apDur'),vol=$('#apVol'),mute=$('#apMute'),spd=$('#apSpd');
  const fill=(el,v)=>el.style.setProperty('--p',v+'%');
  const sync=()=>{
    const D_=a.duration;
    cur_.textContent=mm(a.currentTime||0);
    if(isFinite(D_)){dur.textContent=mm(D_);if(!seek.matches(':active'))seek.value=D_?a.currentTime/D_*1000:0}
    fill(seek,seek.value/10);
  };
  const state=()=>{play.innerHTML=a.paused?AP_ICON.play:AP_ICON.pause;play.setAttribute('aria-label',a.paused?'Воспроизвести':'Пауза')};
  play.onclick=()=>a.paused?a.play().catch(()=>{}):a.pause();
  ['play','pause','ended'].forEach(e=>a.addEventListener(e,state));
  ['timeupdate','loadedmetadata','durationchange','seeked'].forEach(e=>a.addEventListener(e,sync));
  seek.oninput=()=>{if(isFinite(a.duration))a.currentTime=seek.value/1000*a.duration;sync()};
  const rates=[1,1.25,1.5,2,0.75];
  spd.onclick=()=>{const i=(rates.indexOf(a.playbackRate)+1)%rates.length;a.playbackRate=rates[i];spd.textContent=rates[i]+'×'};
  /* иконка звука отражает уровень: нет звука / тихо / громко */
  let last=100;
  const level=()=>{
    const v=a.muted?0:a.volume;
    mute.innerHTML=v===0?AP_ICON.mute:v<.5?AP_ICON.low:AP_ICON.vol;
    mute.setAttribute('aria-label',a.muted||!v?'Включить звук':'Выключить звук');
    mute.classList.toggle('off',v===0);
    fill(vol,v*100);vol.value=v*100;
  };
  vol.oninput=()=>{a.muted=false;a.volume=vol.value/100;if(a.volume)last=vol.value;level()};
  mute.onclick=()=>{
    if(a.muted||!a.volume){a.muted=false;a.volume=(last||100)/100}else a.muted=true;
    level();
  };
  level();sync();
}
function renderChat(){
  const d=D[cur];
  const player=CQA_API.enabled&&d.audio
    ?`<div class="player" title="Нажмите на время реплики — запись перемотается к этому месту"><audio id="aud" preload="metadata" src="${CQA_API.audioUrl(d.id)}"></audio>
      <button class="pp" id="apPlay" aria-label="Воспроизвести">${AP_ICON.play}</button>
      <span class="pt" id="apCur">00:00</span>
      <input class="rng" id="apSeek" type="range" min="0" max="1000" value="0" step="1" aria-label="Перемотка">
      <span class="pt" id="apDur">--:--</span>
      <button class="spd" id="apSpd" aria-label="Скорость">1×</button>
      <button class="vol" id="apMute" aria-label="Звук">${AP_ICON.vol}</button>
      <input class="rng vl" id="apVol" type="range" min="0" max="100" value="100" aria-label="Громкость">
    </div>`:'';
  const chat=$('#chat');
  chat.innerHTML=player+'<p class="sum" id="dlgSum" hidden></p>'+msgList(cur,d.msgs.map((_,i)=>i));
  loadSummary(d);
  /* реплики появляются по очереди: шаг 50 мс, весь каскад не дольше секунды */
  [...chat.children].filter(el=>!el.classList.contains('player')&&el.id!=='dlgSum').forEach((el,i)=>el.style.setProperty('--d',Math.min(i*50,1000)+'ms'));
  chat.classList.add('in');
  initPlayer();
  $('#cardTitle').textContent=d.id;
  $('#asrTag').hidden=d.channel!=='voice call';
  $('#meta').innerHTML=`<span>${d.lang}</span><span>${d.channel}</span><span>${esc(d.operator)}</span>`
    +(d.checklistName?`<span title="Чек-лист оценки">${esc(d.checklistName)}</span>`:'');
}
/* краткое содержание над транскриптом: в демо оно записано в данных, с бэкендом строится по запросу и кэшируется */
const MOOD_L={positive:'Клиент доволен',neutral:'Спокойный тон',negative:'Клиент недоволен'};
function loadSummary(d){
  const el=$('#dlgSum');if(!el)return;
  const show=()=>{
    if(!d.sum||!$('#dlgSum')||D[cur]!==d)return;
    const e=$('#dlgSum'),k=d.mood||'neutral';
    e.className='sum '+k;
    e.title='Оценка модели, на итоговый балл не влияет';
    e.innerHTML=`<b class="lead">${MOOD_L[k]}.</b> `+esc(d.sum);
    e.hidden=false;
  };
  if(d.sum)return show();
  if(!CQA_API.enabled)return;
  CQA_API.conversationSummary(d.id).then(r=>{d.sum=r.summary;d.mood=r.mood;show()}).catch(()=>{});
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

function renderScore(t=total(cur)){
  renderScoreHtml(t);
  const num=$('#score .n');if(num)countUp(num,t.score,cur);   /* при ожидании оценки числа нет */
}
/* пояснение к грубым ошибкам: без повтора заголовка («Грубые ошибки — Нет.») */
const grossText=s=>{
  let x=String(s||'').replace(/^\s*Грубые ошибки\s*[—–-]\s*(Нет|Да)\.?\s*/i,'').replace(/^\s*Грубых нарушений не выявлено\.?\s*/i,'').trim();
  /* осталось только «(#13–#45)»: пишем, что это проверенный участок */
  const m=x.match(/^\((.+)\)$/);
  return m?'проверены реплики '+m[1].replace(/#(\d+)\s*[–—-]\s*#(\d+)/,'с #$1 по #$2'):x;
};
/* ссылки на реплики показываем, только если их нет в самом тексте пояснения */
function grossRefs(g){
  const txt=String(g.checked||''),rest=(g.ev||[]).filter(n=>!new RegExp('#'+n+'(?!\\d)').test(txt));
  return rest.length?' '+rest.map(n=>`<button class="lk" data-go-msg="${n}">#${n}</button>`).join(', '):'';
}
/* цвет итога: от 85 — зелёный, от 60 — жёлтый, ниже — красный (как в аналитике) */
const scoreLvl=s=>s===null||s===undefined?'':s>=85?'hi':s>=60?'mid':'lo';
/* строка справа от «Грубые ошибки: …». Нет нарушений: что проверяли и на каком участке, без ссылок на реплики.
   Есть нарушение: пояснение модели со ссылками на реплики. */
function grossLine(g){
  if(g.bad||!CQA_API.enabled)return (CQA_API.enabled?'':'проверено ')+linkify(grossText(g.checked))+grossRefs(g);
  const s=String(g.checked||'').replace(/^\s*Грубые ошибки\s*[—–-]\s*(Нет|Да)\.?\s*/i,'');
  const m=s.match(/^\s*Грубых нарушений\s*(?:\(([^)]*)\))?\s*не выявлено\.?\s*/i);
  const r=s.match(/#(\d+)\s*[–—-]\s*#(\d+)/);
  const parts=[];
  if(m&&m[1])parts.push('проверено: '+esc(m[1]));
  if(r)parts.push((parts.length?'реплики':'проверены реплики')+` с #${r[1]} по #${r[2]}`);
  return parts.length?parts.join(' · '):linkify(grossText(g.checked));
}
function renderScoreHtml(t){
  /* исходный итог нужен только для сравнения после решения проверяющего */
  const decided=Object.values(appeals[cur]).some(a=>a.decision);
  const o=decided?total(cur,true):t,d=D[cur];
  const act=CRIT.filter(c=>!pending(cur,c));
  const diff=t.score!==null&&o.score!==null?Math.round((t.score-o.score)*100)/100:0;
  const notes=[];
  if(diff)notes.push(`<span class="up">${diff>0?'+':''}${fmt(diff)} после решения</span>, было ${fmt(o.score)}`);
  if(act.length&&act.length<CRIT.length)notes.push(`ожидают оценки: ${CRIT.length-act.length}`);
  const g=d.gross;
  const btn=CQA_API.enabled?`<div class="sc-act"><button class="btn ${d.evalId?'':'primary'}" id="evalNow">${d.running?'<span class="spin"></span>Оценивается':d.evalId?'Переоценить':'Оценить диалог'}</button>`
    +'</div>':'';
  if(CQA_API.enabled&&!d.evalId){
    $('#score').innerHTML=d.running
      ?`<div class="sc-prog" aria-hidden="true"></div><div class="sc-top"><span class="load" aria-hidden="true"><i></i><i></i><i></i></span><div class="sc-side wait"><b>Подождите, идёт оценка</b>Читаем диалог и проверяем критерии</div></div>${btn}`
      :`<div class="sc-top"><span class="n">—</span><span class="of">из 100</span><div class="sc-side">Диалог ещё не оценён</div></div>${btn}`;
  }else{
    $('#score').innerHTML=`<div class="sc-top"><span class="n ${scoreLvl(t.score)}">${fmt(t.score)}</span><span class="of">из 100</span><div class="sc-side">${notes.join('<br>')}</div></div>
     <div class="gross ${g.bad?'bad':''}"><span class="gt">Грубые ошибки: ${g.bad?'выявлены':'не выявлены'}</span><span class="m2">${grossLine(g)}</span></div>${reviewRow()}${btn}`;
  }
  const b=$('#evalNow');
  if(b)b.onclick=async()=>{
    if(d.running){toast('Оценка уже выполняется');return}
    try{
      await beRunBatch('Оценка диалога '+d.id,{conversation_ids:[d.id]});
      await beRefreshAfterBatch();
    }catch(e){toast('Ошибка: '+e.message)}
  };
}
/* Настроение клиента: отдельный анализ, на балл не влияет. Для звонков — ещё и по голосу из записи. */
const MOOD={calm:'спокоен',positive:'доволен',confused:'растерян',anxious:'волнуется',irritated:'раздражён',angry:'злится'};
const MOOD_CLS={calm:'',positive:'yes',confused:'warn',anxious:'warn',irritated:'no',angry:'no'};
const OP_TONE={friendly:'доброжелательный',neutral:'нейтральный',tense:'напряжённый',irritated:'раздражённый'};
const TRAJ={improved:'стало лучше',unchanged:'без изменений',worsened:'стало хуже'};
function renderMood(){
  const box=$('#mood');if(!box)return;
  const m=CQA_API.enabled&&D[cur].facts&&D[cur].facts.client_mood;
  if(!m){box.hidden=true;box.innerHTML='';return}
  const tag=x=>`<span class="mood ${MOOD_CLS[x]||''}">${esc(MOOD[x]||x)}</span>`;
  const v=m.voice;
  box.hidden=false;
  box.innerHTML=`<div class="tr-h">Настроение клиента <small>· на балл не влияет</small></div>
    <p class="why mood-line">${tag(m.start)} → ${tag(m.end)} <small>${esc(TRAJ[m.trajectory]||'')}${m.confidence==='low'?' · уверенность низкая':''}</small></p>
    <p class="why">${linkify(m.summary||'')}</p>
    ${m.moments&&m.moments.length?`<ul class="fbl">${m.moments.map(x=>`<li class="ev">${x.turn!=null?`<button class="lk" data-go-msg="${x.turn+1}">#${x.turn+1}</button>`:''} ${tag(x.mood)} ${linkify(x.note||'')}</li>`).join('')}</ul>`:''}
    ${v?`<h4>По голосу в записи</h4>
      <p class="why">Клиент: ${tag(v.client_tone)} · оператор: ${esc(OP_TONE[v.operator_tone]||v.operator_tone||'')}. ${esc(v.summary||'')}</p>
      ${v.moments&&v.moments.length?`<ul class="fbl">${v.moments.map(x=>`<li class="ev"><button class="lk" data-seek-t="${esc(x.time)}">${esc(x.time)}</button> ${tag(x.mood)} ${esc(x.cue||'')}</li>`).join('')}</ul>`:''}`
      :(m.audio_error?`<p class="why"><small>Запись недоступна, настроение определено по тексту.</small></p>`:'')}`;
  box.querySelectorAll('[data-seek-t]').forEach(b=>b.onclick=()=>{
    const a=$('#aud');if(!a)return;const [mm,ss]=b.dataset.seekT.split(':').map(Number);
    if(isNaN(mm)||isNaN(ss))return;a.currentTime=mm*60+ss;a.play().catch(()=>{});
  });
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
    ${f.improvements&&f.improvements.length?`<h4 class="fbh w"><span>Что улучшить</span></h4><ul class="fbl w">${f.improvements.map(x=>`<li class="ev">${link(x)} ${linkify(x.text)}${x.criterion_key&&nameOf(x.criterion_key)?` <small>· ${esc(nameOf(x.criterion_key))}</small>`:''}${x.example_phrase?`<span class="say"><small>Можно сказать</small>«${esc(x.example_phrase)}»</span>`:''}</li>`).join('')}</ul>`:''}
    ${f.strengths&&f.strengths.length?`<h4 class="fbh g"><span>Что получилось хорошо</span></h4><ul class="fbl g">${f.strengths.map(x=>`<li class="ev">${link(x)} ${linkify(x.text)}</li>`).join('')}</ul>`:''}`;
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
    if(pending(cur,c)){
      if(CQA_API.enabled&&!D[cur].evalId&&D[cur].running)
        return `<div class="cr loading" data-id="${c.id}" style="--i:${i}"><div class="cr-h"><span class="cr-n">${i+1}</span><span class="cr-t">${esc(c.name)}</span><span class="v na"><span class="spin"></span>Оценивается</span><span></span></div><div class="cr-b"><span class="sk"></span><span class="sk s"></span></div></div>`;
      const msg=CQA_API.enabled&&!D[cur].evalId?'Диалог ещё не оценён.':'Критерий изменён. Примените чек-лист, чтобы оценить его в этом диалоге.';
      return `<div class="cr" data-id="${c.id}"><div class="cr-h"><span class="cr-n">${i+1}</span><span class="cr-t">${esc(c.name)}</span><span class="v na">Ожидает оценки</span><span></span></div><div class="cr-b why">${msg}</div></div>`;
    }
    const r=resOf(cur,c),v=value(cur,c),ap=appeals[cur][c.id];
    const p=points(c,v),eff=v==='na'||!t.den?null:c.w/t.den*100;
    const evHtml=evidenceHtml(cur,c,r,v);
    let state='';
    if(ap&&!ap.decision)state=`<div class="st">Апелляция на проверке: ${esc(ap.text)}</div>`;
    if(ap&&ap.decision)state=`<div class="st done">${outcomeLine(cur,c)}</div>`;
    const dec=reviewer&&ap&&!ap.decision?decideForm(cur,c,ap):'';
    const canAppeal=!ap||ap.decision;
    return `<div class="cr k-${kind(c,v)}" data-id="${c.id}">
      <div class="cr-h"><span class="cr-n">${i+1}</span><span class="cr-t">${esc(c.name)}</span><span class="v ${kind(c,v)}">${label(c,v)}</span><span class="cr-p">${p===null?'—':fmt(Math.round(p*100)/100)} / ${c.w}</span></div>
      ${eff!==null&&Math.abs(eff-c.w)>.05?`<div class="cr-w">вес ${c.w} → ${fmt(Math.round(eff*100)/100)} с учётом N/A</div>`:''}
      <div class="cr-b"><p class="why">${linkify(r.why)}</p>
        ${evHtml}
        <div class="cr-f">${isReview(cur,c)?`<span class="conf low">Сверьте оценку с диалогом</span>`:''}${canAppeal?`<button class="tx" data-ap="${c.id}">Оспорить</button>`:''}</div>
        ${state}${dec}</div></div>`;
}
async function saveDecision(d,id,sel,reason,act){
  if(CQA_API.enabled){await beDecide(d,id,sel,reason,act);return}
  const c=CRIT.find(x=>x.id===id),r=resOf(d,c);
  const v=act==='confirm'?r.v:(c.type==='scale'&&sel!=='na'?Number(sel):sel);
  appeals[d][id].decision={v,reason,act};persist();
}
if(!CQA_API.enabled)$('#pick').innerHTML=Object.entries(D).map(([k,d])=>`<option value="${k}">${d.lang} · ${d.id}</option>`).join('');
/* пустой выбор диалога выглядит как сломанная коробочка: без вариантов его не показываем */
function syncPick(){const p=$('#pick');p.hidden=!p.options.length}
syncPick();
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

/* ---------- «с чего начать»: критерии, которым модель сама не уверена ---------- */
const ROLE={client:'Клиент',operator:'Оператор',bot:'Бот',system:'Система'};
function reviewRow(){
  /* спорные: модель не уверена; из них ждут решения те, по которым человек его ещё не принял */
  const flagged=CRIT.filter(c=>!pending(cur,c)&&resOf(cur,c).conf<.65);
  if(!flagged.length)return '';
  const rv=flagged.filter(c=>isReview(cur,c)),done=flagged.length-rv.length;
  if(!rv.length)return `<div class="rv"><span class="rvt ok">Все спорные критерии проверены: ${done}</span></div>`;
  return `<div class="rv"><div class="rvh"><span class="rvt">Требуют проверки: ${rv.length}</span>${done?`<span class="rvd">проверено: ${done}</span>`:''}</div>`
    +`<div class="rvc">${rv.map(c=>`<button class="chip" data-goto-crit="${c.id}">${esc(c.name)}</button>`).join('')}</div></div>`;
}

/* ---------- доказательства: время, роль и цитата видны без клика ---------- */
function quoteOf(d,n,max=90){
  const m=D[d].msgs[n-1];if(!m)return '';
  const t=String(m[2]).replace(/\s+/g,' ').trim();
  return t.length>max?t.slice(0,max-1).trimEnd()+'…':t;
}
function evItem(d,n){
  const m=D[d].msgs[n-1];if(!m)return '';
  return `<button class="evb bub ${esc(m[0])}" data-go-msg="${n}"><span class="bb">${esc(quoteOf(d,n,160))}<small>${mm(secOf(d,n))} · ${esc(ROLE[m[0]]||m[0])}</small></span></button>`;
}
/* действие пропущено или выполнено не полностью */
const missed=(c,v)=>v==='no'||(c.type==='scale'&&v!=='na'&&v<Math.max(...c.steps));
function evidenceHtml(d,c,r,v){
  const ev=(r.ev||[]).filter(n=>D[d].msgs[n-1]);
  const explicit=r.range?[r.range[0]+1,r.range[1]+1]:null;
  const derived=missed(c,v)&&ev.length>1?[Math.min(...ev),Math.max(...ev)]:null;
  const rg=explicit||derived;
  let range='';
  if(rg&&(explicit||missed(c,v))){
    const a=Math.min(...rg),b=Math.max(...rg);
    if(D[d].msgs[a-1]&&D[d].msgs[b-1])
      range=`<button class="rgb" data-go-range="${a}-${b}" title="Показать участок в транскрипте">${a===b?`реплика ${a}`:`реплики ${a}–${b}`} · ${mm(secOf(d,a))}–${mm(secOf(d,b))}</button>`;
  }
  let out='';
  if(ev.length||range)out+=`<div class="evg"><div class="evh"><span>${ev.length?'Основание':'Проверенный участок'}</span>${ev.length&&range?'<small>проверено: </small>':''}${range}</div>${ev.map(n=>evItem(d,n)).join('')}</div>`;
  if(r.q&&!/^«/.test(r.q))out+=`<div class="ev"><span class="q">${esc(r.q)}</span></div>`;
  return out;
}

/* ---------- исход апелляции одной строкой ---------- */
function changeText(c,from,to){
  if(c.type==='scale'&&from!=='na'&&to!=='na')return `${from} → ${to} из ${Math.max(...c.steps)}`;
  return `${label(c,from)} → ${label(c,to)}`;
}
function outcomeLine(d,c){
  const dec=appeals[d][c.id].decision,r=resOf(d,c);
  const imp=decisionImpact(d,c);
  const tot=imp.before===imp.after?`Итог: ${fmt(imp.after)}`:`Итог: ${fmt(imp.before)} → ${fmt(imp.after)}`;
  const head=dec.act==='confirm'?`${esc(c.name)}: ${esc(label(c,r.v))}, подтверждена`:`${esc(c.name)}: ${esc(changeText(c,r.v,dec.v))}`;
  return `<b>${head}</b> · ${tot}<span class="why2">Причина: ${esc(dec.reason)}</span>`;
}
