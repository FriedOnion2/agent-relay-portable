"""Run the real-client smoke scripts when the clients are installed (otherwise skipped).

CI installs the clients in .github/workflows/real-clients.yml; locally these only run on machines that have
``codex`` / ``dsh`` on PATH, and never touch the user's own sessions (throw-away homes only).
"""
import subprocess
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'


def run(script):
    result = subprocess.run([sys.executable, str(SCRIPTS / script)], capture_output=True, text=True,
                            encoding='utf-8', timeout=300)
    if result.returncode == 77:
        raise unittest.SkipTest(result.stdout.strip())
    return result


class RealClientTests(unittest.TestCase):
    def test_codex_can_resume_imported_session(self):
        result = run('smoke_codex_resume.py')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_dsh_can_open_imported_session(self):
        result = run('smoke_dsh_native.py')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
