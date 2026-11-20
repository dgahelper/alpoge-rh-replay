#!/usr/bin/env bash
# independent-check.sh — pilot: check the RH *statement cone* with a kernel
# implementation that is independent of Lean's own C++ kernel.
#
# The required replay (verify.sh) finishes with `leanchecker --fresh Main`,
# which is Lean's own kernel re-checking Lean's own output (README: "It uses
# the same Lean kernel implementation"). This script instead:
#
#   1. compiles kernel/Pilot.lean (imports Mathlib only) against a prepared
#      replay volume, anchoring on `RiemannHypothesis` and `riemannZeta`;
#   2. exports those declarations and their declaration-level dependency
#      cone with lean4export (NDJSON format);
#   3. type-checks the export with nanoda (nanoda_lib, a Rust kernel
#      implementation that shares no code with Lean's kernel), permitting
#      exactly the axioms Audit.lean permits, plus Lean.trustCompiler,
#      in strict mode — an unlisted axiom is a hard error, not a skip;
#   4. prints a PASS/FAIL summary with measured sizes and runtimes.
#
# This is a PILOT, not part of the required replay, and it covers only the
# statement cone of the two anchor declarations — not the project's proof
# modules. See kernel/README.md for measured results and limitations.
#
# Usage:
#   kernel/independent-check.sh <prepared-volume-dir> [output-dir]
#
# <prepared-volume-dir> is a directory prepared by verify.sh (it contains
# elan/ and lean/). Tools are built from the pinned sources in
# kernel/tools.lock into <output-dir>/tools on first use; set
# LEAN4EXPORT_BIN / NANODA_BIN to reuse existing builds instead.
# Prerequisites: git, a Rust toolchain (cargo) for nanoda, curl, python3.
set -uo pipefail

VOL="${1:?usage: independent-check.sh <prepared-volume-dir> [output-dir]}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
OUT="${2:-$SCRIPT_DIR/kernel-out}"
mkdir -p "$OUT/tools" "$OUT/pilot"
OUT="$(cd "$OUT" && pwd -P)"
VOL="$(cd "$VOL" && pwd -P)"

JOBS="${JOBS:-6}"
THREAD_CAP=(nice -n 10)
command -v taskset >/dev/null && THREAD_CAP=(nice -n 10 taskset -c 0-5)

# Pinned tool sources (see kernel/tools.lock for hashes of reference builds).
LEAN4EXPORT_REPO="https://github.com/leanprover/lean4export.git"
LEAN4EXPORT_COMMIT="15f6055e299ad5b89345e533cc2192f4cc00f659" # tag v4.33.0
NANODA_REPO="https://github.com/ammkrn/nanoda_lib.git"
NANODA_COMMIT="0da9f98feadd3a0a2ef4b3dbcf52a298a6fef929" # v0.4.32

# ---- locate the pinned toolchain inside the prepared volume -----------------
TC_DIR="$(ls -d "$VOL"/elan/toolchains/leanprover--lean4---v4.33.1 2>/dev/null || true)"
if [[ -z "$TC_DIR" ]]; then
  echo "INDEPENDENT_KERNEL_FAILED: no leanprover--lean4---v4.33.1 toolchain under $VOL/elan/toolchains" >&2
  exit 1
fi
LEAN_BIN="$TC_DIR/bin/lean"

# ---- run_timed: run a command, record wall time + peak RSS ------------------
# usage: run_timed <stats-file> <cmd...> ; echoes the command's exit status
run_timed() {
  local stats="$1"; shift
  python3 - "$stats" "$@" <<'PYEOF'
import resource, subprocess, sys, time
stats, cmd = sys.argv[1], sys.argv[2:]
t0 = time.time()
rc = subprocess.run(cmd).returncode
wall = time.time() - t0
kb = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
with open(stats, "w") as f:
    f.write(f"wall_seconds={wall:.1f}\nmaxrss_kb={kb}\nexit_code={rc}\n")
sys.exit(rc)
PYEOF
}

fail() { echo "INDEPENDENT_KERNEL_FAILED: $1" >&2; exit 1; }

