#!/usr/bin/env python3
"""Generate dashboard/data.json from the replay tracker's published files.

Standard library only, like the rest of the repo tooling. Run from anywhere:

    python3 dashboard/generate_data.py

Reads tracker/summary.json, tracker/completed.tsv, tracker/packets.tsv,
tracker/modules.jsonl.gz and evidence/volunteers/*.json from the repository
root, applies the completed.tsv overlay to module states exactly as
tracker/tasks.py load() does, and writes aggregated data (never raw module
rows) to dashboard/data.json next to this script. In a full Git checkout,
the first-parent ledger history also supplies the hourly rate and projection,
and the same first-parent walk -- counting the same unique tracked module
IDs -- supplies the cumulative "history" series, so the two charts share
one counting rule and their totals agree.
"""
import csv
import datetime
import gzip
import json
import subprocess
from collections import Counter
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


def git_output(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True)


def ledger_commits():
    """First-parent commits that touched the ledger, oldest first.

    Returns [(published, revision)] with published the commit epoch clamped
    to be non-decreasing -- commit clocks can go backward, so this preserves
    mainline publication order. Returns None for a shallow checkout or when
    no commit has touched the ledger. Both history series below are built
    from this one walk and the one counting rule in ledger_count().
    """
    if git_output("rev-parse", "--is-shallow-repository").strip() == "true":
        return None
    log = git_output("log", "--first-parent", "--reverse", "--format=%ct %H",
                     "--", "tracker/completed.tsv")
    commits = []
    for line in log.splitlines():
        timestamp, revision = line.split()
        published = max(int(timestamp), commits[-1][0] if commits else 0)
        commits.append((published, revision))
    return commits or None


def ledger_count(module_ids, revision):
    """Unique tracked module IDs recorded in the ledger at a revision."""
    rows = csv.DictReader(
        git_output("show", f"{revision}:tracker/completed.tsv").splitlines(),
        delimiter="\t")
    return len(module_ids.intersection(row["id"] for row in rows))


def ledger_history(module_ids, recorded, now):
    """Sample the committed ledger at hourly boundaries ending at generation time."""
    commits = ledger_commits()
    if commits is None:
        return None

    end = int(now.timestamp())
    hours = min(24, (end - commits[0][0]) // 3600)
    if hours < 1:
        return {"hours": [], "per_hour": None, "eta": None}

    samples = []
    pos = 0
    last_revision = None
    for boundary in range(end - hours * 3600, end + 1, 3600):
        while pos + 1 < len(commits) and commits[pos + 1][0] <= boundary:
            pos += 1
        revision = commits[pos][1]
        if revision != last_revision:
            count = ledger_count(module_ids, revision)
            last_revision = revision
        samples.append(count)

    if samples[-1] != recorded:
        # Local edits or a future-dated commit can put HEAD ahead of our samples.
        return None
    points = [
        {"end": end - (hours - i) * 3600, "net_modules": samples[i] - samples[i - 1]}
        for i in range(1, hours + 1)
    ]
    rate = (samples[-1] - samples[0]) / hours
    remaining = len(module_ids) - recorded
    eta = None
    if remaining and rate > 0:
        eta = (now + datetime.timedelta(hours=remaining / rate)).date().isoformat()
    return {"hours": points, "per_hour": rate, "eta": eta}


def cumulative_history(module_ids, recorded):
    """Cumulative modules with recorded evidence over the ledger's history.

    One point per commit from the same first-parent walk ledger_history()
    samples, counting the same unique tracked module IDs via ledger_count(),
    so this series ends at the same displayed total the hourly chart is
    built from. Points are downsampled to at most 240, first and last
    always kept; the sampling happens before any ledger reads, so at most
    240 revisions are ever read. Returns [] whenever the walk is
    unavailable or its final count disagrees with the snapshot total --
    this series is optional and must never fail the whole generation.
    """
    try:
        commits = ledger_commits()
        if not commits:
            return []
        if len(commits) > 240:
            keep = sorted({round(i * (len(commits) - 1) / 239)
                           for i in range(240)})
            commits = [commits[i] for i in keep]
        points = []
        for published, revision in commits:
            when = datetime.datetime.fromtimestamp(
                published, datetime.timezone.utc)
            points.append({
                "t": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "with_evidence": ledger_count(module_ids, revision),
            })
        if points[-1]["with_evidence"] != recorded:
            return []
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

    now = datetime.datetime.now(datetime.timezone.utc)
    try:
        history = ledger_history({row["id"] for row in modules}, with_evidence, now)
    except (FileNotFoundError, subprocess.CalledProcessError):
        history = None  # Downloaded archives can still render the snapshot dashboard.
    cumulative = cumulative_history({row["id"] for row in modules}, with_evidence)
    data = {
        "ledger_history": history,
        "history": cumulative,
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
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
    }
    OUT.write_text(json.dumps(data, indent=2) + "\n")
    print(f"Wrote {OUT}: {with_evidence}/{total} modules with evidence "
          f"({data['totals']['percent_done']}%), {packets_total} packets, "
          f"{len(leaderboard)} volunteers")


if __name__ == "__main__":
    main()
