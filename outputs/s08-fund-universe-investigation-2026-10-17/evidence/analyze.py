"""Offline analysis of retained investigation evidence only."""
import csv
import json
import hashlib
import statistics
from pathlib import Path
from decimal import Decimal, InvalidOperation
from datetime import datetime
from collections import Counter

OUT=Path(__file__).resolve().parent
load=lambda name:json.loads((OUT/name).read_text(encoding='utf-8'))
def dump(name,obj):
    (OUT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def value_state(row):
    if 'r0_net' not in row:return 'MISSING_FIELD'
    if row['r0_net'] is None or row['r0_net']=='':return 'MISSING_VALUE'
    try:
        v=Decimal(str(row['r0_net']))
        if not v.is_finite():return 'INVALID_VALUE'
    except (InvalidOperation,ValueError):return 'INVALID_VALUE'
    return 'VALID_ZERO' if v==0 else 'VALID_NONZERO'

logs=[json.loads(x) for x in (OUT/'request-log.jsonl').read_text(encoding='utf-8').splitlines()]
prior=load('prior-reuse.json');plan=load('sample-plan.json');cal=load('calendar.json');recent={};captures={};all_values=[]
for log in logs:
    if 'raw_file' in log:
        body=(OUT/log['raw_file']).read_bytes()
        assert hashlib.sha256(body).hexdigest()==log['sha256']
    if not log.get('params'):continue
    code=log['params']['daima'];page=log['params']['page']
    try:rows=json.loads(body)
    except (json.JSONDecodeError,UnicodeDecodeError):rows=None
    captures[(code,page)]={'meta':log,'rows':rows}
    if isinstance(rows,list):all_values.extend([value_state(r) for r in rows if isinstance(r,dict)])
    if page==1:recent[code]=rows
for code,p in prior.items():recent[code]=p['recent']
csvrows=[];sample_summary=[]
for code in plan['symbols']:
    rows=recent.get(code);array_ok=isinstance(rows,list);mapping={r['opendate']:r for r in rows or [] if isinstance(r,dict) and 'opendate' in r}
    latest=max(mapping) if mapping else None;states=Counter();evidence='prior-reuse.json' if code in prior else captures.get((code,1),{}).get('meta',{}).get('raw_file')
    for d in cal['recent_five']:
        row=mapping.get(d)
        state=value_state(row) if row is not None else 'MISSING_DATE' if array_ok else 'SOURCE_FAILURE'
        states[state]+=1
        csvrows.append({'symbol':code,'business_date':d,'r0_net_raw':row.get('r0_net') if row else None,'unit':'CNY','value_state':state,
                        'latest_business_date':latest,'freshness':'STALE' if latest and latest<cal['recent_five'][-1] else 'CURRENT_DATE_PRESENT' if latest else 'UNKNOWN',
                        'evidence':evidence,'reused':code in prior})
    sample_summary.append({'symbol':code,'latest':latest,'states':dict(states),'evidence':evidence,'reused':code in prior})
with (OUT/'five-day-values.csv').open('w',encoding='utf-8',newline='') as f:
    w=csv.DictWriter(f,fieldnames=csvrows[0]);w.writeheader();w.writerows(csvrows)
hist=[]
for code in list(plan['reused'])+list(plan['new_history']):
    if code in prior:
        pages=prior[code]['pages'];rows=prior[code]['recent']
        hist.append({'symbol':code,'reused':True,'pages':pages,'page_count':len(pages),'reported_rows':sum(p['rows'] for p in pages),
                     'reported_target_sessions':len(cal['days']),'independent_current_body_reaudit':'PARTIAL_TOOL_TEXT_TRUNCATION',
                     'retained_recent_rows':len(rows),'reported_target_missing':0,'reported_duplicate_dates':0,'reported_invalid':0,'reported_zeros':0})
        continue
    pages=[];rows=[]
    for p in range(1,14):
        capture=captures.get((code,p))
        if not capture:continue
        data=capture['rows'];m=capture['meta']
        if isinstance(data,list):rows.extend(data)
        pages.append({'page':p,'rows':len(data) if isinstance(data,list) else None,'first':data[0].get('opendate') if data else None,'last':data[-1].get('opendate') if data else None,
                      'sha256':m['sha256'],'raw_file':m['raw_file'],'elapsed_s':m['elapsed_s'],'started_at':m['started_at'],'completed_at':m['completed_at']})
    dates=[r['opendate'] for r in rows if isinstance(r,dict) and 'opendate' in r];selected=[r for r in rows if r.get('opendate') in cal['days']]
    hist.append({'symbol':code,'reused':False,'pages':pages,'page_count':len(pages),'returned_rows':len(rows),'first':min(dates) if dates else None,'last':max(dates) if dates else None,
                 'target_rows':len(selected),'missing_target_dates':sorted(set(cal['days'])-set(dates)),'unexpected_target_dates':sorted(d for d in dates if cal['start']<=d<=cal['end'] and d not in cal['days']),
                 'duplicate_dates':len(dates)-len(set(dates)),'strict_newest_first':all(a>b for a,b in zip(dates,dates[1:])),
                 'value_states':dict(Counter(value_state(r) for r in rows))})
fundlogs=[l for l in logs if l.get('params')]
times=[l['elapsed_s'] for l in fundlogs]
elapsed=(datetime.fromisoformat(logs[-1]['completed_at'])-datetime.fromisoformat(logs[0]['started_at'])).total_seconds()
stats={'new_local_sina_attempts':len(logs),'new_fund_attempts':len(fundlogs),'robots_requests':len(logs)-len(fundlogs),'unobservable_web_robots_attempt_reserve':1,
       'conservative_sina_budget_used':len(logs)+1,'limit':100,'fund_http_statuses':dict(Counter(str(l.get('http_status')) for l in fundlogs)),
       'source_failures':sum(l.get('http_status')!=200 for l in fundlogs),'network_exception_count':sum('error_type' in l for l in logs),'retry_count':sum(l['retry'] for l in logs),
       'http200_nonarray_count':sum(not isinstance(c['rows'],list) for c in captures.values()),'empty_array_count':sum(c['rows']==[] for c in captures.values()),
       'elapsed_wall_seconds_including_pacing':elapsed,'fund_network_elapsed_sum':sum(times),'fund_network_min':min(times),'fund_network_median':statistics.median(times),
       'fund_network_mean':statistics.mean(times),'fund_network_max':max(times),'observed_mean_cycle_seconds_assumption':statistics.mean(times)+2.5,
       'recent_slot_states':dict(Counter(r['value_state'] for r in csvrows)),'recent_complete_symbols':sum(sum(s['states'].get(k,0) for k in ['VALID_ZERO','VALID_NONZERO'])==5 for s in sample_summary),
       'recent_expected_symbols':20,'freshness_counts':dict(Counter('CURRENT_DATE_PRESENT' if s['latest']==cal['recent_five'][-1] else 'STALE' if s['latest'] else 'UNKNOWN' for s in sample_summary)),
       'all_new_fund_returned_value_states':dict(Counter(all_values))}
dump('request-summary.json',stats);dump('sample-summary.json',sample_summary);dump('history-coverage.json',hist)
print(json.dumps(stats,ensure_ascii=False))
print(json.dumps([{'symbol':s['symbol'],'latest':s['latest'],'states':s['states']} for s in sample_summary],ensure_ascii=False))
print(json.dumps([{k:v for k,v in h.items() if k not in ['pages']} for h in hist],ensure_ascii=False))
