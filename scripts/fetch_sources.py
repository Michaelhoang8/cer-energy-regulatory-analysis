"""Download a candidate snapshot without overwriting the reviewed active sources."""
import argparse
import concurrent.futures
import datetime
import hashlib
import json
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'reports/runs/candidate-source')
    args=parser.parse_args()
    output=args.output.resolve()
    active=(ROOT/'data/source').resolve()
    if output==active or active in output.parents:
        parser.error('Choose a candidate directory outside data/source; promotion requires source review.')
    source=ROOT/'data/source'
    entries=json.loads((source/'initial_manifest.json').read_text(encoding='utf-8'))
    entries+=json.loads((source/'resource_manifest.json').read_text(encoding='utf-8'))['resources']
    entries+=json.loads((source/'geo_manifest.json').read_text(encoding='utf-8'))['resources']
    entries={e['file']:e for e in entries if not e['file'].endswith('.pdf')}
    output.mkdir(parents=True,exist_ok=True)
    def fetch(entry):
        url=entry.get('download_url',entry.get('url'))
        request=urllib.request.Request(url,headers={'User-Agent':'CER-Energy-Portfolio/1.0'})
        with urllib.request.urlopen(request,timeout=180) as response:
            data=response.read()
        path=output/entry['file']
        path.write_bytes(data)
        return {'file':entry['file'],'url':url,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),
                'retrieved_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        records=list(pool.map(fetch,entries.values()))
    (output/'candidate_manifest.json').write_text(json.dumps(records,indent=2),encoding='utf-8',newline='\n')
    print(f'Downloaded {len(records)} candidate files. Profile and review changes before promotion.')

if __name__=='__main__':main()
