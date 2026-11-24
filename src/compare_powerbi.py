"""Independently compare native DAX output with the SQL-built report payload."""
import json
import math
from collections import defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
COUNTS=['ObservedDays','ExpectedDays','PairedDays','ThroughputDays','CapacityDays','MissingCapacityDays','MissingThroughputDays','OverCapacityDays','NegativeThroughputDays']
SUMS=['ThroughputSum','CapacitySum','ThroughputAllSum','CapacityAllSum']
FIELDS=COUNTS+SUMS


def ratios(row):
    for result,numerator,denominator in [('MeanThroughput','ThroughputAllSum','ThroughputDays'),('MeanCapacity','CapacityAllSum','CapacityDays'),
         ('Utilization','ThroughputSum','CapacitySum'),('Coverage','ObservedDays','ExpectedDays')]:
        row[result]=row[numerator]/row[denominator] if row[denominator] else None
    return row


def equal(actual,expected):
    if expected is None:return actual is None
    if isinstance(actual,bool) or not isinstance(actual,(int,float)):return False
    if isinstance(expected,int):return actual==expected
    return math.isclose(actual,expected,rel_tol=1e-10,abs_tol=1e-8)


def native_rows(value):return [value] if isinstance(value,dict) else value


def compare(native,payload):
    flow=defaultdict(lambda:{key:0 for key in FIELDS});total={key:0 for key in FIELDS}
    for row in payload['flow']:
        key=(int(row.get('Year',str(row['Month'])[:4])),row['PointId'])
        for field in FIELDS:
            value=int(row[field]) if field in COUNTS else float(row[field])
            flow[key][field]+=value;total[field]+=value
    for row in flow.values():ratios(row)
    ratios(total)
    actual_list=native_rows(native['flow'])
    actual={(int(r['Year']),r['PointId']):r for r in actual_list}
    checks={'flow_groups_nonempty':bool(flow),'flow_group_keys_match':set(actual)==set(flow),'flow_group_keys_unique':len(actual)==len(actual_list)}
    for field in FIELDS+['MeanThroughput','MeanCapacity','Utilization','Coverage']:
        checks['flow_'+field+'_matches_every_point_year']=set(actual)==set(flow) and all(field in actual[k] and equal(actual[k][field],v[field]) for k,v in flow.items())
    incidents=defaultdict(lambda:{'Records':0,'Open':0,'Significant':0,'Located':0})
    for row in payload['incidents']:
        year=int(row.get('Year',str(row['Month'])[:4]));r=incidents[(year,row['Province'])]
        r['Records']+=1;r['Open']+=row['Status'] in {'Initially Submitted','Submitted'}
        r['Significant']+=row['Significant']=='Yes'
        r['Located']+=row.get('Latitude') not in (None,'') and row.get('Longitude') not in (None,'')
    actual_list=native_rows(native['incidents'])
    actual={(int(r['Year']),r['Province']):r for r in actual_list}
    checks['incident_group_keys_match']=set(actual)==set(incidents)
    checks['incident_group_keys_unique']=len(actual)==len(actual_list)
    for field in ['Records','Open','Significant','Located']:
        checks['incidents_'+field+'_matches_every_province_year']=set(actual)==set(incidents) and all(field in actual[k] and equal(actual[k][field],v[field]) for k,v in incidents.items())
    single_point=len({key[1] for key in flow})==1
    expected_measures={
        'Observed point-days':total['ObservedDays'],'Expected point-days':total['ExpectedDays'],'Paired point-days':total['PairedDays'],
        'Mean throughput':total['MeanThroughput'] if single_point else None,'Mean capacity':total['MeanCapacity'] if single_point else None,
        'Utilization':total['Utilization'] if single_point else None,'Reporting coverage':total['Coverage'],
        'Missing capacity days':total['MissingCapacityDays'],'Missing throughput days':total['MissingThroughputDays'],
        'Above reported capacity':total['OverCapacityDays'],'Negative throughput days':total['NegativeThroughputDays'],
        'Incidents':sum(r['Records'] for r in incidents.values()),'Open incidents':sum(r['Open'] for r in incidents.values()),
        'Significant incidents':sum(r['Significant'] for r in incidents.values()),'Located incidents':sum(r['Located'] for r in incidents.values()),
    }
    overall=native_rows(native['allMeasures'])
    checks['global_single_result_row']=len(overall)==1
    overall=overall[0] if len(overall)==1 else {}
    checks['all_fifteen_measures_executed']=native['measureCount']==len(expected_measures) and set(overall)==set(expected_measures)
    for field,value in expected_measures.items():checks['global_'+field+'_matches']=field in overall and equal(overall[field],value)
    checks['multi_point_flow_rates_are_blank']=single_point or all(overall.get(field) is None for field in ['Mean throughput','Mean capacity','Utilization'])
    return checks,{'flow_groups':len(flow),'incident_groups':len(incidents)}


def main():
    native=json.loads((ROOT/'reports/powerbi_native_results.json').read_text(encoding='utf-8-sig'))
    payload=json.loads((ROOT/'reports/dashboard_data.json').read_text(encoding='utf-8-sig'))
    checks,groups=compare(native,payload)
    (ROOT/'reports/powerbi_validation_results.json').write_text(json.dumps({'groups':groups,'checks':checks},indent=2)+'\n',encoding='utf-8',newline='\n')
    failed=[key for key,value in checks.items() if not value]
    if failed:raise AssertionError('Native reconciliation failed: '+'; '.join(failed))
    print(f'{len(checks)} native checks passed: {groups}')


if __name__=='__main__':main()
