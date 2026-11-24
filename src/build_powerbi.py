"""Build a portable native report without combining unrelated pipeline flows."""
import base64
import csv
import json
import math
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = 'CER_Energy_Analysis'
OUT = ROOT / 'powerbi/native'
REPORT = OUT / (NAME + '.Report')
MODEL = OUT / (NAME + '.SemanticModel')
SCHEMA = 'https://developer.microsoft.com/json-schemas/fabric/item/report/'
COUNTS = ['ObservedDays', 'ExpectedDays', 'PairedDays', 'ThroughputDays', 'CapacityDays',
          'MissingCapacityDays', 'MissingThroughputDays', 'OverCapacityDays', 'NegativeThroughputDays']
SUMS = ['ThroughputSum', 'CapacitySum', 'ThroughputAllSum', 'CapacityAllSum']
HEADERS = {
    'DimPoint': ['PointId','Pipeline','KeyPoint','PointLabel','Company','Direction','TradeType','Province','Latitude','Longitude'],
    'DimMonth': ['Month','Year'],
    'DimProvince': ['Province'],
    'FactFlow': ['Month','PointId','ObservedDays','ExpectedDays','PairedDays','ThroughputSum','CapacitySum','ThroughputDays','CapacityDays','ThroughputAllSum','CapacityAllSum','MissingCapacityDays','MissingThroughputDays','OverCapacityDays','NegativeThroughputDays'],
    'FactIncident': ['IncidentId','Month','Year','Province','Company','Status','Significant','Types','SpatialStatus','Latitude','Longitude','ClosureDays'],
}
# table, DAX expression, format, explanation
MEASURES = {
    'Observed point-days': ('FactFlow','SUM(FactFlow[ObservedDays])','#,0','Reported daily observations, counted separately at each key point.'),
    'Expected point-days': ('FactFlow','SUM(FactFlow[ExpectedDays])','#,0','Expected daily observations under the documented active-series coverage policy.'),
    'Paired point-days': ('FactFlow','SUM(FactFlow[PairedDays])','#,0','Days with usable paired volumetric throughput and positive capacity.'),
    'Mean throughput': ('FactFlow','IF(HASONEVALUE(DimPoint[PointId]), DIVIDE(SUM(FactFlow[ThroughputAllSum]), SUM(FactFlow[ThroughputDays])))','#,0.0','Mean valid daily throughput at one selected point; thousand cubic metres per day.'),
    'Mean capacity': ('FactFlow','IF(HASONEVALUE(DimPoint[PointId]), DIVIDE(SUM(FactFlow[CapacityAllSum]), SUM(FactFlow[CapacityDays])))','#,0.0','Mean valid reported capacity at one selected point; thousand cubic metres per day.'),
    'Utilization': ('FactFlow','IF(HASONEVALUE(DimPoint[PointId]), DIVIDE(SUM(FactFlow[ThroughputSum]), SUM(FactFlow[CapacitySum])))','0.0%','Paired throughput divided by paired reported capacity at one point. This is a ratio of sums, not an average of monthly ratios.'),
    'Reporting coverage': ('FactFlow','DIVIDE([Observed point-days], [Expected point-days])','0.00%','Observed point-days divided by expected point-days. Does not imply field completeness.'),
    'Missing capacity days': ('FactFlow','SUM(FactFlow[MissingCapacityDays])','#,0','Observed point-days whose capacity is missing or unusable under pipeline validation.'),
    'Missing throughput days': ('FactFlow','SUM(FactFlow[MissingThroughputDays])','#,0','Observed point-days whose throughput is missing or unusable under pipeline validation.'),
    'Above reported capacity': ('FactFlow','SUM(FactFlow[OverCapacityDays])','#,0','Point-days above the published capacity estimate; not a finding of noncompliance.'),
    'Negative throughput days': ('FactFlow','SUM(FactFlow[NegativeThroughputDays])','#,0','Negative volumetric observations retained as review flags.'),
    'Incidents': ('FactIncident','COUNTROWS(FactIncident)','#,0','Unique incident records in the comprehensive CER extract, grouped by reported month.'),
    'Open incidents': ('FactIncident','COALESCE(CALCULATE(COUNTROWS(FactIncident), KEEPFILTERS(FactIncident[Status] IN {"Initially Submitted", "Submitted"})), 0)','#,0','Incidents with preliminary or submitted review status at snapshot time.'),
    'Significant incidents': ('FactIncident','COALESCE(CALCULATE(COUNTROWS(FactIncident), KEEPFILTERS(FactIncident[Significant] = "Yes")), 0)','#,0','Incidents explicitly classified Significant=Yes by the source.'),
    'Located incidents': ('FactIncident','COALESCE(COUNTROWS(FILTER(FactIncident, NOT(ISBLANK(FactIncident[Latitude])) && NOT(ISBLANK(FactIncident[Longitude])))), 0)','#,0','Incident records with usable latitude and longitude; does not establish an exact pipeline match.'),
}
RELATIONSHIPS = [('FactFlow','PointId','DimPoint','PointId'),('FactFlow','Month','DimMonth','Month'),
                 ('FactIncident','Month','DimMonth','Month'),('FactIncident','Province','DimProvince','Province'),
                 ('DimPoint','Province','DimProvince','Province')]


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')


