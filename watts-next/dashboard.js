'use strict';
const $=id=>document.getElementById(id);
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=(value,digits=0)=>value==null?'Not available':Number(value).toLocaleString('en-US',{maximumFractionDigits:digits});
const money=value=>value==null?'Not available':new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:0}).format(value);
const colors=['#11766e','#3778bd','#b27035'];
let data,comparison=[],selectedRecord=null;
const kpi=(label,value,detail)=>`<div class="kpi"><div class="label">${esc(label)}</div><div class="value">${esc(value)}</div><div class="detail">${esc(detail)}</div></div>`;
function safeLink(url,label){try{const u=new URL(url);if(u.protocol!=='https:')return esc(label);return `<a href="${esc(u.href)}" target="_blank" rel="noopener noreferrer">${esc(label)} ↗</a>`;}catch{return esc(label);}}
function svgChart(lines,{yLabel='Demand · GW',xLabel='Share of hours, highest to lowest',labels=null}={}){
  const width=700,height=270,left=62,right=18,top=23,bottom=43,w=width-left-right,h=height-top-bottom;
  const max=Math.max(...lines.flatMap(l=>l.values)),scale=max>0?max*1.1:1;
  const points=values=>values.map((v,i)=>`${(left+i*w/Math.max(1,values.length-1)).toFixed(2)},${(top+h-v/scale*h).toFixed(2)}`).join(' ');
  let svg=`<svg class="chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(lines.map(l=>l.label).join(' compared with '))}. ${esc(yLabel)}. ${esc(xLabel)}."><title>${esc(lines.map(l=>l.label).join(' / '))}</title>`;
  for(let i=0;i<=4;i++){const y=top+h-i*h/4;svg+=`<line class="grid" x1="${left}" x2="${width-right}" y1="${y}" y2="${y}"/><text x="${left-10}" y="${y+4}" text-anchor="end">${fmt(scale*i/4/1000,1)}</text>`;}
  for(let i=0;i<=4;i++)svg+=`<text x="${left+i*w/4}" y="${height-22}" text-anchor="middle">${esc(labels?labels[Math.round(i*(labels.length-1)/4)]:i*25+'%')}</text>`;
  svg+=`<text x="${left}" y="12">${esc(yLabel)}</text><text x="${left+w/2}" y="${height-2}" text-anchor="middle">${esc(xLabel)}</text>`;
  for(const line of lines)svg+=`<polyline points="${points(line.values)}" fill="none" stroke="${line.color}" stroke-width="2.6" stroke-linejoin="round"/>`;
  return svg+'</svg>';
}
function sampled(values,count=101){return Array.from({length:Math.min(count,values.length)},(_,i)=>values[Math.round(i*(values.length-1)/(Math.min(count,values.length)-1))]);}
function renderOverview(){
  $('overview-kpis').innerHTML=kpi('Historical demand coverage','3 regions','8,760 hourly intervals per region')+kpi('Local evidence pilot','3 counties','LAUS through Aug 2026 · preliminary')+kpi('ISNE policy evaluation',fmt(data.isne.evaluation.evaluation_hours)+' h','32 declared case / shape combinations')+kpi('Accepted site recommendations','0','Connection feasibility remains unknown');
  $('overview-chart').innerHTML=svgChart(data.regions.map((r,i)=>({label:r.name,color:colors[i],values:sampled([...r.demand_mw].sort((a,b)=>b-a))})));
  const evaluation=data.isne.evaluation;
  $('research-highlight').innerHTML=`<div class="research-stat"><strong>${fmt(evaluation.forecast_mae_mw)} MW</strong><span>Forecast MAE · week-ago reference ${fmt(evaluation.week_ago_utc_reference_mae_mw)} MW</span></div>`;
  $('county-cards').innerHTML=data.counties.map(c=>{const l=c.laus_latest,q=c.qcew_total;return `<article class="county"><header><div><span class="fips">${esc(c.state)} · FIPS ${esc(c.fips)}</span><h3>${esc(c.name)}</h3></div><span class="tag amber">Acquired</span></header><dl><dt>Resident labor force</dt><dd>${fmt(l.labor_force)}</dd><dt>Unemployment rate</dt><dd>${fmt(l.unemployment_rate_pct,1)}%</dd><dt>Covered workplace jobs</dt><dd>${q?fmt(q.month3_emplvl):'Not available'}</dd></dl><small>LAUS ${esc(l.month)}${l.preliminary==='True'?' · preliminary':''}; QCEW March 2026, all industries / ownership. Specialist workforce availability is unknown.</small><p class="fine">${esc(c.status)}. County evidence does not change the regional scenario.</p><a class="text-link" href="#evidence">Inspect source definitions →</a></article>`;}).join('');
}
function scenario(){return {load_mw:Number($('load').value),utilization:Number($('utilization').value),pue:Number($('pue').value),basis:$('basis').value,profile:$('profile').value};}
function updateScenario(){
  const s=scenario();$('load-value').textContent=fmt(s.load_mw)+' MW';$('util-value').textContent=fmt(100*s.utilization)+'%';$('pue-value').textContent=s.pue.toFixed(2);$('pue').disabled=s.basis==='facility';$('pue-note').textContent=s.basis==='facility'?'Whole-building size already includes cooling; the multiplier is not applied.':'A multiplier of 1.20 adds 20% for cooling and other building needs.';
  document.querySelectorAll('[data-load]').forEach(b=>b.classList.toggle('active',Number(b.dataset.load)===s.load_mw));
  comparison=data.regions.map(r=>WattsScenario.calculate(r,s));
  const current=comparison.find(r=>r.region_id===$('chart-region').value)||comparison[0],region=data.regions.find(r=>r.id===current.region_id);
  $('scenario-kpis').innerHTML=kpi('Added facility energy',fmt(current.annual_facility_mwh/1000,1)+' GWh',region.name+' · one historical year')+kpi('Combined peak increase',fmt(current.peak_increment_mw,1)+' MW','Derived from the selected profile')+kpi('Hours above historical peak',fmt(current.hours_above_historical_peak),'Exceeds historical maximum, not capacity');
  $('scenario-chart').innerHTML=svgChart([{label:'Historical baseline',color:'#bdc8cf',values:sampled(current.sorted_baseline)},{label:'Baseline plus facility',color:colors[0],values:sampled(current.sorted_combined)}]);
  $('scenario-table').innerHTML='<table><caption>2025 hourly demand · local day/night conventions · no dispatch intervention</caption><thead><tr><th>Region</th><th class="num">Historical peak<br>MW</th><th class="num">Peak increment<br>MW</th><th class="num">Additional hours<br>above p99</th><th class="num">Hours above<br>historical peak</th></tr></thead><tbody>'+comparison.map((r,i)=>`<tr><td><strong>${esc(data.regions[i].name)}</strong><small>${esc(data.regions[i].timezone)}</small></td><td class="num">${fmt(r.baseline_peak_mw)}</td><td class="num">${fmt(r.peak_increment_mw,1)}</td><td class="num">${fmt(r.additional_hours_above_p99)}</td><td class="num">${fmt(r.hours_above_historical_peak)}</td></tr>`).join('')+'</tbody></table>';
  WattsContext.update({scenario:s});
}
const caseNames={reference:'Reference · 20% flexibility',flex_zero:'No flexibility',flex_low:'10% flexibility',flex_high:'30% flexibility',flat_energy_price:'Flat energy price',higher_energy_spread:'Higher energy price spread',no_demand_charge:'No demand charge',higher_demand_charge:'Higher demand charge'};
function strategyTable(options,baseline){return '<table><caption>All changes compared with no intervention, within this table’s period and shape</caption><thead><tr><th>Strategy</th><th class="num">Modeled period bill</th><th class="num">Bill change vs no intervention</th><th class="num">Regional combined<br>peak · MW</th><th class="num">Peak change<br>MW</th><th class="num">Mean facility increment at top 100 baseline hours · MW</th><th class="num">Top-100 relief vs no intervention · MW</th></tr></thead><tbody>'+options.map(o=>`<tr><td><strong>${esc(o.strategy)}</strong><small>${esc(o.status)}</small></td><td class="num">${money(o.modeled_period_bill_usd)}</td><td class="num">${o.modeled_period_bill_usd==null?'Not available':money(o.modeled_period_bill_usd-baseline.modeled_period_bill_usd)}</td><td class="num">${fmt(o.regional_combined_peak_mw,2)}</td><td class="num">${o.regional_combined_peak_mw==null?'Not available':fmt(o.regional_combined_peak_mw-baseline.regional_combined_peak_mw,2)}</td><td class="num">${fmt(o.mean_increment_at_top_baseline_hours_mw,2)}</td><td class="num">${o.mean_increment_at_top_baseline_hours_mw==null?'Not available':fmt(baseline.mean_increment_at_top_baseline_hours_mw-o.mean_increment_at_top_baseline_hours_mw,2)}</td></tr>`).join('')+'</tbody></table>';}
function renderISNE(){
  const i=data.isne,e=i.evaluation;
  $('isne-kpis').innerHTML=kpi('Verified source intervals','8,760','2025 UTC year · native balancing authority')+kpi('Publisher-imputed hours',fmt(i.quality.publisher_imputed||0),'Source flags preserved, not hidden')+kpi('Evaluation days',fmt(e.evaluation_days),'183 local days · includes fall DST')+kpi('Source acceptance',i.source_status,'Method and independent review remain open');
  $('isne-lineage').innerHTML=`Source <code>${esc(i.source_id)}</code><br>Input SHA-256 <code>${esc(i.input_sha256)}</code><br>Snapshot <code>${esc(i.snapshot_id)}</code>`;
  const max=Math.max(e.forecast_mae_mw,e.week_ago_utc_reference_mae_mw);
  $('forecast-result').innerHTML='<div class="forecast-bars">'+[['Eight-week hour-of-week forecast',e.forecast_mae_mw],['Week-ago UTC-hour reference',e.week_ago_utc_reference_mae_mw]].map(([label,value])=>`<div class="forecast-bar"><span>${esc(label)}</span><strong>${fmt(value,2)} MW</strong><div class="bar"><i style="width:${100*value/max}%"></i></div></div>`).join('')+'</div>';
  $('isne-case').innerHTML=[...new Set(e.records.map(r=>r.case))].map(c=>`<option value="${esc(c)}">${esc(caseNames[c]||c)}</option>`).join('');
  $('isne-profile').innerHTML=[...new Set(e.records.map(r=>r.profile))].map(p=>`<option>${esc(p)}</option>`).join('');
  $('isne-limits').innerHTML=i.pilot.limitations.map(l=>`<li>${esc(l)}</li>`).join('');
  updateISNE();
  const probe=data.publisher_forecast_probe;
  $('publisher-probe').innerHTML=`<h3>Publisher forecast qualification</h3><p>Matched ${fmt(probe.matched_forecast_hours)} of ${fmt(probe.evaluation_hours)} hours. Retrospective current-vintage error: ${fmt(probe.mae_mw_on_matched_hours,2)} MW MAE (lower is better).</p><p><strong>${esc(probe.qualification)}</strong> No scheduling policy was run using this forecast. The day-ahead EIA publication deadline is 11 a.m. Eastern, after this experiment’s midnight decision; exact earlier issue times remain unverified.</p><a href="https://www.eia.gov/electricity/930-content/about.html" target="_blank" rel="noopener">EIA publication documentation</a>`;
}
function updateISNE(){
  selectedRecord=data.isne.evaluation.records.find(r=>r.case===$('isne-case').value&&r.profile===$('isne-profile').value);
  if(!selectedRecord){$('isne-table').textContent='No matching run in this release.';return;}
  WattsContext.update({isne_case:selectedRecord.case,isne_profile:selectedRecord.profile});
  $('isne-table').innerHTML=strategyTable(selectedRecord.options,selectedRecord.options[0]);
  $('isne-case-note').textContent=`${caseNames[selectedRecord.case]||selectedRecord.case} · ${selectedRecord.profile}. Evaluation facility energy: ${fmt(selectedRecord.evaluation_facility_mwh)} MWh. Negative changes mean reductions; positive bill changes are adverse.`;
  const pilot=data.isne.pilot.profiles.find(r=>r.profile===selectedRecord.profile);
  $('pilot-table').innerHTML='<p class="muted">Separate full-year experiment: do not compare its totals with the partial-year policy table.</p>'+strategyTable(pilot.options,pilot.options[0]);
}
function renderSources(){
  const counts=data.sources.reduce((m,s)=>(m[s.status]=(m[s.status]||0)+1,m),{});
  $('source-kpis').innerHTML=kpi('Registered source records',fmt(data.sources.length),'Each has a product identity and source link')+kpi('Candidate sources',fmt(counts.candidate||0),'Acquired / identified; qualification pending')+kpi('Conditional sources',fmt(counts.conditional||0),'Measured; acceptance remains independent')+kpi('Accepted sources',fmt(counts.accepted||0),'Acceptance is not inferred from loading');
  updateSources();
  const f=data.ferc.forecasts;
  $('ferc-chart').innerHTML=svgChart([{label:'FERC ISNE summer forecast',color:colors[0],values:f.map(r=>r.summer_peak_mw)},{label:'FERC ISNE winter forecast',color:colors[1],values:f.map(r=>r.winter_peak_mw)}],{yLabel:'Forecast peak · GW',xLabel:'Forecast year · summer / winter',labels:f.map(r=>r.year)});
  $('ferc-table').innerHTML='<table><thead><tr><th>Forecast year</th><th class="num">Summer peak MW</th><th class="num">Winter peak MW</th></tr></thead><tbody>'+f.map(r=>`<tr><td>${r.year}</td><td class="num">${fmt(r.summer_peak_mw)}</td><td class="num">${fmt(r.winter_peak_mw)}</td></tr>`).join('')+'</tbody></table>';
  $('planning-list').innerHTML=data.planning_sources.map(p=>`<div class="planning-item">${safeLink(p.requested_url,p.file)}<small>${esc(p.status?.replaceAll('_',' '))} · acquired ${esc(p.retrieved_utc?.slice(0,10))}</small></div>`).join('');
  $('release-details').innerHTML=`<p>Built ${esc(data.built_at_utc)}. Historical three-region release: <code>${esc(data.release_id)}</code>.</p><ul>${data.limitations.map(l=>`<li>${esc(l)}</li>`).join('')}</ul><p class="fine">Source snapshots are frozen. This is not live grid monitoring. Cloud hosting does not refresh source data automatically.</p>`;
}
function updateSources(){
 const query=$('source-search').value.toLowerCase();
 const usage=(data.usage_inventory||[]).filter(s=>JSON.stringify(s).toLowerCase().includes(query));
 $('usage-table').innerHTML=usage.map(s=>`<details class="source-entry"><summary><strong>${esc(s.name)}</strong><span>${esc(s.use_status)}</span></summary><p>${esc(s.purpose)}</p><dl><dt>How we obtain it</dt><dd>${esc(s.acquisition)}</dd><dt>Where it is stored</dt><dd>${esc(s.storage)}</dd><dt>How it is processed</dt><dd>${esc(s.processing)}</dd><dt>Period and review</dt><dd>${esc(s.period)} · ${esc(s.review)}</dd></dl>${s.code?safeLink('https://github.com/jeffsickoria/watts-next/blob/codex/cloud-dashboard/'+s.code,'Acquisition / processing code'):''}</details>`).join('')||( '<p class="empty">No datasets match that filter.</p>');
 const rows=data.sources.filter(s=>JSON.stringify(s).toLowerCase().includes(query));
 $('source-table').innerHTML='<table><caption>Source review register. Candidate and conditional are review labels; they do not tell you whether a dataset is displayed.</caption><thead><tr><th>Source / product</th><th>Native geography</th><th>Review state</th><th>Period covered</th><th>Fingerprint</th></tr></thead><tbody>'+rows.map(s=>`<tr><td>${safeLink(s.url,s.id)}<small>${esc(s.product)}</small></td><td>${esc(s.geography_id||s.geography_type||'See product')}</td><td><span class="tag ${s.status==='conditional'?'amber':''}">${esc(s.status)}</span></td><td>${esc(s.period_start||'Not recorded')}<small>to ${esc(s.period_end||'Not recorded')}</small></td><td><code title="${esc(s.sample_sha256)}">${esc(s.sample_sha256?.slice(0,12))}…</code></td></tr>`).join('')+'</tbody></table>';
}
function download(value,name,type='application/json'){const blob=new Blob([typeof value==='string'?value:JSON.stringify(value,null,2)],{type}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
