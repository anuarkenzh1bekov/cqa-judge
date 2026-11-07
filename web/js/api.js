/* Обращение к бэкенду. Пока адрес не задан, сеть не используется. */
const CQA_API={
  get enabled(){return !!CQA_CONFIG.apiBase},
  async evaluate(record,checklist){
    if(!this.enabled)throw new Error('бэкенд не подключён');
    const r=await fetch(CQA_CONFIG.apiBase.replace(/\/$/,'')+'/evaluate',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({record,checklist})});
    if(!r.ok)throw new Error('HTTP '+r.status);
    return r.json();
  }
};
