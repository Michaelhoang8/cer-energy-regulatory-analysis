import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';

// NODE_PATH may point to an authorized @oai/artifact-tool installation.
const require = createRequire(import.meta.url);
const { Workbook, SpreadsheetFile } = await import(pathToFileURL(require.resolve('@oai/artifact-tool')).href);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const payloadBytes = await fs.readFile(path.join(root, 'reports/dashboard_data.json'));
const payload = JSON.parse(payloadBytes);
const year = payload.meta.default_year;
const point = payload.points.find(p => p.PointId === payload.meta.default_point);
const monthly = payload.flow.filter(r => r.PointId === point.PointId && r.Year === year).sort((a,b) => a.Month.localeCompare(b.Month));
const incidents = payload.incidents.filter(r => r.Year === year).sort((a,b) => a.ReportedDate.localeCompare(b.ReportedDate) || a.IncidentId.localeCompare(b.IncidentId));
const quality = payload.quality;
const snapshotDate = payload.meta.downloaded_at.slice(0,10);
if (monthly.length !== 12 || !incidents.length || !quality.length) throw Error('Expected a complete twelve-month point series and populated review inputs.');
const wb = Workbook.create();
const flow = wb.worksheets.add('Flow review');
const incident = wb.worksheets.add('Incident review');
const review = wb.worksheets.add('Quality review');
const palette = { charcoal:'#26343A', teal:'#22786F', amber:'#B37822', muted:'#61727A', input:'#1D5EA8', pale:'#EDF3F2' };
const number = '#,##0.0;(#,##0.0);"0.0"';
const integer = '#,##0;(#,##0);"0"';
const checks = [];
const assert = (name, ok, actual, expected) => {
  checks.push({name,passed:!!ok,actual,expected});
  if (!ok) throw Error(`${name}: expected ${expected}, got ${actual}`);
};
const near = (name, actual, expected) => assert(name, typeof actual === 'number' && Math.abs(actual-expected) <= Math.max(1e-8,Math.abs(expected)*1e-10), actual, expected);
function style(sheet, range, widths) {
  sheet.showGridLines = false;
  sheet.getRange(range).format = {font:{name:'Arial',size:10,color:palette.charcoal},rowHeight:24,verticalAlignment:'center'};
  for (const [column,width] of Object.entries(widths)) sheet.getRange(`${column}:${column}`).format.columnWidth = width;
  sheet.getRange('A2').format.font = {name:'Arial',size:16,bold:true,color:palette.charcoal};
  sheet.tabColor = palette.charcoal;
}
function header(sheet, range) {
  sheet.getRange(range).format = {fill:palette.charcoal,font:{name:'Arial',size:10,bold:true,color:'#FFFFFF'},rowHeight:40,wrapText:true,horizontalAlignment:'center',verticalAlignment:'center',borders:{insideVertical:{style:'thin',color:'#FFFFFF'}}};
}
function source(sheet, cell, text) { sheet.getRange(cell).values=[[text]]; sheet.getRange(cell).format.font={name:'Arial',size:10,color:palette.muted,italic:true}; }
function total(sheet, range) {sheet.getRange(range).format={fill:palette.pale,font:{bold:true,color:palette.charcoal},borders:{top:{style:'thin',color:palette.teal}},rowHeight:28};}
function chartStyle(chart) {
  chart.titleTextStyle.typeface='Arial'; chart.titleTextStyle.fontSize=13;
  chart.legend={position:'top',textStyle:{typeface:'Arial',fontSize:11}};
  chart.xAxis={axisType:'textAxis',textStyle:{typeface:'Arial',fontSize:11}};
  chart.yAxis={numberFormatCode:'#,##0',numberFormatSourceLinked:false,textStyle:{typeface:'Arial',fontSize:11}};
}

