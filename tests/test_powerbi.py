"""Exercise model guards and independent native-result reconciliation."""
import base64
import copy
import csv
import importlib.util
import json
from pathlib import Path
import re
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


def module(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'src'/(name+'.py'))
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


def flow_row(month,point,**changes):
    result={'Month':month,'PointId':point,'ObservedDays':2,'ExpectedDays':2,'PairedDays':2,'ThroughputSum':20.,'CapacitySum':40.,
         'ThroughputDays':2,'CapacityDays':2,'ThroughputAllSum':20.,'CapacityAllSum':40.,'MissingCapacityDays':0,
         'MissingThroughputDays':0,'OverCapacityDays':0,'NegativeThroughputDays':0}
    result.update(changes);return result


def source():
    return {'flow':[
       flow_row('2025-01','A'),
       flow_row('2025-02','A',ThroughputSum=60.,CapacitySum=60.,ThroughputAllSum=60.,CapacityAllSum=60.),
       flow_row('2025-01','B',ObservedDays=1,PairedDays=0,ThroughputSum=0.,CapacitySum=0.,ThroughputDays=1,CapacityDays=0,
                ThroughputAllSum=4.,CapacityAllSum=0.,MissingCapacityDays=1)],
      'incidents':[
        {'IncidentId':'I1','Month':'2025-01','Year':2025,'Province':'Alberta','Company':'Operator A','Status':'Closed','Significant':'Yes','Types':'Fire','SpatialStatus':'match','Latitude':50.,'Longitude':-110.,'ClosureDays':10},
        {'IncidentId':'I2','Month':'2025-02','Year':2025,'Province':'Alberta','Company':'Operator A','Status':'Submitted','Significant':'No','Types':'Release','SpatialStatus':'invalid_coordinates','Latitude':None,'Longitude':None,'ClosureDays':None},
        {'IncidentId':'I3','Month':'2025-01','Year':2025,'Province':'Québec','Company':'Operator B','Status':'Initially Submitted','Significant':'No','Types':'Fire','SpatialStatus':'match','Latitude':45.,'Longitude':-72.,'ClosureDays':None}]}


def native_fixture():
    return {'flow':[
      {'Year':2025,'PointId':'A','ObservedDays':4,'ExpectedDays':4,'PairedDays':4,'ThroughputSum':80.,'CapacitySum':100.,'ThroughputDays':4,'CapacityDays':4,
       'ThroughputAllSum':80.,'CapacityAllSum':100.,'MissingCapacityDays':0,'MissingThroughputDays':0,'OverCapacityDays':0,'NegativeThroughputDays':0,
       'MeanThroughput':20.,'MeanCapacity':25.,'Utilization':.8,'Coverage':1.},
      {'Year':2025,'PointId':'B','ObservedDays':1,'ExpectedDays':2,'PairedDays':0,'ThroughputSum':0.,'CapacitySum':0.,'ThroughputDays':1,'CapacityDays':0,
       'ThroughputAllSum':4.,'CapacityAllSum':0.,'MissingCapacityDays':1,'MissingThroughputDays':0,'OverCapacityDays':0,'NegativeThroughputDays':0,
       'MeanThroughput':4.,'MeanCapacity':None,'Utilization':None,'Coverage':.5}],
      'incidents':[{'Year':2025,'Province':'Alberta','Records':2,'Open':1,'Significant':1,'Located':1},
                   {'Year':2025,'Province':'Québec','Records':1,'Open':1,'Significant':0,'Located':1}],
      'allMeasures':[{'Observed point-days':5,'Expected point-days':6,'Paired point-days':4,'Mean throughput':None,'Mean capacity':None,'Utilization':None,
                      'Reporting coverage':5/6,'Missing capacity days':1,'Missing throughput days':0,'Above reported capacity':0,'Negative throughput days':0,
                      'Incidents':3,'Open incidents':2,'Significant incidents':1,'Located incidents':2}], 'measureCount':15}


