"""One-off evidence collection. Not product code; never imports either project."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import subprocess
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

OUT = Path(__file__).resolve().parent
MISHI = OUT.parents[2]
SUPPLIER = MISHI.parent / 'chstockdata'
VIP = SUPPLIER / '.rh3a2-vipdoc'
TZ = timezone(timedelta(hours=8))
END = date(2026, 10, 16)
START = date(2025, 10, 16)
SNAP = 20260922
DTYPE = [('date', '<u4'), ('open', '<u4'), ('high', '<u4'), ('low', '<u4'),
         ('close', '<u4'), ('amount', '<f4'), ('volume', '<u4'), ('reserved', '<u4')]
REC = struct.Struct('<IIIIIfII')


def dump(name, obj):
    (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def git(root, *args):
    return subprocess.check_output(['git', '-c', f'safe.directory={root.as_posix()}', '-C', str(root), *args], text=True, encoding='utf-8', stderr=subprocess.DEVNULL).strip()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def baseline():
    state = {}
    for root in [MISHI, SUPPLIER]:
        tracked = git(root, 'ls-files', '-z').split('\0')
        untracked = git(root, 'ls-files', '--others', '--exclude-standard', '-z').split('\0')
        files = sorted(set(p for p in tracked + untracked if p and not p.startswith('outputs/s08-fund-universe-investigation-2026-10-17/') and (p in tracked or Path(p).suffix in {'.md', '.py', '.json', '.toml', '.txt'})))
        state[str(root)] = {'head': git(root, 'rev-parse', 'HEAD'), 'status': git(root, 'status', '--porcelain=v1', '--untracked-files=normal'),
                            'files': {p: sha(root / p) for p in files if (root / p).is_file()}}
    dump('baseline.json', state)
    print(json.dumps({r: {'head': s['head'], 'hashed_files': len(s['files'])} for r,s in state.items()}))


def calendar():
    # Exchange 2026 closure notice; same ranges inspected in prior DR04 evidence.
    closures = [('2026-01-01','2026-01-03'),('2026-02-15','2026-02-23'),
                ('2026-04-04','2026-04-06'),('2026-05-01','2026-05-05'),
                ('2026-06-19','2026-06-21'),('2026-09-25','2026-09-27'),('2026-10-01','2026-10-07')]
    blocked = set()
    for lo,hi in closures:
        d = date.fromisoformat(lo)
        while d <= date.fromisoformat(hi):
            blocked.add(d); d += timedelta(days=1)
    days=[]; d=START
    while d <= END:
        if d.weekday()<5 and d not in blocked: days.append(d.isoformat())
        d += timedelta(days=1)
    return days


def reuse():
    source=json.loads((OUT/'prior-dr04-evidence.json').read_text(encoding='utf-8'))
    tools={i['id']:i for i in source['tool_evidence']}
    a=tools['exec-431d8ac2-6240-47c9-8d9d-61b1bc0c02c2']['output']['text']
    apages=json.loads(a.split('PAGES ',1)[1].splitlines()[0])
    b=tools['exec-283a3f27-d915-4e03-940d-b9b3a959e655']['output']['text']
    decoder=json.JSONDecoder()
    bpages=decoder.raw_decode(b[b.index('"pages":')+8:])[0]
    cross=json.loads(tools['exec-77ced568-7e40-4f59-8819-bf0cdada4b8d']['output']['text'])
    for capture in cross['captures']:
        (OUT/f"prior-{capture['params']['daima']}-distribution.json").write_text(capture['body'],encoding='utf-8')
        assert hashlib.sha256(capture['body'].encode('utf-8')).hexdigest()==capture['sha256']
    # Recover complete record objects from truncated parsed output; never invent trailing bytes.
    parsed=[]; rest=a.split('RAW_PARSED_RECORDS ',1)[1].lstrip()[1:]
    while rest:
        try: obj,n=decoder.raw_decode(rest)
        except json.JSONDecodeError: break
        parsed.append(obj);rest=rest[n:].lstrip(',\r\n ')
    recent_a=parsed[:20]
    marker=b.index('"raw_responses":')
    first_b=decoder.raw_decode(b[marker+len('"raw_responses":')+1:])[0]
    # raw_decode recovers first complete page object even though later text is truncated.
    recent_b=json.loads(first_b['body'])
    prior={'sh600519': {'pages':apages,'recent':recent_a,'raw_history_recovered_rows':len(parsed)},
           'sz000001': {'pages':bpages,'recent':recent_b,'raw_history_recovered_rows':len(recent_b)}}
    dump('prior-reuse.json',prior)
    dump('calendar.json',{'start':str(START),'end':str(END),'days':calendar(),
                         'source':'https://www.szse.cn/disclosure/notice/general/t20251222_618087.html',
                         'recent_five':calendar()[-5:]})
    print(json.dumps({k: {'pages':len(v['pages']),'recent_rows':len(v['recent']),'history_raw_limitation':True} for k,v in prior.items()}))


def offline():
    import numpy as np
    t0=time.perf_counter()
    index=VIP/'sh/lday/sh000001.day'
    idx=np.frombuffer(index.read_bytes(),dtype=DTYPE)
    sessions=idx['date'][(idx['date']>=20250922)&(idx['date']<=SNAP)].astype('int64')
    assert len(set(sessions))==len(sessions) and np.all(np.diff(sessions)>0)
    needed=idx['date'][idx['date']<=SNAP][-20:]
    files=[p for market in ['sh','sz'] for p in sorted((VIP/market/'lday').glob('*.day'))
           if re.fullmatch(r'(sh60\d{4}|sh688\d{3}|sz(?:00|30)\d{4})',p.stem)]
    summary=[]; hist_before=np.zeros(len(sessions),dtype='int64');hist_after=hist_before.copy()
    hist_false=hist_before.copy();hist_ma_false=hist_before.copy();union_before=set();union_after=set();pages_before=0;pages_after=0
    allfiles={market:list((VIP/market/'lday').glob('*.day')) for market in ['sh','sz','bj']}
    last= {}; boards={}; firsts=[]; hashes=[]
    for p in files:
        content=p.read_bytes();hashes.append({'path':str(p),'sha256':hashlib.sha256(content).hexdigest(),'bytes':len(content)})
        bad_size=len(content)%32; a=np.frombuffer(content[:len(content)-bad_size] if bad_size else content,dtype=DTYPE)
        ds=a['date']; n=len(a); ordered=n>0 and bool(np.all(np.diff(ds.astype('int64'))>0))
        board='STAR' if p.stem.startswith('sh68') else 'CHINEXT' if p.stem.startswith('sz30') else 'SH_MAIN' if p.stem.startswith('sh') else 'SZ_MAIN'
        boards[board]=boards.get(board,0)+1
        end=int(ds[-1]) if n else None; last[str(end)]=last.get(str(end),0)+1
        firsts.append((int(ds[0]) if n else 0,p.stem,n,end))
        close_sum=np.concatenate(([0],np.cumsum(a['close'].astype('int64'))))
        valid_amount=np.isfinite(a['amount'])&(a['amount']>=0)
        amount_sum=np.concatenate(([0.],np.cumsum(np.where(valid_amount,a['amount'],0),dtype='float64')))
        bad_sum=np.concatenate(([0],np.cumsum(~valid_amount)))
        def assess(t,window):
            pos=int(np.searchsorted(ds,t)) if ordered else 0
            exact=ordered and pos<n and int(ds[pos])==int(t)
            complete=exact and pos>=19 and np.array_equal(ds[pos-19:pos+1],window) and bad_size==0
            amount_ok=complete and bad_sum[pos+1]==bad_sum[pos-19]
            low=bool(amount_ok and amount_sum[pos+1]-amount_sum[pos-19]<600_000_000)
            # >=120 actual records is sufficient evidence of at least 120 sessions since listing;
            # fewer rows is UNKNOWN because file start is not an official listing date.
            age=True if exact and pos+1>=120 else None
            px_ok=complete and bool(np.all(a['close'][pos-19:pos+1]>0))
            ma=bool(int(a['close'][pos])*20>int(close_sum[pos+1]-close_sum[pos-19])) if px_ok else None
            return pos,exact,complete,low,age,ma,float((amount_sum[pos+1]-amount_sum[pos-19])/20) if amount_ok else None
        pos,exact,complete,low,age,ma,avg=assess(SNAP,needed)
        base='FAIL' if low else 'UNKNOWN'
        final='FAIL' if low or ma is False else 'UNKNOWN'
        summary.append({'symbol':p.stem,'board':board,'first_date':int(ds[0]) if n else None,'last_date':end,'records':n,'ordered_unique':ordered,'trailing_bytes':bad_size,
                        'snapshot_bar':exact,'window20_complete':complete,'amount20_mean_cny':avg,'liquidity':'FAIL' if low else 'PASS' if avg is not None else 'UNKNOWN',
                        'age120':'PASS' if age else 'UNKNOWN','st_delisting_status':'UNKNOWN','suspension_status':'UNKNOWN',
                        'base':base,'close_gt_ma20':'PASS' if ma is True else 'FAIL' if ma is False else 'UNKNOWN','combined':final})
        has_before=[];has_after=[]
        for k,t in enumerate(sessions):
            ix=int(np.searchsorted(idx['date'],t)); window=idx['date'][max(0,ix-19):ix+1]
            _,_,_,low_h,_,ma_h,_=assess(t,window)
            if low_h: hist_false[k]+=1
            else: hist_before[k]+=1;has_before.append(k)
            if not low_h and ma_h is False: hist_ma_false[k]+=1
            if not low_h and ma_h is not False: hist_after[k]+=1;has_after.append(k)
        for selected,union,page_key in [(has_before,union_before,'before'),(has_after,union_after,'after')]:
            if selected:
                union.add(p.stem)
                # Bounding span includes four prior sessions for five-day funds, not 20 price rows.
                span=selected[-1]-selected[0]+5
                if page_key=='before': pages_before+=math.ceil(span/20)
                else: pages_after+=math.ceil(span/20)
    with (OUT/'universe-records.csv').open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=summary[0]);writer.writeheader();writer.writerows(summary)
    dump('local-input-hashes.json',{'index':{'path':str(index),'sha256':sha(index)},'manifest':{'path':str(VIP/'manifest.json'),'sha256':sha(VIP/'manifest.json')},'stocks':hashes})
    dump('historical-prefilter.json',{'notice':'Local archive envelope only: no historical ST/listing/delisting/suspension master; dates inferred from local Shanghai index, not official PIT certification.',
         'sessions':[int(t) for t in sessions],'days':len(sessions),'stocks':len(files),'base_request_envelope':hist_before.tolist(),'after_ma_request_envelope':hist_after.tolist(),
         'liquidity_confirmed_false':hist_false.tolist(),'additional_ma_confirmed_false':hist_ma_false.tolist(),
         'base_union':sorted(union_before),'after_ma_union':sorted(union_after),'calendar_span_pages20_base':pages_before,'calendar_span_pages20_after':pages_after,
         'span_page_notice':'Hypothesis: 20 calendar-session rows/page and pages can cover a bounding span. Not a measured request plan; compressed missing/suspended rows and positional pages require explicit alignment.'})
    counts=lambda key:dict(__import__('collections').Counter(str(r[key]) for r in summary))
    result={'snapshot':'2026-09-22','scan_elapsed_s':round(time.perf_counter()-t0,3),'manifest_entries':len(json.loads((VIP/'manifest.json').read_text(encoding='utf-8'))['max_bar_date']),
         'all_day_files':{k:len(v) for k,v in allfiles.items()},'stock_file_candidates':len(files),'boards':boards,'last_date_counts':last,
         'snapshot_bars':sum(r['snapshot_bar'] for r in summary),'missing_snapshot_bars':sum(not r['snapshot_bar'] for r in summary),'window20':counts('window20_complete'),
         'base':counts('base'),'liquidity':counts('liquidity'),'age120':counts('age120'),'ma20':counts('close_gt_ma20'),'combined':counts('combined'),
         'retained_before':sum(r['base']!='FAIL' for r in summary),'retained_after':sum(r['combined']!='FAIL' for r in summary),
         'youngest':sorted(firsts,reverse=True)[:15],'history_days':len(sessions),'history_union_base':len(union_before),'history_union_after':len(union_after),
         'history_sum_base':int(sum(hist_before)),'history_sum_after':int(sum(hist_after)),'history_pages_span_base':pages_before,'history_pages_span_after':pages_after,
         'history_after_min':int(min(hist_after)),'history_after_max':int(max(hist_after)),
         'unknown_security_master':True,'current_20261016_whole_market_denominator':'UNKNOWN'}
    dump('universe-summary.json',result);print(json.dumps(result,ensure_ascii=False))


def request_one(session,url,params=None):
    path=OUT/'request-log.jsonl'
    prior=[json.loads(x) for x in path.read_text(encoding='utf-8').splitlines()] if path.exists() else []
    # Reserve one unobservable web tool attempt; hard stop includes robots, redirects disabled.
    if len(prior)+1>=100: raise RuntimeError('Request budget exhausted')
    if prior:
        wait=2.5-(datetime.now(TZ)-datetime.fromisoformat(prior[-1]['completed_at'])).total_seconds()
        if wait>0:time.sleep(wait)
    begun=datetime.now(TZ).isoformat();t=time.perf_counter();idx=len(prior)+1
    meta={'request_no':idx,'url':url,'params':params,'started_at':begun,'attempt':1,'retry':False}
    body=None
    try:
        r=session.get(url,params=params,headers={'User-Agent':'Mozilla/5.0','Referer':'https://vip.stock.finance.sina.com.cn/moneyflow/'},timeout=(5,12),allow_redirects=False)
        body=r.content
        raw=OUT/'raw';raw.mkdir(exist_ok=True)
        name=f"{idx:03d}-{params['daima']+'-p'+str(params['page']) if params else 'robots'}.bin"
        (raw/name).write_bytes(body)
        meta.update(http_status=r.status_code,bytes=len(body),sha256=hashlib.sha256(body).hexdigest(),raw_file=f'raw/{name}',response_date=r.headers.get('Date'),last_modified=r.headers.get('Last-Modified'),content_type=r.headers.get('Content-Type'))
    except Exception as exc:
        meta.update(error_type=type(exc).__name__)
    meta.update(completed_at=datetime.now(TZ).isoformat(),elapsed_s=round(time.perf_counter()-t,6))
    with path.open('a',encoding='utf-8') as f:f.write(json.dumps(meta,ensure_ascii=False)+'\n')
    print(json.dumps({k:v for k,v in meta.items() if k in ['request_no','params','http_status','elapsed_s','error_type']}),flush=True)
    if meta.get('http_status') in [403,429]:raise RuntimeError('Source denied or rate limited; stop all requests')
    if 'error_type' in meta:raise RuntimeError('Network request failed; stop rather than expand collection')
    return meta,body


def probe():
    import requests
    import urllib.robotparser
    samples=json.loads((OUT/'sample-plan.json').read_text(encoding='utf-8'))
    session=requests.Session()
    meta,body=request_one(session,'https://vip.stock.finance.sina.com.cn/robots.txt')
    endpoint='https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/MoneyFlow.ssl_qsfx_zjlrqs'
    if meta['http_status']==200:
        rp=urllib.robotparser.RobotFileParser();rp.parse(body.decode('utf-8',errors='replace').splitlines())
        if not rp.can_fetch('*',endpoint):raise RuntimeError('robots disallows endpoint')
        if (rp.crawl_delay('*') or 0)>2.5:raise RuntimeError('Source requests slower pacing; stop for review')
    elif meta['http_status'] not in [404,410]:raise RuntimeError('robots unavailable; no sample requests')
    for code in samples['symbols']:
        if code in samples['reused']:continue
        meta,body=request_one(session,endpoint,{'page':1,'num':20,'sort':'opendate','asc':0,'daima':code})
        if meta['http_status']!=200:raise RuntimeError('Unexpected source status')
    for code in samples['new_history']:
        for page in range(2,14):
            meta,body=request_one(session,endpoint,{'page':page,'num':20,'sort':'opendate','asc':0,'daima':code})
            if meta['http_status']!=200:raise RuntimeError('Unexpected source status')
    dump('probe-completed.json',{'completed_at':datetime.now(TZ).isoformat(),'sina_local_attempts':len((OUT/'request-log.jsonl').read_text(encoding='utf-8').splitlines()),'web_tool_attempt_reserve':1,'automatic_retries':0})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['baseline','reuse','offline','probe']);a=p.parse_args()
    globals()[a.mode]()
