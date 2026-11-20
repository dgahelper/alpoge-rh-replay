import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import tasks

# Transcript shape written by `lake build` when its output is not a terminal.
LOG = '''\
✔ [8706/8709] Built ReciprocityTheory.DualLattices.VEqZeroOfPowEqOne (196s)
⚠ [8707/8709] Built Formalism.PeriodIntegrals.UMultOne (12s)
warning: Formalism/PeriodIntegrals/UMultOne.lean:3:0: unused variable
✔ [8708/8709] Built Mathlib.Algebra.Group.Basic (3s)
\x1b[32m✔ [8709/8709] Built Development.AbelianVarietyTheory.Definitions.Foundations.IsSatFrame (175s)\x1b[0m
Build completed successfully (8709 jobs).
'''
PROJECT = {
    'ReciprocityTheory.DualLattices.VEqZeroOfPowEqOne',
    'Formalism.PeriodIntegrals.UMultOne',
    'Development.AbelianVarietyTheory.Definitions.Foundations.IsSatFrame',
    'Formalism.BehrendSets.Statement',
}
TARGET = {'Development.AbelianVarietyTheory.Definitions.Foundations.IsSatFrame'}


class ReceiptTests(unittest.TestCase):
    def test_rebuilt_imports_come_from_this_build_log(self):
        self.assertEqual(tasks.rebuilt_imports(LOG, PROJECT, TARGET),
                         ['Formalism.PeriodIntegrals.UMultOne', 'ReciprocityTheory.DualLattices.VEqZeroOfPowEqOne'])

    def test_rebuilt_imports_ignore_mathlib_targets_and_unbuilt_modules(self):
        rebuilt = tasks.rebuilt_imports(LOG, PROJECT, TARGET)
        self.assertNotIn('Mathlib.Algebra.Group.Basic', rebuilt)
        self.assertNotIn('Formalism.BehrendSets.Statement', rebuilt)
        self.assertEqual(tasks.rebuilt_imports('Build completed successfully (8705 jobs).\n', PROJECT, TARGET), [])

    def test_failed_jobs_are_not_counted_as_built(self):
        log = '✖ [8706/8707] Building Formalism.BehrendSets.Statement\nerror: build failed\n'
        self.assertEqual(tasks.rebuilt_imports(log, PROJECT, set()), [])

    def test_host_resources_reports_cpu_count(self):
        info = tasks.host_resources()
        self.assertEqual(info['cpu_count'], os.cpu_count())
        if Path('/proc/meminfo').exists():
            self.assertGreater(info['mem_total_kib'], 0)
            self.assertIn('peak_child_rss_kib', info)


class OutputDirectoryTests(unittest.TestCase):
    """A failed pre-build check must not leave a receipt folder that blocks the retry."""

    def checkout(self, root, toolchain='leanprover/lean4:v4.33.1', source=b'import Mathlib\n'):
        project = root / 'volume/lean'
        (project / 'src/A').mkdir(parents=True)
        (project / 'lean-toolchain').write_text(toolchain + '\n')
        (project / 'src/A/B.lean').write_bytes(source)
        return project

    def target(self, sha='0' * 64):
        return [{'id': 'M000001', 'module': 'A.B', 'source_sha256': sha}]

    def test_wrong_toolchain_leaves_no_output_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / 'receipt'
            with self.assertRaisesRegex(SystemExit, 'Wrong Lean toolchain'):
                tasks.run(self.target(), self.checkout(root, 'leanprover/lean4:v4.35.0'), out, False)
            self.assertFalse(out.exists())

    def test_source_hash_mismatch_leaves_no_output_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / 'receipt'
            mathlib = json.loads((tasks.base / 'summary.json').read_text())['mathlib_commit']
            with patch.object(tasks.subprocess, 'check_output', side_effect=['Lean (version 4.33.1)', mathlib]):
                with self.assertRaisesRegex(SystemExit, 'Source hash mismatch: A.B'):
                    tasks.run(self.target(), self.checkout(root), out, False)
            self.assertFalse(out.exists())

    def test_existing_output_directory_is_refused_up_front_and_left_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / 'receipt'
            out.mkdir()
            (out / 'receipt.json').write_text('earlier run')
            with patch.object(tasks.subprocess, 'check_output') as probe:
                with self.assertRaisesRegex(SystemExit, 'Output directory already exists'):
                    tasks.run(self.target(), self.checkout(root), out, False)
            probe.assert_not_called()
            self.assertEqual((out / 'receipt.json').read_text(), 'earlier run')


if __name__ == '__main__':
    unittest.main()
