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
  BE.flags=JSON.parse(JSON.stringify(cl.criteria.filter(c=>c.type==='flag')));  // editable copy
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
  d.gross={bad:false,checked:'—'};  // flags below accumulate into this; start clean on every apply
  d.evalId=ev.id;d.summary=ev;d.operator=ev.operator_name||'—';
  d.feedback=ev.feedback;d.facts=ev.facts;d.models=ev.models;d.cost=ev.cost_usd;d.checklistName=ev.checklist_name;
  const snap=Object.fromEntries(ev.checklist.criteria.map(c=>[c.key,c]));
  ev.results.forEach(r=>{
    const sc=snap[r.key];if(!sc)return;
    if(r.type==='flag'){
      const rng=r.checked_range?` (#${r.checked_range[0]+1}–#${r.checked_range[1]+1})`:'';
      const hit=ev.final_score.gross_error_criteria.includes(r.key);
      const prev=d.gross&&d.gross.parts?d.gross:{parts:[],ev:[]};
      // several flags: show the ones that fired; if none fired, show all explanations
      prev.parts.push({hit,text:(ev.results.filter(x=>x.type==='flag').length>1?r.name+': ':'')+r.explanation+rng});
      if(hit||!prev.ev.length)prev.ev=prev.ev.concat(r.evidence.map(e=>e.index+1));
      const shown=prev.parts.some(q=>q.hit)?prev.parts.filter(q=>q.hit):prev.parts;
      d.gross={bad:ev.final_score.gross_error,checked:shown.map(q=>q.text).join(' '),ev:[...new Set(prev.ev)],parts:prev.parts};
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
  syncPick();
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
/* Пакетная оценка: настоящий прогресс, сводка «Готово N из N», открытие каждого результата
   и повтор только неудавшихся диалогов. */
const beSleep=ms=>new Promise(r=>setTimeout(r,ms));
const beShortErr=s=>{s=String(s||'ошибка');return s.length>60?s.slice(0,59)+'…':s};
function beRunBatch(title,body){
  const ids=(body.conversation_ids||[]).slice();
  const checklist_id=body.checklist_id||null;
  const rows=new Map(ids.map(id=>[id,{status:'pending'}]));
  const busy=new Set();   // пакеты, которые сейчас выполняются
  $('#runTitle').textContent=title;
  const close=$('#runClose');close.disabled=true;
  const failed=()=>[...rows].filter(([,r])=>r.status==='error').map(([id])=>id);
  function render(){
    const all=[...rows.values()],n=s=>all.filter(r=>r.status===s).length;
    const work=n('pending')+n('running'),bad=failed();
    $('#runSub').innerHTML=`<b>Готово ${n('done')} из ${rows.size}</b>`+(work?` · в работе ${work}`:'')
      +(bad.length&&!work?` · ${bad.length===1?'не обработан':'не обработаны'}: ${bad.map(esc).join(', ')}`:'');
    $('#runList').innerHTML=[...rows].map(([id,r])=>{
      const cls=r.status==='done'?'ok':r.status==='running'?'go':r.status==='error'?'err':'';
      let tail='';
      if(r.status==='done')tail=`<span class="rtail">${fmt(r.total)}${r.gross?' · грубая ошибка':''}</span><button class="tx" data-open="${esc(id)}">Открыть</button>`;
      if(r.status==='error')tail=`<span class="ermsg" title="${esc(r.error||'')}">${esc(beShortErr(r.error))}</span><button class="tx" data-retry="${esc(id)}"${busy.size?' disabled':''}>Повторить</button>`;
      return `<div class="${cls}"><i>${r.status==='done'?CHECK_SVG:r.status==='error'?'!':''}</i><span class="rid">${esc(id)}</span>${tail}</div>`;
    }).join('')+(bad.length>1&&!work?`<div class="runall"><button class="tx" data-retry-all>Повторить все неудачные (${bad.length})</button></div>`:'');
    close.disabled=busy.size>0;
  }
  async function track(batchId){
    busy.add(batchId);render();
    let fails=0;
    for(;;){
      let s;
      try{s=await CQA_API.batchStatus(batchId);fails=0}
      catch(e){
        if(++fails>=15){
          rows.forEach((r,id)=>{if(r.status==='pending'||r.status==='running')rows.set(id,{status:'error',error:'нет связи с сервером'})});
          break;
        }
        await beSleep(3000);continue;
      }
      s.evaluations.forEach(e=>rows.set(e.conversation_id,{
        status:e.status==='done'?'done':e.status==='error'?'error':e.status==='running'?'running':'pending',
        total:e.final_total,gross:e.gross_error,error:e.error}));
      render();
      if(s.finished)break;
      await beSleep(2500);
    }
    busy.delete(batchId);
    try{await beLoadAll();if(!$('#v-list').hidden)renderList()}catch(_){}
    render();
  }
  async function start(list){
    list.forEach(id=>rows.set(id,{status:'pending'}));render();
    let b;
    try{b=await CQA_API.batch({conversation_ids:list,checklist_id})}
    catch(e){list.forEach(id=>rows.set(id,{status:'error',error:e.message}));render();return}
    await track(b.batch_id);
  }
  $('#runList').onclick=e=>{
    const o=e.target.closest('[data-open]'),r=e.target.closest('[data-retry]'),ra=e.target.closest('[data-retry-all]');
    if(o){$('#runDlg').close();go('#/card/'+encodeURIComponent(o.dataset.open))}
    if(r&&!busy.size)start([r.dataset.retry]);
    if(ra&&!busy.size)start(failed());
  };
  close.onclick=()=>$('#runDlg').close();
  $('#runDlg').showModal();render();
  return start(ids).then(()=>{
    const all=[...rows.values()];
    return {done:all.filter(r=>r.status==='done').length,total:rows.size,error:all.filter(r=>r.status==='error').length};
  });
}
/* после оценки одного диалога из карточки: перечитать его и перерисовать экран */
async function beRefreshAfterBatch(){
  if(cur&&D[cur])await beLoadDialog(cur,true);
  route();
}
