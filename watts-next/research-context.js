/* Public research context shared by the map, research page and exports. */
(function(){
 'use strict';
 const key='watts-next-public-context-v1';
 const defaults={version:1,counties:[],selected:null,scenario:{load_mw:500,basis:'IT',utilization:.85,pue:1.2,profile:'constant'},isne_case:'reference',isne_profile:'Constant'};
 function clean(raw){
  const c={...defaults,scenario:{...defaults.scenario}},r=raw&&typeof raw==='object'?raw:{};
  c.counties=[...new Set((Array.isArray(r.counties)?r.counties:[]).filter(f=>typeof f==='string'&&/^\d{5}$/.test(f)))].slice(0,4);
  c.map_layer=WattsMapLayers.layers.some(l=>l.id===r.map_layer)?r.map_layer:'overall';
  c.selected=typeof r.selected==='string'&&/^\d{5}$/.test(r.selected)?r.selected:null;
  c.release=typeof r.release==='string'&&/^[a-f0-9]{64}$/.test(r.release)?r.release:null;
  const s=r.scenario||{};
  for(const [k,min,max] of [['load_mw',100,1000],['utilization',.5,1],['pue',1,2]])if(Number.isFinite(s[k])&&s[k]>=min&&s[k]<=max)c.scenario[k]=s[k];
  if(['IT','facility'].includes(s.basis))c.scenario.basis=s.basis;
  if(['constant','day-night'].includes(s.profile))c.scenario.profile=s.profile;
  if(typeof r.isne_case==='string'&&/^[a-z_]{1,40}$/.test(r.isne_case))c.isne_case=r.isne_case;
  if(['Constant','Day-night','Afternoon-heavy','Night-heavy'].includes(r.isne_profile))c.isne_profile=r.isne_profile;
  return c;
 }
 let state=clean(null),warning='';
 try{const p=new URL(location.href).searchParams;if(p.has('context'))state=clean(JSON.parse(p.get('context')));else state=clean(JSON.parse(localStorage.getItem(key)||'null'));}catch{warning='Saved context could not be read. Defaults restored.';}
 function url(path=location.href){const u=new URL(path,location.href);u.searchParams.set('context',JSON.stringify(state));return u.href;}
 function save(){try{localStorage.setItem(key,JSON.stringify(state));}catch{/* Sharing still works when storage is disabled. */}document.querySelectorAll('a[href*="research.html"],a[href*="index.html"]').forEach(a=>{a.href=url(a.href);});}
 window.WattsContext={get:()=>clean(state),update:patch=>{state=clean({...state,...patch});save();window.dispatchEvent(new Event("watts-context-change"));},url,
  attach:release=>{if(state.release&&state.release!==release)warning='This link was saved against a different release. Values shown use the current release; check dates before comparing.';state.release=release;save();return warning;},
  brief:(data,countyRows)=>({kind:'county research brief; no suitability ranking',context_contract_version:1,product_release_id:data.product_release_id,regional_snapshot_id:data.release_id,context:clean(state),counties:countyRows,regional_context:{assignment:'Not assigned to shortlisted counties',scenario:state.scenario},limitations:data.limitations})};
})();
