"""Exercise source reconciliation and daily observations with isolated fixtures."""
import csv
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
spec=importlib.util.spec_from_file_location('cer_pipeline_under_test',ROOT/'src/build.py')
build=importlib.util.module_from_spec(spec);spec.loader.exec_module(build)
from geo import ProvinceIndex

FLOW_HEADERS=['Date','Day','Month','Year','Company','Pipeline','Key Point','Latitude','Longitude','Direction Of Flow',
              'Trade Type','Capacity (1000 m3/d)','Throughput (1000 m3/d)','Throughput (GJ/d)']
INCIDENT_HEADERS=['Incident Number','Reported Date','Closed Date','Province','Company','Status','Significant','Incident Types',
                  'Latitude','Longitude','Why it happened category']


def daily(day,flow='10',capacity='20',**changes):
    parsed=build.date(day)
    row={'Date':day,'Day':str(parsed.day) if parsed else '1','Month':str(parsed.month) if parsed else '1',
         'Year':str(parsed.year) if parsed else '2025','Company':'Operator A','Pipeline':'NGTL System','Key Point':'East Gate',
         'Latitude':'52','Longitude':'-115','Direction Of Flow':'east','Trade Type':'intracanada',
         'Capacity (1000 m3/d)':capacity,'Throughput (1000 m3/d)':flow,'Throughput (GJ/d)':'380'}
    row.update(changes);return row


def incident(code='INC-1',**changes):
    row={'Incident Number':code,'Reported Date':'08/10/2023','Closed Date':'2024/01/23','Province':'Alberta','Company':'Operator A',
         'Status':'Closed','Significant':'No','Incident Types':'Fire','Latitude':'52','Longitude':'-115','Why it happened category':'Maintenance'}
    row.update(changes);return row


