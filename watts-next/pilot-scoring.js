/* Shared scoring arithmetic. Review status is never inferred from a numeric input. */
(function(root){
'use strict';
const factors=[['grid','Grid support and reliability',25],['water','Water and cooling',15],['climate','Climate and hazards',15],['emissions','Emissions and clean power',15],['cost','Cost and time to power',15],['community','Land, permits and community',10],['connectivity','High-capacity connectivity',5]].map(([id,label,weight])=>({id,label,weight}));
const presets={Balanced:[25,15,15,15,15,10,5],'Power first':[40,10,10,10,15,10,5],'Water constrained':[20,30,10,15,10,10,5],'Cost first':[20,10,10,10,35,10,5],'Equal weights':[1,1,1,1,1,1,1]};
const number=x=>x===null||x===undefined||x===''?null:(typeof x==='number'&&Number.isFinite(x)?x:null);
function weights(values){if(!Array.isArray(values)||values.length!==7||values.some(x=>!Number.isFinite(x)||x<0)||values.reduce((a,b)=>a+b,0)<=0)throw Error('Enter at least one positive weight; all weights must be zero or greater.');const total=values.reduce((a,b)=>a+b,0);return values.map(x=>x/total*100);}
function evaluate(candidates,values,{mode='evidence'}={}){
 if(!['evidence','assumptions'].includes(mode))throw Error('Unknown score mode');
 const w=weights(values);if(candidates.length<2)throw Error('At least two candidates are required');
 const contracts=factors.map(f=>candidates.map(c=>c.factors[f.id]));
 const comparable=contracts.map(entries=>entries.every(e=>e&&number(e.score)!==null&&e.score>=0&&e.score<=100&&(mode==='assumptions'||e.status==='accepted'))&&entries.every(e=>e.definition_id&&e.definition_id===entries[0].definition_id&&e.period&&e.period===entries[0].period));
 const complete=comparable.every(Boolean);
 const rows=candidates.map(c=>{let lower=0,unknown=0,coverage=0;const parts=factors.map((f,i)=>{const e=c.factors[f.id],s=comparable[i]?number(e.score):null;if(s!==null){lower+=w[i]*s/100;coverage+=w[i];}else unknown+=w[i];return {id:f.id,score:s,weight:w[i],contribution:s===null?null:w[i]*s/100};});return {id:c.id,name:c.name,parts,coverage,score:complete?lower:null,lower,upper:lower+unknown,rank:null,power_status:c.power_status||'Unknown'};});
 if(complete){rows.sort((a,b)=>b.score-a.score||a.name.localeCompare(b.name));rows.forEach((r,i)=>r.rank=i&&Math.abs(r.score-rows[i-1].score)<1e-9?rows[i-1].rank:i+1);}
 return {mode,weights:w,comparable,complete,rows,publication_status:mode==='assumptions'?'What-if assumptions; not evidence-backed':'Proposed method; independent method review pending'};
}
function sensitivity(candidates,mode){return Object.entries(presets).map(([name,w])=>({name,...evaluate(candidates,w,{mode})}));}
function scenarioDemand(s){
 const {load_mw,utilization,pue,basis,profile}=s||{};
 if(!Number.isFinite(load_mw)||load_mw<100||load_mw>1000||!Number.isFinite(utilization)||utilization<.5||utilization>1||!Number.isFinite(pue)||pue<1||pue>2||!['IT','facility'].includes(basis)||!['constant','day-night'].includes(profile))throw Error('Invalid facility scenario');
 const peak_mw=load_mw*utilization*(basis==='IT'?pue:1);
 return {peak_mw,annual_gwh:peak_mw*8760*(profile==='day-night'?.8:1)/1000};
}
function adjustScore(base,response,reference,scenario){
 if(number(base)===null||base<0||base>100)return {score:null,reason:'Factor assessment missing'};
 const r=scenarioDemand(reference),s=scenarioDemand(scenario),dmw=(s.peak_mw-r.peak_mw)/100,dgwh=(s.annual_gwh-r.annual_gwh)/100;
 const power=response?.per100mw,energy=response?.per100gwh;
 if((Math.abs(dmw)>1e-9&&number(power)===null)||(Math.abs(dgwh)>1e-9&&number(energy)===null))return {score:null,reason:'Scenario changed; factor response not specified'};
 if([power,energy].some(v=>v!==undefined&&v!==null&&(!Number.isFinite(v)||Math.abs(v)>100)))return {score:null,reason:'Invalid response coefficient'};
 const raw=base+(power??0)*dmw+(energy??0)*dgwh;
 return {score:Math.max(0,Math.min(100,raw)),raw,clipped:raw<0||raw>100,delta_mw:s.peak_mw-r.peak_mw,delta_gwh:s.annual_gwh-r.annual_gwh};
}
function bestMatches(result){return result.complete?result.rows.filter(r=>r.rank===1):[];}
const api={factors,presets,weights,evaluate,sensitivity,scenarioDemand,adjustScore,bestMatches};root.WattsScoring=api;if(typeof module!=='undefined')module.exports=api;
})(globalThis);
