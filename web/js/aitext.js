/* Звёздочки ✨ в текстовых полях: ИИ улучшает написанное, а если поле пустое — составляет черновик по контексту.
   Поле помечается атрибутом data-aitext="тип"; кнопка появляется сама, в том числе в полях, которые рисуются позже. */
/* ================= ИИ В ТЕКСТОВЫХ ПОЛЯХ ================= */
(function(){
  const SPARK='<svg width="19" height="19" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M9.5 4.5 11 9l4.5 1.5L11 12l-1.5 4.5L8 12 3.5 10.5 8 9z"/><path fill="currentColor" d="M18 3l.8 2.2L21 6l-2.2.8L18 9l-.8-2.2L15 6l2.2-.8z"/><path fill="currentColor" d="M17 14l.9 2.6L20.5 17.5l-2.6.9L17 21l-.9-2.6-2.6-.9 2.6-.9z"/></svg>';

  /* что модель должна знать о поле: критерий, его правило, оценка, объяснение, апелляция */
  function contextOf(el){
    const ctx={},ec=el.closest('.ec');
    if(ec){
      const c=CRIT[+ec.dataset.i],nm=ec.querySelector('.name');
      ctx.criterion=nm?nm.value:(c&&c.name);
      if(c&&el.dataset.f==='guidance')ctx.rule=c.q;
      return ctx;
    }
    const d=el.dataset.d||cur,cid=+(el.dataset.c||apId||0),c=CRIT.find(x=>x.id===cid);
    if(!c||!D[d])return ctx;
    const r=resOf(d,c);
    ctx.criterion=c.name;ctx.rule=c.q;ctx.current_answer=label(c,r.v);
    ctx.model_explanation=r.why;
    ctx.evidence=(r.ev||[]).slice(0,3).map(n=>`#${n} ${quoteOf(d,n,160)}`).join('; ');
    ctx.dialog_language=D[d].lang;
    const ap=appeals[d]&&appeals[d][c.id];
    if(ap&&el.dataset.aitext!=='appeal')ctx.appeal_comment=ap.text;
    return ctx;
  }

  async function run(el,btn){
    if(!CQA_API.enabled){toast('ИИ доступен при подключённом бэкенде');return}
    btn.disabled=true;btn.classList.add('busy');
    try{
      const r=await CQA_API.post('/api/ai/improve-text',{kind:el.dataset.aitext,text:el.value,context:contextOf(el)});
      el.value=r.text;
      el.dispatchEvent(new Event('input',{bubbles:true}));
      el.dispatchEvent(new Event('change',{bubbles:true}));
      toast(r.drafted?'Черновик от ИИ: проверьте и поправьте':'Текст улучшен ИИ: проверьте перед отправкой');
    }catch(e){toast('ИИ недоступен: '+e.message)}
    finally{btn.disabled=false;btn.classList.remove('busy')}
  }

  function enhance(el){
    if(el.dataset.aiw)return;
    el.dataset.aiw='1';
    const wrap=document.createElement('span');wrap.className='aiw'+(el.tagName==='TEXTAREA'?' ta':'');
    el.parentNode.insertBefore(wrap,el);wrap.appendChild(el);
    const btn=document.createElement('button');
    btn.type='button';btn.className='aib';btn.innerHTML=SPARK;
    btn.title=el.tagName==='TEXTAREA'||el.value?'ИИ: улучшить текст или составить черновик':'ИИ: составить черновик';
    btn.setAttribute('aria-label','Улучшить текст с помощью ИИ');
    btn.onclick=()=>run(el,btn);
    wrap.appendChild(btn);
  }
  const scan=root=>{
    if(root.matches&&root.matches('[data-aitext]'))enhance(root);
    (root.querySelectorAll?root.querySelectorAll('[data-aitext]'):[]).forEach(enhance);
  };
  scan(document);
  new MutationObserver(ms=>ms.forEach(m=>m.addedNodes.forEach(n=>{if(n.nodeType===1)scan(n)})))
    .observe(document.documentElement,{childList:true,subtree:true});
})();
