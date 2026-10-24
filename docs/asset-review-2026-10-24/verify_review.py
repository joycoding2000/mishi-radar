"""Verify this documentation deliverable and its bounded evidence, without tests or deletion."""
import collections
import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
BASE = "34c8b4c7cf9236f316ebd661c175e12bdcbc26cb"
MAIN = "447c0e22edd414abe9ef1efcdfb6ad266c0bcb32"
DOCS = ["RESEARCH_ASSET_INDEX.md", "RESEARCH_DECISION_QUEUE.md", "ASSET_RETENTION_AND_CLEANUP_PLAN.md"]


def save(name, data):
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def git(*args):
    p = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, encoding="utf-8", timeout=30)
    assert p.returncode == 0, p.stderr
    return p.stdout.strip()


def main():
    result = {}
    with (OUT / "asset-files.csv").open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    totals = json.loads((OUT / "retention-summary.json").read_text(encoding="utf-8"))
    assert len(rows) == totals["total_files"] == 2080
    assert sum(int(r["bytes"]) for r in rows) == totals["total_bytes"] == 165166284
    assert len({(r["scope"], r["path"]) for r in rows}) == len(rows)
    assert len({r["file_id"] for r in rows}) == len(rows)
    for category, expected in totals["categories"].items():
        subset = [r for r in rows if r["category"] == category]
        assert len(subset) == expected["files"]
        assert sum(int(r["bytes"]) for r in subset) == expected["bytes"]
    assert sum(v["files"] for v in totals["categories"].values()) == len(rows)
    assert sum(v["bytes"] for v in totals["categories"].values()) == totals["total_bytes"]
    result["classification_partition"] = "PASS_2080_FILES_165166284_BYTES"
    result["candidate_reclaim"] = totals["candidate_reclaim"]
    assert not totals["candidate_reclaim"]["allocation_errors"]
    assert not totals["candidate_reclaim"]["external_hardlinks"]
    assert git("rev-parse", "main") == MAIN
    assert git("rev-parse", "backup/ssd-migration-2026-10-23") == BASE
    assert git("branch", "--show-current") == "codex/research-asset-review-2026-10-24"
    original_tracked = git("ls-tree", "-r", "--name-only", BASE).splitlines()
    original_changes = git("diff", "--name-only", BASE, "--", *original_tracked)
    assert not original_changes, original_changes
    result["original_tracked_files_unchanged"] = len(original_tracked)
    result["main_and_ssd_backup_unchanged"] = True
    for tip in ["b9a7fba6be9515fc3271eac7a7a97ab65f53e64d", "a72c67901e1147f3e4c198207dea8dd56d59a542", "fc02eff5a68b0bc408bc3a60b5b4f0ad272c6758"]:
        assert git("rev-list", "--count", tip, "--not", MAIN) == "0"
    result["historical_tips_reachable_from_main"] = 3
    broken = []
    checked = 0
    for name in DOCS:
        text = (ROOT / name).read_text(encoding="utf-8")
        for link in re.findall(r"\]\(([^)]+)\)", text):
            target = link.split("#", 1)[0]
            if not target or "://" in target:
                continue
            checked += 1
            if not (ROOT / target).exists():
                broken.append({"document": name, "target": target})
    assert not broken, broken
    result["relative_links_checked"] = checked
    z = json.loads((OUT / "zip-equivalence.json").read_text(encoding="utf-8"))
    assert z["all_members_retained"] and len(z["members"]) == 7
    for member in z["members"]:
        assert hashlib.sha256(Path(member["retained_path"]).read_bytes()).hexdigest() == member["sha256"]
    assert hashlib.sha256(Path(z["archive"]).read_bytes()).hexdigest() == z["zip_sha256"]
    result["zip_equivalence"] = "PASS_7_MEMBERS"
    fx = json.loads((OUT / "fx01-identity-check.json").read_text(encoding="utf-8"))
    assert (fx["paused_files"], fx["changed"], fx["unchanged"], fx["recovery_matches"]) == (32, 12, 20, 19)
    result["fx01_identity"] = "32_FILES_12_CHANGED_20_UNCHANGED_19_RECOVERY_MATCHED"
    source = json.loads((OUT / "joinquant-source-check.json").read_text(encoding="utf-8"))
    assert source["status"] == "NOT_CHECKED_SOURCE_ROOT_UNAVAILABLE"
    result["initial_f_path_snapshot"] = source["status"]
    correction = OUT / "e-drive-source-check.json"
    if correction.exists():
        current = json.loads(correction.read_text(encoding="utf-8"))
        assert current["source_hash_check"]["matching_files"] == 594
        result["source_root_current"] = current["current_source_root"]
        result["source_status_current"] = current["source_hash_check"]["status"]
    g = json.loads((OUT / "git-inventory.json").read_text(encoding="utf-8"))
    targets = {"authorization": "NO", "basis": BASE, "exact_membership": "asset-files.csv category=DELETE_CANDIDATE",
               "directories": [], "individual_files": [], "local_branches": [], "remote_branches": []}
    for index, wt in enumerate(g["worktrees"][1:], 1):
        assert not wt["status"]
        assert wt["unique_to_main"] == 0
        for path in wt["ignored_paths"]:
            assert "__pycache__/" in path and path.endswith(".pyc")
        group = f"worktree-{index}"
        targets["directories"].append({"path": wt["worktree"], "group": group, "head": wt["HEAD"],
                                       "files": totals["groups"][group]["files"], "bytes": totals["groups"][group]["bytes"],
                                       "condition": "Owner authorization, unchanged clean status, no active dependencies; retain main and external evidence"})
        targets["local_branches"].append({"ref": wt["branch"], "tip": wt["HEAD"], "unique_to_main": 0})
    for row in rows:
        if row["category"] == "DELETE_CANDIDATE" and not row["scope"].startswith("worktree-"):
            targets["individual_files"].append({"root": row["root"], "path": row["path"], "group": row["group"], "bytes": int(row["bytes"]), "file_id": row["file_id"]})
    assert len(targets["individual_files"]) == 45
    save("cleanup-targets.json", targets)
    result["worktree_status_qualified_at_census"] = "3_CLEAN; IGNORED_0_16_14_BYTECODE_ONLY"
    provenance = []
    sources = [ROOT / p for p in ["docs/CURRENT_STATE.md", "docs/SSD-MIGRATION-RECOVERY-2026-10-23.md",
               "docs/OD1_OD2_OWNER_ACCEPTANCE_2026-10-23.md", "docs/WP_FX01A_OWNER_ACCEPTANCE_2026-10-23.md",
               "docs/joinquant-full-review/FULL_REVIEW.md"]]
    sources += [Path(r"C:\Users\Administrator\.codex\visualizations\2026\10\23\01a16819-10cb-7d40-8978-4957695ac0be\wp-fx01b-reacceptance\evidence\review-result.json"),
                Path(r"C:\Users\Administrator\.codex\visualizations\2026\10\22\01a16446-92f1-7fb1-b25f-112797c67cc7\final-integration-2026-10-23\final_state.json")]
    for p in sources:
        provenance.append({"path": str(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()})
    save("source-provenance.json", provenance)
    result["acceptance_evidence_readable"] = True
    result["product_tests_rerun"] = False
    result["cleanup_executed"] = False
    result["status"] = "PASS_FOR_OWNER_CLEANUP_REVIEW_WITH_EXPLICIT_REVIEW_GROUPS"
    save("verification.json", result)
    files = [ROOT / p for p in DOCS] + sorted(p for p in OUT.iterdir() if p.is_file() and p.name != "sha256-manifest.json")
    manifest = []
    for p in files:
        is_root_document = p.parent == ROOT
        payload = p.read_text(encoding="utf-8").encode("utf-8") if is_root_document else p.read_bytes()
        manifest.append({"path": p.relative_to(ROOT).as_posix(), "bytes": len(payload),
                         "method": "UTF8_LF_NORMALIZED" if is_root_document else "RAW_BYTES",
                         "sha256": hashlib.sha256(payload).hexdigest()})
    save("sha256-manifest.json", manifest)
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
