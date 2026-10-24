"""Qualify groups from the bounded census without changing source assets."""
import collections
import csv
import ctypes
from ctypes import wintypes
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]


def save(name, data):
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    with (OUT / "asset-files.csv").open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    zip_path = Path(r"C:\Users\Administrator\Documents\竞品分析\竞品4量化交易选股系统源码58.65.zip")
    members = []
    with zipfile.ZipFile(zip_path) as z:
        for entry in z.infolist():
            if entry.is_dir():
                continue
            raw = z.read(entry)
            name = entry.filename
            if not entry.flag_bits & 0x800:
                name = name.encode("cp437").decode("gbk")
            parts = Path(name.replace("\\", "/")).parts
            p = zip_path.parent.joinpath(*parts)
            equal = p.is_file() and hashlib.sha256(raw).digest() == hashlib.sha256(p.read_bytes()).digest()
            members.append({"member": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                            "retained_path": str(p), "equal": equal})
    zip_equal = bool(members) and all(x["equal"] for x in members)
    save("zip-equivalence.json", {"archive": str(zip_path), "all_members_retained": zip_equal,
                                  "zip_sha256": hashlib.sha256(zip_path.read_bytes()).hexdigest(), "members": members})
    historical_docs = {
        "2026-10-15-BACKTEST_CAPABILITIES.md", "2026-10-15-LAUNCH_STRATEGIES.md",
        "2026-10-15-PRODUCT_DIRECTION.md", "2026-10-15-V0_1_SCOPE_DISCUSSION.md", "PRODUCT_HANDOFF.md",
        "MISHI_RADAR_V0_1_PRODUCT_SPEC_R3_OWNER_REVIEW_2026-10-16.md", "MISHI_RADAR_V0_1_SPEC_OWNER_REVIEW_R2.md",
    }
    jq_keep = {"README.md", "FULL_REVIEW.md", "READING_STATUS.md", "file-index.csv", "all-reviews.jsonl",
               "source-manifest.json", "coverage-audit.json", "source-integrity.json", "reading-input-integrity.json", "inventory-summary.json"}
    for row in rows:
        scope, path = row["scope"], row["path"]
        parts = path.split("/")
        if scope.startswith("worktree-"):
            category, group = "DELETE_CANDIDATE", scope
        elif scope == "primary":
            if "__pycache__" in parts and path.endswith(".pyc"):
                category, group = "DELETE_CANDIDATE", "primary-python-bytecode"
            elif len(parts) > 2 and parts[:2] == ["docs", "joinquant-full-review"]:
                if len(parts) > 3:
                    category, group = "REVIEW", "joinquant-reading-inputs"
                elif parts[-1] in jq_keep:
                    category, group = "KEEP", "joinquant-final-knowledge"
                else:
                    category, group = "ARCHIVE", "joinquant-stage-records"
            elif len(parts) == 2 and parts[0] == "docs" and parts[1] in historical_docs:
                category, group = "ARCHIVE", "superseded-product-proposals"
            elif path.startswith("outputs/wp-fx01-fixture-vertical-"):
                category, group = "REVIEW", "paused-fx01-evidence"
            elif path.startswith("outputs/wp-fx01b-recovery-"):
                category, group = "KEEP", "fx01b-recovery-for-owner-review"
            elif path.startswith("outputs/wp-fx01b-fixture-"):
                category, group = "KEEP", "fx01b-current-evidence"
            elif path.startswith("outputs/v0.1-owner-review-"):
                category, group = "ARCHIVE", "historical-consumer-review"
            elif path.startswith("outputs/dr04-minimum-consumer-contract-"):
                category, group = "KEEP", "dr04-m-decision-design"
            elif path.startswith("outputs/"):
                category, group = "KEEP", parts[1]
            else:
                category, group = "KEEP", "active-code-contracts-decisions"
        elif scope == "competitor-images":
            if path.endswith(".zip"):
                category, group = ("DELETE_CANDIDATE" if zip_equal else "REVIEW"), "competitor-4-duplicate-container"
            else:
                category, group = "KEEP", "competitor-original-images"
        elif scope == "competitor-3":
            category, group = "ARCHIVE", "competitor-3-source-batch"
        elif scope in {"od-integration-evidence", "od-independent-evidence"}:
            category, group = "ARCHIVE", scope
        elif scope in {"fx01b-independent-evidence", "fx01b-first-review"}:
            category, group = "KEEP", scope
        else:
            category, group = "REVIEW", scope
        row["category"], row["group"] = category, group
    with (OUT / "asset-files.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    # Query allocation size rather than confusing logical or compressed bytes with clusters.
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    class StandardInfo(ctypes.Structure):
        _fields_ = [("allocation", ctypes.c_longlong), ("end_of_file", ctypes.c_longlong),
                    ("number_of_links", wintypes.DWORD), ("delete_pending", ctypes.c_ubyte), ("directory", ctypes.c_ubyte)]
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.GetFileInformationByHandleEx.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.GetFileInformationByHandleEx.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    by_id = collections.defaultdict(list)
    for row in rows:
        by_id[row["file_id"]].append(row)
    groups = {}
    for group in sorted({r["group"] for r in rows}):
        selected = [r for r in rows if r["group"] == group]
        groups[group] = {"category": selected[0]["category"], "files": len(selected), "bytes": sum(int(r["bytes"]) for r in selected)}
    categories = {}
    for category in ["KEEP", "ARCHIVE", "DELETE_CANDIDATE", "REVIEW"]:
        selected = [r for r in rows if r["category"] == category]
        categories[category] = {"files": len(selected), "bytes": sum(int(r["bytes"]) for r in selected)}
    candidates = [r for r in rows if r["category"] == "DELETE_CANDIDATE"]
    reclaim = {"logical_bytes": 0, "allocated_bytes": 0, "files": len(candidates), "allocation_errors": [], "external_hardlinks": []}
    for fid, links in by_id.items():
        if not all(r["category"] == "DELETE_CANDIDATE" for r in links):
            continue
        row = links[0]
        if int(row["links"]) > len(links):
            reclaim["external_hardlinks"].append(fid)
            continue
        p = str(Path(row["root"], row["path"]))
        handle = kernel.CreateFileW(p, 0, 7, None, 3, 0, None)
        info = StandardInfo()
        ok = handle != ctypes.c_void_p(-1).value and kernel.GetFileInformationByHandleEx(handle, 1, ctypes.byref(info), ctypes.sizeof(info))
        error = ctypes.get_last_error()
        if handle != ctypes.c_void_p(-1).value:
            kernel.CloseHandle(handle)
        if not ok:
            reclaim["allocation_errors"].append({"scope": row["scope"], "path": row["path"], "error": error})
            continue
        reclaim["logical_bytes"] += int(row["bytes"])
        reclaim["allocated_bytes"] += info.allocation
    summary = {"groups": groups, "categories": categories,
               "total_files": len(rows), "total_bytes": sum(int(r["bytes"]) for r in rows),
               "unique_file_ids": len(by_id), "hardlink_multi_name_ids": sum(len(x) > 1 for x in by_id.values()),
               "candidate_reclaim": reclaim,
               "historical_missing_f_drive": {"files": 877, "bytes": 4282580626, "status": "2026-10-23_RECORDED_ONLY_NOT_RECOUNTED"}}
    save("retention-summary.json", summary)
    print(json.dumps(summary, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
