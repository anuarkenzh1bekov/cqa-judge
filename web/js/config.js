/* Настройки компонента. Меняются через адрес без правки кода:
   ?embed=1 — режим встраивания (без логотипа, для Dynamics 365)
   ?api=https://host — адрес бэкенда. По умолчанию — тот же адрес, с которого открыт интерфейс
     (бэкенд сам раздаёт web/), а для статического сервера на :5173 — http://localhost:8000
   ?demo=1 — демонстрационный режим без бэкенда (встроенные примеры)
   ?theme=dark|light — тема */
const CQA_CONFIG=(()=>{
  const q=new URLSearchParams(location.search);
  const demo=q.get('demo')==='1';
  let api=q.get('api')||'';
  if(!api&&!demo&&/^https?:$/.test(location.protocol))api=location.port==='5173'?'http://localhost:8000':location.origin;
  return {apiBase:demo?'':api.replace(/\/$/,''),demo,embed:q.get('embed')==='1',theme:q.get('theme')||''};
})();
