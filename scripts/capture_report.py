"""Capture the working energy report and verify displayed selections against its input."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile

from playwright.sync_api import sync_playwright


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_metrics(page):
    result = page.evaluate("""() => {
      const data=JSON.parse(document.getElementById('report-data').textContent),m=window.reportMetrics;
      const finite=v=>v!==null&&v!==undefined&&v!==''&&Number.isFinite(Number(v));
      const sum=(rows,key)=>rows.reduce((a,r)=>a+(finite(r[key])?Number(r[key]):0),0);
      const equal=(a,b)=>a===null||b===null?a===b:Math.abs(a-b)<=1e-8*Math.max(1,Math.abs(b));
      const nf=new Intl.NumberFormat('en-CA',{maximumFractionDigits:0});
      let expected={},matches=false,visible=false;
      if(m.Tab==='flow'){
        const rows=data.flow.filter(r=>String(r.PointId)===m.PointId&&(!m.Year||String(r.Year)===m.Year));
        for(const key of ['ObservedDays','ExpectedDays','PairedDays','ThroughputSum','CapacitySum'])expected[key]=sum(rows,key);
        expected.Utilization=expected.CapacitySum>0?expected.ThroughputSum/expected.CapacitySum:null;
        for(const [field,missing]of [['MeanThroughput','MissingThroughputDays'],['MeanCapacity','MissingCapacityDays']]){
          const values=rows.filter(r=>finite(r[field]));
          const denominator=values.reduce((a,r)=>a+Math.max(0,Number(r.ObservedDays)-Number(r[missing]||0)),0);
          expected[field]=denominator?values.reduce((a,r)=>a+Number(r[field])*Math.max(0,Number(r.ObservedDays)-Number(r[missing]||0)),0)/denominator:null;
        }
        matches=Object.entries(expected).every(([k,v])=>equal(m[k],v));
        visible=document.getElementById('metric-observed').textContent===nf.format(expected.ObservedDays)
          &&document.getElementById('metric-throughput').textContent===(expected.MeanThroughput===null?'—':nf.format(expected.MeanThroughput));
      }else if(m.Tab==='incidents'){
        const rows=data.incidents.filter(r=>(!m.Year||String(r.Year)===m.Year)&&(!m.Province||(r.Province||'Not reported')===m.Province)&&(!m.Status||(r.Status||'Not reported')===m.Status));
        expected={IncidentRows:rows.length,ClosedRows:rows.filter(r=>String(r.Status).toLowerCase()==='closed').length,
          SignificantRows:rows.filter(r=>String(r.Significant).toLowerCase()==='yes').length,
          MappedRows:rows.filter(r=>finite(r.Latitude)&&finite(r.Longitude)&&Number(r.Latitude)>=40&&Number(r.Latitude)<=85&&Number(r.Longitude)>=-142&&Number(r.Longitude)<=-50).length};
        matches=Object.entries(expected).every(([k,v])=>m[k]===v);
        visible=document.getElementById('metric-incidents').textContent===nf.format(rows.length);
      }else{
        expected={FlowSourceRows:Number(data.meta.flow_source_rows),FlowAcceptedRows:Number(data.meta.flow_accepted_rows),IncidentRows:data.incidents.length,QualityRules:data.quality.length};
        matches=Object.entries(expected).every(([k,v])=>m[k]===v);
        visible=document.getElementById('quality-flow-rows').textContent===nf.format(expected.FlowSourceRows);
      }
      return {matches,visible,selection:m,expected};
    }""")
    assert result["matches"] and result["visible"], result
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--browser',default='msedge' if platform.system()=='Windows' else 'chromium')
    args=parser.parse_args()
    root=args.root.resolve()
    report=root/'reports/dashboard.html'
    ffmpeg=shutil.which('ffmpeg')
    if not report.exists():
        parser.error('Build reports/dashboard.html before capturing it.')
    if not ffmpeg:
        parser.error('Install FFmpeg on PATH to encode the continuous walkthrough.')
    shots=root/'docs/screenshots'
    recordings=root/'docs/recordings'
    shots.mkdir(parents=True,exist_ok=True)
    recordings.mkdir(parents=True,exist_ok=True)
    viewport={'width':1440,'height':1100}
    captures=[]
    checks=[]
    errors=[]
    with tempfile.TemporaryDirectory(prefix='cer-energy-capture-') as temp,sync_playwright() as playwright:
        launch={'headless':True}
        if args.browser!='chromium':
            launch['channel']=args.browser
        browser=playwright.chromium.launch(**launch)
        context=browser.new_context(viewport=viewport,record_video_dir=temp,record_video_size=viewport,reduced_motion='reduce')
        page=context.new_page()
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(report.as_uri(),wait_until='load')
        page.wait_for_selector('html[data-ready="true"]')
        meta=page.evaluate("JSON.parse(document.getElementById('report-data').textContent).meta")

        def capture(file,description):
            page.wait_for_timeout(500)
            checks.append(verify_metrics(page))
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'Desktop horizontal overflow'
            path=shots/file
            page.screenshot(path=str(path),full_page=True,animations='disabled')
            captures.append({'file':file,'description':description,'sha256':digest(path),'viewport':viewport,'selection':checks[-1]['selection']})
            page.wait_for_timeout(2100)

        capture('01-flow-capacity.png','Natural gas throughput and reported capacity at the default reporting point and year.')
        alternate=page.evaluate("""() => {
          const data=JSON.parse(document.getElementById('report-data').textContent),current=document.getElementById('flow-point').value;
          const point=data.points.find(p=>String(p.PointId)!==current&&data.flow.some(r=>String(r.PointId)===String(p.PointId)&&String(r.Year)==='2025'))||data.points.find(p=>String(p.PointId)!==current);
          return point?{pipeline:point.Pipeline,point:String(point.PointId)}:null;
        }""")
        if alternate:
            page.locator('#flow-pipeline').select_option(alternate['pipeline'])
            page.locator('#flow-point').select_option(alternate['point'])
        page.locator('#flow-table-details').evaluate('el=>el.open=true')
        capture('02-point-review.png','Another reporting point, with the monthly data table expanded for denominator review.')
        with page.expect_download() as download_info:
            page.locator('.export[data-kind="flow"]').click()
        download=download_info.value
        exported=Path(download.path()).read_text(encoding='utf-8-sig')
        assert 'PointId' in exported and 'PairedDays' in exported
        page.locator('#tab-incidents').click()
        capture('03-incident-map.png','Reported incident locations on openly licensed NRCan province boundaries.')
        provinces=page.locator('#incident-province option').evaluate_all('nodes=>nodes.map(n=>n.value)')
        if 'Alberta' in provinces:
            page.locator('#incident-province').select_option('Alberta')
        page.locator('#incident-year').select_option('')
        page.locator('#incident-status').select_option('Closed')
        capture('04-alberta-review.png','Alberta incident records across reported years, filtered to published Closed status.')
        page.locator('#tab-quality').click()
        capture('05-data-quality.png','Full-snapshot source profiling, spatial checks and provenance.')
        video=page.video
        context.close()
        video_source=Path(video.path())

        mobile=browser.new_context(viewport={'width':390,'height':844},reduced_motion='reduce')
        mp=mobile.new_page()
        mp.on('pageerror',lambda e:errors.append(str(e)))
        mp.goto(report.as_uri(),wait_until='load')
        mp.wait_for_selector('html[data-ready="true"]')
        checks.append(verify_metrics(mp))
        assert mp.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'Mobile horizontal overflow'
        path=shots/'06-mobile-flow.png'
        mp.screenshot(path=str(path),full_page=True,animations='disabled')
        captures.append({'file':path.name,'description':'Working flow report at a 390-pixel viewport.','sha256':digest(path),'viewport':{'width':390,'height':844},'selection':checks[-1]['selection']})
        mp.locator('#tab-incidents').click()
        checks.append(verify_metrics(mp))
        assert mp.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'Mobile map horizontal overflow'
        path=shots/'07-mobile-incidents.png'
        mp.screenshot(path=str(path),full_page=True,animations='disabled')
        captures.append({'file':path.name,'description':'Incident map and record inspection at a 390-pixel viewport.','sha256':digest(path),'viewport':{'width':390,'height':844},'selection':checks[-1]['selection']})
        mobile.close()
        browser.close()
        subprocess.run([ffmpeg,'-y','-loglevel','error','-i',str(video_source),'-c:v','libx264','-preset','fast','-crf','23','-pix_fmt','yuv420p','-movflags','+faststart',str(recordings/'walkthrough.mp4')],check=True)
    assert not errors,errors
    manifest={'captured_at':datetime.now(timezone.utc).isoformat(),'source':'Actual local reports/dashboard.html browser rendering','source_urls':meta.get('source_urls'),'source_downloaded_at':meta.get('downloaded_at'),'report_sha256':digest(report),'recording':'Continuous automated browser review of the working energy report; not manual development footage or a native Power BI recording.','video':{'file':'walkthrough.mp4','sha256':digest(recordings/'walkthrough.mp4')},'viewport':viewport,'browser':args.browser,'page_errors':errors,'metric_checks':checks,'screenshots':captures}
    (recordings/'capture_manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8',newline='\n')
    (recordings/'README.md').write_text('# Recorded report review\n\n[Watch or download the walkthrough](walkthrough.mp4)\n\nContinuous automated browser recording of the working report using official CER and NRCan data. It demonstrates reporting-point selection, monthly denominators, incident-map filtering, and quality review. This is not manual development footage, a native Power BI recording, or evidence of government employment.\n\nThe [capture manifest](capture_manifest.json) records the source snapshot, checks and SHA-256 hashes.\n',encoding='utf-8',newline='\n')
    (shots/'README.md').write_text('# Browser report screenshots\n\nActual browser captures of the generated offline report. Native Power BI evidence, if included elsewhere, is identified separately.\n\n'+'\n\n'.join(f"## {item['file']}\n\n{item['description']}\n\n![{item['description']}]({item['file']})" for item in captures)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'screenshots':len(captures),'metric_checks':len(checks),'browser_errors':errors,'recording':str(recordings/'walkthrough.mp4')}))


if __name__=='__main__':
    main()
