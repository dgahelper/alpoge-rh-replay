#!/usr/bin/env python3
"""Generate dashboard/data.json from the replay tracker's published files.

Standard library only, like the rest of the repo tooling. Run from anywhere:

    python3 dashboard/generate_data.py

Reads tracker/summary.json, tracker/completed.tsv, tracker/packets.tsv,
tracker/modules.jsonl.gz and evidence/volunteers/*.json from the repository
root, applies the completed.tsv overlay to module states exactly as
tracker/tasks.py load() does, and writes aggregated data (never raw module
rows) to dashboard/data.json next to this script.

The "history" series is built from this repository's own git history:
tracker/completed.tsv carries no timestamps, so for each commit that
touched the file we record the commit time and the file's data-row count
at that commit. When git history is unavailable (not a checkout, shallow
clone, git missing) the series is simply empty and generation continues.
"""
import csv
import datetime
import gzip
import json
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "data.json"

# README "Completed parts" labels for the evidence values used in
# tracker/completed.tsv. Unknown values fall back to their raw name so new
# categories are labelled faithfully rather than silently dropped.
EVIDENCE_LABELS = {
    "build-observed": "Successful source build observed",
    "pilot-reused": "Pilot proof object reused",
    "pilot-witness-checked": "Pilot downstream module kernel-checked",
    "wave-reused": "Distributed proof object reused",
    "volunteer-build-reviewed": "Volunteer build evidence reviewed",
}

DEPTH_BANDS = [
    (0, 0, "0"), (1, 1, "1"), (2, 2, "2"), (3, 3, "3"), (4, 4, "4"),
    (5, 5, "5"), (6, 10, "6-10"), (11, 20, "11-20"), (21, 40, "21-40"),
    (41, 80, "41-80"), (81, None, "81+"),
]


def band_for(depth):
    for lo, hi, label in DEPTH_BANDS:
        if depth >= lo and (hi is None or depth <= hi):
            return label
    raise ValueError(depth)


def history_series():
    """Ledger size over time, from the git history of tracker/completed.tsv.

    One point per commit that touched the file: the committer date and the
    file's data-row count at that commit, downsampled to at most ~240
    points (first and last always kept). Counts are reported raw, exactly
    as the file stood at each commit. Returns [] if git history is
    unavailable for any reason -- this series is optional and must never
    fail the whole generation.
    """
    try:
        def git(*args):
            return subprocess.run(
                ["git", "-C", str(ROOT), *args],
                capture_output=True, text=True, timeout=120, check=True,
            ).stdout

        if git("rev-parse", "--is-shallow-repository").strip() == "true":
            return []
        log = git("log", "--reverse", "--format=%H%x09%cI", "--",
                  "tracker/completed.tsv")
        commits = [line.split("\t") for line in log.splitlines()
                   if line.strip()]
        if not commits:
            return []
        if len(commits) > 240:
            keep = sorted({round(i * (len(commits) - 1) / 239)
                           for i in range(240)})
            commits = [commits[i] for i in keep]
        points = []
        for sha, when in commits:
            blob = git("show", f"{sha}:tracker/completed.tsv")
            rows = max(0, len(blob.splitlines()) - 1)  # minus the header
            points.append({"t": when, "with_evidence": rows})
        return points
    except Exception:
        return []


