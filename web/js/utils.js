/* Общие вспомогательные функции. */
/* ================= УТИЛИТЫ ================= */
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const esc=s=>String(s).replace(/[&<>"]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[m]));
/* Текст модели ссылается на реплики как [9] или [9, 11] (нумерация бэкенда с нуля).
   Экранируем и превращаем в кликабельные #10, #12 — как в транскрипте. */
const linkify=s=>!CQA_API.enabled?esc(s):esc(s).replace(/\[(\d+(?:\s*[,–-]\s*\d+)*)\]/g,(_,g)=>
  g.split(/\s*,\s*/).map(part=>{
    const [a,b]=part.split(/\s*[–-]\s*/).map(Number);
    const one=n=>`<button class="lk inl" data-go-msg="${n+1}">#${n+1}</button>`;
    return b!==undefined?one(a)+'–'+one(b):one(a);
  }).join(', '));
const nf=new Intl.NumberFormat('ru-RU',{maximumFractionDigits:2});
const fmt=n=>n===null||n===undefined?'—':nf.format(n);
const maxOf=c=>Math.max(...c.steps);
const label=(c,v)=>v==='na'?'N/A':c.type==='yn'?(v==='yes'?'Да':'Нет'):`${v} из ${maxOf(c)}`;
const kind=(c,v)=>v==='na'?'na':c.type==='yn'?v:'scale';
function toast(t){const e=$('#toast');e.textContent=t;e.classList.add('show');clearTimeout(toast.t);toast.t=setTimeout(()=>e.classList.remove('show'),2400)}
const nAppeals=d=>D[d]&&!D[d].loaded&&D[d].summary?(D[d].summary.open_appeals||0)
  :Object.values(appeals[d]||{}).filter(a=>!a.decision).length;
const pendingAppeals=()=>Object.keys(D).reduce((s,d)=>s+nAppeals(d),0);
function syncCount(){const n=pendingAppeals();$('#apCount').hidden=!n;$('#apCount').textContent=n}

/* Число «набегает» до значения. Без анимации, если в системе включено уменьшение движения. */
const reduceMotion=()=>matchMedia('(prefers-reduced-motion: reduce)').matches;
const countState={key:null,v:0,raf:0};
function countUp(el,to,key,ms=480){
  cancelAnimationFrame(countState.raf);
  const from=countState.key===key?countState.v:0;
  countState.key=key;countState.v=to===null?0:to;
  if(to===null||reduceMotion()||from===to){el.textContent=fmt(to);return}
  const t0=performance.now();
  const tick=now=>{
    const k=Math.min(1,(now-t0)/ms),e=1-Math.pow(1-k,3);
    el.textContent=k<1?fmt(Math.round((from+(to-from)*e)*100)/100):fmt(to);
    if(k<1)countState.raf=requestAnimationFrame(tick);
  };
  countState.raf=requestAnimationFrame(tick);
  setTimeout(()=>{el.textContent=fmt(to)},ms+80);
}
