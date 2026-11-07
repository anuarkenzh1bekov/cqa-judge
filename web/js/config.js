/* Настройки компонента. Меняются через адрес без правки кода:
   ?embed=1 — режим встраивания (без логотипа, для Dynamics 365)
   ?api=https://host — адрес бэкенда; без него работает демонстрационный режим
   ?theme=dark|light — тема */
const CQA_CONFIG=(()=>{
  const q=new URLSearchParams(location.search);
  return {apiBase:q.get('api')||'',embed:q.get('embed')==='1',theme:q.get('theme')||''};
})();
