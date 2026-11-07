/* Выпадающие списки: встроенное меню браузера не стилизуется (синее выделение, нет отступов),
   поэтому каждый select.field получает свою кнопку и меню. Сам <select> остаётся источником значения:
   его value, change и изменение options продолжают работать как раньше. */
(function(){
  const proto=Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value');
  let openDd=null;

  function close(){
    if(!openDd)return;
    const {menu,btn}=openDd;menu.remove();btn.setAttribute('aria-expanded','false');openDd=null;
  }

  function enhance(sel){
    if(sel.dataset.dd)return;
    sel.dataset.dd='1';
    const wrap=document.createElement('span');wrap.className='dd';
    sel.parentNode.insertBefore(wrap,sel);wrap.appendChild(sel);
    sel.tabIndex=-1;sel.setAttribute('aria-hidden','true');sel.classList.add('dd-native');
    const btn=document.createElement('button');
    btn.type='button';btn.className='field ddb';btn.setAttribute('aria-haspopup','listbox');btn.setAttribute('aria-expanded','false');
    const al=sel.getAttribute('aria-label');if(al)btn.setAttribute('aria-label',al);
    wrap.appendChild(btn);
    const label=()=>{const o=sel.options[sel.selectedIndex];btn.textContent=o?o.textContent:'';btn.title=btn.textContent};
    label();
    /* программная запись sel.value = … тоже обновляет подпись */
    Object.defineProperty(sel,'value',{configurable:true,get(){return proto.get.call(this)},set(v){proto.set.call(this,v);label()}});
    new MutationObserver(label).observe(sel,{childList:true,subtree:true,characterData:true,attributes:true,attributeFilter:['selected']});
    sel.addEventListener('change',label);

    function openMenu(){
      close();
      const menu=document.createElement('div');menu.className='ddm';menu.setAttribute('role','listbox');
      [...sel.options].forEach((o,i)=>{
        const it=document.createElement('div');it.className='ddi'+(i===sel.selectedIndex?' on':'');
        it.setAttribute('role','option');it.dataset.i=i;it.textContent=o.textContent;
        if(o.disabled)it.classList.add('dis');
        menu.appendChild(it);
      });
      wrap.appendChild(menu);
      const r=btn.getBoundingClientRect(),h=menu.offsetHeight,below=innerHeight-r.bottom-12,up=r.top-12;
      menu.style.minWidth=r.width+'px';menu.style.left=r.left+'px';
      if(h>below&&up>below){menu.style.bottom=(innerHeight-r.top+6)+'px';menu.style.maxHeight=Math.min(h,up)+'px'}
      else{menu.style.top=(r.bottom+6)+'px';menu.style.maxHeight=Math.max(120,Math.min(h,below))+'px'}
      btn.setAttribute('aria-expanded','true');
      openDd={menu,btn,sel};
      const on=menu.querySelector('.on');if(on)on.scrollIntoView({block:'nearest'});
      menu.onmousemove=e=>{const it=e.target.closest('.ddi');if(!it)return;menu.querySelectorAll('.hot').forEach(x=>x.classList.remove('hot'));it.classList.add('hot')};
      menu.onmousedown=e=>e.preventDefault();
      menu.onclick=e=>{const it=e.target.closest('.ddi');if(it&&!it.classList.contains('dis'))choose(+it.dataset.i)};
    }
    function choose(i){
      close();
      if(i!==sel.selectedIndex){sel.selectedIndex=i;label();sel.dispatchEvent(new Event('input',{bubbles:true}));sel.dispatchEvent(new Event('change',{bubbles:true}))}
      btn.focus();
    }
    btn.onclick=()=>openDd&&openDd.btn===btn?close():openMenu();
    btn.onkeydown=e=>{
      const k=e.key,isOpen=openDd&&openDd.btn===btn;
      if(!isOpen&&(k==='ArrowDown'||k==='ArrowUp'||k==='Enter'||k===' ')){e.preventDefault();openMenu();return}
      if(!isOpen)return;
      const items=[...openDd.menu.querySelectorAll('.ddi:not(.dis)')];
      let cur=items.findIndex(x=>x.classList.contains('hot'));if(cur<0)cur=items.findIndex(x=>x.classList.contains('on'));
      if(k==='ArrowDown'||k==='ArrowUp'){
        e.preventDefault();cur=Math.max(0,Math.min(items.length-1,cur+(k==='ArrowDown'?1:-1)));
        openDd.menu.querySelectorAll('.hot').forEach(x=>x.classList.remove('hot'));items[cur].classList.add('hot');items[cur].scrollIntoView({block:'nearest'});
      }else if(k==='Enter'||k===' '){e.preventDefault();if(items[cur])choose(+items[cur].dataset.i)}
      else if(k==='Escape'){e.preventDefault();e.stopPropagation();close()}
      else if(k==='Tab')close();
    };
  }

  const scan=root=>(root.querySelectorAll?root.querySelectorAll('select.field'):[]).forEach(enhance);
  scan(document);
  new MutationObserver(ms=>ms.forEach(m=>m.addedNodes.forEach(n=>{
    if(n.nodeType!==1)return;
    if(n.matches&&n.matches('select.field'))enhance(n);else scan(n);
  }))).observe(document.documentElement,{childList:true,subtree:true});
  document.addEventListener('mousedown',e=>{if(openDd&&!e.target.closest('.ddm')&&!e.target.closest('.ddb'))close()});
  addEventListener('resize',close);
  addEventListener('scroll',e=>{if(openDd&&!e.target.closest?.('.ddm'))close()},true);
})();
