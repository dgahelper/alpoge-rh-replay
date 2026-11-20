import os
from pathlib import Path
import unittest

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


if __name__ == '__main__':
    unittest.main()
