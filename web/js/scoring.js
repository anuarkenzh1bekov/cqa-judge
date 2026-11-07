/* Расчёт баллов: веса, N/A, перераспределение, округление. */
/* ================= РАСЧЁТ БАЛЛОВ ================= */
const resOf=(d,c)=>{const r=D[d].res[c.id];return r&&r.sig===sigOf(c)?r:null};
const pending=(d,c)=>!resOf(d,c);
function value(d,c,skipId){const a=appeals[d][c.id];return a&&a.decision&&c.id!==skipId?a.decision.v:resOf(d,c).v}
function points(c,v){if(v==='na')return null;if(c.type==='yn')return v==='yes'?c.w:0;return Math.min(1,v/Math.max(...c.steps))*c.w}
function total(d,useOrig,skipId){
  let got=0,den=0;
  CRIT.forEach(c=>{
    if(pending(d,c))return;
    const v=useOrig?resOf(d,c).v:value(d,c,skipId),p=points(c,v);
    if(p===null)return;got+=p;den+=c.w;
  });
  return den?{score:Math.round(got/den*10000)/100,den}:{score:null,den:0};
}

/* Подитоги по секциям (только применимые критерии) */
function sectionScores(d){
  const out=[];
  CRIT.forEach(c=>{
    const name=c.section||'';let s=out.find(x=>x.name===name);
    if(!s){s={name,got:0,den:0};out.push(s)}
    if(pending(d,c))return;
    const p=points(c,value(d,c));if(p===null)return;
    s.got+=p;s.den+=c.w;
  });
  return out.map(s=>({name:s.name,score:s.den?Math.round(s.got/s.den*10000)/100:null}));
}

/* Итог до и после решения по одному критерию (остальные решения учтены как есть). */
function decisionImpact(d,c){return {before:total(d,false,c.id).score,after:total(d).score}}