# ---- step 0: tools -----------------------------------------------------------
if [[ -n "${LEAN4EXPORT_BIN:-}" ]]; then
  L4E="$LEAN4EXPORT_BIN"
else
  L4E="$OUT/tools/lean4export/.lake/build/bin/lean4export"
  if [[ ! -x "$L4E" ]]; then
    echo "== building lean4export @ $LEAN4EXPORT_COMMIT (with the volume's Lean 4.33.1)"
    if [[ ! -d "$OUT/tools/lean4export/.git" ]]; then
      git clone --quiet "$LEAN4EXPORT_REPO" "$OUT/tools/lean4export" \
        || fail "cloning lean4export"
    fi
    git -C "$OUT/tools/lean4export" checkout --quiet "$LEAN4EXPORT_COMMIT" \
      || fail "checking out lean4export $LEAN4EXPORT_COMMIT"
    [[ "$(git -C "$OUT/tools/lean4export" rev-parse HEAD)" == "$LEAN4EXPORT_COMMIT" ]] \
      || fail "lean4export checkout is not at the pinned commit $LEAN4EXPORT_COMMIT"
    (cd "$OUT/tools/lean4export" && "${THREAD_CAP[@]}" env PATH="$TC_DIR/bin:$PATH" \
      "$TC_DIR/bin/lake" build) > "$OUT/lean4export-build.log" 2>&1 \
      || fail "building lean4export (see $OUT/lean4export-build.log)"
  fi
fi

if [[ -n "${NANODA_BIN:-}" ]]; then
  NANODA="$NANODA_BIN"
else
  NANODA="$OUT/tools/nanoda_lib/target/release/nanoda_bin"
  if [[ ! -x "$NANODA" ]]; then
    command -v cargo >/dev/null || fail "cargo not found; install a Rust toolchain (rustup) first"
    cargo --version >/dev/null 2>&1 || fail "cargo is present but not runnable — with rustup this usually means no default toolchain is configured for the current RUSTUP_HOME. Run 'rustup default stable' (or export RUSTUP_HOME/CARGO_HOME for an existing install), then retry."
    echo "== building nanoda_lib @ $NANODA_COMMIT"
    if [[ ! -d "$OUT/tools/nanoda_lib/.git" ]]; then
      git clone --quiet "$NANODA_REPO" "$OUT/tools/nanoda_lib" \
        || fail "cloning nanoda_lib"
    fi
    git -C "$OUT/tools/nanoda_lib" checkout --quiet "$NANODA_COMMIT" \
      || fail "checking out nanoda_lib $NANODA_COMMIT"
    [[ "$(git -C "$OUT/tools/nanoda_lib" rev-parse HEAD)" == "$NANODA_COMMIT" ]] \
      || fail "nanoda_lib checkout is not at the pinned commit $NANODA_COMMIT"
    (cd "$OUT/tools/nanoda_lib" && "${THREAD_CAP[@]}" cargo build --release --locked -j "$JOBS") \
      > "$OUT/nanoda-build.log" 2>&1 \
      || fail "building nanoda_lib (see $OUT/nanoda-build.log)"
  fi
fi
echo "lean4export: $L4E"
echo "nanoda:      $NANODA"

