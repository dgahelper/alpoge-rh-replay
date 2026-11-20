"""Check and measure shared lemmas against source-hashed declarations from the archive."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from scan import ROOT, indexed_sources, declarations

HERE = Path(__file__).resolve().parent
LEAN_COMMIT = '819816b2e0a3bf405af45ae5c7af2491d8f5bee6'
# Each entry identifies the exact text (statement and proof), the replacement term,
# and the source modules found by scan.py --match.
CASES = {
    'b22f16de291d4844b697b2d4d3658ff78484851da81860c87effa4c28ff8a877': (
        'continuous_unitsHom', 'f h',
        'M061176 M102348 M103013 M104155 M104175 M104194 M104195 M104350 M104351 M104984 '
        'M105041 M105077 M105078 M105715 M105987 M106690 M106694 M108432 M171108'),
    '6908455f17486d5184e88449ae58304e52d0bf55948f9ee9989a1bbf7e3a8f6a': (
        'totallyDisconnected_quotient', 'N hN',
        'M103041 M105902 M105903 M105904 M106665 M106666 M106667 M106913 M107059 '
        'M108306 M108608 M108635 M108656 M109071'),
}


def source_cases(project):
    expected = {(task, key) for key, (_, _, tasks) in CASES.items() for task in tasks.split()}
    cases = []
    for row, data in indexed_sources(project, {task for task, _ in expected}):
        for key, match, block in declarations(data):
            ident = (row['id'], key.hex())
            if ident not in expected:
                continue
            expected.remove(ident)
            lemma, args, _ = CASES[ident[1]]
            cases.append((lemma, args, f"{ident[0]}.{match[1].decode()}", block.decode()))
    if expected:
        raise ValueError(f'Missing pinned declarations: {sorted(expected)}')
    return sorted(cases)


def compiler_environment(project, work):
    summary = json.loads((ROOT / 'tracker/summary.json').read_text())
    toolchain = (project / 'lean-toolchain').read_text().strip()
    version = subprocess.check_output(['lean', '--version'], text=True).strip()
    if (toolchain != 'leanprover/lean4:v' + summary['lean'] or LEAN_COMMIT not in version
            or f"version {summary['lean']}," not in version):
        raise ValueError(f'Unexpected compiler: {version} ({toolchain})')
    manifest = json.loads((project / 'lake-manifest.json').read_text())
    packages = project / manifest['packagesDir']
    pins = [p['rev'] for p in manifest['packages'] if p['name'] == 'mathlib']
    actual = subprocess.check_output(['git', '-C', packages / 'mathlib', 'rev-parse', 'HEAD'],
                                     text=True).strip()
    if pins != [actual] or actual != summary['mathlib_commit']:
        raise ValueError(f'Unexpected Mathlib revision: {actual}')
    libraries = [packages / p['name'] / '.lake/build/lib/lean' for p in manifest['packages']]
    return version, actual, {**os.environ, 'LEAN_PATH': os.pathsep.join(map(str, [work, *libraries]))}


def compile_file(work, env, name, save=False):
    cmd = ['lean', '-j1', '-DElab.async=false', '-DautoImplicit=false',
           '-DrelaxedAutoImplicit=false', '-DmaxSynthPendingDepth=3', '-DmaxHeartbeats=4000000',
           '-DwarningAsError=true', '--tstack=400000']
    if save:
        cmd.extend(['-o', name + '.olean'])
    run = subprocess.run([*cmd, name + '.lean'], env=env, cwd=work, text=True,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if run.returncode:
        raise RuntimeError(f"{name} failed:\n{run.stdout}")
    return [int(n) for n in re.findall(r'\bUsed (\d+) heartbeats,', run.stdout)]


def audit(names):
    constants = ', '.join('`' + name for name in names)
    return f'''
open Lean in
run_cmd do
  let allowed := #[`propext, `Classical.choice, `Quot.sound]
  for decl in #[{constants}] do
    for ax in ← collectAxioms decl do
      unless allowed.contains ax do throwError m!"Unexpected axiom {{ax}} in {{decl}}"
'''


def check(project, work):
    cases = source_cases(project)
    version, pin, env = compiler_environment(project, work)
    library = HERE / 'ReplayTopology.lean'
    shutil.copyfile(library, work / library.name)
    compile_file(work, env, 'ReplayTopology', save=True)
    subprocess.run(['leanchecker', 'ReplayTopology'], cwd=work, env=env, check=True)
    # Measure the same two library declarations, including their generalized binders.
    source = library.read_text(encoding='utf-8')
    source = 'import Mathlib.Util.CountHeartbeats\n' + source.replace('\n/--', '\n#count_heartbeats in\n/--')
    (work / 'LibraryCost.lean').write_text(source, encoding='utf-8')
    costs = compile_file(work, env, 'LibraryCost')
    if len(costs) != len(CASES):
        raise ValueError('Missing library heartbeat measurements')

    measurements = {}
    for mode in ('Original', 'Shared'):
        lines = ['import ReplayTopology', 'import Mathlib.Util.CountHeartbeats',
                 'import Lean.Util.CollectAxioms']
        names = []
        for lemma, args, name, block in cases:
            if mode == 'Shared':
                statement, _, _ = block.partition(':= by')
                block = f'{statement}:= ReplayTopology.{lemma} {args}'
            lines.extend(['#count_heartbeats in', f'theorem {name} {block}'])
            names.append(name)
        lines.append(audit(names + ['ReplayTopology.' + lemma for lemma, _, _ in CASES.values()]))
        (work / (mode + '.lean')).write_text('\n\n'.join(lines), encoding='utf-8')
        beats = compile_file(work, env, mode)
        if len(beats) != len(cases):
            raise ValueError(f'Missing {mode} heartbeat measurements')
        totals = Counter()
        for (lemma, _, _, _), n in zip(cases, beats):
            totals[lemma] += n
        measurements[mode] = dict(totals)
    return dict(compiler=version, mathlib=pin, kernel_replayed='ReplayTopology',
                checked=dict(Counter(c[0] for c in cases)),
                heartbeats=measurements, library_heartbeats=sum(costs))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', type=Path, help='prepared lean/ directory')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='rh-proof-reuse-') as temp:
        print(json.dumps(check(args.project.resolve(), Path(temp)), indent=2))


if __name__ == '__main__':
    main()