// The first view calculates results from a retained, single-point monthly input block.
style(flow,'A1:O43',{A:17,B:13,C:13,D:14,E:18,F:18,G:17,H:16,I:16,J:16,K:16,L:16,M:16,N:16,O:16});
flow.getRange('A2').values=[['Natural gas flow']];
flow.getRange('A3').values=[[`${point.Pipeline}, ${point.KeyPoint}, ${point.Direction}`]];
source(flow,'A4',`${year}. Mean daily rates in 1,000 m³/day. Utilization uses paired observations with positive capacity.`);
flow.getRange('A6:G6').values=[['Month','Observed days','Expected days','Date coverage','Mean throughput','Mean capacity','Utilization']];
header(flow,'A6:G6');
const inputStart=29, inputEnd=40;
flow.getRange('A28:N28').values=[['Month','Observed days','Expected days','All throughput sum','Throughput days','All capacity sum','Capacity days','Paired throughput sum','Paired capacity sum','Paired days','Days above capacity','Missing throughput days','Missing capacity days','Chart month']];
header(flow,'A28:N28');
flow.getRange('A28:N28').format.rowHeight=64;
flow.getRange(`A${inputStart}:M${inputEnd}`).values=monthly.map(r=>[new Date(`${r.Month}-01T00:00:00Z`),r.ObservedDays,r.ExpectedDays,r.ThroughputAllSum,r.ThroughputDays,r.CapacityAllSum,r.CapacityDays,r.ThroughputSum,r.CapacitySum,r.PairedDays,r.OverCapacityDays,r.MissingThroughputDays,r.MissingCapacityDays]);
flow.getRange(`A${inputStart}:A${inputEnd}`).setNumberFormat('mmm yyyy');
flow.getRange(`D${inputStart}:D${inputEnd}`).setNumberFormat(number);
flow.getRange(`F${inputStart}:F${inputEnd}`).setNumberFormat(number);
flow.getRange(`H${inputStart}:I${inputEnd}`).setNumberFormat(number);
flow.getRange(`N${inputStart}:N${inputEnd}`).formulas=monthly.map((_,i)=>[`=TEXT(A${inputStart+i},"mmm")`]);
const flowFormulas=monthly.map((_,i)=>{
  const s=inputStart+i,r=7+i;
  return [`=A${s}`,`=B${s}`,`=C${s}`,`=IF(OR(COUNT(B${r}:C${r})<>2,C${r}<=0),"n.a.",B${r}/C${r})`,`=IF(OR(COUNT(D${s}:E${s})<>2,E${s}<=0),"n.a.",D${s}/E${s})`,`=IF(OR(COUNT(F${s}:G${s})<>2,G${s}<=0),"n.a.",F${s}/G${s})`,`=IF(OR(COUNT(H${s}:J${s})<>3,I${s}<=0,J${s}<=0),"n.a.",H${s}/I${s})`];
});
flow.getRange('A7:G18').formulas=flowFormulas;
flow.getRange('A7:A18').setNumberFormat('mmm yyyy');
flow.getRange('B7:C19').setNumberFormat(integer);
flow.getRange('D7:D19').setNumberFormat('0.0%');
flow.getRange('E7:F19').setNumberFormat(number);
flow.getRange('G7:G19').setNumberFormat('0.0%');
flow.getRange('A19').values=[['Weighted year']];
flow.getRange('B19:G19').formulas=[[`=SUM(B7:B18)`,`=SUM(C7:C18)`,`=IF(OR(COUNT(B29:C40)<>24,C19<=0),"n.a.",B19/C19)`,`=IF(OR(COUNT(D29:E40)<>24,SUM(E29:E40)<=0),"n.a.",SUM(D29:D40)/SUM(E29:E40))`,`=IF(OR(COUNT(F29:G40)<>24,SUM(G29:G40)<=0),"n.a.",SUM(F29:F40)/SUM(G29:G40))`,`=IF(OR(COUNT(H29:J40)<>36,SUM(I29:I40)<=0,SUM(J29:J40)<=0),"n.a.",SUM(H29:H40)/SUM(I29:I40))`]];
total(flow,'A19:G19');
flow.getRange('G7:G18').conditionalFormats.add('cellIs',{operator:'greaterThan',formula:1,format:{font:{color:palette.amber,bold:true}}});
source(flow,'A21','Reported capacity is an estimate and may be exceeded. Values above 100% are not breach findings.');
source(flow,'A22','Date coverage is observed / expected calendar days. It does not measure availability or outages.');
source(flow,'A24',`Source: CER pipeline throughput and capacity, downloaded ${snapshotDate}.`);
source(flow,'A25',payload.meta.source_urls.flow);
source(flow,'A26','Open Government Licence – Canada: https://open.canada.ca/en/open-government-licence-canada');
source(flow,'A27','Monthly source aggregates. Rate sums support weighting within this point only. Never sum different points as network throughput.');
flow.tables.add('A28:N40',true,'SelectedPointInputs').style='TableStyleLight1';
const trend=flow.charts.add('line',[flow.getRange('N29:N40'),flow.getRange('E7:E18'),flow.getRange('F7:F18')]);
trend.title='Mean daily throughput and capacity (1,000 m³/day)';
trend.series.items[0].name='Throughput';trend.series.items[1].name='Capacity';
trend.series.items[0].line={fill:palette.teal,style:'solid',width:2};
trend.series.items[1].line={fill:palette.amber,style:'dashed',width:2};
chartStyle(trend);trend.setPosition('I6','O20');

