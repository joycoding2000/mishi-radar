"""Read-only daily-tail cost measurement and source identities."""
import csv
import hashlib
import json
import struct
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

OUT=Path(__file__).resolve().parent
MISHI=OUT.parents[2]
SUPPLIER=MISHI.parent/'chstockdata'
rows=list(csv.DictReader((OUT/'universe-records.csv').open(encoding='utf-8')))
rec=struct.Struct('<IIIIIfII');snap=20260922
start=time.perf_counter();read_bytes=0;pass_ma=fail_ma=unknown_ma=low=0
checks=[]
for item in rows:
    p=SUPPLIER/'.rh3a2-vipdoc'/item['symbol'][:2]/'lday'/(item['symbol']+'.day')
    with p.open('rb') as f:
        size=p.stat().st_size;f.seek(max(0,size-120*32));b=f.read()
    read_bytes+=len(b);bars=list(rec.iter_unpack(b))
    recent=bars[-20:]
    # Reuse already audited completeness; recompute values independently with stdlib.
    if item['window20_complete']=='True':
        assert len(recent)==20 and recent[-1][0]==snap
        condition=recent[-1][4]*20>sum(r[4] for r in recent)
        assert condition==(item['close_gt_ma20']=='PASS')
        amount=sum(r[5] for r in recent)/20
        assert abs(amount-float(item['amount20_mean_cny']))<0.01
        low+=int(amount<30_000_000)
        pass_ma+=condition;fail_ma+=not condition
        if item['symbol'] in ['sh600519','sz000001','sh600000']:
            checks.append({'symbol':item['symbol'],'close_cny':recent[-1][4]/100,'ma20_cny':sum(r[4] for r in recent)/2000,'amount20_mean_cny':amount,'close_gt_ma20':condition})
    else:unknown_ma+=1
elapsed=time.perf_counter()-start
measurement={'measured_at':datetime.now(timezone(timedelta(hours=8))).isoformat(),'snapshot':'2026-09-22','stock_files':len(rows),
             'tail_records_max_per_file':120,'bytes_read':read_bytes,'elapsed_seconds':elapsed,
             'scope':'Local tail read + MA20/Amount recomputation; includes independent verification using prior completeness flags. Excludes network, security master update, eight-strategy execution, persistence and scheduling.',
             'ma_pass':pass_ma,'ma_fail':fail_ma,'ma_unknown':unknown_ma,'liquidity_fail':low,'examples':checks}
(OUT/'daily-local-cost.json').write_text(json.dumps(measurement,ensure_ascii=False,indent=2),encoding='utf-8')
sources=[MISHI/'docs/2026-10-15-LAUNCH_STRATEGIES.md',MISHI/'docs/MISHI_RADAR_V0_1_SPEC_R3_2_SCOPE_APPROVED_DATA_PENDING_2026-10-16.md',
         MISHI/'docs/MISHI_RADAR_TO_CHSTOCKDATA_DR01_DR06_CONSUMER_REQUEST_2026-10-16.md',MISHI/'outputs/v0.1-owner-review-2026-10-16/competitive-feature-gap.md',
         SUPPLIER/'AGENTS.md',SUPPLIER/'src/chstockdata/a_stock.py',SUPPLIER/'src/chstockdata/vipdoc_history.py',
         Path(r'C:\Users\Administrator\Documents\Codex\2026-10-13\3-a-http-124-221-98\outputs\04-scan-result.txt'),
         Path(r'C:\Users\Administrator\Documents\Codex\2026-10-13\3-a-http-124-221-98\outputs\longitudinal\evidence\2026-10-14-r01\scan-rows.txt')]
manifest=[{'path':str(p),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sources if p.is_file()]
(OUT/'source-identities.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(measurement,ensure_ascii=False))
