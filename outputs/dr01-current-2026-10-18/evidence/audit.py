"""Reproducible offline audit of captured DR01 qualification evidence.

This does not implement, publish, or certify a consumer security master.
"""
from collections import Counter
from datetime import date
from pathlib import Path
import hashlib
import io
import json
import re

ROOT = Path(__file__).resolve().parent
PRIOR = Path("C:/Users/Administrator/.codex/visualizations/2026/10/18/"
             "01a14e94-6c4b-7103-9180-acf05cdfa24e/dr01-qualification-temp")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def export_rows(raw):
    import pandas as pd
    return pd.read_excel(io.BytesIO(raw), dtype=str,
                         keep_default_na=False).to_dict(orient="records")


def audit_rows(rows, code_key, fields):
    codes = [r.get(code_key) for r in rows]
    by_code = {}
    for row in rows:
        by_code.setdefault(row.get(code_key), []).append(row)
    return {
        "rows": len(rows), "unique_codes": len(set(codes)),
        "invalid_codes": [c for c in codes if not re.fullmatch(r"[0-9]{6}", str(c))],
        "duplicate_groups": {c: rs for c, rs in by_code.items() if len(rs) > 1},
        "conflict_groups": {c: rs for c, rs in by_code.items()
                            if len({json.dumps(r, sort_keys=True) for r in rs}) > 1},
        "missing": {k: sum(r.get(k) in (None, "", "-") for r in rows) for k in fields},
    }


