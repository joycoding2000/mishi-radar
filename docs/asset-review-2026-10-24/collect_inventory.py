"""Read-only, bounded asset census; writes only this review's evidence directory."""
from __future__ import annotations

import collections
import csv
import ctypes
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
BASE = "34c8b4c7cf9236f316ebd661c175e12bdcbc26cb"
MAIN = "447c0e22edd414abe9ef1efcdfb6ad266c0bcb32"
errors = []


def git(*args, cwd=ROOT):
    p = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True,
                       encoding="utf-8", errors="replace", timeout=45)
    if p.returncode:
        raise RuntimeError(f"git {args[0]}: {p.stderr.strip()}")
    return p.stdout


def save(name, data):
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scan(label, root, exclude_git=False):
    rows = []
    if not root.is_dir():
        errors.append({"scope": label, "error": "ROOT_UNAVAILABLE", "path": str(root)})
        return rows
    def onerror(e):
        errors.append({"scope": label, "path": e.filename, "error": str(e)})
    for directory, dirs, files in os.walk(root, followlinks=False, onerror=onerror):
        dirs[:] = sorted(d for d in dirs if not (exclude_git and d == ".git")
                         and not Path(directory, d).is_symlink()
                         and not Path(directory, d).is_junction())
        for name in sorted(files):
            p = Path(directory, name)
            if exclude_git and p == root / ".git":
                continue
            if label == "primary" and (OUT == p.parent or p.name in {
                "RESEARCH_ASSET_INDEX.md", "RESEARCH_DECISION_QUEUE.md", "ASSET_RETENTION_AND_CLEANUP_PLAN.md"}):
                continue
            try:
                st = p.stat(follow_symlinks=False)
                if p.is_symlink():
                    errors.append({"scope": label, "path": str(p), "error": "LINK_NOT_FOLLOWED"})
                    continue
                rows.append({"scope": label, "root": str(root), "path": p.relative_to(root).as_posix(),
                             "bytes": st.st_size, "mtime_utc": dt.datetime.fromtimestamp(st.st_mtime, dt.timezone.utc).isoformat(),
                             "file_id": f"{st.st_dev}:{st.st_ino}", "links": st.st_nlink,
                             "category": "", "group": ""})
            except OSError as e:
                errors.append({"scope": label, "path": str(p), "error": str(e)})
    return rows


