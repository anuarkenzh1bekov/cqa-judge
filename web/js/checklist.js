/* Экран «Чек-лист»: редактор критериев. */
/* ================= ЧЕК-ЛИСТ ================= */
let dirty=false;
function renderEditor(){
  $('#ed').innerHTML='<datalist id="secList">'+[...new Set(CRIT.map(c=>c.section).filter(Boolean))].map(s=>`<option value="${esc(s)}">`).join('')+'</datalist>'+CRIT.map((c,i)=>`<div class="panel ec ${sigOf(c)!==savedSigs[c.id]?'changed':''}" data-i="${i}">
    <div class="ec-top"><span class="num">${i+1}</span><input class="name" type="text" data-f="name" value="${esc(c.name)}" aria-label="Название">
      <button class="tx" data-mv="-1" aria-label="Выше">↑</button><button class="tx" data-mv="1" aria-label="Ниже">↓</button><button class="tx danger" data-del>Удалить</button></div>
    <div class="fields">
      <div class="fld full"><label>Секция</label><input class="field" list="secList" data-f="section" value="${esc(c.section||'')}"></div>
      <div class="fld full"><label>Формулировка</label><textarea class="field" data-f="q" data-aitext="criterion">${esc(c.q)}</textarea></div>
      <div class="fld"><label>Тип ответа</label><select class="field" data-f="type"><option value="yn" ${c.type==='yn'?'selected':''}>Да / Нет</option><option value="scale" ${c.type==='scale'?'selected':''}>Шкала</option></select></div>
      <div class="fld"><label>Вес</label><input class="field" type="number" min="0" max="100" data-f="w" value="${c.w}"></div>
      ${c.type==='scale'?`<div class="fld full"><label>Ступени</label><input class="field" type="text" data-f="steps" value="${c.steps.join(', ')}" placeholder="0, 5, 10, 15, 20"></div>
      <div class="fld full"><label>Что означает каждая ступень${CQA_API.enabled?' — модель выбирает ступень по этим описаниям':''}</label>
        ${[...c.steps].sort((a,b)=>b-a).map(v=>`<div class="stp"><b>${v}</b><input class="field" data-f="sdesc" data-v="${v}" value="${esc((c.scaleDesc||{})[v]||'')}" placeholder="Когда ставить ${v}"></div>`).join('')}</div>`:''}
      <div class="fld"><label class="chk"><input type="checkbox" data-f="na" ${c.na?'checked':''}>Разрешить N/A</label></div>
      ${c.na?`<div class="fld"><label>Условие N/A</label><input class="field" type="text" data-f="nac" value="${esc(c.nac)}"></div>`:'<div></div>'}
      ${CQA_API.enabled?`<div class="fld full"><label>Пояснения для модели (пограничные случаи, примеры)</label><textarea class="field" data-f="guidance" data-aitext="guidance" placeholder="Необязательно">${esc(c.guidance||'')}</textarea></div>`:''}
    </div></div>`).join('')+flagsEditor();
  if(CQA_API.enabled){
    const sel=$('#applyTo');
    /* refill when the set of datasets changes (e.g. the control set was imported); default is "save only",
       so a click during a demo never starts re-evaluating a whole set by accident */
    const key=BE.groups.join('|');
    if(sel&&sel.dataset.groups!==key){
      const keep=sel.value;
      sel.innerHTML='<option value="">Только сохранить</option>'+BE.groups.map(g=>`<option value="${esc(g)}">Применить к ${g==='UPLOAD'?'загруженным вручную':'набору '+esc(g)}</option>`).join('');
      sel.value=BE.groups.includes(keep)?keep:'';sel.dataset.groups=key;
    }
  }
  refreshSide();
}
function flagsEditor(){
  if(!CQA_API.enabled)return '';
  return `<h3 class="ed-sub">Грубые ошибки — без баллов, отмечаются отдельно</h3>`+BE.flags.map((f,j)=>`<div class="panel ec flag" data-flag="${j}">
    <div class="ec-top"><span class="num">!</span><input class="name" type="text" data-ff="name" value="${esc(f.name)}" aria-label="Название флага">
      <button class="tx danger" data-fdel>Удалить</button></div>
    <div class="fields">
      <div class="fld full"><label>Когда ставить «Да» (что считается нарушением)</label><textarea class="field" data-ff="description">${esc(f.description||'')}</textarea></div>
      <div class="fld full"><label>Пояснения для модели</label><textarea class="field" data-ff="guidance" placeholder="Необязательно">${esc(f.guidance||'')}</textarea></div>
    </div></div>`).join('')+`<button class="btn" data-fadd>Добавить флаг грубой ошибки</button>`;
}
/* название версии: «v1», «v2» или своё; старое длинное имя по умолчанию не показываем */
const verLabel=n=>String(n||'').replace(/^Чек-лист качества чатов \(Freedom Broker\)/,'').replace(/^[\s·]+/,'').trim()||'v1';
function refreshSide(){
  const sum=CRIT.reduce((a,c)=>a+(+c.w||0),0);
  $('#wlist').innerHTML=CRIT.map(c=>`<div class="wl"><span class="t">${esc(c.name)}</span><span>${c.w}</span></div>`).join('')+`<div class="wl total"><span>Сумма</span><span>${sum}</span></div>`;
  const changed=CRIT.filter(c=>sigOf(c)!==savedSigs[c.id]).length;
  dirty=dirty||changed>0;
  /* название «Чек-лист качества чатов (Freedom Broker)» очевидно из контекста: показываем только версию */
  $('#verTitle').textContent=CQA_API.enabled&&BE.checklist?(BE.checklist.draft?'черновик':verLabel(BE.checklist.name)):'v'+ver;
  const vn=$('#verName');
  $('#verNameBox').hidden=!CQA_API.enabled;
  if(CQA_API.enabled&&BE.checklist&&!BE.checklist.draft&&document.activeElement!==vn&&vn.dataset.cid!==String(BE.checklist.id)){
    vn.value=verLabel(BE.checklist.name);vn.dataset.cid=BE.checklist.id;
  }
  $('#verNote').innerHTML=`<p class="vn ${dirty?'dirty':'clean'}">${dirty?'● Есть несохранённые изменения'+(changed?` (критериев: ${changed})`:''):'✓ Всё сохранено'}</p>`
    +(dirty&&CQA_API.enabled?'<p class="vn-s">При сохранении появится новая версия. Старые оценки остаются со своей версией.</p>':'')
    +(CQA_API.enabled?`<p class="vn-s">Грубые ошибки (${BE.flags.length}) не дают баллов, они только отмечаются в диалоге.</p>`:'')
    +(sum!==100?`<p class="vn-s">Сумма весов ${sum}, итог всё равно приводится к 100.</p>`:'')
    +(CQA_API.enabled&&BE.checklist?(BE.checklist.submission_ready&&!dirty
      ?'<p class="vn-s sub-ok">✓ Подходит для файла результатов организаторам</p>'
      :'<p class="vn-s">Для файла результатов организаторам нужен исходный чек-лист из PDF без изменений.</p>'):'');
}
$('#ed').addEventListener('input',e=>{
  const ff=e.target.dataset.ff;
  if(ff){BE.flags[+e.target.closest('[data-flag]').dataset.flag][ff]=e.target.value;dirty=true;refreshSide();return}
  const f=e.target.dataset.f;if(!f)return;
  const i=+e.target.closest('.ec').dataset.i,c=CRIT[i];
  if(f==='w')c.w=Math.max(0,+e.target.value||0);
  else if(f==='sdesc'){c.scaleDesc=c.scaleDesc||{};c.scaleDesc[e.target.dataset.v]=e.target.value}
  else if(f==='na'){c.na=e.target.checked;dirty=true;renderEditor();return}
  else if(f==='type'){c.type=e.target.value;if(c.type==='scale'&&!c.steps)c.steps=[0,5,10];dirty=true;renderEditor();return}
  else if(f==='steps'){
    const s=[...new Set(e.target.value.split(/[,\s;]+/).map(Number).filter(n=>!isNaN(n)&&n>=0))].sort((a,b)=>a-b);
    if(s.length>=2)c.steps=s;else return;
  }else c[f]=e.target.value;
  dirty=true;
  e.target.closest('.ec').classList.toggle('changed',sigOf(c)!==savedSigs[c.id]);
  refreshSide();
});
$('#ed').addEventListener('change',e=>{if(e.target.dataset.f==='steps')renderEditor()});
$('#ed').addEventListener('click',e=>{
  if(e.target.closest('[data-fadd]')){
    BE.flags.push({key:'flag_'+Date.now().toString(36),section:'Грубые нарушения',name:'Новый флаг',description:'',
      type:'flag',weight:0,na_allowed:false,na_condition:null,scale:null,guidance:null});
    dirty=true;renderEditor();$$('.ec.flag').at(-1).scrollIntoView({block:'center'});return;
  }
  const fl=e.target.closest('[data-flag]');
  if(fl){if(e.target.closest('[data-fdel]')){BE.flags.splice(+fl.dataset.flag,1);dirty=true;renderEditor()}return}
  const card=e.target.closest('.ec');if(!card)return;const i=+card.dataset.i;
  const mv=e.target.closest('[data-mv]');
  if(mv){const j=i+ +mv.dataset.mv;if(j<0||j>=CRIT.length)return;[CRIT[i],CRIT[j]]=[CRIT[j],CRIT[i]];dirty=true;renderEditor()}
  if(e.target.closest('[data-del]')){if(CRIT.length<=1){toast('Нужен хотя бы один критерий');return}CRIT.splice(i,1);dirty=true;renderEditor()}
});
$('#addCrit').onclick=()=>{
  CRIT.push({id:nextId++,name:'Новый критерий',q:'',w:5,type:'yn',na:false,nac:''});
  dirty=true;renderEditor();$$('.ec').at(-1).scrollIntoView({block:'center'});
};
/* «Помощь ИИ»: модель собирает черновик критерия из описания; ничего не сохраняется, пока не нажато «Сохранить» */
if(CQA_API.enabled)$('#aiCrit').hidden=false;
$('#aiCrit').onclick=()=>{$('#aiText').value='';$('#aiInfo').textContent='';$('#aiGo').disabled=true;$('#aiDlg').showModal();$('#aiText').focus()};
$('#aiNo').onclick=()=>$('#aiDlg').close();
$('#aiText').oninput=()=>{$('#aiGo').disabled=$('#aiText').value.trim().length<3};
$('#aiGo').onclick=async()=>{
  const go=$('#aiGo'),info=$('#aiInfo');
  go.disabled=true;go.textContent='Думаю…';info.textContent='';
  try{
    const r=await CQA_API.suggestCriterion({brief:$('#aiText').value.trim(),existing:CRIT.map(c=>c.name),
      sections:[...new Set(CRIT.map(c=>c.section).filter(Boolean))]});
    const c=critToFront({...r.criterion,key:'ai_'+Date.now().toString(36)});
    CRIT.push(c);dirty=true;renderEditor();
    $('#aiDlg').close();
    $$('.ec').at(-1).scrollIntoView({block:'center'});
    toast('Критерий добавлен внизу списка: проверьте формулировку и вес');
  }catch(e){info.textContent='Не получилось: '+e.message}
  finally{go.textContent='Предложить критерий';go.disabled=$('#aiText').value.trim().length<3}
};
$('#applyBtn').onclick=async()=>{
  if(CQA_API.enabled){
    const bad=CRIT.find(c=>!String(c.name).trim());
    if(bad){toast('У критерия нет названия');return}
    const noDesc=CRIT.find(c=>c.type==='scale'&&c.steps.some(v=>!String((c.scaleDesc||{})[v]||'').trim()));
    if(noDesc){toast(`«${noDesc.name}»: опишите каждую ступень шкалы — по описаниям модель выбирает балл`);return}
    const badFlag=BE.flags.find(f=>!String(f.name).trim()||!String(f.description||'').trim());
    if(badFlag){toast('У флага грубой ошибки нужны название и описание нарушения');return}
    const grp=$('#applyTo')?$('#applyTo').value:'';
    $('#applyBtn').disabled=true;
    try{
      const cl=await beSaveChecklist();
      clDraft=false;dirty=false;renderEditor();loadVersions();toast('Сохранено: '+cl.name);
      if(grp){
        const s=await beRunBatch(`Применяем «${cl.name}» к набору ${grp}`,{group:grp,checklist_id:cl.id});
        await beRefreshAfterBatch();
        toast(`Чек-лист применён: ${s.done} из ${s.total}`+(s.error?`, ошибок ${s.error}`:''));
      }
    }catch(e){toast('Ошибка: '+e.message)}
    finally{$('#applyBtn').disabled=false}
    return;
  }
  const need=CRIT.filter(c=>Object.keys(D).some(d=>pending(d,c)));
  const cached=CRIT.length-need.length;
  CRIT.forEach(c=>savedSigs[c.id]=sigOf(c));
  ver++;
  if(!need.length){dirty=false;persist();renderEditor();toast('Сохранено как v'+ver+'. Пересчёт не нужен');return}
  runProgress('Применяем v'+ver,`Диалогов: ${Object.keys(D).length}. Демонстрационный режим`,
    need.map(c=>({t:`Пересчёт: ${c.name}`})).concat([{t:`Из кэша: ${cached} критериев`,cache:true}]),
    ()=>{
      Object.keys(D).forEach(d=>need.forEach(c=>{
        if(!pending(d,c))return;
        D[d].res[c.id]={v:c.type==='yn'?'yes':maxOf(c),ev:[],why:'Демо-результат. В рабочей версии критерий оценит модель и приложит реплику-доказательство.',q:'',conf:.6,sig:sigOf(c)};
      }));
      dirty=false;persist();renderEditor();toast('Чек-лист применён');
    });
};
$('#resetState').onclick=async()=>{
  if(!CQA_API.enabled){resetSaved();return}
  if(!confirm('Создать новую версию чек-листа из исходного PDF и сделать её активной?'))return;
  try{
    const t=await CQA_API.defaultChecklist();
    await CQA_API.createChecklist(t);await beLoadChecklist();clDraft=false;dirty=false;renderEditor();loadVersions();toast('Восстановлен исходный чек-лист');
  }catch(e){toast('Ошибка: '+e.message)}
};

$('#verName').addEventListener('input',()=>{dirty=true;refreshSide()});