// Incident counts have a different population from the gas flow point.
const inputIncidentStart=30,inputIncidentEnd=inputIncidentStart+incidents.length-1;
const provinceNames=[...new Set([...payload.boundaries.features.map(f=>f.properties.Province),...incidents.map(r=>r.Province||'Not reported')])].sort();
const provinceStart=7,provinceEnd=provinceStart+provinceNames.length-1,provinceTotal=provinceEnd+1;
style(incident,`A1:N${inputIncidentEnd}`,{A:29,B:13,C:13,D:15,E:16,F:16,G:15,H:3,I:18,J:18,K:18,L:18,M:18,N:18});
incident.tabColor=palette.teal;
incident.getRange('A2').values=[['Reported pipeline incidents']];
source(incident,'A3',`${year} reported year. All CER-regulated products and facilities. Status reflects the source snapshot, not year-end.`);
source(incident,'A4','Open = status other than Closed. GIS review = spatial status other than match. These are review categories, not risk rankings.');
incident.getRange('A6:G6').values=[['Province / territory','Incidents','Closed','Open','Significant','GIS review','Closed share']];
header(incident,'A6:G6');
incident.getRange(`A${provinceStart}:A${provinceEnd}`).values=provinceNames.map(v=>[v]);
incident.getRange(`A${inputIncidentStart}:H${inputIncidentEnd}`).values=incidents.map(r=>[r.IncidentId,new Date(`${r.ReportedDate}T00:00:00Z`),r.Province||'Not reported',r.Status,r.Significant,r.SpatialStatus,r.Company,r.SourceRow]);
incident.getRange(`B${inputIncidentStart}:B${inputIncidentEnd}`).setNumberFormat('yyyy-mm-dd');
incident.getRange(`A${inputIncidentStart}:G${inputIncidentEnd}`).format.wrapText=true;
incident.getRange(`A${inputIncidentStart}:H${inputIncidentEnd}`).format.rowHeight=96;
incident.getRange('A29:H29').values=[['Incident ID','Reported date','Reported province','Status','Significant','Spatial status','Company','Source row']];
header(incident,'A29:H29');
incident.getRange('H29:H97').format.columnWidth=12;
const provRange=`$C$${inputIncidentStart}:$C$${inputIncidentEnd}`,statusRange=`$D$${inputIncidentStart}:$D$${inputIncidentEnd}`,sigRange=`$E$${inputIncidentStart}:$E$${inputIncidentEnd}`,geoRange=`$F$${inputIncidentStart}:$F$${inputIncidentEnd}`;
incident.getRange(`B${provinceStart}:G${provinceEnd}`).formulas=provinceNames.map((_,i)=>{
 const r=provinceStart+i;
 return [`=COUNTIFS(${provRange},$A${r})`,`=COUNTIFS(${provRange},$A${r},${statusRange},"Closed")`,`=B${r}-C${r}`,`=COUNTIFS(${provRange},$A${r},${sigRange},"Yes")`,`=COUNTIFS(${provRange},$A${r},${geoRange},"<>match")`,`=IF(B${r}=0,"n.a.",C${r}/B${r})`];
});
incident.getRange(`A${provinceTotal}`).values=[['Total']];
incident.getRange(`B${provinceTotal}:G${provinceTotal}`).formulas=[[...['B','C','D','E','F'].map(c=>`=SUM(${c}${provinceStart}:${c}${provinceEnd})`),`=IF(B${provinceTotal}=0,"n.a.",C${provinceTotal}/B${provinceTotal})`]];
incident.getRange(`B${provinceStart}:F${provinceTotal}`).setNumberFormat(integer);
incident.getRange(`G${provinceStart}:G${provinceTotal}`).setNumberFormat('0.0%');
incident.getRange(`G${provinceStart}:G${provinceTotal}`).format.horizontalAlignment='right';
total(incident,`A${provinceTotal}:G${provinceTotal}`);
source(incident,'A23','Incident counts are descriptive. Reporting dates can differ from occurrence dates. Preliminary records may change.');
source(incident,'A24','Approximate incident coordinates are compared with generalized NRCan boundaries. Source coordinates are preserved.');
source(incident,'A26',`Source: CER comprehensive incident records, downloaded ${snapshotDate}.`);
source(incident,'A27',payload.meta.source_urls.incidents);
source(incident,'A28','Open Government Licence – Canada. Input rows retain incident identifiers and original CSV row references.');
incident.tables.add(`A29:H${inputIncidentEnd}`,true,'SelectedYearIncidents').style='TableStyleLight1';
const provinceCodes=new Map(payload.boundaries.features.map(f=>[f.properties.Province,f.properties.ProvinceCode]));
incident.getRange('J29:K29').values=[['Province code','Incidents']];
header(incident,'J29:K29');
incident.getRange(`J30:J${29+provinceNames.length}`).values=provinceNames.map(p=>[provinceCodes.get(p)||p]);
incident.getRange(`K30:K${29+provinceNames.length}`).formulas=provinceNames.map((_,i)=>[`=B${provinceStart+i}`]);
const incidentChart=incident.charts.add('bar',incident.getRange(`J29:K${29+provinceNames.length}`));
incidentChart.title=`Reported incidents by province (${year})`;incidentChart.hasLegend=false;
incidentChart.series.items[0].fill=palette.teal;chartStyle(incidentChart);incidentChart.hasLegend=false;incidentChart.setPosition('I6','N21');

