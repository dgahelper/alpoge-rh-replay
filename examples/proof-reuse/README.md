# Reusing proofs across the replay archive

The archive contains 19 copies of a continuity proof for homomorphisms into units and 14 copies of a proof about quotients of compact totally disconnected groups. The two lemmas in [ReplayTopology.lean](ReplayTopology.lean) discharge all 33 extracted statements. Both are universe-polymorphic. The continuity lemma only needs continuous inversion on the source group.

## Use the lemmas

In a research checkout with the pinned Mathlib, make [ReplayTopology.lean](ReplayTopology.lean) available as the module `ReplayTopology`. For a Lake project, copy the file to its configured source directory, add `lean_lib ReplayTopology` to a Lean lakefile (or a `[[lean_lib]]` entry named `ReplayTopology` in TOML), and run `lake build ReplayTopology`.

| Goal | Declaration |
| --- | --- |
| Prove continuity of a homomorphism into units from continuity after coercion to the monoid | `ReplayTopology.continuous_unitsHom` |
| Give the quotient of a compact totally disconnected group by a closed normal subgroup a totally disconnected topology | `ReplayTopology.totallyDisconnected_quotient` |

```lean
import ReplayTopology

example {G R : Type*} [Group G] [TopologicalSpace G] [ContinuousInv G]
    [Monoid R] [TopologicalSpace R] (f : G →* Rˣ) (h : Continuous fun x => (f x : R)) :
    Continuous f :=
  ReplayTopology.continuous_unitsHom f h

example {G : Type*} [Group G] [TopologicalSpace G] [IsTopologicalGroup G]
    [CompactSpace G] [TotallyDisconnectedSpace G] (N : Subgroup G) [N.Normal]
    (hN : IsClosed (N : Set G)) : TotallyDisconnectedSpace (G ⧸ N) :=
  ReplayTopology.totallyDisconnected_quotient N hN
```

## Measured elaboration cost

| Lean declaration workload | Original heartbeats | Heartbeats using the shared lemmas |
| --- | ---: | ---: |
| Units-valued continuity, 19 declarations | 3,105 | 1,925 |
| Totally disconnected quotient, 14 declarations | 8,753 | 658 |
| Prove the two shared lemmas once | 0 | 840 |
| **Total** | **11,858** | **3,423** |

The 71.1% reduction measures synchronous elaboration of those declarations with identical imports for the two sets of consumers. Import loading, other declarations, Lake scheduling and review time fall outside the measurement. Both runs produced the same counts using Lean 4.33.1 on native AArch64 Linux and emulated x86-64 Linux with the prepared Mathlib cache. Each compiler built its own library object. The official replay checks hashes of the published sources. Use the shared lemmas in a separate research checkout or when writing new proofs. [Compiler results and source digests](results.json)

## Find another repeated proof

From the tracker repository, point the scanner at a volume prepared by `verify.sh`.

```bash
volume=/path/to/prepared/replay-volume
python3 examples/proof-reuse/scan.py "$volume/lean" --limit 20
```

The scanner hashes every source against the tracker index. Across 175,187 modules it recognized 665,170 candidate declaration blocks and found 12,478 repeated fingerprints, with 15,932 occurrences beyond the first. For example, 33 blocks share a spectrum-map composition argument and 27 share an absolute-norm argument. Inspect any group by passing its full SHA-256 to `--match`. The result includes every matching task ID, local declaration name and line.

The fingerprint covers the text following a declaration name, including its binders, proposition and tactic script, with outer whitespace trimmed. The recognizer looks for plain column-zero theorem or lemma declarations with indented continuations and a literal `:= by`. It skips files containing block-comment, string or backtick delimiters and blocks with line comments. Different local namespaces, variables and instances can give identical text different meanings. Check a proposed abstraction with Lean in the intended context before using it.

To contribute a lemma, record the fingerprint and matching task IDs, then compare the hypotheses and imports at those sites. Add the shared declaration and a check that applies it to the original statements. Include the compiler and Mathlib pins, axiom check, and measured cost of both the original proofs and the shared lemma plus its uses. Link the new declaration and its evidence from this guide so other agents can find it.

## Reproduce the Lean check

Start in the tracker checkout. The example uses the same prepared volume as the contributor build.

```bash
example="$(pwd)/examples/proof-reuse"
export ELAN_HOME="$volume/elan" XDG_CACHE_HOME="$volume/cache"
cd "$volume/lean"
elan run leanprover/lean4:v4.33.1 lake env python3 "$example/check.py" "$PWD"
```

The checker verifies the compiler commit, the Mathlib revision and the source hashes of all 33 modules. It compiles the shared library in a fresh temporary directory and replays its declarations with `leanchecker ReplayTopology` against the imported Mathlib environment. For each recorded site it elaborates the original block and a second declaration with the same binder list and proposition whose proof calls the shared lemma. It checks the resulting axiom dependencies against `propext`, `Classical.choice` and `Quot.sound`. The JSON result reports the costs from Mathlib's `#count_heartbeats in`, with one compiler thread and asynchronous elaboration disabled. This check covers the extracted declarations in a common Mathlib environment. Whole-module replay receipts use the contributor build.