def uid(value):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, 'cer-energy-analysis/' + value))


def literal(value):
    encoded = ('true' if value else 'false') if isinstance(value,bool) else (str(value)+'D' if isinstance(value,(int,float)) else "'"+value.replace("'","''")+"'")
    return {'expr': {'Literal': {'Value': encoded}}}


def color(value):
    return {'solid': {'color': literal(value)}}


def projection(table, column, is_measure=False):
    return {'field': {'Measure' if is_measure else 'Column': {'Expression': {'SourceRef': {'Entity': table}}, 'Property': column}},
            'queryRef': table+'.'+column, 'nativeQueryRef': column}


def measure(name):
    return projection(MEASURES[name][0], name, True)


def load_inputs():
    tables = {}
    for name, headers in HEADERS.items():
        with (ROOT/'data/model'/f'{name}.csv').open(encoding='utf-8-sig',newline='') as source:
            reader=csv.DictReader(source)
            if reader.fieldnames != headers:
                raise ValueError(f'{name}: unexpected column order {reader.fieldnames}')
            tables[name]=list(reader)
        if not tables[name]:
            raise ValueError(f'{name}: empty model input')
    keys={}
    for table,key in [('DimPoint','PointId'),('DimMonth','Month'),('DimProvince','Province')]:
        keys[table]={r[key] for r in tables[table]}
        if '' in keys[table] or len(keys[table])!=len(tables[table]):
            raise ValueError(f'{table}: duplicate or empty dimension key')
    for fact,fk,dim,pk in RELATIONSHIPS:
        if any(r[fk] not in keys[dim] for r in tables[fact]):
            raise ValueError(f'{fact}.{fk}: orphan dimension key')
    grains=set()
    for row in tables['FactFlow']:
        grain=(row['Month'],row['PointId'])
        if grain in grains: raise ValueError(f'Duplicate flow grain {grain}')
        grains.add(grain)
        counts={key:int(row[key]) for key in COUNTS}
        if any(n<0 for n in counts.values()) or counts['ObservedDays']>counts['ExpectedDays']:
            raise ValueError(f'Invalid observed/expected counts at {grain}')
        if any(counts[key]>counts['ObservedDays'] for key in COUNTS if key!='ExpectedDays'):
            raise ValueError(f'Invalid count bounds at {grain}')
        if counts['PairedDays']>min(counts['ThroughputDays'],counts['CapacityDays']):
            raise ValueError(f'Paired days exceed valid observations at {grain}')
        if any(not math.isfinite(float(row[key])) for key in SUMS):
            raise ValueError(f'Nonfinite flow aggregate at {grain}')
    ids=[r['IncidentId'] for r in tables['FactIncident']]
    if len(ids)!=len(set(ids)) or '' in ids: raise ValueError('Duplicate or empty incident ID')
    for row in tables['FactIncident']:
        if row['Month']=='Not reported' and str(row['Year'])=='0': continue
        if row['Month'][:4] != str(row['Year']): raise ValueError('Incident year/month disagreement')
    years={int(r['Year']) for r in tables['DimMonth']}
    default_year=2025 if 2025 in years else max(years)
    preferred=[r for r in tables['DimPoint'] if r['Pipeline']=='NGTL System' and r['KeyPoint']=='East Gate']
    default_point=(preferred or tables['DimPoint'])[0]['PointLabel']
    payload_path=ROOT/'reports/dashboard_data.json'
    if payload_path.exists():
        metadata=json.loads(payload_path.read_text(encoding='utf-8-sig')).get('meta',{})
        requested_year=metadata.get('default_year')
        if str(requested_year).isdigit() and int(requested_year) in years:
            default_year=int(requested_year)
        requested_point=next((r for r in tables['DimPoint'] if r['PointId']==metadata.get('default_point')),None)
        if requested_point:default_point=requested_point['PointLabel']
    return tables,default_year,default_point


