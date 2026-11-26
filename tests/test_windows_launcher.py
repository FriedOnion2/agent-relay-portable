import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(sys.platform == "win32", "requires Windows cmd.exe")
class WindowsSourceLauncherTests(unittest.TestCase):
    def test_starts_server_directly_and_forwards_arguments(self):
        launcher = Path(__file__).resolve().parents[1] / "启动_AgentRelay.bat"
        with tempfile.TemporaryDirectory(prefix="AgentRelay source 中文 ") as folder:
            root = Path(folder)
            shutil.copyfile(launcher, root / launcher.name)
            app = root / "app"
            app.mkdir()
            (app / "bootstrap.py").write_text("raise AssertionError('unexpected full source scan')", encoding="utf-8")
            (app / "cli.py").write_text(
                "import json, sys\nfrom pathlib import Path\n"
                "Path('args.json').write_text(json.dumps(sys.argv[1:]), encoding='utf-8')\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                ["cmd.exe", "/d", "/c", launcher.name, "--no-browser", "--port", "18745"],
                cwd=root, env=dict(os.environ, RELAY_PYTHON=sys.executable),
                stdin=subprocess.DEVNULL, capture_output=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
            self.assertEqual(json.loads((root / "args.json").read_text(encoding="utf-8")),
                             ["serve", "--no-browser", "--port", "18745"])
