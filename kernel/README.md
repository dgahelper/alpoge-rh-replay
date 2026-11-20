# Independent-kernel pilot

**Status: optional pilot. This is not part of the required replay, and it
does not check the project's proof of the Riemann Hypothesis.** It checks
one small, precisely delimited thing: the *statement cone* — the
declarations that define `RiemannHypothesis` and `riemannZeta` in Mathlib —
with a kernel implementation that is independent of Lean's own kernel.

## Why

`verify.sh` ends with `leanchecker --fresh Main`. As the README puts it,
"it uses the same Lean kernel implementation": every stage of the required
replay ultimately trusts Lean's C++ kernel, the same kernel that produced
the original claim. An independent kernel checker breaks that circularity
for whatever it is run on. This pilot establishes whether the tooling chain
works at all against this project's pinned environment (Lean 4.33.1,
Mathlib `0df444a360eaa60ab8c11dca51a86af692955474`), and measures what it
costs, starting with the smallest cone that matters: the statement itself.

## What it does

`independent-check.sh <prepared-volume-dir> [output-dir]`:

1. Compiles `kernel/Pilot.lean` against the prepared volume's prebuilt
   Mathlib oleans. `Pilot.lean` imports **only Mathlib** (never the
   project's `Main`) and references `RiemannHypothesis` — the statement
   definition `Audit.lean` anchors on — and `riemannZeta`.
2. Exports the two anchor declarations and their declaration-level
   dependency cone with
   [lean4export](https://github.com/leanprover/lean4export) (NDJSON format).
3. Type-checks the export with
   [nanoda](https://github.com/ammkrn/nanoda_lib) (`nanoda_lib`, a Rust
   implementation of the Lean kernel that shares no code with Lean's C++
   kernel). The checker configuration permits exactly the axioms
   `Audit.lean` permits — `propext`, `Classical.choice`, `Quot.sound` —
   plus `Lean.trustCompiler`, with the Nat and String kernel extensions
   enabled.

## Reference run (measured, 2026-11-20)

Machine: home desktop, AMD Ryzen 5 5600 (12 threads), WSL2 Ubuntu 24.04.2,
15 GiB visible RAM. All steps capped at 6 threads, `nice -n 10`; a packet
build was running concurrently on the same machine, so wall times are
shared-load values, not clean benchmarks.

| Step | Wall time | Peak RSS | Result |
| --- | --- | --- | --- |
| Compile `Pilot.lean` (Lean 4.33.1) | 15.4 s | 6.12 GB | `#check` confirms `RiemannHypothesis : Prop`, `riemannZeta : ℂ → ℂ` |
| lean4export of the cone | 61.3 s | 6.14 GB | 347,115,719 bytes NDJSON |
| nanoda check (6 threads) | 35.3 s | 0.42 GB | **exit 0 — no typechecker errors** |

Export facts:

- Meta line: exporter lean4export 3.1.0, **format version 3.1.0**, produced
  from Lean **4.33.1** (githash `819816b2e0a3bf405af45ae5c7af2491d8f5bee6`,
  the replay's pinned toolchain).
- Declaration records: **51,211** — 40,045 theorems, 10,149 definitions,
  967 inductives, 46 opaque, 4 quot. nanoda reports "Checked 53240
  declarations", counting constructors and recursors inside inductive
  groups individually.
- SHA-256 of the reference export:
  `2e8cb9c6b6807c6583c4673368496d45c72012ef0c98c54c2379bb76bed09df6`
  (the export itself is a build artifact and is not committed; the script
  regenerates it — a second run produced the identical byte count).

nanoda's full output line was:

```
Checked 53240 declarations with no typechecker errors, 1 pretty printer errors: [
    "Unable to print axioms",
]
```

The pretty-printer error is cosmetic: it comes from nanoda's pretty
printer (`pretty_printer.rs`) being asked to print the axiom list after
checking; it is not a checking error, and the exit code is 0.

### Negative controls

The checker was also run on two deliberately corrupted copies of the
export, and rejected both (exit 101 in both cases):

- Swapping the *types* of two definitions: rejected while parsing
  (the NDJSON format requires expression indices to be defined before
  use; the corrupted stream violates that and the parser asserts).
- Swapping one definition's *type* and *value* fields: rejected by the
  type checker itself (`ensure_pi could not produce a pi`, `tc.rs`).

nanoda currently reports errors by panicking in its worker threads rather
than with formatted diagnostics — ugly, but the rejections are real: the
pilot's PASS is not a vacuous one.

## What this does and does not establish

It establishes that Mathlib's definitions of the RH statement and of
`riemannZeta`, together with everything those definitions transitively
rest on, type-check under an independent kernel implementation — the
anchor definitions are not somehow acceptable only to Lean's own kernel.

It does **not** check the project's proof. `riemannHypothesis` lives in
the project's `Main`, which this pilot never imports, and no full build of
`Main` has been produced by anyone yet. Extending independent checking to
the proof is the follow-on work, gated on a completed build.

## Is a full-environment independent check plausible?

Measured here: the 2-declaration statement cone is 347 MB and ~51k
declaration records; nanoda checked it in 35 s using 0.42 GB. **Checking
is not the bottleneck — exporting is.** The exporter took about a minute
and 6.1 GB just to load the Mathlib environment and write this cone.

A full-environment export (all of Mathlib plus the project's 175,187
modules) was **not** attempted and its size is unknown; it would
plausibly reach tens of GB (an extrapolation from this cone, not a
measurement). The sensible next step is to export the cone of one
completed project packet once built modules exist, and measure how the
export grows, before committing to a full-environment stage. Nothing in
the checker numbers above suggests nanoda would be the limiting factor.

## Tool pins and version coupling

All pins live in `tools.lock`. The two couplings that matter:

- **Exporter ↔ Lean version.** lean4export must be built against the
  Lean version that produced the oleans. There is no `v4.33.1` tag of
  lean4export; the reference build uses the `v4.33.0` tag's sources
  (commit `15f6055e299ad5b89345e533cc2192f4cc00f659`) built with the
  volume's Lean 4.33.1 toolchain, which worked unchanged. The export's
  meta line records the producing toolchain's githash, so this is
  auditable from the artifact itself.
- **Checker ↔ export format.** nanoda_lib 0.4.32 (commit
  `0da9f98feadd3a0a2ef4b3dbcf52a298a6fef929`) consumes NDJSON format
  version 3.1.0. (The older `ammkrn/nanoda` repository is deprecated and
  targets the pre-NDJSON text format; `nanoda_lib` is its successor.)

Lean 4.35+ toolchains bundle external checkers (nanoda, lean4lean,
others); this project's pin (4.33.1) predates that, which is why the
tools are built from pinned sources here. The same export could also be
fed to lean4lean; that was not needed for this pilot since nanoda
consumed it successfully, and it remains an obvious second opinion.

## Prerequisites

- A volume prepared by `verify.sh` (contains `elan/` and `lean/`).
- `git`, `python3`, `curl` (archive fetch is verify.sh's job, not this
  script's).
- A Rust toolchain for nanoda: `cargo` must actually run — under rustup
  that means a default toolchain is configured for the current
  `RUSTUP_HOME` (`rustup default stable`), or export
  `RUSTUP_HOME`/`CARGO_HOME` for an existing install. The script checks
  this and says so if it is missing.
- First run builds the tools from the pinned sources (~5 minutes);
  they are cached in `<output-dir>/tools`. Set `LEAN4EXPORT_BIN` /
  `NANODA_BIN` to reuse existing builds of the pinned versions.

## Layout

- `Pilot.lean` — the Mathlib-only anchor module.
- `independent-check.sh` — the whole pipeline; prints
  `INDEPENDENT_KERNEL_PASSED` on success.
- `tools.lock` — every pin, with reference-build hashes.
- This README.
