"""Bounded, sequential public-source qualification; no production code.

Each HTTPS attempt reserves three budget units (HTTP, TCP, TLS). Redirects,
adapter retries and environment proxy discovery are disabled. Raw responses
and a flushed request ledger survive errors. No imported supplier code runs.
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


def save(value):
    LEDGER.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    specs = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    events = json.loads(LEDGER.read_text(encoding="utf-8")) if LEDGER.exists() else []
    # One firecrawl --status command made two account fetch attempts. The
    # installed status.js was inspected offline; reserve 3 units for each.
    prior_units = 6
    with requests.Session() as session:
        session.trust_env = False
        session.mount("https://", requests.adapters.HTTPAdapter(max_retries=0))
        session.mount("http://", requests.adapters.HTTPAdapter(max_retries=0))
        session.headers.update({"User-Agent": "Mozilla/5.0"})
        for spec in specs:
            if any(e["label"] == spec["label"] for e in events):
                raise ValueError("Label already attempted; no implicit retry")
            if prior_units + 3 * (len(events) + 1) > 100:
                raise ValueError("100-unit network budget exhausted")
            event = {"id": len(events) + 1, "label": spec["label"],
                     "url": spec["url"], "params": spec.get("params", {}),
                     "started_at": now(), "reserved_budget_units": 3,
                     "retries": 0, "redirects_followed": 0}
            events.append(event)
            save(events)
            try:
                response = session.get(spec["url"], params=spec.get("params"),
                                       headers=spec.get("headers"), timeout=(8, 20),
                                       allow_redirects=False)
                raw = response.content
                name = f"{event['id']:03d}-{spec['label']}.bin"
                (ROOT / name).write_bytes(raw)
                event.update(status_code=response.status_code, raw_file=name,
                             bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                             headers={k: response.headers[k] for k in
                                      ("Date", "Last-Modified", "Content-Type", "Content-Length")
                                      if k in response.headers})
                event["status"] = "RECEIVED" if response.status_code == 200 else "HTTP_FAILURE"
            except Exception as exc:
                event.update(status="REQUEST_FAILED", exception_type=type(exc).__name__)
            event["completed_at"] = now()
            save(events)
            print(json.dumps(event, ensure_ascii=True), flush=True)
            if event.get("status_code") in (403, 429):
                break
            time.sleep(0.5)
    print(json.dumps({"attempts": len(events), "conservative_budget_used":
                      prior_units + 3 * len(events), "limit": 100}), flush=True)


if __name__ == "__main__":
    main()