class GeneratorTests(unittest.TestCase):
    def setUp(self):
        self.build=module('build_powerbi');self.temp=tempfile.TemporaryDirectory(prefix='cer-model-test-');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);(self.root/'data/model').mkdir(parents=True)
        self.build.ROOT=self.root;self.build.OUT=self.root/'powerbi/native'
        self.build.REPORT=self.build.OUT/(self.build.NAME+'.Report');self.build.MODEL=self.build.OUT/(self.build.NAME+'.SemanticModel')
        self.tables={'DimPoint':[
            {'PointId':'A','Pipeline':'NGTL System','KeyPoint':'East Gate','PointLabel':'NGTL System · East Gate','Company':'Operator A','Direction':'east','TradeType':'intracanada','Province':'Alberta','Latitude':50,'Longitude':-110},
            {'PointId':'B','Pipeline':'TQM','KeyPoint':'Québec','PointLabel':'TQM · Québec','Company':'Operator B','Direction':'south','TradeType':'export','Province':'Québec','Latitude':45,'Longitude':-72}],
          'DimMonth':[{'Month':'2025-01','Year':2025},{'Month':'2025-02','Year':2025}],
          'DimProvince':[{'Province':'Alberta'},{'Province':'Québec'}],
          'FactFlow':source()['flow'],'FactIncident':source()['incidents']}
        self.write_tables()

    def write_tables(self):
        for name,rows in self.tables.items():
            with (self.root/'data/model'/(name+'.csv')).open('w',encoding='utf-8',newline='') as f:
                writer=csv.DictWriter(f,fieldnames=self.build.HEADERS[name]);writer.writeheader();writer.writerows(rows)

    def files(self):return {str(p.relative_to(self.root)):p.read_bytes() for p in (self.root/'powerbi').rglob('*') if p.is_file()}

    def test_portable_deterministic_generation_preserves_utf8_and_nulls(self):
        self.build.main();before=self.files();self.build.main();self.assertEqual(before,self.files())
        model=json.loads((self.build.MODEL/'model.bim').read_text(encoding='utf-8'))['model']
        self.assertEqual({t['name'] for t in model['tables']},set(self.tables))
        for table in model['tables']:
            expression='\n'.join(table['partitions'][0]['source']['expression'])
            encoded=re.search(r'Binary.FromText\("([A-Za-z0-9+/=]+)"',expression).group(1)
            self.assertEqual(base64.b64decode(encoded),(self.root/'data/model'/(table['name']+'.csv')).read_bytes())
            self.assertIn('Table.ReplaceValue(Headers, "", null',expression)
            self.assertNotIn('File.Contents',expression);self.assertNotIn(str(self.root),expression)

    def test_relationships_keep_facts_separate_and_rates_guarded(self):
        self.build.main();model=json.loads((self.build.MODEL/'model.bim').read_text(encoding='utf-8'))['model']
        self.assertEqual(len(model['relationships']),5)
        self.assertFalse(any(r['fromTable'].startswith('Fact') and r['toTable'].startswith('Fact') for r in model['relationships']))
        self.assertTrue(all(r['isActive'] and r['crossFilteringBehavior']=='oneDirection' for r in model['relationships']))
        tables={t['name']:t for t in model['tables']};measures={m['name']:m for t in tables.values() for m in t.get('measures',[])}
        self.assertEqual(len(measures),15)
        for name in ['Mean throughput','Mean capacity','Utilization']:
            self.assertIn('HASONEVALUE(DimPoint[PointId])',measures[name]['expression'])
        self.assertIn('SUM(FactFlow[ThroughputSum]), SUM(FactFlow[CapacitySum])',measures['Utilization']['expression'])
        self.assertEqual(next(c for c in tables['DimMonth']['columns'] if c['name']=='Year')['dataType'],'int64')
        for path in self.build.REPORT.rglob('visual.json'):
            visual=json.loads(path.read_text(encoding='utf-8'))['visual']
            for role in visual.get('query',{}).get('queryState',{}).values():
                for item in role['projections']:
                    kind,field=next(iter(item['field'].items()));table=field['Expression']['SourceRef']['Entity']
                    self.assertIn(field['Property'],{x['name'] for x in tables[table]['measures' if kind=='Measure' else 'columns']})

    def test_duplicate_incident_ids_are_rejected(self):
        self.tables['FactIncident'].append(dict(self.tables['FactIncident'][0]));self.write_tables()
        with self.assertRaisesRegex(ValueError,'incident ID'):self.build.main()

    def test_undated_incident_cohort_is_retained(self):
        self.tables['DimMonth'].append({'Month':'Not reported','Year':0})
        self.tables['FactIncident'][0]['Month']='Not reported';self.tables['FactIncident'][0]['Year']=0
        self.write_tables();self.build.main()
        model=json.loads((self.build.MODEL/'model.bim').read_text(encoding='utf-8'))['model']
        self.assertIn('FactIncident',{table['name'] for table in model['tables']})

    def test_default_selection_follows_validated_report_metadata(self):
        self.tables['DimMonth'].append({'Month':'2024-01','Year':2024})
        self.tables['FactFlow'][0]['Month']='2024-01';self.write_tables()
        (self.root/'reports').mkdir()
        (self.root/'reports/dashboard_data.json').write_text(json.dumps({'meta':{'default_year':2024,'default_point':'B'}}),encoding='utf-8')
        _,year,point=self.build.load_inputs()
        self.assertEqual(year,2024);self.assertEqual(point,'TQM · Québec')

    def test_orphan_province_is_rejected_before_writing(self):
        self.tables['DimPoint'][0]['Province']='Unknown';self.write_tables()
        with self.assertRaisesRegex(ValueError,'orphan dimension key'):self.build.main()
        self.assertFalse(self.build.OUT.exists())

    def test_duplicate_grain_and_invalid_pair_counts_are_rejected(self):
        self.tables['FactFlow'].append(dict(self.tables['FactFlow'][0]));self.write_tables()
        with self.assertRaisesRegex(ValueError,'Duplicate flow grain'):self.build.main()
        self.tables['FactFlow'].pop();self.tables['FactFlow'][0]['ThroughputDays']=1;self.write_tables()
        with self.assertRaisesRegex(ValueError,'Paired days'):self.build.main()


