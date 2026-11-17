/* Shared map presentation contract. Unknown scores never acquire a color value. */
(function(root){
'use strict';
const layers=[
 ['overall','Overall fit','score','Higher scores mean a better fit under the current requirements and priorities. This is not permission to build.'],
 ['grid','Power and grid','factor','Grid-support and reliability factor. Regional demand and utility names do not prove available power at a parcel.'],
 ['water','Water and cooling','factor','Water/cooling factor. A score needs comparable water-use, availability and service evidence.'],
 ['climate','Climate and hazards','factor','Climate/hazard factor. County exposure is not a parcel engineering assessment.'],
 ['cost','Cost and timing','factor','Cost/time-to-power factor. Prices, upgrades and connection dates need comparable evidence.'],
 ['emissions','Emissions and clean power','factor','Emissions/clean-power factor under a stated accounting method and period.'],
 ['community','Permits and community','factor','Land, permits and community factor. Reported news is not a representative opinion survey.'],
 ['connectivity','Network connectivity','factor','High-capacity connectivity factor. Residential broadband does not prove data-center network service.'],
 ['evidence_coverage','Scoring evidence coverage','coverage','Share of the planned scoring weight with accepted comparable inputs. Assumptions never count as accepted evidence.'],
 ['requirements','Must-have checks','requirements','Required power, date, water and other constraints need separate checks. Automatic checking is not implemented yet.'],
 ['pilot_coverage','Data availability','availability','Enabled counties have pilot data. Other counties show geographic boundaries only. Enabled does not mean suitable.'],
 ['labor_force','Labor force · context','context','Resident labor force in the released pilot month. This is not available specialist staff or jobs created by a center.'],
 ['unemployment_rate_pct','Unemployment · context','context','Unemployment rate in the released pilot month. This is local context, not a suitability score.']
].map(([id,label,kind,help])=>({id,label,kind,help}));
function value(id,fips,enabled,properties={},snapshot={}){
 const layer=layers.find(l=>l.id===id)||layers[0];
 if(!enabled)return {status:'disabled',value:null,label:'Not enabled'};
 const row=snapshot.result?.rows.find(r=>r.id===fips),assumed=snapshot.mode==='assumptions';
 if(layer.kind==='availability')return {status:'known',value:100,label:'Pilot data enabled'};
 if(layer.kind==='requirements')return {status:'pending',value:null,label:'Must-haves not checked'};
 if(layer.kind==='coverage'){const v=snapshot.mode==='evidence'&&row?row.coverage:0;return {status:'known',value:v,label:v.toFixed(1)+'% accepted comparable scoring evidence'};}
 if(layer.kind==='context'){const v=properties[id];return v!==null&&v!==undefined&&v!==''&&Number.isFinite(Number(v))?{status:'known',value:Number(v),label:Number(v).toLocaleString('en-US')+(id==='unemployment_rate_pct'?'%':'')+' · '+(properties.workforce_period||'period not recorded')}:{status:'pending',value:null,label:'Context data pending'};}
 const v=layer.kind==='score'?row?.score:row?.parts?.find(p=>p.id===id)?.score;
 return Number.isFinite(v)?{status:assumed?'assumed':'known',value:v,label:(assumed?'What-if ':'')+v.toFixed(2)+'/100'}:{status:'pending',value:null,label:(row?'Score pending':'Not in current comparison; score pending')};
}
function color(state,id){
 if(state.status==='disabled')return '#d8e0e2';
 if(state.value===null)return 'url(#pending-county)';
 if(id==='pilot_coverage')return '#278d75';
 let t=id==='labor_force'?(Math.log10(Math.max(state.value,100))-2)/5:id==='unemployment_rate_pct'?(state.value-2)/10:state.value/100;
 t=Math.max(0,Math.min(1,t));const a=[225,240,239],b=[13,104,92];return 'rgb('+a.map((v,i)=>Math.round(v+(b[i]-v)*t)).join(',')+')';
}
const api={layers,value,color};root.WattsMapLayers=api;if(typeof module!=='undefined')module.exports=api;
})(globalThis);
