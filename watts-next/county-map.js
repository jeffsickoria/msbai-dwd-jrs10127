// County projection, SVG paths, search and pan/zoom reused from the latest app/app.js.
(function(){
'use strict';
const $=id=>document.getElementById(id),num=n=>Number(n).toLocaleString('en-US',{maximumFractionDigits:1});
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let featureIndex=new Map(),countyData=null,selectedCounty=null,suppressMapClick=false,pilotCounties=[];
const fullMapView={x:0,y:0,w:960,h:520};let mapView={...fullMapView};
function countyProject(point){let lon=Number(point[0]),lat=Number(point[1]);if(lon>0)lon-=360;if(lat>50&&lon<-130)return [35+(lon+180)*3.2,320+(72-lat)*3.5];if(lat<24&&lon<-150)return [190+(lon+161)*6,420+(23-lat)*6];return [215+(lon+125)*11,45+(50-lat)*14.5]}
function countyPath(feature){const polygons=feature.geometry.type==='Polygon'?[feature.geometry.coordinates]:feature.geometry.coordinates;let path='';polygons.forEach(polygon=>polygon.forEach(ring=>{ring.forEach((point,index)=>{const [x,y]=countyProject(point);path+=(index?'L':'M')+x.toFixed(1)+' '+y.toFixed(1)});path+='Z'}));return path}
function layerState(feature){return WattsMapLayers.value($('county_metric').value,feature.id,pilotCounties.some(c=>c.fips===feature.id),feature.properties,window.WattsPilotScores?.snapshot()||{});}
function layerPresentation(){
 const id=$('county_metric').value,l=WattsMapLayers.layers.find(l=>l.id===id),snap=window.WattsPilotScores?.snapshot()||{};
 const score=l.kind==='score'||l.kind==='factor',known=pilotCounties.filter(c=>{const f=countyData.features.find(f=>f.id===c.fips);return f&&layerState(f).value!==null;}).length;
 $('map-layer-description').innerHTML='<strong>'+esc(l.label)+'</strong><span>'+esc(l.help)+'</span><small>'+(score?(snap.mode==='assumptions'?'WHAT-IF ASSUMPTIONS · ':'AVAILABLE EVIDENCE · ')+known+' of '+pilotCounties.length+' enabled counties have a comparable value.':l.kind==='coverage'?'Accepted scoring inputs only; assumptions are excluded.':l.kind==='requirements'?'All must-have checks remain pending.':l.kind==='context'?'Released pilot workforce period; independent acceptance pending.':'Enabled for research does not mean eligible to build.')+'</small>';
 const ends=l.kind==='context'?(id==='labor_force'?['Smaller workforce','Larger workforce']:['Lower unemployment','Higher unemployment']):l.kind==='coverage'?['0% accepted','100% accepted']:l.kind==='availability'?['Not enabled','Data enabled']:l.kind==='requirements'?['Unchecked','No verified checks']:['0 · less favorable','100 · more favorable'];
 return '<div class="county-legend"><span>'+ends[0]+'</span><span class="county-gradient"></span><span>'+ends[1]+'</span><span class="pending-key"></span><span>Pending / unchecked</span><span class="disabled-key"></span><span>Not enabled</span></div>';
}
function refreshLayers(){
 if(!countyData)return;
 const legend=$('county_map').querySelector('.county-legend');if(legend)legend.outerHTML=layerPresentation();
 $('county_map').querySelectorAll('.county-shape').forEach(node=>{const f=featureIndex.get(node.dataset.fips),state=layerState(f);node.setAttribute('fill',WattsMapLayers.color(state,$('county_metric').value));node.querySelector('title').textContent=f.properties.county_name+', '+f.properties.state_abbreviation+' · '+state.label;});
 $('county_map').querySelectorAll('.pilot-marker').forEach(node=>{const f=featureIndex.get(node.dataset.fips),state=layerState(f);node.querySelector('circle').style.fill=WattsMapLayers.color(state,$('county_metric').value);node.querySelector('title').textContent=state.label;});
}
function constrainMapView(view){
  const ratio=fullMapView.w/fullMapView.h,w=Math.max(120,Math.min(fullMapView.w,view.w)),h=w/ratio;
  return {x:Math.max(0,Math.min(fullMapView.w-w,view.x)),y:Math.max(0,Math.min(fullMapView.h-h,view.y)),w,h};
}
function applyMapView(){
  const svg=$('county_map')?.querySelector('.county-map-svg');if(!svg)return;
  svg.setAttribute('viewBox',[mapView.x,mapView.y,mapView.w,mapView.h].map(value=>value.toFixed(2)).join(' '));
  $('map_zoom_value').textContent=Math.round(100*fullMapView.w/mapView.w)+'%';
}
function zoomCountyMap(factor,screenX=null,screenY=null){
  const svg=$('county_map')?.querySelector('.county-map-svg');if(!svg)return;
  const rect=svg.getBoundingClientRect(),rx=screenX==null ? .5 : Math.max(0,Math.min(1,(screenX-rect.left)/rect.width)),ry=screenY==null ? .5 : Math.max(0,Math.min(1,(screenY-rect.top)/rect.height));
  const w=mapView.w*factor,h=w/(fullMapView.w/fullMapView.h),anchorX=mapView.x+rx*mapView.w,anchorY=mapView.y+ry*mapView.h;
  mapView=constrainMapView({x:anchorX-rx*w,y:anchorY-ry*h,w,h});applyMapView();
}
function resetCountyMap(){mapView={...fullMapView};applyMapView()}
function initMapNavigation(){
  const svg=$('county_map').querySelector('.county-map-svg');if(!svg)return;
  $('map_zoom_in').onclick=()=>zoomCountyMap(.7);$('map_zoom_out').onclick=()=>zoomCountyMap(1/.7);$('map_zoom_reset').onclick=resetCountyMap;
  svg.addEventListener('wheel',event=>{if(!event.ctrlKey&&!event.metaKey)return;event.preventDefault();zoomCountyMap(event.deltaY<0 ? .82 : 1/.82,event.clientX,event.clientY)},{passive:false});
  const pointers=new Map();let start=null,pinch=null,moved=false;
  const pinchState=()=>{const values=[...pointers.values()],a=values[0],b=values[1];return {distance:Math.hypot(a.x-b.x,a.y-b.y),centerX:(a.x+b.x)/2,centerY:(a.y+b.y)/2,view:{...mapView}}};
  svg.addEventListener('pointerdown',event=>{pointers.set(event.pointerId,{x:event.clientX,y:event.clientY});if(pointers.size===1){start={x:event.clientX,y:event.clientY,view:{...mapView}};moved=false}else if(pointers.size===2){pinch=pinchState();start=null}});
  svg.addEventListener('pointermove',event=>{if(!pointers.has(event.pointerId))return;pointers.set(event.pointerId,{x:event.clientX,y:event.clientY});const rect=svg.getBoundingClientRect();if(pointers.size===2&&pinch){const now=pinchState(),factor=pinch.distance/Math.max(now.distance,1),rx=(pinch.centerX-rect.left)/rect.width,ry=(pinch.centerY-rect.top)/rect.height,w=pinch.view.w*factor,h=w/(fullMapView.w/fullMapView.h),anchorX=pinch.view.x+rx*pinch.view.w,anchorY=pinch.view.y+ry*pinch.view.h;mapView=constrainMapView({x:anchorX-rx*w,y:anchorY-ry*h,w,h});moved=true;applyMapView()}else if(start){const dx=event.clientX-start.x,dy=event.clientY-start.y;if(Math.abs(dx)+Math.abs(dy)>3)moved=true;mapView=constrainMapView({x:start.view.x-dx*start.view.w/rect.width,y:start.view.y-dy*start.view.h/rect.height,w:start.view.w,h:start.view.h});applyMapView()}if(moved){try{svg.setPointerCapture(event.pointerId)}catch{}}svg.classList.toggle('dragging',moved)});
  const end=event=>{pointers.delete(event.pointerId);try{svg.releasePointerCapture(event.pointerId)}catch(e){/* Capture may already be released. */}if(moved){suppressMapClick=true;setTimeout(()=>{suppressMapClick=false;},0);}svg.classList.remove('dragging');if(pointers.size===1){const remaining=[...pointers.values()][0];start={x:remaining.x,y:remaining.y,view:{...mapView}};pinch=null}else{start=null;pinch=null}};
  svg.addEventListener('click',event=>{if(suppressMapClick){event.preventDefault();event.stopImmediatePropagation();suppressMapClick=false;}},true);
  svg.addEventListener('pointerup',end);svg.addEventListener('pointercancel',end);applyMapView();
}
function renderCountyMap(){
  if(!countyData)return;const metric=$('county_metric').value; $('county_map').dataset.metric=metric;const features=countyData.features.filter(feature=>feature.properties.national_screen_eligible);
  let svg='<svg class="county-map-svg" viewBox="0 0 960 520" role="group" aria-label="County map: '+esc($('county_metric').selectedOptions[0].textContent)+'"><defs><pattern id="pending-county" patternUnits="userSpaceOnUse" width="6" height="6"><rect width="6" height="6" fill="#f4efe1"/><path d="M-1 1L1-1M0 6L6 0M5 7L7 5" stroke="#a59361" stroke-width="1.2"/></pattern></defs>';
  features.forEach(feature=>{const p=feature.properties,state=layerState(feature),label=p.county_name+', '+p.state_abbreviation+' · '+state.label;svg+='<path class="county-shape'+(feature.id===selectedCounty?' selected':'')+'" data-fips="'+esc(feature.id)+'" d="'+countyPath(feature)+'" fill="'+WattsMapLayers.color(state,metric)+'"><title>'+esc(label)+'</title></path>'});
  const markers=pilotCounties.map(c=>{const f=features.find(f=>f.id===c.fips);if(!f)return '';const ring=f.geometry.type==='Polygon'?f.geometry.coordinates[0]:f.geometry.coordinates[0][0],xy=ring.map(countyProject),x=(Math.min(...xy.map(p=>p[0]))+Math.max(...xy.map(p=>p[0])))/2,y=(Math.min(...xy.map(p=>p[1]))+Math.max(...xy.map(p=>p[1])))/2;return '<g class="pilot-marker" data-fips="'+esc(c.fips)+'" role="button" tabindex="0" aria-label="Inspect '+esc(c.name)+', '+esc(c.state)+'"><title>'+esc(layerState(f).label)+'</title><circle style="fill:'+WattsMapLayers.color(layerState(f),metric)+'" cx="'+x+'" cy="'+y+'" r="7"/><text x="'+(x-9)+'" y="'+(y-9)+'" text-anchor="end">'+esc(c.name.replace(' County',''))+'</text></g>';}).join('');
  $('county_map').innerHTML=layerPresentation()+svg+markers+'</svg>';
  $('county_map').querySelectorAll('.county-shape').forEach(node=>node.onclick=()=>{if(suppressMapClick){suppressMapClick=false;return}showCounty(countyData.features.find(feature=>feature.id===node.dataset.fips))});$('county_map').querySelectorAll('.pilot-marker').forEach(node=>{const choose=()=>showCounty(featureIndex.get(node.dataset.fips));node.onclick=choose;node.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();choose();}};});initMapNavigation();
}
async function loadCounties(){
  try{const response=await wattsReleaseData('county-screen.geojson');if(!response.ok)throw Error('County layer unavailable');countyData=await response.json();featureIndex=new Map(countyData.features.map(f=>[f.id,f]));
    const withWorkforce=countyData.features.filter(feature=>feature.properties.labor_force!=null).length,eligible=countyData.features.filter(feature=>feature.properties.national_screen_eligible).length;
    $('county_map_status').textContent=num(eligible)+' U.S. county boundaries · '+pilotCounties.length+' counties with data enabled · all other counties show geography only.';
    $('county_options').innerHTML=countyData.features.filter(feature=>feature.properties.national_screen_eligible).map(feature=>'<option value="'+esc(feature.properties.county_name+', '+feature.properties.state_abbreviation+' ('+feature.id+')')+'"></option>').join('');
    $('county_metric').innerHTML=WattsMapLayers.layers.map(l=>'<option value="'+l.id+'">'+esc(l.label)+'</option>').join('');$('county_metric').value=WattsContext.get().map_layer;
    $('county_metric').onchange=()=>{WattsContext.update({map_layer:$('county_metric').value});renderCountyMap();};$('county_search').onchange=()=>{const text=$('county_search').value.trim().toLowerCase(),feature=countyData.features.find(row=>(row.properties.county_name+', '+row.properties.state_abbreviation+' ('+row.id+')').toLowerCase()===text)||countyData.features.find(row=>row.id===text);if(feature){$('county-search-message').textContent='';showCounty(feature);}else {const normalize=v=>v.toLowerCase().replace(/\bcounty\b/g,'').replace(/[^a-z0-9]/g,'');const hits=countyData.features.filter(row=>row.properties.national_screen_eligible&&(normalize(row.properties.county_name)===normalize(text)||normalize(row.properties.county_name+row.properties.state_abbreviation)===normalize(text)));if(hits.length===1){$('county-search-message').textContent='';showCounty(hits[0]);}else {$('county-search-message').textContent=hits.length?'More than one match. Choose the county and state; the previous selection is retained.':'No county matches. Choose a suggestion or five-digit FIPS; the previous selection is retained.';$('county_detail').innerHTML=hits.length?'<h3>More than one county matches</h3><p>Choose the county and state from the suggestions, or enter its five-digit FIPS code.</p>':'<h3>No county found</h3><p>Choose a county from the suggestion list or enter its five-digit FIPS code.</p>'; } }};
    $('county_search').disabled=false;$('county_search').onkeydown=event=>{if(event.key==='Enter'){event.preventDefault();$('county_search').onchange();}};
    renderCountyMap();
  }catch(error){$('county_map_status').textContent=error.message;$('county_map').innerHTML='<p class="empty">Build the county layer to enable the map.</p>'}
}

