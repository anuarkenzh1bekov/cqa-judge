/* Версии чек-листа: переключение активной версии и создание нового чек-листа
   (пустой, копия, исходный из PDF или собранный ИИ по описанию). Новый чек-лист открывается черновиком
   в редакторе и становится версией только после «Сохранить». */
let clDraft=false;

async function loadVersions(){
  const sel=$('#clPick');if(!sel)return;
  if(!CQA_API.enabled){sel.hidden=true;$('#newCl').hidden=true;return}
  const canEdit=typeof reviewer==='undefined'||reviewer;  // operator role: view only
  sel.hidden=false;sel.disabled=!canEdit;$('#newCl').hidden=!canEdit;
  let list=[];
  try{list=await CQA_API.checklists()}catch(e){toast('Ошибка: '+e.message);return}
  sel.innerHTML=(clDraft?'<option value="draft" selected>Черновик — ещё не сохранён</option>':'')
    +list.slice().reverse().map(c=>`<option value="${c.id}" ${c.is_active&&!clDraft?'selected':''}>${esc(c.name)} · №${c.id}`
      +`${c.is_active?' · активный':''} · оценок ${c.evaluations||0}${c.submission_ready?' · ✓ для сдачи':''}</option>`).join('');
}

$('#clPick').addEventListener('change',async e=>{
  const id=e.target.value;
  if(id==='draft')return;
  if(dirty&&!confirm('Несохранённые изменения пропадут. Переключиться на другую версию?')){loadVersions();return}
  try{
    const cl=await CQA_API.activateChecklist(+id);
    clDraft=false;dirty=false;
    await beLoadChecklist();renderEditor();loadVersions();
    toast('Активный чек-лист: '+cl.name+' — по нему оцениваются новые диалоги');
  }catch(err){toast('Ошибка: '+err.message);loadVersions()}
});

function loadDraft(cl){
  BE.checklist={id:null,name:'',description:cl.description||'',criteria:cl.criteria,is_active:false,draft:true};
  BE.flags=JSON.parse(JSON.stringify(cl.criteria.filter(c=>c.type==='flag')));
  CRIT.splice(0,CRIT.length,...cl.criteria.filter(c=>c.type!=='flag').map(critToFront));
  Object.keys(savedSigs).forEach(k=>delete savedSigs[k]);
  clDraft=true;dirty=true;
  const vn=$('#verName');vn.value=cl.name;vn.dataset.cid='draft';
  renderEditor();loadVersions();
  $('#ed').scrollIntoView({behavior:reduceMotion()?'auto':'smooth',block:'start'});
}

const ncKind=()=>($('input[name="ncKind"]:checked')||{}).value;
function ncSync(){
  const k=ncKind();
  $('#ncAiBox').hidden=k!=='ai';
  $('#ncGo').textContent=k==='ai'?'Собрать черновик':'Открыть черновик';
  $('#ncGo').disabled=k==='ai'&&$('#ncBrief').value.trim().length<5;
  $('#ncInfo').textContent=k==='pdf'?'Только этот вариант подходит для файла результатов организаторам (8 критериев из PDF).':'';
}
$('#newCl').onclick=()=>{
  if(dirty&&!confirm('Несохранённые изменения в текущем чек-листе пропадут. Продолжить?'))return;
  $('#ncName').value='';$('#ncBrief').value='';
  $$('input[name="ncKind"]').forEach(r=>r.checked=r.value==='ai');
  ncSync();$('#newClDlg').showModal();
};
$$('input[name="ncKind"]').forEach(r=>r.onchange=ncSync);
$('#ncBrief').oninput=ncSync;
$('#ncNo').onclick=()=>$('#newClDlg').close();
$('#ncGo').onclick=async()=>{
  const k=ncKind(),go=$('#ncGo'),name=$('#ncName').value.trim();
  go.disabled=true;
  try{
    let cl;
    if(k==='empty')cl={name:name||'Новый чек-лист',description:'',criteria:[{key:'k01',section:'',name:'Новый критерий',
      description:'',type:'binary',weight:100,na_allowed:false,na_condition:null,scale:null,guidance:null}]};
    else if(k==='copy')cl={name:name||(verLabel(BE.checklist&&BE.checklist.name)+' (копия)'),
      description:BE.checklist&&BE.checklist.description,criteria:JSON.parse(JSON.stringify(CRIT.map(critToBack).concat(BE.flags)))};
    else if(k==='pdf'){const t=await CQA_API.defaultChecklist();cl={...t,name:name||t.name}}
    else{
      go.innerHTML='<span class="spin"></span>Собираем…';
      $('#ncInfo').textContent='Модель составляет критерии, веса и шкалы — обычно 20–30 секунд';
      const r=await CQA_API.generateChecklist($('#ncBrief').value.trim());
      cl={...r.checklist,name:name||r.checklist.name};
    }
    $('#newClDlg').close();
    loadDraft(cl);
    toast('Черновик открыт. Проверьте критерии и нажмите «Сохранить»');
  }catch(e){toast('Ошибка: '+e.message)}
  finally{go.disabled=false;ncSync()}
};
