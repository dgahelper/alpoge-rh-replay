import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import tasks


def row(task, packet, imports=(), state='open'):
    return dict(id=task, packet=packet, module=task, imports=imports,
                depth=int(bool(imports)), state=state)


class ColdModuleTests(unittest.TestCase):
    def test_claims_and_ledger_states(self):
        rows = [row('M1', 'P1'), row('M2', 'P1'), row('M3', 'P2'),
                row('M4', 'P3', state='build-observed'), row('M5', 'P3', state='assigned')]
        self.assertEqual([r['id'] for r, _, _ in tasks.cold_modules(rows, {'M1', 'P2'})], ['M2'])
        self.assertEqual(tasks.cold_modules(rows, {'P1', 'P2'}), [])

    def test_rank_by_sole_import_then_direct_consumers_then_id(self):
        rows = [row('A', 'P1'), row('B', 'P1'), row('C', 'P1'), row('D', 'P1'),
                row('E', 'P2', ['A', 'A']), row('F', 'P2', ['B', 'C']),
                row('G', 'P2', ['B', 'C']), row('H', 'P3', ['D']),
                row('I', 'P4', ['D']), row('J', 'P5', ['D'], state='assigned')]
        ranked = tasks.cold_modules(rows, {'P3', 'I'})
        self.assertEqual([(r['id'], sole, direct) for r, sole, direct in ranked],
                         [('A', 1, 1), ('B', 0, 2), ('C', 0, 2), ('D', 0, 0)])

    def test_cold_cli_and_default_packet_suggestions(self):
        rows = [row('M1', 'P1'), row('M2', 'P1', state='assigned'), row('M3', 'P2', ['M1'])]
        def next_output(*args):
            output = io.StringIO()
            with patch.object(tasks, 'load', return_value=rows), patch.object(tasks, 'claims', return_value=set()), \
                 patch('sys.argv', ['tasks.py', 'next', *args]), redirect_stdout(output):
                self.assertEqual(tasks.main(), 0)
            return output.getvalue()
        self.assertEqual(next_output(), 'P2 depth 1 begins with M3 1/1 open\n')
        self.assertEqual(next_output('--cold', '--limit', '1'),
                         'M1 P1 M1 sole-project-import consumers 1 direct consumers 1\n')
        self.assertEqual(next_output('--cold', '--limit', '0'), '')


def prow(task, packet, depth=0, state='open'):
    return dict(id=task, packet=packet, module=task, imports=[],
                depth=depth, state=state)


class PacketSuggestionTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            prow('M1', 'P1'), prow('M2', 'P1'),
            prow('M3', 'P2', state='build-observed'), prow('M4', 'P2'),
            prow('M5', 'P3', state='wave-reused'), prow('M6', 'P3', state='assigned'),
            prow('M7', 'P4', state='volunteer-build-reviewed'),
            prow('M8', 'P5', depth=1, state='pilot-reused'), prow('M9', 'P5', depth=1),
            prow('M10', 'P5', depth=1),
            prow('M11', 'P6', depth=1, state='build-observed'), prow('M12', 'P6', depth=1),
        ]

    def test_default_lists_only_fully_open_packets(self):
        full, partial = tasks.packet_suggestions(self.rows, set())
        self.assertEqual([(r['packet'], o, t) for r, o, t in full], [('P1', 2, 2)])
        self.assertEqual(partial, [])

    def test_partial_packets_need_open_modules_and_no_assigned(self):
        full, partial = tasks.packet_suggestions(self.rows, set(), include_partial=True)
        self.assertEqual([(r['packet'], o, t) for r, o, t in partial],
                         [('P2', 1, 2), ('P5', 2, 3), ('P6', 1, 2)])

    def test_claimed_packet_or_module_hides_the_packet(self):
        for busy in ({'P2'}, {'M4'}, {'P1'}):
            full, partial = tasks.packet_suggestions(self.rows, busy, include_partial=True)
            shown = [r['packet'] for r, _, _ in full + partial]
            if 'P1' in busy:
                self.assertNotIn('P1', shown)
            else:
                self.assertNotIn('P2', shown)

    def test_partial_cli_output(self):
        def next_output(*args):
            output = io.StringIO()
            with patch.object(tasks, 'load', return_value=self.rows), \
                 patch.object(tasks, 'claims', return_value=set()), \
                 patch('sys.argv', ['tasks.py', 'next', *args]), redirect_stdout(output):
                self.assertEqual(tasks.main(), 0)
            return output.getvalue()
        self.assertEqual(next_output(),
                         'P1 depth 0 begins with M1 2/2 open\n')
        self.assertEqual(next_output('--include-partial'),
                         'P1 depth 0 begins with M1 2/2 open\n'
                         'P2 depth 0 begins with M4 1/2 open (partial)\n'
                         'P5 depth 1 begins with M9 2/3 open (partial)\n'
                         'P6 depth 1 begins with M12 1/2 open (partial)\n'
                         'Partial packets already have evidence for some modules and cannot be claimed as a packet.\n'
                         'Claim their open modules individually: show <packet> lists them, then claim <module ID>.\n')


if __name__ == '__main__':
    unittest.main()