function showCounty(feature){
 if(!feature)return;selectedCounty=feature.id;
 document.querySelectorAll('.county-shape').forEach(node=>node.classList.toggle('selected',node.dataset.fips===selectedCounty));
 const p=feature.properties,pilot=pilotCounties.find(c=>c.fips===p.county_fips),l=pilot?.laus_latest;
 if(!pilot){$('county_detail').innerHTML='<h3>'+esc(p.county_name)+', '+esc(p.state_abbreviation)+'</h3><p>FIPS '+esc(p.county_fips)+'. Geographic boundary only.</p><p>County data, suitability scores and analysis are not enabled for this location.</p>';if(window.WattsResearch)window.WattsResearch.selected(feature);return;}
 const force=l.labor_force,rate=l.unemployment_rate_pct;
 const row=(name,value)=>'<dt>'+esc(name)+'</dt><dd>'+esc(value)+'</dd>';
 $('county_detail').innerHTML='<h3>'+esc(p.county_name)+', '+esc(p.state_abbreviation)+'</h3><p class="hint">FIPS '+esc(p.county_fips)+'</p><dl>'+row('Labor force',force==null?'Not available':num(force))+row('Unemployment',rate==null?'Not available':num(rate)+'%')+row('Workforce period',l?l.month+(l.preliminary==='True'?' preliminary':''):p.workforce_period||'Not available')+row('Evidence state',l?'Acquired; acceptance pending':'Historical prototype')+(pilot?row('QCEW March 2026 jobs',pilot.qcew_total?num(pilot.qcew_total.month3_emplvl):'Not available'):'')+row('Grid support','Pending')+row('Water and cooling','Pending')+row('Climate and hazards','Pending')+row('Emissions','Pending')+row('Connectivity','Pending')+row('Site power','Unknown')+'</dl><p class="hint">'+(pilot?'This county has newer acquired pilot evidence. Map colors and county detail use the same released pilot workforce period.':'National workforce is the original August 2025 prototype; no current national refresh is inferred from the three-county acquisition.')+'</p><p class="hint">County selection does not change the regional power comparison. Resident labor force and workplace jobs are different measures.</p><a href="research.html#evidence">Inspect data and source states →</a>';
 if(window.WattsResearch)window.WattsResearch.selected(feature);
}
window.WattsCountyMap={mount:async function(counties){pilotCounties=counties;await loadCounties();},show:f=>showCounty(typeof f==='string'?countyData.features.find(c=>c.id===f):f),feature:f=>countyData?.features.find(c=>c.id===f),refreshLayers:()=>{if(countyData){$('county_metric').value=WattsContext.get().map_layer;refreshLayers();}}};
})();
