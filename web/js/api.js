/* Обращение к бэкенду (FastAPI). Описание эндпоинтов — API.md в корне репозитория. */
const CQA_API={
  get enabled(){return !!CQA_CONFIG.apiBase},
  url(p){return CQA_CONFIG.apiBase+p},
  async req(method,p,body){
    const r=await fetch(this.url(p),{method,headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined});
    let j=null;try{j=await r.json()}catch(_){}
    if(!r.ok){
      const d=j&&j.detail;
      const msg=Array.isArray(d)?d.map(x=>(x.loc||[]).slice(1).join('.')+': '+x.msg).join('; '):(d||('HTTP '+r.status));
      throw new Error(msg);
    }
    return j;
  },
  get(p){return this.req('GET',p)},
  post(p,b){return this.req('POST',p,b||{})},
  put(p,b){return this.req('PUT',p,b)},

  health(){return this.get('/api/health')},
  conversations(){return this.get('/api/conversations')},
  evaluation(id){return this.get('/api/evaluations/'+id)},
  activeChecklist(){return this.get('/api/checklists/active')},
  checklists(){return this.get('/api/checklists')},
  defaultChecklist(){return this.get('/api/checklists/default-template')},
  conversationSummary(id){return this.get('/api/conversations/'+encodeURIComponent(id)+'/summary')},
  saveReview(evalId,body){return this.put('/api/evaluations/'+evalId+'/review',body)},
  suggestCriterion(body){return this.post('/api/checklists/suggest-criterion',body)},
  createChecklist(body){return this.post('/api/checklists?activate=true',body)},
  importGroup(group_id){return this.post('/api/datasets/import',{group_id})},
  upload(records){return this.post('/api/conversations',{records,group:'UPLOAD'})},
  batch(body){return this.post('/api/evaluations/batch',body)},
  batchStatus(id){return this.get('/api/batches/'+id)},
  appeal(evalId,criterion_key,comment){return this.post(`/api/evaluations/${evalId}/appeals`,{criterion_key,comment,author:'Оператор'})},
  appeals(){return this.get('/api/appeals')},
  aiReview(apId){return this.post(`/api/appeals/${apId}/ai-review`)},
  decide(apId,body){return this.post(`/api/appeals/${apId}/decision`,body)},
  stats(){return this.get('/api/stats')},
  calibration(){return this.get('/api/calibration')},
  compare(a,b){return this.get(`/api/checklist-compare?a=${a}&b=${b}`)},
  exportUrl(format){return this.url('/api/export?format='+format)},
  operator(name){return this.get('/api/operators/'+encodeURIComponent(name))},
  audioUrl(cid){return this.url('/api/conversations/'+encodeURIComponent(cid)+'/audio')}
};
