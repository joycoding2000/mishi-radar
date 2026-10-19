"""Sequential qualification requests, capped at 120 actual HTTP attempts.

No hidden retries, redirects, environment proxy discovery, or parallel source
requests. A unique label cannot be retried implicitly. All attempts are logged
before transport; responses are retained verbatim. This is investigation code.
"""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import sys
import time

import requests

ROOT = Path(__file__).resolve().parent
LEDGER = ROOT / "requests.json"


def now():
    return datetime.now(timezone.utc).isoformat()


def save(events):
    LEDGER.write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    specs = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    events = json.loads(LEDGER.read_text(encoding="utf-8")) if LEDGER.exists() else []
    with requests.Session() as session:
        session.trust_env = False
        for scheme in ("https://", "http://"):
            session.mount(scheme, requests.adapters.HTTPAdapter(max_retries=0))
        session.headers.update({"User-Agent": "Mozilla/5.0"})
        for spec in specs:
            if any(e["label"] == spec["label"] for e in events):
                raise ValueError("Duplicate label: no implicit retry")
            if len(events) >= 120:
                raise ValueError("Actual HTTP attempt budget exhausted")
            event = {"id": len(events) + 1, "label": spec["label"], "url": spec["url"],
                     "params": spec.get("params", {}), "started_at": now(),
                     "implicit_retries": 0, "redirects_followed": 0}
            events.append(event)
            save(events)
            try:
                response = session.get(spec["url"], params=spec.get("params"),
                                       headers=spec.get("headers"), timeout=(8, 25),
                                       allow_redirects=False)
                raw = response.content
                filename = f"{event['id']:03d}-{spec['label']}.bin"
                (ROOT / filename).write_bytes(raw)
                event.update(status_code=response.status_code, raw_file=filename,
                             bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                             headers={k: response.headers[k] for k in
                                      ("Date", "Last-Modified", "Content-Type", "Content-Length")
                                      if k in response.headers},
                             status="RECEIVED" if response.status_code == 200 else "HTTP_FAILURE")
            except Exception as exc:
                event.update(status="REQUEST_FAILED", exception_type=type(exc).__name__)
            event["completed_at"] = now()
            save(events)
            print(json.dumps(event, ensure_ascii=True), flush=True)
            if event.get("status_code") in (403, 429):
                break
            time.sleep(0.6)
    print(json.dumps({"actual_HTTP_attempts": len(events), "limit": 120}), flush=True)


if __name__ == "__main__":
    main()
