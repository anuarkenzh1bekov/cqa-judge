/* Экран «Чек-лист»: редактор критериев. */
/* ================= ЧЕК-ЛИСТ ================= */
let dirty=false;
function renderEditor(){
  $('#ed').innerHTML='<datalist id="secList">'+[...new Set(CRIT.map(c=>c.section).filter(Boolean))].map(s=>`<option value="${esc(s)}">`).join('')+'</datalist>'+CRIT.map((c,i)=>`<div class="panel ec ${sigOf(c)!==savedSigs[c.id]?'changed':''}" data-i="${i}">
    <div class="ec-top"><span class="num">${i+1}</span><input class="name" type="text" data-f="name" value="${esc(c.name)}" aria-label="Название">
      <button class="tx" data-mv="-1" aria-label="Выше">↑</button><button class="tx" data-mv="1" aria-label="Ниже">↓</button><button class="tx danger" data-del>Удалить</button></div>
    <div class="fields">
      <div class="fld full"><label>Секция</label><input class="field" list="secList" data-f="section" value="${esc(c.section||'')}"></div>
      <div class="fld full"><label>Формулировка</label><textarea class="field" data-f="q">${esc(c.q)}</textarea></div>
      <div class="fld"><label>Тип ответа</label><select class="field" data-f="type"><option value="yn" ${c.type==='yn'?'selected':''}>Да / Нет</option><option value="scale" ${c.type==='scale'?'selected':''}>Шкала</option></select></div>
      <div class="fld"><label>Вес</label><input class="field" type="number" min="0" max="100" data-f="w" value="${c.w}"></div>
      ${c.type==='scale'?`<div class="fld full"><label>Ступени</label><input class="field" type="text" data-f="steps" value="${c.steps.join(', ')}" placeholder="0, 5, 10, 15, 20"></div>`:''}
      <div class="fld"><label class="chk"><input type="checkbox" data-f="na" ${c.na?'checked':''}>Разрешить N/A</label></div>
      ${c.na?`<div class="fld"><label>Условие N/A</label><input class="field" type="text" data-f="nac" value="${esc(c.nac)}"></div>`:'<div></div>'}
      ${CQA_API.enabled?`<div class="fld full"><label>Пояснения для модели (пограничные случаи, примеры)</label><textarea class="field" data-f="guidance" placeholder="Необязательно">${esc(c.guidance||'')}</textarea></div>`:''}
    </div></div>`).join('');
  if(CQA_API.enabled){
    const sel=$('#applyTo');
    if(sel&&!sel.dataset.filled){
      sel.innerHTML='<option value="">Только сохранить</option>'+BE.groups.map(g=>`<option value="${esc(g)}">Применить к набору ${esc(g)}</option>`).join('');
      sel.value=BE.groups[BE.groups.length-1]||'';sel.dataset.filled='1';
    }
  }
  refreshSide();
}
function refreshSide(){
  const sum=CRIT.reduce((a,c)=>a+(+c.w||0),0);
  $('#wlist').innerHTML=CRIT.map(c=>`<div class="wl"><span class="t">${esc(c.name)}</span><span>${c.w}</span></div>`).join('')+`<div class="wl total"><span>Сумма</span><span>${sum}</span></div>`;
  const changed=CRIT.filter(c=>sigOf(c)!==savedSigs[c.id]).length;
  dirty=dirty||changed>0;
  $('#verTitle').textContent=CQA_API.enabled&&BE.checklist?BE.checklist.name:'v'+ver;
  const tail=CQA_API.enabled?' Сохранение создаёт новую версию чек-листа; старые оценки остаются со своей версией.'
    :' Остальные результаты берутся из кэша.';
  $('#verNote').innerHTML=dirty?`<span class="dirty">Есть изменения</span>${changed?`, критериев: ${changed}.${tail}`:'.'}`:'<span class="clean">Сохранён, изменений нет.</span>'
    +(CQA_API.enabled&&BE.flags.length?`<br><small>Грубые ошибки (${BE.flags.map(f=>esc(f.name)).join(', ')}) проверяются всегда и отмечаются отдельно.</small>`:'')
    +(sum!==100?`<br><small>Сумма весов ${sum} — итог всё равно нормируется к 100.</small>`:'');
}
$('#ed').addEventListener('input',e=>{
  const f=e.target.dataset.f;if(!f)return;
  const i=+e.target.closest('.ec').dataset.i,c=CRIT[i];
  if(f==='w')c.w=Math.max(0,+e.target.value||0);
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
$('#ed').addEventListener('click',e=>{
  const card=e.target.closest('.ec');if(!card)return;const i=+card.dataset.i;
  const mv=e.target.closest('[data-mv]');
  if(mv){const j=i+ +mv.dataset.mv;if(j<0||j>=CRIT.length)return;[CRIT[i],CRIT[j]]=[CRIT[j],CRIT[i]];dirty=true;renderEditor()}
  if(e.target.closest('[data-del]')){if(CRIT.length<=1){toast('Нужен хотя бы один критерий');return}CRIT.splice(i,1);dirty=true;renderEditor()}
});
$('#addCrit').onclick=()=>{
  CRIT.push({id:nextId++,name:'Новый критерий',q:'',w:5,type:'yn',na:false,nac:''});
  dirty=true;renderEditor();$$('.ec').at(-1).scrollIntoView({block:'center'});
};
$('#applyBtn').onclick=async()=>{
  if(CQA_API.enabled){
    const bad=CRIT.find(c=>!String(c.name).trim()||(!String(c.q||'').trim()&&!String(c.name).trim()));
    if(bad){toast('У критерия нет названия');return}
    const grp=$('#applyTo')?$('#applyTo').value:'';
    $('#applyBtn').disabled=true;
    try{
      const cl=await beSaveChecklist();
      dirty=false;renderEditor();toast('Сохранено: '+cl.name);
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
    await CQA_API.createChecklist(t);await beLoadChecklist();dirty=false;renderEditor();toast('Восстановлен исходный чек-лист');
  }catch(e){toast('Ошибка: '+e.message)}
};