def spatial_fixture():
    return ProvinceIndex({'type':'FeatureCollection','features':[{'type':'Feature','properties':{'COUNTRY':1,'POLITICALDIV':1},
             'geometry':{'type':'Polygon','coordinates':[[[-120,49],[-110,49],[-110,60],[-120,60],[-120,49]]]}}]})


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='cer-pipeline-test-');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.source=self.root/'data/source';self.source.mkdir(parents=True)
        self.spatial=spatial_fixture()

    def write(self,name,rows,headers,encoding='utf-8'):
        with (self.source/name).open('w',encoding=encoding,newline='') as handle:
            writer=csv.DictWriter(handle,fieldnames=headers);writer.writeheader();writer.writerows(rows)

    def flow(self,rows):
        self.write('fixture.csv',rows,FLOW_HEADERS)
        connection=sqlite3.connect(':memory:');connection.row_factory=sqlite3.Row;self.addCleanup(connection.close)
        connection.executescript((ROOT/'sql/schema.sql').read_text(encoding='utf-8'))
        with patch.object(build,'FLOW_FILES',('fixture.csv',)):
            points,profiles,quality,source_count,accepted=build.ingest_flow(connection,self.root,self.spatial)
        connection.executescript((ROOT/'sql/analysis.sql').read_text(encoding='utf-8'))
        facts=build.aggregate_flow(connection,points)
        return connection,points,quality,source_count,accepted,facts

    def test_exact_duplicates_removed_but_conflicting_daily_keys_quarantined(self):
        first=daily('2025-01-01')
        connection,points,quality,source_count,accepted,facts=self.flow([
            first,dict(first),daily('2025-01-02','10'),daily('2025-01-02','11'),daily('2025-01-03','15'),daily('invalid-date')])
        self.assertEqual((source_count,accepted),(6,2))
        self.assertEqual(quality['exact_duplicates_removed'],1)
        self.assertEqual(quality['conflicting_key_rows_quarantined'],2)
        self.assertEqual(quality['invalid_dates_quarantined'],1)
        self.assertEqual(connection.execute('SELECT COUNT(*) FROM conflicting_keys').fetchone()[0],1)
        retained=[r['Date'] for r in connection.execute('SELECT Date FROM flow_daily ORDER BY Date')]
        self.assertEqual(retained,['2025-01-01','2025-01-03'])
        self.assertEqual((facts[0]['ObservedDays'],facts[0]['ExpectedDays']),(2,3))

    def test_missing_and_zero_capacity_are_distinct_and_negative_flow_is_retained(self):
        connection,_,quality,_,_,facts=self.flow([
            daily('2025-01-01','10',''),daily('2025-01-02','20','0'),daily('2025-01-03','','10'),
            daily('2025-01-04','-2','10'),daily('2025-01-05','6','-5'),daily('2025-01-06','inf','NaN')])
        row=facts[0]
        self.assertEqual(row['MissingCapacityDays'],3)
        self.assertEqual(row['MissingThroughputDays'],2)
        self.assertEqual(row['CapacityDays'],3)
        self.assertEqual(row['ThroughputDays'],4)
        self.assertEqual(row['PairedDays'],1)
        self.assertEqual(row['ThroughputSum'],-2)
        self.assertEqual(row['CapacitySum'],10)
        self.assertAlmostEqual(row['Utilization'],-.2)
        self.assertAlmostEqual(row['MeanThroughput'],8.5)
        self.assertEqual(row['NegativeThroughputDays'],1)
        self.assertEqual(quality['negative_capacity'],1)
        raw={r['Date']:dict(r) for r in connection.execute('SELECT * FROM flow_daily')}
        self.assertIsNone(raw['2025-01-01']['Capacity'])
        self.assertEqual(raw['2025-01-02']['Capacity'],0)
        self.assertEqual(raw['2025-01-04']['Throughput'],-2)

    def test_ratio_uses_paired_weighting_and_calendar_gaps_remain_visible(self):
        _,_,_,_,_,facts=self.flow([daily('2025-01-01','10','20'),daily('2025-01-02','90','100'),daily('2025-03-01','20','100')])
        january,february,march=facts
        self.assertAlmostEqual(january['Utilization'],100/120)
        self.assertNotAlmostEqual(january['Utilization'],(.5+.9)/2)
        self.assertEqual((january['ObservedDays'],january['ExpectedDays']),(2,31))
        self.assertEqual((february['ObservedDays'],february['ExpectedDays']),(0,28))
        self.assertIsNone(february['MeanThroughput']);self.assertIsNone(february['Utilization'])
        self.assertEqual((march['ObservedDays'],march['ExpectedDays']),(1,1))

    def test_zero_pair_denominator_is_missing_not_zero_utilization(self):
        _,_,_,_,_,facts=self.flow([daily('2025-01-01','0','0')])
        self.assertEqual(facts[0]['ThroughputDays'],1)
        self.assertEqual(facts[0]['MeanThroughput'],0)
        self.assertIsNone(facts[0]['Utilization'])

    def test_cp1252_source_decoding_preserves_names_and_punctuation(self):
        self.write('text.csv',[{'Company':'Société – Québec','Notes':'l’entreprise'}],['Company','Notes'],encoding='cp1252')
        rows,encoding=build.source_rows(self.source/'text.csv')
        self.assertEqual(encoding,'cp1252');self.assertEqual(rows[0]['Company'],'Société – Québec')
        self.assertEqual(rows[0]['Notes'],'l’entreprise')

    def test_malformed_csv_fails_without_silently_dropping_fields(self):
        for text in ['A,B\n1,2,3\n','A,B\n1\n']:
            (self.source/'bad.csv').write_text(text,encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'Malformed CSV'):build.source_rows(self.source/'bad.csv')

    def test_duplicate_headers_are_rejected_before_fields_can_be_overwritten(self):
        (self.source/'bad.csv').write_text('Company,Company\nOperator A,Operator B\n',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'(?i)duplicate'):build.source_rows(self.source/'bad.csv')

    def test_quarantined_conflicts_do_not_select_the_point_metadata(self):
        _,points,quality,_,accepted,_=self.flow([
            daily('2025-01-01','10',Latitude='58',Company='Conflicting operator'),
            daily('2025-01-01','11',Latitude='58',Company='Conflicting operator'),
            daily('2025-01-02','15',Latitude='52',Company='Accepted operator')])
        self.assertEqual(accepted,1);self.assertEqual(quality['conflicting_key_rows_quarantined'],2)
        self.assertEqual(points[0]['Latitude'],52);self.assertEqual(points[0]['Company'],'Accepted operator')

    def test_incident_dates_and_non_canadian_location_are_preserved(self):
        row=incident(Province='Maine',Latitude='45.2',Longitude='-67.3')
        self.write('incidents.csv',[row],INCIDENT_HEADERS)
        self.write('incidents_map.csv',[row],INCIDENT_HEADERS)
        facts,profile,quality=build.ingest_incidents(self.root,self.spatial)
        self.assertEqual(facts[0]['ReportedDate'],'2023-08-10')
        self.assertEqual(facts[0]['ClosedDate'],'2024-01-23')
        self.assertEqual(facts[0]['ClosureDays'],166)
        self.assertEqual(facts[0]['Province'],'Maine')
        self.assertEqual(facts[0]['SpatialStatus'],'outside_generalized_boundary')
        reconciled,_,counts=build.reconcile_incidents(self.root,facts)
        self.assertEqual(counts,{'matched':1});self.assertEqual(reconciled[0]['DifferentFields'],'')

    def test_invalid_date_and_negative_closure_remain_auditable(self):
        self.write('incidents.csv',[incident('BAD',**{'Reported Date':'not a date'}),incident('NEG',**{'Closed Date':'2023/01/01'})],INCIDENT_HEADERS)
        facts,_,quality=build.ingest_incidents(self.root,self.spatial)
        self.assertEqual((facts[0]['Month'],facts[0]['Year']),('Not reported',0))
        self.assertEqual(quality['invalid_reported_dates'],1);self.assertEqual(quality['negative_closure_intervals'],1)
        self.assertIsNone(facts[0]['ClosureDays']);self.assertIsNone(facts[1]['ClosureDays'])

    def test_reconciliation_reports_field_and_coverage_differences(self):
        a=incident('A');b=incident('B');c=incident('C')
        self.write('incidents.csv',[a,b],INCIDENT_HEADERS)
        self.write('incidents_map.csv',[{**a,'Status':'Submitted'},c],INCIDENT_HEADERS)
        facts,_,_=build.ingest_incidents(self.root,self.spatial)
        rows,_,counts=build.reconcile_incidents(self.root,facts)
        self.assertEqual(counts,{'field_difference_review':1,'comprehensive_only':1,'map_only':1})
        self.assertEqual(next(r for r in rows if r['IncidentId']=='A')['DifferentFields'],'Status')
        self.assertEqual(facts[0]['Status'],'Closed')

    def test_duplicate_incident_ids_are_rejected_in_both_sources(self):
        a=incident()
        self.write('incidents.csv',[a,a],INCIDENT_HEADERS)
        with self.assertRaisesRegex(ValueError,'Duplicate or missing Incident Number'):build.ingest_incidents(self.root,self.spatial)
        self.write('incidents.csv',[a],INCIDENT_HEADERS);self.write('incidents_map.csv',[a,a],INCIDENT_HEADERS)
        facts,_,_=build.ingest_incidents(self.root,self.spatial)
        with self.assertRaisesRegex(ValueError,'missing/duplicate IDs'):build.reconcile_incidents(self.root,facts)