def data_type(header):
    if header in COUNTS or header=='Year': return 'int64','Int64.Type'
    if header in SUMS or header in ['Latitude','Longitude','ClosureDays']: return 'double','type number'
    return 'string','type text'


def build_model(tables):
    model={'name':NAME,'compatibilityLevel':1606,'model':{'culture':'en-US','defaultPowerBIDataSourceVersion':'powerBI_V3','tables':[],
           'relationships':[],'annotations':[{'name':'__PBI_TimeIntelligenceEnabled','value':'0'}]}}
    for name in tables:
        columns=[];types=[];numeric=[]
        for header in HEADERS[name]:
            dtype,mtype=data_type(header)
            column={'name':header,'dataType':dtype,'sourceColumn':header,'summarizeBy':'none','lineageTag':uid(name+'/'+header),
                    'isHidden':name=='FactFlow' or (name=='FactIncident' and header in ['Month','Year','Latitude','Longitude','ClosureDays']) or header=='PointId'}
            if header in ['Latitude','Longitude']: column['dataCategory']=header
            columns.append(column);types.append('{"'+header+'", '+mtype+'}')
            if dtype!='string': numeric.append('"'+header+'"')
        raw=(ROOT/'data/model'/f'{name}.csv').read_bytes()
        encoded=base64.b64encode(raw).decode('ascii')
        expression=['let',f' Source = Csv.Document(Binary.FromText("{encoded}", BinaryEncoding.Base64), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),',
                    ' Headers = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),',
                    ' Nullable = Table.ReplaceValue(Headers, "", null, Replacer.ReplaceValue, {'+', '.join(numeric)+'}),',
                    ' Typed = Table.TransformColumnTypes(Nullable, {'+', '.join(types)+'}, "en-US")','in',' Typed']
        table={'name':name,'columns':columns,'lineageTag':uid(name),'partitions':[{'name':name,'mode':'import','source':{'type':'m','expression':expression}}]}
        measures=[{'name':key,'expression':dax,'formatString':fmt,'description':description,'lineageTag':uid('measure/'+key)}
                  for key,(owner,dax,fmt,description) in MEASURES.items() if owner==name]
        if measures: table['measures']=measures
        model['model']['tables'].append(table)
    for fact,fk,dim,pk in RELATIONSHIPS:
        model['model']['relationships'].append({'name':uid(fact+'/'+fk+'/'+dim),'fromTable':fact,'fromColumn':fk,'fromCardinality':'many',
             'toTable':dim,'toColumn':pk,'toCardinality':'one','crossFilteringBehavior':'oneDirection','isActive':True})
    write(MODEL/'model.bim',model)
    write(MODEL/'definition.pbism',{'version':'4.0','settings':{}})
    (ROOT/'powerbi/measures.dax').write_text('\n\n'.join('// '+d+'\n'+n+' = '+x for n,(_,x,_,d) in MEASURES.items())+'\n',encoding='utf-8',newline='\n')


