"""Reproducible CER natural-gas observations and incident reporting analysis."""
from __future__ import annotations
import calendar
import csv
import datetime as dt
import hashlib
import io
import json
import math
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from geo import ProvinceIndex, canonical_province, valid_coordinates

ROOT = Path(__file__).resolve().parents[1]
FLOW_FILES = ('ngtl.csv', 'tcpl-mainline.csv', 'foothills.csv', 'alliance.csv', 'westcoast.csv', 'tqm.csv', 'mnp.csv')
FLOW_FIELDS = ['Month','PointId','ObservedDays','ExpectedDays','PairedDays','ThroughputSum','CapacitySum',
               'ThroughputDays','CapacityDays','ThroughputAllSum','CapacityAllSum','MissingCapacityDays',
               'MissingThroughputDays','OverCapacityDays','NegativeThroughputDays']
POINT_FIELDS = ['PointId','Pipeline','KeyPoint','PointLabel','Company','Direction','TradeType','Province','Latitude','Longitude']
INCIDENT_FIELDS = ['IncidentId','Month','Year','Province','Company','Status','Significant','Types','SpatialStatus','Latitude','Longitude','ClosureDays']


def number(raw):
    try:
        value = float(str(raw).strip())
        return value if math.isfinite(value) else None
    except (ValueError, TypeError):
        return None


def source_rows(path):
    content = path.read_bytes()
    try:
        text = content.decode('utf-8-sig')
        encoding = 'utf-8-sig'
    except UnicodeDecodeError:
        text = content.decode('cp1252')
        encoding = 'cp1252'
    csv.field_size_limit(10_000_000)
    reader=csv.DictReader(io.StringIO(text, newline=''))
    headers=reader.fieldnames or []
    if not headers or len(headers)!=len(set(headers)):
        raise ValueError(f'Missing or duplicate CSV column names: {path.name}')
    rows = list(reader)
    for index, row in enumerate(rows, 1):
        if None in row or any(value is None for value in row.values()):
            raise ValueError(f'Malformed CSV record: {path.name}:{index}')
    return rows, encoding


def write_json(path, value, compact=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=None if compact else 2,
                               separators=(',', ':') if compact else None, allow_nan=False), encoding='utf-8', newline='\n')


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def date(raw, fmt='%Y-%m-%d'):
    try:
        return dt.datetime.strptime(raw.strip(), fmt).date()
    except (ValueError, AttributeError):
        return None


def province_name(raw):
    return canonical_province(raw) or raw.strip() or 'Not reported'


def verify_sources(root=ROOT):
    folder = root / 'data/source'
    initial = json.loads((folder / 'initial_manifest.json').read_text(encoding='utf-8'))
    resources = json.loads((folder / 'resource_manifest.json').read_text(encoding='utf-8'))['resources']
    geometry = json.loads((folder / 'geo_manifest.json').read_text(encoding='utf-8'))['resources']
    entries = {entry['file']: entry for entry in initial + resources + geometry if not entry['file'].endswith('.pdf')}
    for entry in entries.values():
        path = folder / entry['file']
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
            raise ValueError(f"Source hash mismatch: {entry['file']}")
    return entries


def point_id(row):
    key = [row[name].strip() for name in ('Pipeline','Key Point','Direction Of Flow','Trade Type')]
    return hashlib.sha256(json.dumps(key, ensure_ascii=False).encode()).hexdigest()[:16]


