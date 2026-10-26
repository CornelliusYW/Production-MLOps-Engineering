"""Exercise the planning command's failure response."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class PlanningCommandTests(unittest.TestCase):
    def test_missing_publication_returns_a_clear_error(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'not_published'
            command = Path(__file__).with_name('planning_app.py')
            result = subprocess.run(
                [sys.executable, str(command), '--output', str(output)],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn('Planning load stopped:', result.stderr)
            self.assertIn('current.json', result.stderr)
            self.assertNotIn('Traceback', result.stderr)
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