# ---- LEAN_PATH over the volume's prebuilt package oleans --------------------
LP=""
for pkg in "$VOL"/lean/.lake/packages/*/; do
  d="${pkg}.lake/build/lib/lean"
  [[ -d "$d" ]] && LP="${LP:+$LP:}$d"
done
[[ -n "$LP" ]] || fail "no package olean dirs found under $VOL/lean/.lake/packages"
export LEAN_PATH="$LP:$OUT/pilot"

# ---- step 1: compile Pilot.lean ----------------------------------------------
echo "== compiling Pilot.lean against the volume's Mathlib oleans"
cp "$SCRIPT_DIR/Pilot.lean" "$OUT/pilot/Pilot.lean"
run_timed "$OUT/pilot.stats" "${THREAD_CAP[@]}" "$LEAN_BIN" \
  "$OUT/pilot/Pilot.lean" -o "$OUT/pilot/Pilot.olean" \
  > "$OUT/pilot-compile.log" 2>&1
rc=$?
cat "$OUT/pilot.stats"
[[ $rc -eq 0 ]] || fail "Pilot.lean did not compile (see $OUT/pilot-compile.log)"
echo "PILOT_COMPILE_PASSED"

# ---- step 2: export the statement cone ---------------------------------------
echo "== exporting RiemannHypothesis + riemannZeta cone with lean4export"
# lean4export spawns `lean` as an external process, so the pinned toolchain
# must be on PATH for this step.
run_timed "$OUT/export.stats" "${THREAD_CAP[@]}" env PATH="$TC_DIR/bin:$PATH" "$L4E" \
  Pilot -- RiemannHypothesis riemannZeta \
  > "$OUT/pilot.ndjson" 2> "$OUT/export.log"
rc=$?
cat "$OUT/export.stats"
[[ $rc -eq 0 ]] || fail "lean4export failed (see $OUT/export.log)"
EXPORT_BYTES="$(stat -c%s "$OUT/pilot.ndjson")"
DECLS="$(python3 - "$OUT/pilot.ndjson" <<'PYEOF'
import json, sys
# Declaration record kinds in the NDJSON export format (format_ndjson.md):
# axiom, definition ("def"), theorem ("thm"), opaque, quot, inductive.
# Constructors and recursors are grouped inside the inductive record, so
# an independent checker may report a higher declaration count than the
# record count here. A declaration record is a single-key object whose
# key is one of the kinds; every other record in the format is the meta
# line (single key "meta") or a name/level/expression record whose object
# has several keys and contains no declaration kind. Count every kind
# encountered and FAIL on anything unrecognized: a silently skipped kind
# publishes a wrong total. (That is not hypothetical — axioms were once
# counted under the key "ax", which the exporter never emits, and the
# 3 axiom records dropped out of the published count.)
decl_kinds = {"axiom", "def", "thm", "opaque", "quot", "inductive"}
counts = {k: 0 for k in decl_kinds}
with open(sys.argv[1]) as f:
    for line in f:
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if not isinstance(obj, dict):
            continue
        kinds = decl_kinds.intersection(obj)
        if len(obj) == 1 and kinds:
            counts[next(iter(kinds))] += 1
        elif kinds or (len(obj) == 1 and "meta" not in obj):
            sys.exit(f"unrecognized record shape in export: {sorted(obj)[:4]}")
print(" ".join(f"{k}={counts[k]}" for k in sorted(counts)), file=sys.stderr)
print(sum(counts.values()))
PYEOF
)" || fail "counting declaration records in the export failed"
echo "EXPORT_DONE bytes=$EXPORT_BYTES declarations=$DECLS file=$OUT/pilot.ndjson"

# ---- step 3: independent kernel check ----------------------------------------
cat > "$OUT/nanoda-config.json" <<EOF
{
  "export_file_path": "$OUT/pilot.ndjson",
  "use_stdin": false,
  "num_threads": $JOBS,
  "stack_size_bytes": 1073741824,
  "permitted_axioms": ["propext", "Classical.choice", "Quot.sound", "Lean.trustCompiler"],
  "unpermitted_axiom_hard_error": true,
  "nat_extension": true,
  "string_extension": true,
  "print_success_message": true
}
EOF
echo "== checking the export with nanoda (independent Rust kernel)"
run_timed "$OUT/nanoda.stats" "${THREAD_CAP[@]}" "$NANODA" "$OUT/nanoda-config.json" \
  > "$OUT/nanoda.log" 2>&1
rc=$?
cat "$OUT/nanoda.stats"
cat "$OUT/nanoda.log"
if [[ $rc -eq 0 ]]; then
  echo "INDEPENDENT_KERNEL_PASSED checker=nanoda declarations=$DECLS export_bytes=$EXPORT_BYTES"
else
  fail "nanoda rejected the export with exit code $rc (see $OUT/nanoda.log)"
fi
