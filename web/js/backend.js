/* Связь интерфейса с бэкендом: загрузка диалогов, оценок, чек-листа и апелляций
   в структуры экрана (CRIT, D, appeals) и отправка действий на сервер. */
const BE={
  checklist:null,      // активный чек-лист с сервера
  flags:[],            // критерии-флаги (грубые ошибки) — в редакторе не показываются, при сохранении добавляются
  keyId:{},            // key критерия на сервере -> числовой id в интерфейсе
  groups:[],           // группы наборов данных (DEV, контрольный и т.д.)
  health:null,
  idFor(key){if(!(key in this.keyId))this.keyId[key]=nextId++;return this.keyId[key]},
  keyOf(id){return Object.keys(this.keyId).find(k=>this.keyId[k]===id)}
};

/* ---------- преобразование критериев ---------- */
function critToFront(c){
  const f={id:BE.idFor(c.key),key:c.key,section:c.section||'',name:c.name,q:c.description,w:c.weight,
    type:c.type==='scale'?'scale':'yn',na:!!c.na_allowed,nac:c.na_condition||'',guidance:c.guidance||''};
  if(c.type==='scale'){
    f.steps=c.scale.map(s=>s.value).sort((a,b)=>a-b);
    f.scaleDesc=Object.fromEntries(c.scale.map(s=>[s.value,s.description]));
  }
  return f;
}
function critToBack(f){
  const key=f.key||('custom_'+f.id+'_'+Date.now().toString(36));
  f.key=key;BE.keyId[key]=f.id;
  const c={key,section:f.section||null,name:f.name,description:(f.q||'').trim()||f.name,
    type:f.type==='scale'?'scale':'binary',weight:+f.w||0,na_allowed:!!f.na,
    na_condition:f.na?((f.nac||'').trim()||'Критерий неприменим'):null,guidance:f.guidance||null};
  if(f.type==='scale')c.scale=f.steps.map(v=>({value:v,description:(f.scaleDesc&&f.scaleDesc[v])||`${v} баллов`}));
  return c;
}
const ansToFront=(c,a)=>c.type==='scale'&&a!=='na'?Number(a):a;

/* ---------- загрузка ---------- */
async function beLoadChecklist(){
  const cl=await CQA_API.activeChecklist();
  BE.checklist=cl;
  BE.flags=cl.criteria.filter(c=>c.type==='flag');
  CRIT.splice(0,CRIT.length,...cl.criteria.filter(c=>c.type!=='flag').map(critToFront));
  CRIT.forEach(c=>savedSigs[c.id]=sigOf(c));
  ver=cl.id;
}
function stubDialog(c){
  const s=c.latest_evaluation;
  return {id:c.id,group:c.group,lang:c.language,channel:c.channel,operator:(s&&s.operator_name)||'—',
    msgs:[],res:{},gross:{bad:!!(s&&s.gross_error),checked:''},loaded:false,summary:s,audio:c.has_audio,turns:c.turns};
}
async function beLoadAll(){
  const [convs]=await Promise.all([CQA_API.conversations(),beLoadChecklist(),
    CQA_API.health().then(h=>BE.health=h).catch(()=>null)]);
  const keep=new Set(convs.map(c=>c.id));
  Object.keys(D).forEach(k=>{if(!keep.has(k)){delete D[k];delete appeals[k]}});
  convs.forEach(c=>{
    const old=D[c.id],s=c.latest_evaluation;
    // перезагружаем полную карточку только если на сервере появилась новая оценка
    if(old&&old.loaded&&s&&old.evalId===s.id&&s.status==='done'){old.summary=s;return}
    D[c.id]=stubDialog(c);appeals[c.id]=appeals[c.id]||{};
  });
  BE.groups=[...new Set(convs.map(c=>c.group).filter(Boolean))];
  if(!cur||!D[cur])cur=Object.keys(D)[0]||'';
  fillPick();
}
/* полная карточка диалога: транскрипт + последняя завершённая оценка */
async function beLoadDialog(cid,force){
  const d=D[cid];if(!d)return;
  if(d.loaded&&!force)return;
  const conv=await CQA_API.get('/api/conversations/'+encodeURIComponent(cid));
  d.msgs=conv.transcript.map(t=>[t.speaker,normTs(t.timestamp),t.text]);
  d.audio=conv.has_audio;d.lang=conv.language;d.channel=conv.channel;
  const done=conv.evaluations.find(e=>e.status==='done');
  d.running=conv.evaluations.some(e=>e.status==='pending'||e.status==='running');
  d.res={};d.gross={bad:false,checked:'—'};d.evalId=null;d.feedback=null;appeals[cid]={};
  if(done){
    const ev=await CQA_API.evaluation(done.id);
    applyEvaluation(d,ev);
  }
  d.loaded=true;
}
function applyEvaluation(d,ev){
  d.evalId=ev.id;d.summary=ev;d.operator=ev.operator_name||'—';
  d.feedback=ev.feedback;d.facts=ev.facts;d.models=ev.models;d.cost=ev.cost_usd;d.checklistName=ev.checklist_name;
  const snap=Object.fromEntries(ev.checklist.criteria.map(c=>[c.key,c]));
  ev.results.forEach(r=>{
    const sc=snap[r.key];if(!sc)return;
    if(r.type==='flag'){
      const rng=r.checked_range?` (#${r.checked_range[0]+1}–#${r.checked_range[1]+1})`:'';
      d.gross={bad:ev.final_score.gross_error,checked:r.explanation+rng,ev:r.evidence.map(e=>e.index+1)};
      return;
    }
    const fc=critToFront(sc);
    const first=r.evidence[0];
    d.res[fc.id]={v:ansToFront(fc,r.answer),ev:r.evidence.map(e=>e.index+1),why:r.explanation,
      q:first?'«'+String(first.text).slice(0,160)+(String(first.text).length>160?'…':'')+'»':'',
      conf:r.needs_review?.5:(r.confidence==='high'?.95:r.confidence==='medium'?.8:.6),
      sig:sigOf(fc),gemini:r.gemini,jev:r.jev,agreement:r.agreement,adjudication:r.adjudication,
      reasons:r.review_reasons,range:r.checked_range};
  });
  appeals[d.id]={};
  ev.appeals.forEach(a=>{
    const id=BE.keyId[a.criterion_key];if(!id)return;
    const c=CRIT.find(x=>x.id===id)||{type:'yn'};
    const item={text:a.comment,_id:a.id,ai:a.ai_review};
    if(a.status!=='open')item.decision={act:a.status==='changed'?'change':'confirm',reason:a.reason||'',
      v:ansToFront(c,a.status==='changed'?a.new_answer:a.original_answer)};
    appeals[d.id][id]=item;
  });
}
/* ISO-время звонков с 7 знаками дробной части Date.parse понимает не везде — обрезаем до миллисекунд */
function normTs(ts){return String(ts).replace(/(\.\d{3})\d+/,'$1')}
function fillPick(){
  $('#pick').innerHTML=Object.entries(D).map(([k,d])=>`<option value="${esc(k)}">${d.lang} · ${esc(d.id)}</option>`).join('');
  if(cur)$('#pick').value=cur;
}