def main():
    tracker = ROOT / "tracker"
    summary = json.loads((tracker / "summary.json").read_text())

    with (tracker / "completed.tsv").open(newline="") as f:
        completed_rows = list(csv.DictReader(f, delimiter="\t"))
    done = {r["id"]: r["evidence"] for r in completed_rows}

    with gzip.open(tracker / "modules.jsonl.gz", "rt") as f:
        modules = [json.loads(line) for line in f]
    for row in modules:
        if row["id"] in done:
            row["state"] = done[row["id"]]

    total = len(modules)
    with_evidence = sum(1 for row in modules if row["id"] in done)
    evidence_counts = Counter(r["evidence"] for r in completed_rows)
    evidence_categories = [
        {
            "value": value,
            "label": EVIDENCE_LABELS.get(value, value),
            "count": evidence_counts[value],
        }
        for value in sorted(evidence_counts, key=lambda v: -evidence_counts[v])
    ]

    state_counts = Counter(r["state"] for r in modules)

    band_totals = Counter()
    band_done = Counter()
    for row in modules:
        label = band_for(row["depth"])
        band_totals[label] += 1
        if row["id"] in done:
            band_done[label] += 1
    depth_bands = [
        {
            "band": label,
            "total": band_totals[label],
            "done": band_done[label],
            "percent": round(100.0 * band_done[label] / band_totals[label], 2)
            if band_totals[label] else 0.0,
        }
        for _, _, label in DEPTH_BANDS
    ]

    done_per_packet = Counter(r["packet"] for r in completed_rows)
    packets_total = packets_full = packets_partial = packets_untouched = 0
    with (tracker / "packets.tsv").open(newline="") as f:
        for prow in csv.DictReader(f, delimiter="\t"):
            packets_total += 1
            n_done = done_per_packet.get(prow["packet"], 0)
            if n_done >= int(prow["modules"]):
                packets_full += 1
            elif n_done > 0:
                packets_partial += 1
            else:
                packets_untouched += 1
    packet_stats = {
        "total": packets_total,
        "fully_done": packets_full,
        "partially_done": packets_partial,
        "untouched": packets_untouched,
    }

    volunteers = {}
    vol_dir = ROOT / "evidence" / "volunteers"
    for path in sorted(vol_dir.glob("*.json")):
        receipt = json.loads(path.read_text())
        entry = volunteers.setdefault(
            receipt["contributor"],
            {"contributor": receipt["contributor"], "modules": 0,
             "packets": set(), "receipts": 0},
        )
        entry["modules"] += len(receipt["tasks"])
        # The leaderboard's Packets column counts packets, but a
        # single-module receipt stores that module's M... ID in its
        # "packet" field, not a P... packet ID -- count only packets.
        if receipt["packet"].startswith("P"):
            entry["packets"].add(receipt["packet"])
        entry["receipts"] += 1
    leaderboard = [
        {"contributor": e["contributor"], "modules": e["modules"],
         "packets": len(e["packets"]), "receipts": e["receipts"]}
        for e in sorted(volunteers.values(),
                        key=lambda e: (-e["modules"], e["contributor"]))
    ]

    # completed.tsv is sorted by module ID and has no timestamps, so this
    # "recent" list is the last ledger rows (highest module IDs), NOT the
    # most recent completions in time. The dashboard labels it accordingly.
    recent = [
        {"id": r["id"], "packet": r["packet"], "module": r["module"],
         "evidence": r["evidence"],
         "evidence_label": EVIDENCE_LABELS.get(r["evidence"], r["evidence"])}
        for r in completed_rows[-25:][::-1]
    ]

    data = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc)
        .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "snapshot": summary.get("snapshot"),
        "scope": summary.get("scope"),
        "lean": summary.get("lean"),
        "mathlib_commit": summary.get("mathlib_commit"),
        "totals": {
            "modules": total,
            "packets": packets_total,
            "with_evidence": with_evidence,
            "remaining": total - with_evidence,
            "percent_done": round(100.0 * with_evidence / total, 2) if total else 0.0,
        },
        "evidence_categories": evidence_categories,
        "state_counts": dict(sorted(state_counts.items())),
        "snapshot_state_counts": summary.get("state_counts", {}),
        "depth_bands": depth_bands,
        "packets": packet_stats,
        "volunteers": leaderboard,
        "recent": recent,
        "history": history_series(),
    }
    OUT.write_text(json.dumps(data, indent=2) + "\n")
    print(f"Wrote {OUT}: {with_evidence}/{total} modules with evidence "
          f"({data['totals']['percent_done']}%), {packets_total} packets, "
          f"{len(leaderboard)} volunteers")


if __name__ == "__main__":
    main()
