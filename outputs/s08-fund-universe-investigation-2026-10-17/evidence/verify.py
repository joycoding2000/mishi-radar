"""Verification of investigation arithmetic, provenance and read-only boundary."""
import csv
import hashlib
import json
import re
import subprocess
import struct
from decimal import Decimal
from datetime import datetime
from pathlib import Path

E=Path(__file__).resolve().parent
O=E.parent
load=lambda name:json.loads((E/name).read_text(encoding='utf-8'))
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
result={'checks':[]}
def check(name,condition):
    if not condition:raise AssertionError(name)
    result['checks'].append(name)

baseline=load('baseline.json');preserved={}
for root,data in baseline.items():
    p=Path(root)
    changed=[name for name,expected in data['files'].items() if not (p/name).is_file() or digest(p/name)!=expected]
    check('preexisting file hashes unchanged: '+root,not changed)
    def git(*args):
        return subprocess.check_output(['git','-c',f'safe.directory={p.as_posix()}','-C',str(p),*args],text=True,encoding='utf-8',stderr=subprocess.DEVNULL).strip()
    check('HEAD unchanged: '+root,git('rev-parse','HEAD')==data['head'])
    check('Git status unchanged: '+root,git('status','--porcelain=v1','--untracked-files=normal')==data['status'])
    preserved[root]={'head':data['head'],'hashed_files':len(data['files']),'changed_files':changed,'status':data['status']}
result['preservation']=preserved

logs=[json.loads(x) for x in (E/'request-log.jsonl').read_text(encoding='utf-8').splitlines()]
q=load('request-summary.json');s=load('universe-summary.json');hist=load('history-coverage.json');h=load('historical-prefilter.json');cal=load('calendar.json')
check('request count including web reserve <=100',len(logs)+1==44 and len(logs)+1<=100)
check('sequential request numbers', [r['request_no'] for r in logs]==list(range(1,44)))
check('source pacing after previous completion >=2.5 seconds',all((datetime.fromisoformat(b['started_at'])-datetime.fromisoformat(a['completed_at'])).total_seconds()>=2.499 for a,b in zip(logs,logs[1:])))
check('no retries',all(not r['retry'] for r in logs))
for r in logs:check('raw response hash: '+r['raw_file'],digest(E/r['raw_file'])==r['sha256'])
check('fixed 18 new symbols,42 fund attempts',len({r['params']['daima'] for r in logs if r.get('params')})==18 and sum(bool(r.get('params')) for r in logs)==42)
check('no duplicate symbol page requests',len({(r['params']['daima'],r['params']['page']) for r in logs if r.get('params')})==42)
for item in hist:
    check('13 pages: '+item['symbol'],item['page_count']==13)
    if not item['reused']:
        check('new annual target exactly243 unique sessions: '+item['symbol'],item['target_rows']==243 and not item['missing_target_dates'] and not item['unexpected_target_dates'] and item['duplicate_dates']==0 and item['strict_newest_first'])
    else:check('prior evidence truncation disclosed: '+item['symbol'],item['independent_current_body_reaudit']=='PARTIAL_TOOL_TEXT_TRUNCATION')

five=list(csv.DictReader((E/'five-day-values.csv').open(encoding='utf-8')))
check('20 symbols x5 slots',len(five)==100 and len({r['symbol'] for r in five})==20)
check('90 numeric,10 missing,missing never zero',sum(r['value_state']=='VALID_NONZERO' for r in five)==90 and sum(r['value_state']=='MISSING_DATE' for r in five)==10 and all(not r['r0_net_raw'] for r in five if r['value_state']=='MISSING_DATE'))
check('recent raw amounts parse finite Decimal',all(Decimal(r['r0_net_raw']).is_finite() for r in five if r['r0_net_raw']))
universe=list(csv.DictReader((E/'universe-records.csv').open(encoding='utf-8')))
check('5556stock classes no CDR',len(universe)==5556 and all(r['symbol']!='sh689009' for r in universe))
check('latest and missing reconcile',s['snapshot_bars']+s['missing_snapshot_bars']==5556)
check('base three-state arithmetic',s['base']['FAIL']==400 and s['base']['UNKNOWN']==5156 and s['retained_before']==5156)
check('combined three-state arithmetic',s['combined']['FAIL']==2518 and s['combined']['UNKNOWN']==3038 and s['retained_after']==3038)
check('UNKNOWN never excluded',all(r['combined']!='FAIL' for r in universe if r['liquidity']=='UNKNOWN' and r['close_gt_ma20']=='UNKNOWN'))
check('safe additional false count2118',sum(r['base']!='FAIL' and r['close_gt_ma20']=='FAIL' for r in universe)==2118)
check('historical daily envelope monotonicity',len(h['sessions'])==243 and all(a<=b for a,b in zip(h['after_ma_request_envelope'],h['base_request_envelope'])))
check('historical totals match',sum(h['after_ma_request_envelope'])==644268 and sum(h['base_request_envelope'])==1304020)
check('historical set inclusion',set(h['after_ma_union'])<=set(h['base_union']) and len(h['after_ma_union'])==5552)
check('current candidate list not reused for all history',len(h['after_ma_union'])>3038 and len(set(h['after_ma_request_envelope']))>1)

reports=[O/'s08-fund-source-qualification.md',O/'s08-universe-and-scan-cost.md']
fields=[]
for report in reports:
    text=report.read_text(encoding='utf-8')
    fields.extend(re.findall(r'^\| ([A-Z][A-Z0-9_]+) \|',text.split('\n## ',1)[0],re.M))
    for _,target in re.findall(r'\[([^\]]+)\]\(([^)]+)\)',text):
        if target.startswith(('http://','https://')):continue
        clean=re.sub(r':\d+$','',target)
        check('local link exists: '+target,(report.parent/clean).exists())
    check('Owner Review present: '+report.name,'Owner Review' in text)
expected={'CURRENT_SHA','DR04_SOURCE_VERDICT','FIVE_DAY_COVERAGE','HISTORICAL_COVERAGE','UNIVERSE_QUALITY','S08_PREFILTER_COUNT','REQUEST_REDUCTION','DAILY_REQUEST_ESTIMATE','HISTORY_BACKFILL_ESTIMATE','DATA_CONTRACT_GAPS','CONFIRMED_DEFECTS_AND_RISKS','OWNER_DECISIONS_REQUIRED'}
check('exactly12 specified status fields across2reports',len(fields)==12 and set(fields)==expected)
result['status_fields']=fields
result['report_hashes']={p.name:digest(p) for p in reports}
result['request_budget_used']=44
result['result']='PASS_INVESTIGATION_ARTIFACT_VERIFICATION_ONLY_NOT_PRODUCT_GATE'
(E/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
manifest=[{'relative_path':str(p.relative_to(O)).replace('\\','/'),'bytes':p.stat().st_size,'sha256':digest(p)} for p in sorted(O.rglob('*')) if p.is_file() and p.name!='sha256-manifest.json']
(E/'sha256-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'result':result['result'],'checks':len(result['checks']),'status_fields':fields,'report_hashes':result['report_hashes'],'request_budget_used':44,'preserved_files':{k:v['hashed_files'] for k,v in preserved.items()}},ensure_ascii=False))
