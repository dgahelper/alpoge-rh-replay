"""Find repeated, byte-identical theorem statements and tactic scripts in the pinned source tree."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
# This recognizes column-zero declarations and indented continuations in the archive.
# Keep explicit universe parameters and everything after the name in the fingerprint.
DECL = re.compile(
    rb"^(?:private )?(?:theorem|lemma) ([A-Za-z_][A-Za-z_0-9']*(?:\.[A-Za-z_][A-Za-z_0-9']*)*)"
    rb"(?=[ \t:({\[]|\.\{)([^\n]*(?:\n(?:[ \t][^\n]*)?)*)", re.M
)


def indexed_sources(project, tasks=None):
    with gzip.open(ROOT / 'tracker/modules.jsonl.gz', 'rt') as stream:
        for row in map(json.loads, stream):
            if tasks is not None and row['id'] not in tasks:
                continue
            path = project / 'src' / (row['module'].replace('.', '/') + '.lean')
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != row['source_sha256']:
                raise ValueError(f"Source hash mismatch for {row['id']} at {path}")
            yield row, data


def declarations(data):
    # Skip files that might put apparent commands inside multiline comments, strings or quotations.
    if any(marker in data for marker in (b'/-', b'"', b'`')):
        return
    for match in DECL.finditer(data):
        block = match[2].strip()
        if b':= by' in block and b'--' not in block:
            yield hashlib.sha256(block).digest(), match, block


def scan(project, limit, wanted):
    counts = Counter()
    examples = {}
    matches = []
    modules = 0
    for row, data in indexed_sources(project):
        modules += 1
        for key, match, _ in declarations(data):
            counts[key] += 1
            if counts[key] == 2 or key in wanted:
                location = dict(task=row['id'], name=match[1].decode(),
                                line=data.count(b'\n', 0, match.start()) + 1)
                if counts[key] == 2:
                    examples[key] = location
                if key in wanted:
                    matches.append(dict(sha256=key.hex(), **location))
    repeated = sorted(examples, key=lambda k: (-counts[k], k))
    return dict(modules=modules, candidates=sum(counts.values()), repeated_groups=len(repeated),
                occurrences_after_first=sum(counts[k] - 1 for k in repeated),
                top=[dict(sha256=k.hex(), occurrences=counts[k], example=examples[k])
                     for k in repeated[:limit]], matches=matches)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', type=Path, help='prepared lean/ directory')
    parser.add_argument('--limit', type=int, default=10)
    parser.add_argument('--match', action='append', default=[], metavar='SHA256',
                        help='include every task, declaration name and line for this fingerprint')
    args = parser.parse_args()
    if args.limit < 0 or any(not re.fullmatch('[0-9a-fA-F]{64}', k) for k in args.match):
        parser.error('use a nonnegative limit and full SHA-256 fingerprints')
    print(json.dumps(scan(args.project, args.limit, {bytes.fromhex(k) for k in args.match}), indent=2))


if __name__ == '__main__':
    main()
