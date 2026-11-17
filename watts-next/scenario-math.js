// Shared by the browser and Node verification. These are declared scenario
// calculations, never an optimizer, capacity estimate, or siting score.
(function(root){
  'use strict';
  function quantile(sorted,q){const i=(sorted.length-1)*q,j=Math.floor(i);return sorted[j]+(sorted[Math.min(j+1,sorted.length-1)]-sorted[j])*(i-j);}
  function calculate(region,scenario){
    const {load_mw,utilization,pue,basis,profile}=scenario;
    if(!Number.isFinite(load_mw)||load_mw<100||load_mw>1000||!Number.isFinite(utilization)||utilization<.5||utilization>1||!Number.isFinite(pue)||pue<1||pue>2)throw Error('Scenario inputs outside declared bounds');
    if(!['IT','facility'].includes(basis)||!['constant','day-night'].includes(profile))throw Error('Unknown scenario definition');
    const baseline=region.demand_mw;
    if(!baseline.length||baseline.some(v=>!Number.isFinite(v)||v<=0)||region.local_hours.length!==baseline.length)throw Error('Incomplete demand/calendar series');
    const sorted=[...baseline].sort((a,b)=>a-b),peak=sorted.at(-1),threshold=quantile(sorted,.99);
    const facility=load_mw*utilization*(basis==='IT'?pue:1);
    let combinedPeak=0,annualMwh=0,above99=0,abovePeak=0,baselineAbove99=0;
    const combined=baseline.map((value,i)=>{const h=region.local_hours[i],mw=facility*(profile==='day-night'&&(h<8||h>=20)?.6:1);const total=value+mw;annualMwh+=mw;combinedPeak=Math.max(combinedPeak,total);above99+=total>threshold;abovePeak+=total>peak;baselineAbove99+=value>threshold;return total;});
    return {region_id:region.id,baseline_peak_mw:peak,combined_peak_mw:combinedPeak,peak_increment_mw:combinedPeak-peak,annual_facility_mwh:annualMwh,threshold_p99_mw:threshold,baseline_hours_above_p99:baselineAbove99,hours_above_p99:above99,additional_hours_above_p99:above99-baselineAbove99,hours_above_historical_peak:abovePeak,sorted_baseline:sorted.reverse(),sorted_combined:combined.sort((a,b)=>b-a)};
  }
  const api={quantile,calculate};root.WattsScenario=api;if(typeof module!=='undefined')module.exports=api;
})(globalThis);
