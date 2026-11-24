"""Verify that captured report/workbook evidence belongs to the current outputs."""
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def check(path,expected):
    if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
        raise ValueError(f'Stale or changed evidence: {path.relative_to(ROOT)}')

if __name__=='__main__':
    capture=json.loads((ROOT/'docs/recordings/capture_manifest.json').read_text(encoding='utf-8'))
    check(ROOT/'reports/dashboard.html',capture['report_sha256'])
    check(ROOT/'docs/recordings'/capture['video']['file'],capture['video']['sha256'])
    for item in capture['screenshots']:
        check(ROOT/'docs/screenshots'/item['file'],item['sha256'])
    assert not capture['page_errors']
    assert all(r['matches'] and r['visible'] for r in capture['metric_checks'])
    native=json.loads((ROOT/'docs/screenshots/native_manifest.json').read_text(encoding='utf-8'))
    for item in native['screenshots']:
        check(ROOT/'docs/screenshots'/item['file'],item['sha256'])
    for file,sha in native['project_sha256'].items():
        check(ROOT/file,sha)
    excel=json.loads((ROOT/'reports/excel_validation.json').read_text(encoding='utf-8'))
    check(ROOT/excel['input_file'],excel['input_sha256'])
    check(ROOT/excel['workbook'],excel['workbook_sha256'])
    for file,sha in excel['render_sha256'].items():
        check(ROOT/file,sha)
    assert all(item['passed'] for item in excel['formula_checks'])
    print('Browser, native Power BI and Excel evidence hashes verified')
