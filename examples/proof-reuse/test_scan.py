import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import scan


class ProofScanTests(unittest.TestCase):
    def test_groups_by_statement_and_script_and_rejects_changed_input(self):
        source = (b'theorem a : True := by\n  trivial\n\n'
                  b'private theorem b : True := by\n  trivial\n'
                  b'theorem c : 0 = 0 := by\n  trivial\n')
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / 'src').mkdir()
            (project / 'tracker').mkdir()
            file = project / 'src/T.lean'
            file.write_bytes(source)
            row = dict(id='M000001', module='T', source_sha256=hashlib.sha256(source).hexdigest())
            with gzip.open(project / 'tracker/modules.jsonl.gz', 'wt') as stream:
                stream.write(json.dumps(row) + '\n')
            key = hashlib.sha256(b': True := by\n  trivial').digest()
            with patch.object(scan, 'ROOT', project):
                result = scan.scan(project, 1, {key})
                self.assertEqual(result['candidates'], 3)
                self.assertEqual(result['occurrences_after_first'], 1)
                self.assertEqual([(m['name'], m['line']) for m in result['matches']], [('a', 1), ('b', 4)])
                file.write_bytes(source + b'\n')
                with self.assertRaisesRegex(ValueError, 'Source hash mismatch'):
                    scan.scan(project, 1, {key})

    def test_ignores_possible_multiline_comment_content(self):
        self.assertEqual(list(scan.declarations(b'/-\ntheorem a : True := by\n  trivial\n-/')), [])


if __name__ == '__main__':
    unittest.main()