// Review workflow is terminal: no business result depends on a reviewer status.
const qualityStart=8,qualityEnd=qualityStart+quality.length-1;
style(review,`A1:G${qualityEnd+9}`,{A:41,B:27,C:15,D:17,E:19,F:31,G:72});
review.tabColor=palette.amber;
review.getRange('A2').values=[['Data quality review']];
review.getRange('A3').values=[['Unresolved affected rules']];
review.getRange('B3').formulas=[[`=COUNTIFS(C${qualityStart}:C${qualityEnd},">0",D${qualityStart}:D${qualityEnd},"<>Checked",E${qualityStart}:E${qualityEnd},"<>Closed")`]];
review.getRange('A4').values=[['Rules with findings closed']];
review.getRange('B4').formulas=[[`=COUNTIFS(C${qualityStart}:C${qualityEnd},">0",D${qualityStart}:D${qualityEnd},"<>Checked",E${qualityStart}:E${qualityEnd},"Closed")`]];
source(review,'A5',`All source periods, downloaded ${snapshotDate}. Counts overlap and must not be added as a total defect count.`);
source(review,'A6','Edit the blue Status and Reviewer notes fields. A finding remains unresolved until its status is Closed.');
review.getRange('A7:G7').values=[['Rule','Dataset','Affected records','Class','Status','Reviewer notes','Interpretation']];
header(review,'A7:G7');
review.getRange(`A${qualityStart}:G${qualityEnd}`).values=quality.map(r=>[r.Rule,r.Dataset,r.Rows,r.Severity,r.Rows>0&&r.Severity!=='Checked'?'Open':'Not required','',r.Meaning]);
review.getRange(`A${qualityStart}:G${qualityEnd}`).format={wrapText:true,rowHeight:51,verticalAlignment:'center'};
review.getRange(`E${qualityStart}:F${qualityEnd}`).format={fill:'#EDF4FC',font:{name:'Arial',size:10,color:palette.input}};
review.getRange(`C${qualityStart}:C${qualityEnd}`).setNumberFormat(integer);
review.getRange(`D${qualityStart}:D${qualityEnd}`).format.horizontalAlignment='center';
review.getRange(`E${qualityStart}:E${qualityEnd}`).dataValidation={rule:{type:'list',values:['Open','In progress','Closed','Not required']}};
review.getRange(`E${qualityStart}:E${qualityEnd}`).conditionalFormats.add('containsText',{text:'Open',format:{fill:'#FFF2D7',font:{color:palette.amber,bold:true}}});
review.getRange(`E${qualityStart}:E${qualityEnd}`).conditionalFormats.add('containsText',{text:'In progress',format:{fill:'#E6F1F0',font:{color:palette.teal,bold:true}}});
review.tables.add(`A7:G${qualityEnd}`,true,'QualityReview').style='TableStyleLight1';
review.freezePanes.freezeRows(7);
source(review,`A${qualityEnd+2}`,'Sources: CER daily flow, comprehensive incidents and map-feed reconciliation; NRCan provincial boundaries.');
source(review,`A${qualityEnd+3}`,payload.meta.source_urls.flow);
source(review,`A${qualityEnd+4}`,payload.meta.source_urls.incidents);
source(review,`A${qualityEnd+5}`,payload.meta.source_urls.boundaries);
source(review,`A${qualityEnd+6}`,'Open Government Licence – Canada: https://open.canada.ca/en/open-government-licence-canada');

