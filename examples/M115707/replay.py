"""Compare the published and revised M115707 declarations in a pinned Lean environment."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

here = Path(__file__).resolve().parent
receipt = json.loads((here / "receipt.json").read_text())
module = Path("Development/AutomorphicArithmetic/IntegralCasts/CapelliIdentities/SelectionLemmas")
source = Path("src") / module.with_suffix(".lean")
namespace = b"UpperTheory.Reformulated.B.SelectionLemmas"


def checked(path, key):
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != receipt["sha256"][key]:
        raise SystemExit(f"Unexpected SHA-256 for {key}: {path}")
    return data


def prepare(project, work):
    published = checked(project / source, "published")
    checked(here / "selector.patch", "patch")
    checked(here / "AuditAll.lean", "audit")
    candidate = work / source
    candidate.parent.mkdir(parents=True)
    candidate.write_bytes(published)
    subprocess.run(["git", "apply", str(here / "selector.patch")], cwd=work, check=True,
                   env={**os.environ, "GIT_CEILING_DIRECTORIES": str(work.parent)})
    revision = checked(candidate, "revised")

    header, body = published.split(b"\n", 1)
    if header != b"import Mathlib":
        raise SystemExit("Unexpected published import")
    imports = [line for line in revision.splitlines() if line.startswith(b"import ")]
    reference = work / "src/PublishedSelector.lean"
    reference.write_bytes(b"\n".join(imports) + b"\n" + body.replace(namespace, b"PublishedSelector"))
    checked(reference, "reference")
    shutil.copyfile(here / "AuditAll.lean", work / "src/AuditAll.lean")
    print("Verified the published, revised, reference and audit sources.", flush=True)


def compile_pair(project, src):
    pin = receipt["mathlib"]
    manifest = json.loads((project / "lake-manifest.json").read_text())
    pins = [p.get("rev") for p in manifest["packages"] if p.get("name") == "mathlib"]
    if pins != [pin] or (project / "lean-toolchain").read_text().strip() != receipt["toolchain"]:
        raise SystemExit("Unexpected project toolchain or Mathlib pin")
    mathlib = project / ".lake/packages/mathlib"
    if mathlib.is_dir():
        actual = subprocess.check_output(["git", "-C", str(mathlib), "rev-parse", "HEAD"], text=True).strip()
        if actual != pin:
            raise SystemExit("Unexpected Mathlib checkout")
    version = subprocess.check_output(["lean", "--version"], text=True).strip()
    if "version 4.33.1," not in version or receipt["lean_commit"] not in version:
        raise SystemExit(f"Unexpected compiler: {version}")
    search = os.environ.get("LEAN_PATH")
    if not search:
        raise SystemExit("Run the compiler check inside the prepared project's lake env")
    env = {**os.environ, "LEAN_PATH": str(src) + os.pathsep + search}
    lean = ["lean", "--root=" + str(src), *receipt["lean_flags"]]
    for name in (Path("PublishedSelector"), module):
        stem = src / name
        subprocess.run([*lean, "-o", stem.with_suffix(".olean"), stem.with_suffix(".lean")],
                       check=True, env=env, cwd=project)
    subprocess.run([*lean, src / "AuditAll.lean"], check=True, env=env, cwd=project)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path, help="prepared lean/ directory")
    parser.add_argument("--sources-only", action="store_true", help="verify source digests and exit")
    args = parser.parse_args()
    project = args.project.resolve()
    with tempfile.TemporaryDirectory(prefix="rh-selector-") as tmp:
        work = Path(tmp).resolve()
        prepare(project, work)
        if not args.sources_only:
            compile_pair(project, work / "src")


if __name__ == "__main__":
    main()
