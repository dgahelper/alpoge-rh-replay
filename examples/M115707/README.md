# Optional check of the local Gram determinant argument

This example compares task M115707 in packet P0056 with a shorter version of the same module. For instance, Mathlib’s sesquilinear-map constructor expresses a 1,055-line matrix pairing in six lines. The determinant bound has a ten-line statement and retains its original proof body. Across the module the source falls from 3,547 to 386 lines. [Discussion and original measurements](https://github.com/rohanarun/alpoge-rh-replay/issues/17)

The [audit](AuditAll.lean) compares all 23 public declarations using `rfl` and checks their argument names, order, visibility and universes. For definitions this checks the resulting values. Theorems are compared by their propositions, using proof irrelevance. The full comparison passed on x86-64 Linux with the pinned Mathlib objects. The bound reported only `propext`, `Classical.choice` and `Quot.sound`. With the same imports, synchronous elaboration of the 23 declarations on ARM64 macOS used 26,436 heartbeats before and 20,086 afterward. [Pin, source digests and results](receipt.json)

Start in the root of a clean checkout of this repository on Linux. Set `volume` below to the absolute path of the replay volume prepared with `./verify.sh /path/to/new/replay-volume --prepare-only` as described in the [contributor guide](../../CONTRIBUTING.md#build-a-task). You can reuse an existing prepared volume.

```bash
example="$(pwd)/examples/M115707/replay.py"
volume=/path/to/prepared/replay-volume
export ELAN_HOME="$volume/elan" XDG_CACHE_HOME="$volume/cache"
cd "$volume/lean"
elan run leanprover/lean4:v4.33.1 lake env python3 "$example" "$PWD"
```

The script applies a [single-module patch](selector.patch) to a temporary copy. It uses the candidate’s five imports for both versions and gives the published declarations a distinct namespace so Lean can compare them in one environment. To check only the source digests with Python and Git, run `python3 examples/M115707/replay.py "$volume/lean" --sources-only` from the checkout root. All generated modules and proof objects stay in the temporary directory, and the script removes them when it exits. This check covers M115707. The volunteer build and fresh-kernel checks for the published archive run through the existing replay workflow.
