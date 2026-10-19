"""Offline DR01 source delta audit; not a consumer implementation.

Reuses the previous official master captures. Never imports supplier code,
requests the network, or manufactures suspension state from traded volume.
"""
from collections import Counter
from datetime import date
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path
import hashlib
import io
import json
import re
import unicodedata

ROOT = Path(__file__).resolve().parent
PREV = ROOT.parents[1] / "dr01-current-2026-10-18" / "evidence"
DAY = "2026-10-16"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def excel(raw):
    import pandas as pd
    return pd.read_excel(io.BytesIO(raw), dtype=str,
                         keep_default_na=False).to_dict(orient="records")


def norm(text):
    return "".join(unicodedata.normalize("NFKC", text).split())


class PublicTablePage(HTMLParser):
    """Read visible cells and links without executing the page's scripts."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.links = []
        self.text = []
        self.date_inputs = []
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "a":
            self.links.append(values.get("href", ""))
        elif tag == "input" and values.get("name") == "d":
            self.date_inputs.append(values.get("value"))
        elif tag == "tr":
            self.row = []
        elif tag == "td":
            self.cell = []

    def handle_data(self, data):
        self.text.append(data)
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag == "td" and self.cell is not None:
            self.row.append(" ".join(" ".join(self.cell).split()))
            self.cell = None
        elif tag == "tr":
            if self.row:
                self.rows.append(self.row)
            self.row = None


def public_page(path):
    page = PublicTablePage()
    page.feed(path.read_text(encoding="utf-8"))
    return page


def run():
    checks = []

    def check(name, passed):
        checks.append({"name": name, "passed": bool(passed)})

    ledger = read(ROOT / "requests.json")
    by_label = {e["label"]: e for e in ledger}

    def payload(label):
        return read(ROOT / by_label[label]["raw_file"])

    for e in ledger:
        raw = (ROOT / e["raw_file"]).read_bytes()
        check("raw_hash:" + e["label"], sha(raw) == e["sha256"])
    check("request_budget", len(ledger) <= 120)
    check("sequential_unique_attempts", len(by_label) == len(ledger))
    check("no_implicit_retries_or_redirects",
          all(e["implicit_retries"] == e["redirects_followed"] == 0 for e in ledger))

    previous = read(PREV / "qualification.json")
    reused = []
    for item in previous["reused_evidence"]:
        if item["file"].endswith(".response.bin"):
            p = PREV / "reused" / item["file"]
            raw = p.read_bytes()
            check("reused_master_hash:" + p.name, sha(raw) == item["sha256"])
            reused.append({"path": str(p), "sha256": item["sha256"]})
    sh_master = [r for n in ("main", "star") for r in
                 read(PREV / "reused" / f"official-SH-{n}.response.bin")["result"]]
    sz_master = excel((PREV / "reused" / "official-SZ-A.response.bin").read_bytes())
    sh_map = {r["A_STOCK_CODE"]: r for r in sh_master}
    sz_map = {r["A股代码"]: r for r in sz_master}
    check("reused_5226_records", len(sh_master) + len(sz_master) == 5226)

    parts = [payload("sse-equity-snapshot-p" + str(p)) for p in (1, 2, 3)]
    all_quotes = [r for p in parts for r in p["list"]]
    quotes = {r[0]: r for r in all_quotes}
    check("SH_dates_are_D", all(str(p["date"]) == DAY.replace("-", "") for p in parts))
    check("SH_same_source_timestamp", len({(p["date"], p["time"]) for p in parts}) == 1)
    check("SH_complete_total", len(all_quotes) == len(quotes) == parts[0]["total"] == 2361)
    check("SH_stable_total", all(p["total"] == 2361 for p in parts))
    check("SH_contiguous_pages", [(p["begin"], p["end"]) for p in parts]
          == [(0, 1000), (1000, 2000), (2000, 2361)])
    check("SH_complete_row_width", all(len(r) == 15 for r in all_quotes))
    check("SH_source_security_types", set(r[13] for r in all_quotes) == {"ASH", "KSH", "BSH"})
    sh_reference = {c: r for c, r in quotes.items() if r[13] in ("ASH", "KSH")}
    check("SH_master_exact_code_set", set(sh_reference) == set(sh_map))
    check("SH_master_exact_names", all(sh_reference[c][1] == r["SEC_NAME_CN"] for c, r in sh_map.items()))
    check("SH_master_product_status_at_D", all(sh_reference[c][14] == r["PRODUCT_STATUS"] for c, r in sh_map.items()))
    sh_risk = [c for c, r in sh_reference.items() if "ST" in r[1]]
    old_risk = {r["INSTRUMENT_ID"] for r in read(PREV / "021-sse-main-risk.bin")["result"]}
    old_risk.update(r["secCode"] for r in read(PREV / "023-sse-star-risk.bin")["result"])
    check("SH_dated_risk_names_match_official_risk_set", set(sh_risk) == old_risk & set(sh_map))
    cdr = read(PREV / "011-sse-689009-overview.bin")["result"][0]
    check("CDR_689009_still_explicitly_excluded", cdr["SEC_TYPE"] == "科创CDR" and "689009" in sh_reference)
    check("future_delisting_not_applied", all(sh_map[c]["DELIST_DATE"] == "20261019"
          and c in sh_reference for c in ("601059", "601198")))

    dates = {}
    for label, d in [("sse-suspension-D15", "2026-10-15"),
                     ("sse-suspension-D-new-p1", DAY),
                     ("sse-suspension-D19", "2026-10-19")]:
        p = payload(label)
        check("SH_suspension_complete:" + d, len(p["result"]) == p["pageHelp"]["total"]
              and p["pageHelp"]["pageCount"] == 1)
        rs = [r for r in p["result"] if r["controlType"] == "TR"]
        dates[d] = rs
        check("SH_suspension_intervals_overlap_query:" + d,
              all(r["startStopDate"] <= d.replace("-", "")
                  and (not r["endStopDate"] or r["endStopDate"] >= d.replace("-", "")) for r in rs))
    suspended_D = {r["productCode"] for r in dates[DAY]}
    quote_paused = {c for c, r in sh_reference.items() if r[10].strip().startswith("P")}
    check("SH_four_suspended_from_independent_official_paths", suspended_D == quote_paused
          == {"600293", "601059", "601198", "688496"})
    check("SH_includes_cross_day_continuous_suspensions",
          all(r["startStopDate"] < "20261016" for r in dates[DAY]))
    check("SH_resumption_example_600825", "600825" in {r["productCode"] for r in dates["2026-10-15"]}
          and "600825" not in suspended_D and sh_reference["600825"][10].strip().startswith("E"))
    check("SH_end_date_inclusive_example", {"601059", "601198"} <= suspended_D
          and not {"601059", "601198"} & {r["productCode"] for r in dates["2026-10-19"]})

    sz_meta = payload("szse-stock-D-metadata")[0]
    sz_quotes = excel((ROOT / by_label["szse-stock-D-export"]["raw_file"]).read_bytes())
    sz_daily = {r["证券代码"]: r for r in sz_quotes}
    check("SZ_complete_export", len(sz_quotes) == len(sz_daily) == sz_meta["metadata"]["recordcount"] == 2945)
    check("SZ_all_rows_dated_D", all(r["交易日期"] == DAY for r in sz_quotes))
    sz_ref = {c: r for c, r in sz_daily.items() if c in sz_map}
    check("SZ_master_all_2906_present", set(sz_ref) == set(sz_map))
    check("SZ_names_match_after_width_space_normalization",
          all(norm(sz_ref[c]["证券简称"]) == norm(r["A股简称"]) for c, r in sz_map.items()))
    zero_codes = sorted(c for c, r in sz_ref.items()
                        if Decimal(r["成交量(万股)"].replace(",", "")) == 0)
    check("SZ_zero_volume_candidates_six", zero_codes == ["000016", "002388", "002717", "002731", "300773", "301314"])
    check("SZ_daily_report_has_no_suspension_fact_field",
          not any("停" in k or "复牌" in k or "状态" in k for k in sz_quotes[0]))
    normal = payload("szse-phase-normal")
    paused = payload("szse-phase-suspended")
    check("SZ_phase_examples_both_D", normal["data"]["marketTime"].startswith(DAY)
          and paused["data"]["marketTime"].startswith(DAY))
    check("SZ_closed_phase_does_not_distinguish_examples",
          normal["data"]["tradingPhaseCode1"] == paused["data"]["tradingPhaseCode1"] == "00"
          and normal["data"]["tradingPhaseCode2"] == paused["data"]["tradingPhaseCode2"] == "00")
    check("SZ_multicode_not_supported_by_probe", payload("szse-phase-multicode-capability")["code"] == "-1")

    em = payload("em-suspension-D")["result"]
    check("EM_transport_response_complete_not_state_certification", len(em["data"]) == em["count"] == 16 and em["pages"] == 1)
    future = [r["SECUCODE"] for r in em["data"] if r["SUSPEND_START_DATE"][:10] > DAY]
    ended = [r["SECUCODE"] for r in em["data"] if r["SUSPEND_END_TIME"] and r["SUSPEND_END_TIME"][:10] < DAY]
    check("EM_D_query_contains_three_future_events", len(future) == 3)
    check("EM_D_query_contains_two_already_ended_events", len(ended) == 2)
    em_overlap = [r for r in em["data"] if r["SUSPEND_START_DATE"][:10] <= DAY
                  and (not r["SUSPEND_END_TIME"] or r["SUSPEND_END_TIME"][:10] >= DAY)]
    em_sz = sorted(r["SECURITY_CODE"] for r in em_overlap if r["SECUCODE"].endswith(".SZ")
                   and r["SECURITY_CODE"] in sz_map)
    check("EM_interval_candidates_agree_with_SZ_zero_rows", em_sz == zero_codes)
    check("predicted_resume_is_not_proven_listing_or_tradability",
          all(r["PREDICT_RESUME_DATE"].startswith("2026-10-19") for r in em["data"]
              if r["SECURITY_CODE"] in ("601059", "601198")))

    z_pages = {kind: public_page(ROOT / by_label[label]["raw_file"])
               for kind, label in (
                   ("S", "zhunshangshi-full-day-suspensions"),
                   ("R", "zhunshangshi-day-resumptions"),
                   ("all", "zhunshangshi-summary"))}
    z_about = public_page(ROOT / by_label["zhunshangshi-about-source-lineage"]["raw_file"])
    z_rows = {}
    for kind, page in z_pages.items():
        records = []
        for row in page.rows:
            check("ZSS_six_columns:" + kind + ":" + row[0], len(row) == 6)
            match = re.search(r"\b(\d{6})\.(SH|SZ|BJ)\b", row[0])
            check("ZSS_explicit_exchange_code:" + kind + ":" + row[0], match is not None)
            records.append({"code": match[1], "exchange": match[2], "status": row[1],
                            "board": row[2], "continuous_trading_days": row[3],
                            "suspension_start": row[4], "intraday_interval": row[5]})
        z_rows[kind] = records
        check("ZSS_explicit_target_day:" + kind, page.date_inputs == [DAY])
        check("ZSS_declared_count_matches_rows:" + kind,
              f"{DAY} · {len(records)} 条" in " ".join(" ".join(page.text).split()))
        check("ZSS_unique_identity:" + kind,
              len({(r["exchange"], r["code"]) for r in records}) == len(records))
    z_sh = sorted(r["code"] for r in z_rows["S"] if r["exchange"] == "SH")
    z_sz = sorted(r["code"] for r in z_rows["S"] if r["exchange"] == "SZ")
    check("ZSS_10_suspended_and_1_resumed", len(z_rows["S"]) == 10 and len(z_rows["R"]) == 1)
    check("ZSS_summary_equals_both_tabs", z_rows["all"] == z_rows["S"] + z_rows["R"])
    check("ZSS_SH_exactly_matches_official_D_suspensions", z_sh == sorted(suspended_D))
    check("ZSS_SZ_matches_EM_intervals_and_official_zero_candidates", z_sz == em_sz == zero_codes)
    check("ZSS_suspensions_are_continuous_not_new_D_events",
          all(r["suspension_start"] < DAY and r["status"] == "停牌" for r in z_rows["S"]))
    check("ZSS_resumption_matches_official_SH_example",
          [(r["exchange"], r["code"], r["status"]) for r in z_rows["R"]]
          == [("SH", "600825", "复牌")])
    check("ZSS_describes_daily_continuing_state",
          "停牌期间每个交易日都会各出一条记录" in "".join(z_pages["all"].text))
    check("ZSS_about_names_multiple_possible_third_party_providers",
          "东方财富、Tushare" in "".join(z_about.text))
    check("ZSS_examined_pages_have_no_upstream_data_link",
          not any(re.search(r"(?:sse|szse|eastmoney|tushare)\.(?:com|cn|pro)", link)
                  for p in [*z_pages.values(), z_about] for link in p.links))

    bulletin_groups = []
    bulletin_rows = []
    bulletin_pages = []
    for e in ledger:
        if e["label"].startswith("sse-bulletins-D-weekend-p"):
            p = read(ROOT / e["raw_file"])
            bulletin_groups.extend(p["result"])
            bulletin_rows.extend(r for group in p["result"] for r in group)
            bulletin_pages.append(p["pageHelp"]["pageNo"])
            check("bulletin_total_stable:" + e["label"], p["pageHelp"]["total"] == 921)
    check("bulletin_all_ten_pages", sorted(bulletin_pages) == list(range(1, 11)))
    check("bulletin_all_921_groups", len(bulletin_groups) == 921)
    check("bulletin_group_ids_unique", len({g[0]["ORG_BULLETIN_ID"] for g in bulletin_groups}) == 921)
    notice_risk = [r for r in bulletin_rows if r["SECURITY_CODE"] == "603838" and "撤销退市风险警示" in r["TITLE"]]
    check("publication_date_not_current_state", notice_risk and notice_risk[0]["SSEDATE"] == "2026-10-17"
          and quotes["603838"][1].startswith("*ST"))
    rejected_pdf = []
    for label in ("sse-resumption-600825-notice", "sse-risk-change-603838-notice"):
        e = by_label[label]
        raw = (ROOT / e["raw_file"]).read_bytes()
        check("reject_HTTP200_HTML_instead_of_PDF:" + label,
              e["status_code"] == 200 and not raw.startswith(b"%PDF-") and b"<html>" in raw[:100])
        rejected_pdf.append({"label": label, "reason": "HTTP_200_JS_CHALLENGE_NOT_PDF_NOT_BYPASSED"})

    baselines = []
    for b in previous["baseline"]:
        actual = sha(Path(b["path"]).read_bytes())
        check("frozen_or_supplier_source_unchanged:" + Path(b["path"]).name, actual == b["sha256"])
        baselines.append(b)
    return {
        "verdict": "BLOCKED", "mode": "QUALIFICATION_DELTA_ONLY_NO_CONSUMER_IMPLEMENTATION",
        "target_completed_day": DAY,
        "contract_responsibility": {"DR01_CURRENT": "Full current identity and listing/risk/suspend-resume facts with date, unknown counts and denominator",
                                    "DR06_NOT_REIMPLEMENTED": "Historical eligibility, rules and execution feasibility; not a new Gate for DR01"},
        "resolved_previous_blockers": ["SSE master and risk-state effective-date bridge via full official dated product snapshot",
                                       "SSE target-day continuous suspension coverage via official overlap-date query"],
        "SH": {"snapshot_timestamp_CST": "2026-10-16T16:29:04+08:00", "all_equities": len(all_quotes),
               "type_counts": dict(Counter(r[13] for r in all_quotes)), "target_records_including_CDR": len(sh_reference),
               "ordinary_A_after_CDR_exclusion": len(sh_reference) - 1,
               "master_missing": sorted(set(sh_map) - set(sh_reference)),
               "risk_A_count": len(sh_risk), "suspended_at_D": sorted(suspended_D),
               "query_date_semantics": "Overlapping suspension interval, including older continuing starts, not announcement publication day",
               "end_date_semantics_observed": "Inclusive final suspension date; end reason must distinguish resumption from delisting",
               "normal_empty_suspension_query_is_not_error": True},
        "SZ": {"source_day": DAY, "all_equities": len(sz_quotes), "A_coverage": len(sz_ref),
               "B_or_other_rows_outside_A_master": len(sz_quotes) - len(sz_ref),
               "master_missing": sorted(set(sz_map) - set(sz_ref)),
               "zero_volume_candidates_not_promoted_to_status": zero_codes,
               "phase_examples": {"000001": {k: normal["data"][k] for k in ("marketTime", "tradingPhaseCode1", "tradingPhaseCode2")},
                                  "000016": {k: paused["data"][k] for k in ("marketTime", "tradingPhaseCode1", "tradingPhaseCode2")}},
               "suspend_resume_status_qualification": "UNKNOWN_FULL_MARKET_STATE_NOT_CERTIFIED"},
        "universe": {"reused_records": 5226, "stock_only_observed": 5225,
                     "target_D_code_sets_both_markets_reconciled": True,
                     "qualified_current_scan_denominator": None},
        "third_party": {"source": "Eastmoney latest suspension-event report", "returned_count": em["count"],
                        "future_events_in_D_query": future, "already_ended_events_in_D_query": ended,
                        "SZ_interval_candidates": em_sz, "lineage_and_target_day_state_completeness": "UNVERIFIED",
                        "upgraded_to_authority": False},
        "zhunshangshi": {
            "URLs": ["https://www.zhunshangshi.com/tfp/?t=S",
                     "https://www.zhunshangshi.com/tfp/?t=R",
                     "https://www.zhunshangshi.com/tfp/",
                     "https://www.zhunshangshi.com/about.html"],
            "explicit_source_day": DAY, "tab_counts": {k: len(v) for k, v in z_rows.items()},
            "suspensions": z_rows["S"], "resumptions": z_rows["R"],
            "SH_confirmed_by_official_dated_query_and_snapshot": True,
            "SZ_agrees_with_other_event_source_and_zero_volume_candidates": True,
            "page_describes_daily_continuous_suspension_not_only_new_events": True,
            "lineage": "About page lists exchanges, Eastmoney and Tushare among general sources; examined pages do not identify the specific upstream, request scope, or completeness receipt for this table.",
            "independence_from_Eastmoney_established": False,
            "displayed_rows_equal_displayed_count": True,
            "SZ_full_universe_state_completeness_established": False,
            "upgraded_to_authority": False,
        },
        "bulletins": {"complete_pages": 10, "complete_groups": len(bulletin_groups),
                      "individual_files_listed": len(bulletin_rows), "rejected_bodies": rejected_pdf,
                      "publication_date_was_not_used_as_effective_date": True},
        "sole_remaining_root_cause": "No qualified complete Shenzhen suspend/resume state for D. The Owner-supplied Zhunshangshi pages confirm a dated list of six Shenzhen suspensions, but table-specific upstream lineage and full-market completion are not established. Agreement with Eastmoney cannot establish independent completeness. Official price/volume and closed phase cannot supply the missing state fact.",
        "published_summary_reference": {"original_URL_supplied_by_Owner": True,
                                        "all_three_pages_received_and_audited": True,
                                        "general_source_about_page_received_and_audited": True},
        "next_feasible_decision": "Obtain a verifiable Shenzhen D full suspend/resume state file, or table-specific upstream and full-fetch completion evidence from the published summary provider. Owner must decide the supplier or availability if this evidence is unavailable. Replacing facts with zero-volume or positive-trading proxies, or relaxing source qualification, requires a consumer qualification Change Request; no such change was approved. No further repeated source searches are proposed.",
        "production_implementation": "NOT_STARTED_SOURCE_GATE_FAILED",
        "consumer_fault_injection_and_regression": "NOT_RUN_NO_IMPLEMENTATION_CANDIDATE",
        "owner_acceptance_candidate": False,
        "request_budget": {"actual_HTTP_attempts": len(ledger), "limit": 120,
                           "HTTP_status_counts": dict(Counter(str(e["status_code"]) for e in ledger)),
                           "implicit_retries": 0, "redirects": 0, "concurrent_source_requests": 0,
                           "stopped_because_budget_exhausted": False},
        "checks": checks, "checks_passed": sum(c["passed"] for c in checks),
        "reused_evidence": reused, "baseline": baselines,
        "scope": "No DR04-P, DR02, DR04-M, DR06, Mishi product code, database, platform or framework changes; no commit/push/release",
    }


if __name__ == "__main__":
    first, second = run(), run()
    a = json.dumps(first, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
    b = json.dumps(second, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
    assert a == b, "Evidence audit was not deterministic"
    assert all(c["passed"] for c in first["checks"]), [c for c in first["checks"] if not c["passed"]]
    (ROOT / "delta-qualification.json").write_bytes(a)
    verification = {"deterministic_runs": 2, "identical_bytes": True, "sha256": sha(a),
                    "evidence_checks_passed": first["checks_passed"], "audit_network_requests": 0,
                    "verdict": first["verdict"], "consumer_tests": "NOT_RUN_GATE_FAILED"}
    (ROOT / "verification.json").write_text(json.dumps(verification, indent=2), encoding="utf-8")
    print(json.dumps(verification))
