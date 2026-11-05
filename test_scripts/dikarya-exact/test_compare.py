"""Check that operational normalization cannot hide scientific differences."""

import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('dikarya_replay', Path(__file__).with_name('run.py'))
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)


class ExactComparisonTests(unittest.TestCase):
    def test_elapsed_fields_are_normalized(self):
        left = (b'IQ-TREE version 3.1.4 built Oct 8 2026\n'
                b'Seed: 71\nElapsed: 3.2 sec using 99% CPU\nCPU time: 4.2\n')
        right = (b'IQ-TREE version 3.1.4-dikarya2 built Oct 27 2026\n'
                 b'Seed: 71\nElapsed: 1.1 sec\nCPU time: 1.3\n')
        self.assertEqual(replay.normalize(left, Path('/tmp/a')),
                         replay.normalize(right, Path('/tmp/b')))

    def test_scientific_fields_are_never_normalized(self):
        for left, right in (
            ('Seed: 71', 'Seed: 72'),
            ('Optimal log-likelihood: -4322.398', 'Optimal log-likelihood: -4322.397'),
            ('Model of substitution: HKY+F+G4', 'Model of substitution: GTR+F+G4'),
            ('Total number of iterations: 5', 'Total number of iterations: 4'),
            ('Kernel: AVX+FMA - 1 threads', 'Kernel: AVX - 1 threads'),
            ('State frequencies: 0.2392', 'State frequencies: 0.2393'),
        ):
            with self.subTest(left=left):
                self.assertNotEqual(replay.normalize(left.encode(), Path('/tmp/a')),
                                    replay.normalize(right.encode(), Path('/tmp/b')))

    def test_missing_results_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertFalse(replay.compare(root / 'a', root / 'b')['identical'])

    def test_unknown_artifacts_are_checked_and_checkpoint_is_excluded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for side in ('a', 'b'):
                for suffix in ('.treefile', '.log', '.iqtree', '.future-result'):
                    (root / (side + suffix)).write_bytes(b'identical\n')
            (root / 'a.ckp.gz').write_bytes(b'operational snapshot')
            self.assertTrue(replay.compare(root / 'a', root / 'b')['identical'])
            (root / 'b.future-result').write_bytes(b'different\n')
            self.assertFalse(replay.compare(root / 'a', root / 'b')['identical'])


if __name__ == '__main__':
    unittest.main()