def main():
    worktrees = []
    for block in git("worktree", "list", "--porcelain").strip().split("\n\n"):
        item = dict(line.split(" ", 1) if " " in line else (line, True) for line in block.splitlines())
        p = Path(item["worktree"])
        item["exists"] = p.is_dir()
        try:
            item["status"] = git("status", "--porcelain=v1", "--untracked-files=all", cwd=p)
            item["ignored_paths"] = git("ls-files", "--others", "--ignored", "--exclude-standard", cwd=p).splitlines()
            item["unique_to_main"] = int(git("rev-list", "--count", item["HEAD"], "--not", MAIN))
            item["tracked_count"] = len(git("ls-files", cwd=p).splitlines())
        except Exception as e:
            item["error"] = str(e)
        worktrees.append(item)
    refs = []
    for line in git("for-each-ref", "--format=%(refname) %(objectname)", "refs/heads", "refs/remotes", "refs/tags").splitlines():
        ref, oid = line.split()
        refs.append({"ref": ref, "sha": oid, "unique_to_main": int(git("rev-list", "--count", oid, "--not", MAIN)),
                     "unique_to_retained_backup": int(git("rev-list", "--count", oid, "--not", BASE))})
    snapshot = {"observed_at": dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(),
                "main": git("rev-parse", "main").strip(), "baseline": BASE,
                "head": git("rev-parse", "HEAD").strip(), "branch": git("branch", "--show-current").strip(),
                "worktrees": worktrees, "refs": refs, "stash": git("stash", "list"),
                "object_storage": git("count-objects", "-v"),
                "baseline_tree": git("ls-tree", "-r", "-l", BASE),
                "main_backup_diff": git("diff", "--stat", MAIN, BASE),
                "backup_commits": git("log", "--format=%H %s", f"{MAIN}..{BASE}")}
    save("git-inventory.json", snapshot)
    rows = scan("primary", ROOT, True)
    for n, item in enumerate(worktrees[1:], 1):
        rows.extend(scan(f"worktree-{n}", Path(item["worktree"]), True))
    externals = {
        "competitor-images": Path(r"C:\Users\Administrator\Documents\竞品分析"),
        "competitor-3": Path(r"C:\Users\Administrator\Documents\Codex\2026-10-13\3-a-http-124-221-98\outputs"),
        "joinquant-source": Path(r"E:\BaiduNetdiskDownload\2020-2026聚宽600条源码"),
        "intro-source": Path(r"E:\BaiduNetdiskDownload\量化交易入门"),
        "qmt-source": Path(r"E:\BaiduNetdiskDownload\Qmt策略"),
        "qmt-bridge-source": Path(r"E:\BaiduNetdiskDownload\聚宽中转 qmt 自动交易"),
        "course-source": Path(r"E:\BaiduNetdiskDownload\量化交易课程类"),
        "od-integration-evidence": Path(r"C:\Users\Administrator\.codex\visualizations\2026\10\22\01a16446-92f1-7fb1-b25f-112797c67cc7\final-integration-2026-10-23"),
        "od-independent-evidence": Path(r"C:\Users\Administrator\.codex\visualizations\2026\10\22\01a163dd-e5fd-7ad0-919e-edf98f203aca\g01-g07-final-reacceptance"),
        "fx01b-independent-evidence": Path(r"C:\Users\Administrator\.codex\visualizations\2026\10\23\01a16819-10cb-7d40-8978-4957695ac0be\wp-fx01b-reacceptance"),
        "fx01b-first-review": Path(r"C:\Users\Administrator\.codex\visualizations\2026\10\23\01a16819-10cb-7d40-8978-4957695ac0be\wp-fx01b-independent-review"),
    }
    for label, path in externals.items():
        rows.extend(scan(label, path))
    jq = ROOT / "docs/joinquant-full-review"
    manifest = json.loads((jq / "source-manifest.json").read_text(encoding="utf-8"))
    checks = []
    source_available = externals["joinquant-source"].is_dir()
    for f in manifest["files"] if source_available else []:
        p = externals["joinquant-source"] / f["relative_path"]
        try:
            actual = sha(p)
            checks.append({"id": f["id"], "path": f["relative_path"], "expected": f["sha256"], "actual": actual, "match": actual == f["sha256"]})
        except OSError as e:
            checks.append({"id": f["id"], "path": f["relative_path"], "error": str(e), "match": False})
    save("joinquant-source-check.json", {"purpose": "Prove retained originals for cleanup of generated reading inputs; bounded 594 files / 8 MB, no cross-drive duplicate scan", "source_available": source_available, "manifest_file_count": len(manifest["files"]), "status": "CHECKED" if source_available else "NOT_CHECKED_SOURCE_ROOT_UNAVAILABLE", "checks": checks})
    fields = ["scope", "root", "path", "bytes", "mtime_utc", "file_id", "links", "category", "group"]
    with (OUT / "asset-files.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    totals = {}
    for label in sorted({r["scope"] for r in rows}):
        selected = [r for r in rows if r["scope"] == label]
        totals[label] = {"files": len(selected), "bytes": sum(r["bytes"] for r in selected)}
    save("collection-summary.json", {"observed_at": snapshot["observed_at"], "scopes": totals,
                                     "source_matches": sum(c["match"] for c in checks), "source_count": len(checks),
                                     "source_manifest_count": len(manifest["files"]),
                                     "source_status": "CHECKED" if source_available else "NOT_CHECKED_SOURCE_ROOT_UNAVAILABLE", "errors": errors})
    print(json.dumps({"scopes": totals, "source_matches": sum(c["match"] for c in checks), "errors": errors}, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