def ingest_flow(connection, root, spatial):
    profiles = []
    titles = Counter()
    metadata_by_hash = {}
    metadata_values = {}
    seen = set()
    quality = Counter()
    source_count = 0
    for filename in FLOW_FILES:
        rows, encoding = source_rows(root / 'data/source' / filename)
        profiles.append({'file': filename, 'rows': len(rows), 'encoding': encoding, 'frequency': 'daily'})
        batch = []
        for source_row, row in enumerate(rows, 1):
            source_count += 1
            fingerprint = hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            if fingerprint in seen:
                quality['exact_duplicates_removed'] += 1
                continue
            seen.add(fingerprint)
            day = date(row['Date'])
            if not day:
                quality['invalid_dates_quarantined'] += 1
                continue
            code = point_id(row)
            lat, lon = number(row['Latitude']), number(row['Longitude'])
            cap, flow = number(row['Capacity (1000 m3/d)']), number(row['Throughput (1000 m3/d)'])
            # A negative capacity is unusable for either completeness or ratios; signed flow is retained.
            if cap is not None and cap < 0:
                quality['negative_capacity'] += 1
                cap = None
            if (str(day.day), str(day.month), str(day.year)) != (row['Day'].strip(),row['Month'].strip(),row['Year'].strip()):
                quality['date_component_mismatch'] += 1
            metadata=(code,row['Pipeline'].strip(),row['Key Point'].strip(),row['Company'].strip(),
                      row['Direction Of Flow'].strip(),row['Trade Type'].strip(),lat,lon)
            metadata_by_hash[fingerprint]=metadata_values.setdefault(metadata,metadata)
            batch.append((filename,source_row,fingerprint,code,day.isoformat(),day.strftime('%Y-%m'),cap,flow,
                          number(row['Throughput (GJ/d)'])))
        connection.executemany('INSERT INTO flow_raw VALUES (?,?,?,?,?,?,?,?,?)', batch)
        print(f'Loaded {filename}: {len(rows):,} daily source records', flush=True)
    connection.executescript('''
    CREATE INDEX raw_daily_key ON flow_raw(PointId,Date);
    CREATE TABLE conflicting_keys AS SELECT PointId,Date,COUNT(*) AS Records FROM flow_raw GROUP BY PointId,Date HAVING COUNT(*)>1;
    CREATE TABLE flow_daily AS SELECT r.* FROM flow_raw r WHERE NOT EXISTS
      (SELECT 1 FROM conflicting_keys c WHERE c.PointId=r.PointId AND c.Date=r.Date);
    CREATE INDEX flow_point_month ON flow_daily(PointId,Month);
    ''')
    quality['conflicting_key_rows_quarantined'] = connection.execute('SELECT COALESCE(SUM(Records),0) FROM conflicting_keys').fetchone()[0]
    for record in connection.execute('SELECT RowHash FROM flow_daily'):
        titles[metadata_by_hash[record[0]]] += 1
    points = []
    for code in sorted({key[0] for key in titles}):
        candidates = [(n,key) for key,n in titles.items() if key[0] == code]
        item = sorted(candidates, key=lambda item: (-item[0],str(item[1])))[0][1]
        _,pipeline,key_point,company,direction,trade,lat,lon = item
        stats = connection.execute('SELECT MIN(Date),MAX(Date),COUNT(*) FROM flow_daily WHERE PointId=?',(code,)).fetchone()
        if not stats[2]:
            continue
        names = spatial.locate(lon,lat)
        province = names[0] if len(names)==1 else 'Not located'
        points.append({'PointId':code,'Pipeline':pipeline,'KeyPoint':key_point,'PointLabel':pipeline+' · '+key_point+' · '+direction,
                       'Company':company,'Direction':direction,'TradeType':trade,'Latitude':lat,'Longitude':lon,'Province':province,
                       'FirstDate':stats[0],'LastDate':stats[1],'Records':stats[2]})
    accepted = connection.execute('SELECT COUNT(*) FROM flow_daily').fetchone()[0]
    assert source_count == accepted + quality['exact_duplicates_removed'] + quality['invalid_dates_quarantined'] + quality['conflicting_key_rows_quarantined']
    return points, profiles, quality, source_count, accepted


def aggregate_flow(connection, points):
    groups = {(row['PointId'],row['Month']):dict(row) for row in connection.execute('SELECT * FROM flow_monthly')}
    facts = []
    for point in points:
        first,last = date(point['FirstDate']),date(point['LastDate'])
        current = first.replace(day=1)
        while current <= last:
            month = current.strftime('%Y-%m')
            end = current.replace(day=calendar.monthrange(current.year,current.month)[1])
            expected = (min(end,last)-max(current,first)).days+1
            row = groups.get((point['PointId'],month))
            if row is None:
                row = {key:0 for key in FLOW_FIELDS if key not in ('Month','PointId')}
                row.update(Month=month,PointId=point['PointId'])
            row['ExpectedDays'] = expected
            row['Year'] = current.year
            row['MeanThroughput'] = row['ThroughputAllSum']/row['ThroughputDays'] if row['ThroughputDays'] else None
            row['MeanCapacity'] = row['CapacityAllSum']/row['CapacityDays'] if row['CapacityDays'] else None
            row['Utilization'] = row['ThroughputSum']/row['CapacitySum'] if row['CapacitySum']>0 else None
            assert 0 <= row['PairedDays'] <= row['ObservedDays'] <= expected
            facts.append(row)
            current = end + dt.timedelta(days=1)
    return sorted(facts,key=lambda row:(row['Month'],row['PointId']))