/* ---------- действия ---------- */
async function beSendAppeal(d,critId,text){
  if(!D[d].evalId)throw new Error('диалог ещё не оценён');
  await CQA_API.appeal(D[d].evalId,BE.keyOf(critId),text);
  await beLoadDialog(d,true);
}
async function beDecide(d,critId,sel,reason,act){
  const ap=appeals[d][critId];
  await CQA_API.decide(ap._id,{decision:act==='confirm'?'confirm':'change',
    new_answer:act==='change'?String(sel):null,reason,reviewer:'Проверяющий'});
  await beLoadDialog(d,true);
}
async function beSaveChecklist(){
  const body={name:(BE.checklist&&BE.checklist.name||'Чек-лист').replace(/\s*·\s*v\d+$/,'')+' · v'+(ver+1),
    description:BE.checklist&&BE.checklist.description,criteria:CRIT.map(critToBack).concat(BE.flags)};
  const cl=await CQA_API.createChecklist(body);
  await beLoadChecklist();
  return cl;
}
/* пакетная оценка с настоящим прогрессом */
async function beRunBatch(title,body){
  const b=await CQA_API.batch(body);
  return new Promise(resolve=>{
    $('#runTitle').textContent=title;
    $('#runSub').textContent=`Диалогов: ${b.total}. Модели: ${BE.health?BE.health.gemini_model:'Gemini'}${BE.health&&BE.health.jev_enabled?' + '+BE.health.jev_model:''}`;
    $('#runList').innerHTML='';$('#runClose').disabled=true;$('#runDlg').showModal();
    const ok='<svg width="8" height="8" viewBox="0 0 8 8"><path d="M1 4.2 3.2 6.2 7 1.8" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>';
    const tick=async()=>{
      let s;try{s=await CQA_API.batchStatus(b.batch_id)}catch(e){setTimeout(tick,3000);return}
      $('#runSub').textContent=`Готово ${s.done} из ${s.total}`+(s.error?`, ошибок ${s.error}`:'')+(s.running?` · оценивается ${s.running}`:'');
      $('#runList').innerHTML=s.evaluations.map(e=>{
        const cls=e.status==='done'?'ok':e.status==='running'?'go':e.status==='error'?'err':'';
        const tail=e.status==='done'?` — ${fmt(e.final_total)}${e.gross_error?' · грубая ошибка':''}`:e.status==='error'?' — ошибка':'';
        return `<div class="${cls}" title="${esc(e.error||'')}"><i>${e.status==='done'?ok:''}</i>${esc(e.conversation_id)}${tail}</div>`;
      }).join('');
      if(s.finished){$('#runClose').disabled=false;resolve(s);return}
      setTimeout(tick,2500);
    };
    $('#runClose').onclick=()=>$('#runDlg').close();
    tick();
  });
}
async function beRefreshAfterBatch(){
  await beLoadAll();
  if(cur&&D[cur])await beLoadDialog(cur,true);
  route();
}