class ExportTests(unittest.TestCase):
    @unittest.skipUnless((ROOT/'reports/dashboard_data.json').exists(),'Generated project outputs are not present')
    def test_full_snapshot_counts_and_foreign_keys_reconcile(self):
        payload=json.loads((ROOT/'reports/dashboard_data.json').read_text(encoding='utf-8'))
        def read(name):
            with (ROOT/'data/model'/(name+'.csv')).open(encoding='utf-8-sig',newline='') as stream:return list(csv.DictReader(stream))
        points=read('DimPoint');months=read('DimMonth');provinces=read('DimProvince');flows=read('FactFlow');incidents=read('FactIncident')
        point_ids={r['PointId'] for r in points};month_ids={r['Month'] for r in months};province_ids={r['Province'] for r in provinces}
        self.assertEqual(len(point_ids),len(points));self.assertEqual(len(month_ids),len(months));self.assertEqual(len(province_ids),len(provinces))
        self.assertTrue(all(r['Province'] in province_ids for r in points+incidents))
        self.assertTrue(all(r['Month'] in month_ids and r['PointId'] in point_ids for r in flows))
        self.assertTrue(all(r['Month'] in month_ids for r in incidents))
        self.assertEqual(sum(int(r['ObservedDays']) for r in flows),payload['meta']['flow_accepted_rows'])
        self.assertEqual(len(incidents),payload['meta']['incident_rows'])
        self.assertEqual(len({r['IncidentId'] for r in incidents}),len(incidents))
        self.assertEqual(len({(r['PointId'],r['Month']) for r in flows}),len(flows))
        payload_rows={(r['PointId'],r['Month']):r for r in payload['flow']}
        for row in flows:
            expected=payload_rows[(row['PointId'],row['Month'])]
            for field in build.FLOW_FIELDS:
                if field not in ('Month','PointId'):self.assertAlmostEqual(float(row[field]),float(expected[field]),places=8)
        profile=json.loads((ROOT/'reports/source_profile.json').read_text(encoding='utf-8'))
        quality=profile['raw_quality']
        excluded=sum(quality.get(k,0) for k in ['exact_duplicates_removed','invalid_dates_quarantined','conflicting_key_rows_quarantined'])
        self.assertEqual(payload['meta']['flow_source_rows'],payload['meta']['flow_accepted_rows']+excluded)


if __name__=='__main__':unittest.main()