def ingest_incidents(root, spatial):
    rows, encoding = source_rows(root / 'data/source/incidents.csv')
    facts = []
    seen = set()
    quality = Counter()
    for index,row in enumerate(rows,1):
        code = row['Incident Number'].strip()
        if not code or code in seen:
            raise ValueError(f'Duplicate or missing Incident Number at source row {index}; reconcile before reporting')
        seen.add(code)
        reported = date(row['Reported Date'],'%m/%d/%Y')
        closed = date(row['Closed Date'],'%Y/%m/%d') or date(row['Closed Date'])
        if not reported:
            quality['invalid_reported_dates'] += 1
        lat,lon = number(row['Latitude']),number(row['Longitude'])
        if not valid_coordinates(lon,lat):
            lat=lon=None
        province = province_name(row['Province'])
        assessment = spatial.assess(lon,lat,province)
        elapsed = (closed-reported).days if closed and reported else None
        if elapsed is not None and elapsed<0:
            quality['negative_closure_intervals'] += 1
            elapsed=None
        item = {'IncidentId':code,'SourceRow':index,'Month':reported.strftime('%Y-%m') if reported else 'Not reported',
                'Year':reported.year if reported else 0,'ReportedDate':reported.isoformat() if reported else '',
                'Province':province,'Company':row['Company'].strip(),'Status':row['Status'].strip(),
                'Significant':row['Significant'].strip(),'Types':row['Incident Types'].strip(),
                'Latitude':lat,'Longitude':lon,**assessment,'CauseCategory':row['Why it happened category'].strip(),
                'ClosedDate':closed.isoformat() if closed else '', 'ClosureDays':elapsed}
        facts.append(item)
    return facts, {'file':'incidents.csv','rows':len(rows),'encoding':encoding},quality


def reconcile_incidents(root, incidents):
    path = root / 'data/source/incidents_map.csv'
    if not path.exists():
        raise ValueError('Missing secondary incident map extract for source reconciliation')
    rows,encoding = source_rows(path)
    primary={item['IncidentId']:item for item in incidents}
    secondary={}
    for index,row in enumerate(rows,1):
        # Public map export uses the same stable Incident Number identifier.
        clean={key.strip():value for key,value in row.items()}
        code=clean.get('Incident Number',clean.get('Incident ID','')).strip()
        if not code or code in secondary:
            raise ValueError('Secondary incident feed has missing/duplicate IDs; review its grain before reconciliation')
        secondary[code]=(index,clean)
    results=[]
    for code in sorted(primary.keys()|secondary.keys()):
        left=primary.get(code)
        entry=secondary.get(code)
        right=entry[1] if entry else None
        fields=[]
        if left and right:
            status='matched'
            for field in ('Company','Province','Status','Significant'):
                if field in right:
                    a=province_name(right[field]) if field=='Province' else right[field].strip()
                    if a!=left[field]: fields.append(field)
            if 'Reported Date' in right:
                published=date(right['Reported Date'].split(' ')[0],'%m/%d/%Y')
                if (published.isoformat() if published else '')!=left['ReportedDate']:
                    fields.append('ReportedDate')
            right_coords={field:number(right.get(field)) for field in ('Latitude','Longitude')}
            if not valid_coordinates(right_coords['Longitude'],right_coords['Latitude']):
                right_coords={'Latitude':None,'Longitude':None}
            for field in ('Latitude','Longitude'):
                if field in right:
                    a,b=right_coords[field],left[field]
                    if (a is None)!=(b is None) or (a is not None and b is not None and not math.isclose(a,b,abs_tol=0.00001,rel_tol=0)):
                        fields.append(field)
            if fields: status='field_difference_review'
        else:
            status='comprehensive_only' if left else 'map_only'
        results.append({'IncidentId':code,'Result':status,'DifferentFields':' | '.join(fields),
                        'ComprehensiveSourceRow':left['SourceRow'] if left else None,'MapSourceRow':entry[0] if entry else None})
    return results,{'file':path.name,'rows':len(rows),'encoding':encoding},dict(Counter(row['Result'] for row in results))