class NativeComparisonTests(unittest.TestCase):
    def setUp(self):self.compare=module('compare_powerbi');self.payload=source();self.native=native_fixture()

    def test_counts_weighted_ratios_and_incident_context_reconcile(self):
        checks,groups=self.compare.compare(self.native,self.payload)
        self.assertTrue(all(checks.values()),[k for k,v in checks.items() if not v]);self.assertEqual(groups,{'flow_groups':2,'incident_groups':2})

    def test_unweighted_monthly_ratio_is_rejected(self):
        self.native['flow'][0]['Utilization']=(.5+1)/2
        checks,_=self.compare.compare(self.native,self.payload);self.assertFalse(checks['flow_Utilization_matches_every_point_year'])

    def test_multi_point_rate_is_blank(self):
        self.native['allMeasures'][0]['Utilization']=.8
        checks,_=self.compare.compare(self.native,self.payload);self.assertFalse(checks['multi_point_flow_rates_are_blank'])

    def test_zero_denominator_must_not_be_coerced_to_zero(self):
        self.native['flow'][1]['Utilization']=0
        checks,_=self.compare.compare(self.native,self.payload);self.assertFalse(checks['flow_Utilization_matches_every_point_year'])

    def test_duplicate_and_missing_native_groups_are_rejected(self):
        self.native['flow'].append(copy.deepcopy(self.native['flow'][0]))
        self.native['incidents'].pop()
        checks,_=self.compare.compare(self.native,self.payload)
        self.assertFalse(checks['flow_group_keys_unique']);self.assertFalse(checks['incident_group_keys_match'])

    def test_every_measure_value_is_checked(self):
        self.native['allMeasures'][0]['Significant incidents']=2
        checks,_=self.compare.compare(self.native,self.payload);self.assertTrue(checks['all_fifteen_measures_executed'])
        self.assertFalse(checks['global_Significant incidents_matches'])


if __name__=='__main__':unittest.main()