// Independent expected values are derived from retained input components in JS.
wb.recalculate();
const sum=(rows,key)=>rows.reduce((a,r)=>a+r[key],0);
for(let i=0;i<monthly.length;i++) {
 const values=flow.getRange(`D${7+i}:G${7+i}`).values[0],r=monthly[i];
 near(`${r.Month} coverage`,values[0],r.ObservedDays/r.ExpectedDays);
 near(`${r.Month} mean throughput`,values[1],r.ThroughputAllSum/r.ThroughputDays);
 near(`${r.Month} mean capacity`,values[2],r.CapacityAllSum/r.CapacityDays);
 near(`${r.Month} utilization`,values[3],r.ThroughputSum/r.CapacitySum);
}
near('Weighted annual utilization',flow.getRange('G19').values[0][0],sum(monthly,'ThroughputSum')/sum(monthly,'CapacitySum'));
near('Weighted annual throughput',flow.getRange('E19').values[0][0],sum(monthly,'ThroughputAllSum')/sum(monthly,'ThroughputDays'));
near('Annual date coverage',flow.getRange('D19').values[0][0],sum(monthly,'ObservedDays')/sum(monthly,'ExpectedDays'));
for(let i=0;i<provinceNames.length;i++) {
 const name=provinceNames[i],rows=incidents.filter(r=>(r.Province||'Not reported')===name),r=provinceStart+i;
 const actual=incident.getRange(`B${r}:F${r}`).values[0];
 const expected=[rows.length,rows.filter(x=>x.Status==='Closed').length,rows.filter(x=>x.Status!=='Closed').length,rows.filter(x=>x.Significant==='Yes').length,rows.filter(x=>x.SpatialStatus!=='match').length];
 assert(`${name} incident counts`,JSON.stringify(actual)===JSON.stringify(expected),actual,expected);
}
near('Incident total',incident.getRange(`B${provinceTotal}`).values[0][0],incidents.length);
const openExpected=quality.filter(r=>r.Rows>0&&r.Severity!=='Checked').length;
near('Initial unresolved rules',review.getRange('B3').values[0][0],openExpected);
const editable=qualityStart+quality.findIndex(r=>r.Rows>0&&r.Severity!=='Checked');
review.getRange(`E${editable}`).values=[['Closed']];
near('Closing a review reduces unresolved count',review.getRange('B3').values[0][0],openExpected-1);
near('Closed count responds to review edit',review.getRange('B4').values[0][0],1);
review.getRange(`E${editable}`).values=[['']];
near('Blank review status remains unresolved',review.getRange('B3').values[0][0],openExpected);
review.getRange(`E${editable}`).values=[['Open']];
const capacitySum=flow.getRange('I29').values[0][0];
flow.getRange('I29').values=[[null]];
assert('Blank paired-capacity denominator stays unavailable',flow.getRange('G7').values[0][0]==='n.a.',flow.getRange('G7').values[0][0],'n.a.');
assert('Incomplete annual capacity denominator stays unavailable',flow.getRange('G19').values[0][0]==='n.a.',flow.getRange('G19').values[0][0],'n.a.');
flow.getRange('I29').values=[[0]];
assert('Zero paired-capacity denominator stays unavailable',flow.getRange('G7').values[0][0]==='n.a.',flow.getRange('G7').values[0][0],'n.a.');
flow.getRange('I29').values=[[capacitySum]];
const expectedDays=flow.getRange('C29').values[0][0];
flow.getRange('C29').values=[[null]];
assert('Blank expected-day input stays unavailable',flow.getRange('D7').values[0][0]==='n.a.',flow.getRange('D7').values[0][0],'n.a.');
flow.getRange('C29').values=[[expectedDays]];
wb.recalculate();
near('Restored annual utilization',flow.getRange('G19').values[0][0],sum(monthly,'ThroughputSum')/sum(monthly,'CapacitySum'));
near('Restored unresolved rules',review.getRange('B3').values[0][0],openExpected);
const errorScan=await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!',options:{useRegex:true,maxResults:20},maxChars:3000});
assert('Workbook formula error scan',errorScan.ndjson.includes('matched 0 entries'),errorScan.ndjson,'Cell search matched 0 entries.');
const views=[];
for(const [sheetName,range] of [['Flow review','A6:G19'],['Incident review',`A6:G${provinceTotal}`],['Quality review','A3:B4']]) {
 views.push({sheetName,inspection:(await wb.inspect({kind:'table',range:`'${sheetName}'!${range}`,include:'values,formulas',tableMaxRows:16,tableMaxCols:7,maxChars:9000})).ndjson});
}
await fs.mkdir(path.join(root,'excel'),{recursive:true});
await fs.mkdir(path.join(root,'docs/screenshots'),{recursive:true});
const renderFiles=[];
for(const [sheetName,range,stem] of [['Flow review','A1:O26','flow'],['Incident review','A1:N28','incidents'],['Quality review',`A1:G${qualityEnd+6}`,'quality'],['Flow review','A24:N34','flow-inputs'],['Incident review','A26:H34','incident-inputs']]) {
 const image=await wb.render({sheetName,range,scale:1.2,format:'png'});
 const target=`docs/screenshots/excel-${stem}.png`;
 await fs.writeFile(path.join(root,target),new Uint8Array(await image.arrayBuffer()));renderFiles.push(target);
}
const filename='excel/cer-energy-review.xlsx';
await(await SpreadsheetFile.exportXlsx(wb)).save(path.join(root,filename));
const validation={input_file:'reports/dashboard_data.json',input_sha256:crypto.createHash('sha256').update(payloadBytes).digest('hex'),year,point_id:point.PointId,point_label:point.PointLabel,source_download_date:payload.meta.downloaded_at,monthly_rows:monthly.length,incident_rows:incidents.length,quality_rows:quality.length,formula_checks:checks,error_scan:errorScan.ndjson,inspections:views,render_files:renderFiles,workbook:filename,limitations:['Generated, recalculated and inspected with @oai/artifact-tool; desktop Microsoft Excel was not run.','Review status is a local analyst workflow field and does not change CER records.']};
await fs.writeFile(path.join(root,'reports/excel_validation.json'),JSON.stringify(validation,null,2)+'\n');
console.log(JSON.stringify({workbook:filename,checks:checks.length,quality_rows:quality.length,input_sha256:validation.input_sha256,error_scan:errorScan.ndjson,render_files:renderFiles}));