def quality_report(flow,incidents,raw_quality,incident_quality,reconciliation,monthly_rows):
    rows=[]
    def add(rule,dataset,count,severity,meaning):
        rows.append({'Rule':rule,'Dataset':dataset,'Rows':int(count),'Severity':severity,'Meaning':meaning})
    add('Missing capacity','Daily flow',sum(x['MissingCapacityDays'] for x in flow),'Completeness','Not imputed; excludes affected observations from the paired utilization denominator.')
    add('Missing throughput','Daily flow',sum(x['MissingThroughputDays'] for x in flow),'Completeness','Not imputed as zero. Observation coverage and numeric completeness are separate.')
    add('Throughput above reported capacity','Daily flow',sum(x['OverCapacityDays'] for x in flow),'Review','Reported capacity is an estimate and may be exceeded. This is not a regulatory breach finding.')
    add('Signed negative throughput','Daily flow',sum(x['NegativeThroughputDays'] for x in flow),'Review','Retained with its published sign; no automatic absolute-value conversion.')
    add('Missing dates inside series window','Daily flow',sum(x['ExpectedDays']-x['ObservedDays'] for x in flow),'Completeness','Calendar dates between first and last published observation; not an availability or outage metric.')
    for key,description in [('exact_duplicates_removed','Exact repeated raw records removed'),('invalid_dates_quarantined','Invalid dates quarantined'),('conflicting_key_rows_quarantined','Conflicting daily keys quarantined'),('date_component_mismatch','Date component differences')]:
        add(description,'Daily flow',raw_quality[key],'Review','Preserve source file and row references for analyst review.')
    add('Monthly-frequency source excluded','Brunswick',monthly_rows,'Scope','Retained source has monthly observations and is excluded from daily coverage calculations.')
    for status,count in sorted(Counter(x['SpatialStatus'] for x in incidents).items()):
        add(status,'Incident GIS',count,'Checked' if status=='match' else 'Review','Approximate source points compared with generalized NRCan polygons; no source-coordinate corrections.')
    for status,count in sorted(reconciliation.items()):
        add(status,'Incident source reconciliation',count,'Checked' if status=='matched' else 'Review','Independent official publications can differ in coverage, publication timing or field values; no automatic overwrite.')
    add('Invalid reported dates','Incidents',incident_quality['invalid_reported_dates'],'Review','Undated records remain visible in the Not reported cohort.')
    add('Negative closure interval','Incidents',incident_quality['negative_closure_intervals'],'Review','Reported-to-closed intervals below zero are excluded from duration summaries.')
    add('Source dictionary unit inconsistency','Metadata',1,'Review','Gas capacity header states 1000 m3/d while dictionary description says GJ/day. Preserve the source; use the explicit column header unit.')
    add('Source dictionary coordinate descriptions reversed','Metadata',2,'Review','Incident dictionary latitude/longitude descriptions are reversed. Use CSV headers and coordinate-range checks; do not swap data.')
    return rows