class ReportBuilder:
    def __init__(self,year,point): self.year=year;self.point=point;self.counter=0;self.pages=[]

    def page(self,name,title):
        self.pages.append(name);path=REPORT/'definition/pages'/name
        write(path/'page.json',{'$schema':SCHEMA+'definition/page/2.0.0/schema.json','name':name,'displayName':title,'displayOption':'FitToPage',
             'width':1280,'height':800,'objects':{'background':[{'properties':{'color':color('#EEF2EF'),'transparency':literal(0)}}]}})
        return path

    def visual(self,page,kind,title,x,y,w,h,roles=None,objects=None):
        self.counter+=1;name=f'v{self.counter:019d}'
        visual={'visualType':kind,'drillFilterOtherVisuals':True,'visualContainerObjects':{
          'title':[{'properties':{'show':literal(bool(title)),'text':literal(title),'fontSize':literal(11),'fontColor':color('#173A32')}}],
          'background':[{'properties':{'show':literal(True),'color':color('#FFFFFF'),'transparency':literal(0)}}],
          'border':[{'properties':{'show':literal(False)}}]}}
        if roles: visual['query']={'queryState':{k:{'projections':v} for k,v in roles.items()}}
        if objects: visual['objects']=objects
        if kind=='tableEx': visual['objects']={'grid':[{'properties':{'rowPadding':literal(5)}}],
             'values':[{'properties':{'fontSize':literal(10)}}],'columnHeaders':[{'properties':{'fontSize':literal(10)}}]}
        item={'$schema':SCHEMA+'definition/visualContainer/2.4.0/schema.json','name':name,
              'position':{'x':x,'y':y,'width':w,'height':h,'z':self.counter,'tabOrder':self.counter},'visual':visual}
        path=page/'visuals'/name/'visual.json';write(path,item);return item,path

    def text(self,page,text,x,y,w,h,size=11,dark=False):
        item,path=self.visual(page,'textbox','',x,y,w,h,objects={'general':[{'properties':{'paragraphs':[{'textRuns':[{'value':text,
            'textStyle':{'fontFamily':'Segoe UI','fontSize':str(size)+'pt','color':'#FFFFFF' if dark else '#4B655D'}}]}]}}]})
        item['visual']['visualContainerObjects']['background'][0]['properties']['color']=color('#173A32' if dark else '#EEF2EF')
        write(path,item)

    def slicer(self,page,title,table,column,x,y,w,h,value=None):
        item,path=self.visual(page,'slicer',title,x,y,w,h,{'Values':[projection(table,column)]},{'data':[{'properties':{'mode':literal('Dropdown')}}]})
        if value is not None:
            encoded=str(value)+'L' if isinstance(value,int) else "'"+value.replace("'","''")+"'"
            item['visual']['objects']['general']=[{'properties':{'filter':{'filter':{'Version':2,'From':[{'Name':'d','Entity':table,'Type':0}],
                  'Where':[{'Condition':{'In':{'Expressions':[{'Column':{'Expression':{'SourceRef':{'Source':'d'}},'Property':column}}],
                  'Values':[[{'Literal':{'Value':encoded}}]]}}}]}}}}]
            write(path,item)

    def header(self,page,title,point=False):
        self.text(page,title,24,16,1232,54,22,True)
        context = 'Volumetric rates: thousand m³/day' if page.name=='Flow' else ('Incident counts by reported date' if page.name=='Incidents' else 'Daily-record completeness and source review')
        self.text(page,'Canada Energy Regulator open data | Independent analysis | '+context,24,71,1232,30,11)
        self.slicer(page,'Calendar year','DimMonth','Year',24,108,180,70,self.year)
        if point:self.slicer(page,'Reporting point — choose one','DimPoint','PointLabel',220,108,1036,70,self.point)
        else:self.slicer(page,'Reported province / territory','DimProvince','Province',220,108,1036,70)

    def cards(self,page,names):
        for i,name in enumerate(names):
            self.visual(page,'card',name,24+i*312,198,296,96,{'Values':[measure(name)]},{
                 'labels':[{'properties':{'fontSize':literal(25),'labelDisplayUnits':literal(1),'color':color('#173A32')}}],
                 'categoryLabels':[{'properties':{'show':literal(False)}}]})

    def build(self):
        flow=self.page('Flow','Point throughput');self.header(flow,'Natural gas · point-level flow',True)
        self.cards(flow,['Mean throughput','Mean capacity','Utilization','Reporting coverage'])
        self.visual(flow,'lineChart','Mean daily throughput and reported capacity',24,314,790,356,
                    {'Category':[projection('DimMonth','Month')],'Y':[measure('Mean throughput'),measure('Mean capacity')]})
        self.visual(flow,'tableEx','Monthly observation coverage',830,314,426,356,{'Values':[projection('DimMonth','Month'),measure('Observed point-days'),measure('Reporting coverage')]})
        self.text(flow,'Select one reporting point. Mean rates use valid daily observations; utilization uses paired throughput and capacity. Rates remain blank for multiple points to prevent double-counting interconnected gas flows. Throughput above reported capacity is a review flag, not a regulatory finding.',24,692,1232,82,11)
        incidents=self.page('Incidents','Incident reporting');self.header(incidents,'Reported incidents · federal pipelines')
        self.cards(incidents,['Incidents','Open incidents','Significant incidents','Located incidents'])
        self.visual(incidents,'clusteredBarChart','Incidents by reported province',24,314,600,356,
                    {'Category':[projection('DimProvince','Province')],'Y':[measure('Incidents')]})
        self.visual(incidents,'clusteredColumnChart','Incidents by reported month',640,314,616,356,
                    {'Category':[projection('DimMonth','Month')],'Y':[measure('Incidents')]})
        self.text(incidents,'Incident dates refer to reporting, which may differ from occurrence. Submitted records can change. Counts have no exposure denominator and are not a safety ranking or a rate per unit of gas. This page has no inferred link between an incident and a throughput key point.',24,692,1232,82,11)
        quality=self.page('Quality','Data quality');self.header(quality,'Source completeness · review controls',True)
        self.cards(quality,['Observed point-days','Missing capacity days','Missing throughput days','Negative throughput days'])
        self.visual(quality,'lineChart','Observed / expected point-days',24,314,600,356,
                    {'Category':[projection('DimMonth','Month')],'Y':[measure('Reporting coverage')]},
                    {'valueAxis':[{'properties':{'start':literal(0),'end':literal(1)}}]})
        self.visual(quality,'tableEx','Monthly quality findings',640,314,616,356,
                    {'Values':[projection('DimMonth','Month'),measure('Missing capacity days'),measure('Missing throughput days'),measure('Above reported capacity')]})
        self.text(quality,'Blank values remain missing. Negative observations are retained for review. Above-capacity flags compare with a published estimate, not actual operating limits. Monthly Brunswick observations are retained in the source archive and excluded from the daily model.',24,692,1232,82,11)
        write(REPORT/'definition/pages/pages.json',{'$schema':SCHEMA+'definition/pagesMetadata/1.0.0/schema.json','pageOrder':self.pages,'activePageName':'Flow'})


def main():
    tables,year,point=load_inputs();build_model(tables)
    write(OUT/(NAME+'.pbip'),{'$schema':'https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json',
       'version':'1.0','artifacts':[{'report':{'path':NAME+'.Report'}}],'settings':{'enableAutoRecovery':True}})
    write(REPORT/'definition.pbir',{'$schema':SCHEMA+'definitionProperties/2.0.0/schema.json','version':'4.0','datasetReference':{'byPath':{'path':'../'+NAME+'.SemanticModel'}}})
    write(REPORT/'definition/version.json',{'$schema':SCHEMA+'definition/versionMetadata/1.0.0/schema.json','version':'2.0.0'})
    write(REPORT/'definition/report.json',{'$schema':SCHEMA+'definition/report/3.0.0/schema.json','themeCollection':{},'settings':{'useStylableVisualContainerHeader':True}})
    ReportBuilder(year,point).build()
    print(f'Built {NAME}: 5 tables, 5 relationships, {len(MEASURES)} measures, 3 pages; default {year} / {point}')


if __name__=='__main__':main()