def run():
    checks = []

    def check(label, passed):
        checks.append({"check": label, "passed": bool(passed)})

    # Preserve only the reused evidence relevant to DR01; leave originals intact.
    reused = ROOT / "reused"
    reused.mkdir(exist_ok=True)
    prior_manifest = read(PRIOR / "sha256-manifest.json")
    manifest_map = {str(Path(e["path"])): e for e in prior_manifest}
    names = ["official-SH-main.response.bin", "official-SH-star.response.bin",
             "official-SZ-A.response.bin", "official-requests.json", "offline-audit.json",
             "sha256-manifest.json"]
    reused_inventory = []
    for name in names:
        raw = (PRIOR / name).read_bytes()
        if name != "sha256-manifest.json":
            check("prior_manifest:" + name,
                  digest(raw) == manifest_map[str(PRIOR / name)]["sha256"])
        (reused / name).write_bytes(raw)
        reused_inventory.append({"file": name, "bytes": len(raw), "sha256": digest(raw)})

    ledger = read(ROOT / "requests.json")
    for event in ledger:
        raw = (ROOT / event["raw_file"]).read_bytes()
        check("new_response_hash:" + event["label"], digest(raw) == event["sha256"])
        check("http_200:" + event["label"], event["status_code"] == 200)
    prior_requests = read(PRIOR / "official-requests.json")
    sh_parts = [read(PRIOR / f"official-SH-{board}.response.bin") for board in ("main", "star")]
    sh = [r for p in sh_parts for r in p["result"]]
    sz = export_rows((PRIOR / "official-SZ-A.response.bin").read_bytes())
    risk_sz = export_rows((ROOT / "015-szse-risk-export.bin").read_bytes())
    for board, payload in zip(("main", "star"), sh_parts):
        check("SSE_total_matches_rows:" + board,
              len(payload["result"]) == payload["pageHelp"]["total"])
        check("SSE_raw_matches_prior_derived:" + board,
              payload["result"] == read(PRIOR / f"official-SH-{board}.rows.json"))
    check("SZSE_raw_matches_prior_derived", sz == read(PRIOR / "official-SZ-A.rows.json"))
    audits = {
        "SH": audit_rows(sh, "A_STOCK_CODE", ["A_STOCK_CODE", "SEC_NAME_CN", "LIST_DATE", "LIST_BOARD"]),
        "SZ": audit_rows(sz, "A股代码", ["A股代码", "A股简称", "A股上市日期", "板块"]),
    }
    for market, a in audits.items():
        check(market + ":valid_unique_complete_identity", not a["invalid_codes"]
              and not a["duplicate_groups"] and not any(a["missing"].values()))

    sz_meta = read(ROOT / "003-szse-list-metadata.bin")[0]["metadata"]
    check("SZSE_independent_total", sz_meta["recordcount"] == len(sz))
    target_date = sz_meta["subname"].strip()
    check("SZSE_explicit_date", bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", target_date)))
    risk_meta = read(ROOT / "014-szse-risk-metadata.bin")[0]["metadata"]
    check("SZSE_risk_export_complete", risk_meta["recordcount"] == len(risk_sz))
    sz_period = read(ROOT / "018-szse-delisting-period-metadata.bin")[1]
    check("SZSE_period_complete", sz_period["metadata"]["recordcount"] == len(sz_period["data"]))
    check("SZSE_status_dates_align", risk_meta["subname"].strip() == target_date
          == sz_period["metadata"]["subname"].strip())
    sz_map = {r["A股代码"]: r for r in sz}
    risk_sz_a = [r for r in risk_sz if r["证券代码"] in sz_map]
    check("SZSE_risk_names_align", all(r["证券简称"] == sz_map[r["证券代码"]]["A股简称"]
                                       for r in risk_sz_a))
    check("SZSE_risk_markers_set_align",
          {r["证券代码"] for r in risk_sz_a} == {r["A股代码"] for r in sz if "ST" in r["A股简称"]})
    check("SZSE_period_member_present", all(r["zqdm"] in sz_map for r in sz_period["data"]))

    sh_map = {r["A_STOCK_CODE"]: r for r in sh}
    sh_risk = []
    sh_status_observations = []
    for num, name, code_key in [(21, "sse-main-risk", "INSTRUMENT_ID"),
                                (22, "sse-main-delisting-period", "INSTRUMENT_ID"),
                                (23, "sse-star-risk", "secCode"),
                                (24, "sse-star-delisting-period", "secCode")]:
        p = read(ROOT / f"{num:03d}-{name}.bin")
        rs = p["result"]
        check("SSE_status_total:" + name, len(rs) == p["pageHelp"]["total"])
        check("SSE_status_unique:" + name, len({r[code_key] for r in rs}) == len(rs))
        own = [r for r in rs if r[code_key] in sh_map]
        if name.endswith("risk"):
            sh_risk.extend(r[code_key] for r in own)
        sh_status_observations.append({"source": name, "rows": len(rs), "A_members": len(own),
                                       "outside_A_codes": [r[code_key] for r in rs if r[code_key] not in sh_map],
                                       "source_effective_date": None,
                                       "queryDate": p.get("queryDate"),
                                       "row_keys": list(rs[0]) if rs else []})
    check("SSE_status_set_matches_name_markers",
          set(sh_risk) == {r["A_STOCK_CODE"] for r in sh if "ST" in r["SEC_NAME_CN"]})
    check("SSE_STATE_CODE7_matches_official_risk_list",
          set(sh_risk) == {r["A_STOCK_CODE"] for r in sh if r["STATE_CODE"] == "7"})

    cdr = read(ROOT / "011-sse-689009-overview.bin")["result"][0]
    check("689009_official_type_CDR", cdr["A_STOCK_CODE"] == "689009" and cdr["SEC_TYPE"] == "科创CDR")
    listed_stock_count_observed = len(sh) - 1 + len(sz)
    future_delist = [{k: r[k] for k in ("A_STOCK_CODE", "SEC_NAME_CN", "DELIST_DATE")}
                     for r in sh if r["DELIST_DATE"] != "-" and r["DELIST_DATE"] > "20261018"]
    check("future_delist_dates_not_yet_effective", len(future_delist) == 2
          and all(r["DELIST_DATE"] == "20261019" for r in future_delist))
    future_listing = [r["A_STOCK_CODE"] for r in sh if r["LIST_DATE"] > "20261018"]
    future_listing += [r["A股代码"] for r in sz if r["A股上市日期"] > "2026-10-18"]
    check("no_future_listings_observed", not future_listing)
    identities = [("SH", r["A_STOCK_CODE"]) for r in sh] + [("SZ", r["A股代码"]) for r in sz]
    check("exchange_code_unique", len(set(identities)) == len(identities))
    stats = read(ROOT / "020-sse-dated-statistic.bin")["result"]
    check("statistics_date_matches_SZ", all(r["TRADE_DATE"] == target_date.replace("-", "") for r in stats))

    baseline = []
    for p in [Path("D:/Dev/Projects/mishi-radar/docs/MISHI_RADAR_V0_1_SPEC_R3_2_SCOPE_APPROVED_DATA_PENDING_2026-10-16.md"),
              Path("D:/Dev/Projects/mishi-radar/docs/MISHI_RADAR_TO_CHSTOCKDATA_DR01_DR06_CONSUMER_REQUEST_2026-10-16.md"),
              *[Path("D:/Dev/Projects/chstockdata/src/chstockdata") / n for n in
                ("a_stock.py", "delisting.py", "suspension.py", "tradability.py")]]:
        sha = digest(p.read_bytes())
        check("baseline_unchanged:" + p.name, sha == manifest_map[str(p)]["sha256"])
        baseline.append({"path": str(p), "sha256": sha})

    result = {
        "audit_kind": "SOURCE_QUALIFICATION_ONLY_NOT_CONSUMER_IMPLEMENTATION",
        "verdict": "BLOCKED", "target_latest_completed_date": target_date,
        "checks": checks, "check_counts": dict(Counter(str(c["passed"]) for c in checks)),
        "universe_audits": audits,
        "observed_list_records": len(sh) + len(sz),
        "observed_stock_only_records_after_CDR_exclusion": listed_stock_count_observed,
        "qualified_current_scan_denominator": None,
        "board_counts": {"SH_MAIN": len(sh_parts[0]["result"]),
                         "SH_STAR_with_CDR": len(sh_parts[1]["result"]),
                         "SZ": dict(Counter(r["板块"] for r in sz))},
        "SZSE_date": target_date, "SZSE_recordcount": sz_meta["recordcount"],
        "risk_observations": {"SH_A": len(sh_risk), "SZ_A": len(risk_sz_a),
                              "SZ_B_excluded": [r["证券代码"] for r in risk_sz if r not in risk_sz_a],
                              "SZ_delisting_period": sz_period["data"],
                              "SH_sources": sh_status_observations},
        "special_type": {"identity": ["SH", cdr["A_STOCK_CODE"]], "official_SEC_TYPE": cdr["SEC_TYPE"],
                         "ordinary_A_scope": "EXCLUDED_CDR", "source_list_STOCK_TYPE8_is_board_not_security_type": True},
        "future_delisting_records_retained": future_delist,
        "future_delisting_applied_early": False,
        "SSE_aggregate_statistics": stats,
        "time_semantics": {"SSE_list_business_date": None, "SSE_status_business_date": None,
                           "SSE_aggregate_date_does_not_date_constituent_lists": True,
                           "HTTP_Date_and_XLSX_creation_are_not_business_effective_time": True,
                           "current_only_suspension_API_does_not_certify_prior_completed_session": True},
        "confirmed_blockers": [
            "SSE listed universe and risk/delisting-period responses lack a validated business effective date; cannot certify they describe the target completed session.",
            "Existing suspension API explicitly rejects historical-date requests and its latest-event snapshot is not certified full-market suspension/resumption state for the target completed session."
        ],
        "minimum_solution": "Obtain a date-stamped full SH/SZ security qualification snapshot (listed/ST/*ST/delisting-period/suspend-resume), or documented effective-date semantics for the existing official sources, then reconcile it to the already captured official code sets; no full mootdx reconciliation gate is required.",
        "request_budget": {"new_public_HTTP_attempts": len(ledger), "preflight_status_CLI_invocations": 1,
                           "preflight_status_account_attempts": 2,
                           "preflight_count_evidence": "firecrawl-cli 1.18.5 dist/commands/status.js calls fetchQueueStatus and fetchCreditUsage once each via Promise.all; neither retries",
                           "conservative_HTTP_TCP_TLS_units": 6 + sum(e["reserved_budget_units"] for e in ledger),
                           "limit": 100, "probe_redirects": 0, "probe_retries": 0,
                           "approval_failure_before_execution_not_a_source_request": True,
                           "prior_round_units_reused_without_new_network": read(PRIOR / "offline-audit.json")["request_budget"]["conservative_budget_units"]},
        "implementation": "NOT_STARTED_SOURCE_GATE_FAILED", "owner_acceptance_candidate": False,
        "baseline": baseline, "reused_evidence": reused_inventory,
    }
    return result


if __name__ == "__main__":
    first = run()
    second = run()
    raw = json.dumps(first, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
    check_raw = json.dumps(second, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
    assert raw == check_raw, "Offline audit is not deterministic"
    assert all(c["passed"] for c in first["checks"]), "Evidence integrity check failed"
    assert first["request_budget"]["conservative_HTTP_TCP_TLS_units"] <= 100
    (ROOT / "qualification.json").write_bytes(raw)
    verification = {"identical_runs": 2, "deterministic": True, "sha256": digest(raw),
                    "integrity_checks_passed": len(first["checks"]), "network_requests": 0,
                    "consumer_gate": first["verdict"]}
    (ROOT / "verification.json").write_text(json.dumps(verification, indent=2), encoding="utf-8")
    print(json.dumps(verification))