def build(root=ROOT):
    entries=verify_sources(root)
    spatial=ProvinceIndex(root/'data/source/provinces.geojson')
    (root/'reports').mkdir(parents=True,exist_ok=True)
    target=root/'data/energy.sqlite'
    stage=target.with_suffix('.building.sqlite')
    if stage.exists():stage.unlink()
    connection=sqlite3.connect(stage)
    connection.row_factory=sqlite3.Row
    try:
        connection.executescript((root/'sql/schema.sql').read_text(encoding='utf-8'))
        points,profiles,raw_quality,source_count,accepted=ingest_flow(connection,root,spatial)
        connection.executescript((root/'sql/analysis.sql').read_text(encoding='utf-8'))
        flow=aggregate_flow(connection,points)
        incidents,incident_profile,incident_quality=ingest_incidents(root,spatial)
        reconciled,map_profile,rec_counts=reconcile_incidents(root,incidents)
        monthly_rows=len(source_rows(root/'data/source/brunswick.csv')[0])
        quality=quality_report(flow,incidents,raw_quality,incident_quality,rec_counts,monthly_rows)
        connection.executemany('INSERT INTO incident_audit VALUES (?,?,?,?,?,?)',[(r['IncidentId'],r['SourceRow'],r['Year'],r['Province'],r['SpatialStatus'],json.dumps(r,ensure_ascii=False)) for r in incidents])
        connection.commit()
        selected=next(p for p in points if p['Pipeline']=='NGTL System' and p['KeyPoint']=='East Gate')
        months=sorted({r['Month'] for r in flow}|{r['Month'] for r in incidents})
        provinces=sorted({r['Province'] for r in points+incidents}|{f['properties']['Province'] for f in spatial.feature_collection()['features']})
        write_csv(root/'data/model/DimPoint.csv',points,POINT_FIELDS)
        write_csv(root/'data/model/DimMonth.csv',[{'Month':m,'Year':int(m[:4]) if m!='Not reported' else 0} for m in months],['Month','Year'])
        write_csv(root/'data/model/DimProvince.csv',[{'Province':p} for p in provinces],['Province'])
        write_csv(root/'data/model/FactFlow.csv',flow,FLOW_FIELDS)
        write_csv(root/'data/model/FactIncident.csv',incidents,INCIDENT_FIELDS)
        write_csv(root/'reports/incident_reconciliation.csv',reconciled,['IncidentId','Result','DifferentFields','ComprehensiveSourceRow','MapSourceRow'])
        write_csv(root/'reports/quality.csv',quality,['Rule','Dataset','Rows','Severity','Meaning'])
        write_csv(root/'reports/spatial_review.csv',[r for r in incidents if r['SpatialStatus']!='match'],['IncidentId','SourceRow','Province','Latitude','Longitude','SpatialStatus','SpatialProvince'])
        assert sum(r['ObservedDays'] for r in flow)==accepted
        default_year=max(int(p['LastDate'][:4]) for p in points)-1
        retrieved=max((e.get('retrieved_at_utc',e.get('retrieved_at','')) for e in entries.values()),default='')
        meta={'flow_source_rows':source_count,'flow_accepted_rows':accepted,'incident_rows':len(incidents),
              'point_count':len(points),'default_point':selected['PointId'],'default_year':default_year,
              'downloaded_at':retrieved,'flow_first_date':min(p['FirstDate'] for p in points),
              'flow_last_date':max(p['LastDate'] for p in points),'incident_last_date':max(r['ReportedDate'] for r in incidents),
              'reconciliation':rec_counts,'monthly_source_excluded_rows':monthly_rows,
              'source_urls':{'flow':'https://open.canada.ca/data/en/dataset/dc343c43-a592-4a27-8ee7-c77df56afb34',
                             'incidents':'https://open.canada.ca/data/en/dataset/7dffedc4-23fa-440c-a36d-adf5a6cc09f1',
                             'boundaries':'https://open.canada.ca/data/en/dataset/443e98f0-a461-45ab-8fa2-57645b3efbb5'},
              'notes':['Daily natural-gas series only; Brunswick monthly source is excluded from daily coverage.',
                       'Rates are 1000 m3/day. GJ/day is retained separately in the audit database and never mixed with volume.',
                       'Utilization uses paired observations with positive capacity; it may exceed 100%.',
                       'Key points can measure the same physical gas. Never sum rates across points as network throughput.',
                       'Incidents cover CER-regulated facilities across products, a different population from these seven gas systems.',
                       'No incident-to-throughput risk rate or causal relationship is inferred.',
                       'GIS comparisons use generalized boundaries and approximate points; spatial differences are review items.']}
        payload={'meta':meta,'points':points,'flow':flow,'incidents':incidents,'quality':quality,
                 'boundaries':spatial.feature_collection(),'company_reconciliation':[],
                 'incident_reconciliation':reconciled}
        write_json(root/'reports/dashboard_data.json',payload,compact=True)
        write_json(root/'reports/source_profile.json',{'meta':meta,'sources':profiles+[incident_profile,map_profile],
                    'raw_quality':dict(raw_quality),'incident_quality':dict(incident_quality),'source_files_verified':len(entries)})
        template=root/'src/dashboard_template.html'
        if template.exists():
            encoded=json.dumps(payload,ensure_ascii=False,separators=(',',':'),allow_nan=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
            (root/'reports/dashboard.html').write_text(template.read_text(encoding='utf-8').replace('__DATA__',encoded),encoding='utf-8',newline='\n')
        write_findings(root,payload)
    finally:
        connection.close()
    stage.replace(target)
    print(json.dumps({**{k:meta[k] for k in ('flow_source_rows','flow_accepted_rows','incident_rows','point_count')},'monthly_groups':len(flow),'reconciliation':rec_counts}),flush=True)


def write_findings(root,payload):
    meta=payload['meta']
    year=meta['default_year']
    flow=[r for r in payload['flow'] if r['PointId']==meta['default_point'] and r['Year']==year]
    cap=sum(r['CapacitySum'] for r in flow)
    ratio=sum(r['ThroughputSum'] for r in flow)/cap if cap else None
    selected=[r for r in payload['incidents'] if r['Year']==year]
    text=f'''# Regulatory data review

## Scope

The daily model contains {meta['flow_accepted_rows']:,} published observations at {meta['point_count']} distinct pipeline/key-point/direction/trade combinations across seven natural-gas systems. Source coverage is {meta['flow_first_date']} through {meta['flow_last_date']}. Brunswick's {meta['monthly_source_excluded_rows']} monthly observations are retained as a source but excluded from daily coverage calculations.

The comprehensive incident extract contains {meta['incident_rows']:,} distinct incident IDs. It spans multiple energy products and regulated facilities; it is a separate reporting population. The incident extract's latest reported date is {meta['incident_last_date']}.

## Selected-point result

NGTL System, East Gate, {year} has {sum(r['ObservedDays'] for r in flow):,} observed daily records and {sum(r['PairedDays'] for r in flow):,} paired observations. Capacity-weighted utilization is {ratio:.2%}. There are {sum(r['OverCapacityDays'] for r in flow):,} observations above reported capacity. CER explains that reported capacity is estimated and can be exceeded; this is not a finding of noncompliance.

## Incident reporting

There are {len(selected):,} incidents reported in {year}. Status and significance reflect the extract date, not what was known at the end of {year}. Counts describe reported incidents, not exposure-adjusted safety performance.

## Source reconciliation

The comprehensive extract and the separate public incident-map feed are reconciled by Incident Number. Counts: {json.dumps(meta['reconciliation'],sort_keys=True)}. See `incident_reconciliation.csv` for every ID and differing fields. Neither publication overwrites the other; coverage, timing and schema differences require source-owner review.

## Recommended review actions

1. Review missing capacity/throughput as distinct completeness issues. Keep null values out of paired ratios; do not convert them into zero flow or zero capacity.
2. Preserve signed flows and capacity exceedances for source confirmation. Avoid clipping values to make a chart appear compliant.
3. Resolve documented dictionary inconsistencies with the publisher: volumetric capacity versus energy units, and reversed coordinate descriptions. Keep the original metadata and the explicitly documented interpretation.
4. Review source-ID differences and GIS province differences using the original record references. Generalized boundaries and approximate incident coordinates do not establish a location error.
5. Keep the completed {year} comparison cohort separate from partial {year+1} data. Review per-source dates and first/last observations before interpreting change.

## Limits

The project does not infer pipeline outages, operational availability, regulatory breaches, actual damages, causal relationships or a company safety ranking. Multiple key points can observe the same gas. No network flow total or incidents-per-volume metric is calculated. Calendar coverage is bounded by each series' first and last published observation and cannot identify missing observations beyond those boundaries.

Contains information licensed under the Open Government Licence – Canada.
'''
    (root/'reports/findings.md').write_text(text,encoding='utf-8',newline='\n')


if __name__=='__main__':
    build()
