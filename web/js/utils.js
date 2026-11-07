/* Общие вспомогательные функции. */
/* ================= УТИЛИТЫ ================= */
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const esc=s=>String(s).replace(/[&<>"]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[m]));
const nf=new Intl.NumberFormat('ru-RU',{maximumFractionDigits:2});
const fmt=n=>n===null||n===undefined?'—':nf.format(n);
const maxOf=c=>Math.max(...c.steps);
const label=(c,v)=>v==='na'?'N/A':c.type==='yn'?(v==='yes'?'Да':'Нет'):`${v} из ${maxOf(c)}`;
const kind=(c,v)=>v==='na'?'na':c.type==='yn'?v:'scale';
function toast(t){const e=$('#toast');e.textContent=t;e.classList.add('show');clearTimeout(toast.t);toast.t=setTimeout(()=>e.classList.remove('show'),2400)}
const nAppeals=d=>Object.values(appeals[d]).filter(a=>!a.decision).length;
const pendingAppeals=()=>Object.keys(D).reduce((s,d)=>s+nAppeals(d),0);
function syncCount(){const n=pendingAppeals();$('#apCount').hidden=!n;$('#apCount').textContent=n}
