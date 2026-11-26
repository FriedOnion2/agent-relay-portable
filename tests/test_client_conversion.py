import os
from importlib.util import find_spec
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from relay import ir, preview, registry


class ClientConversionTests(unittest.TestCase):
    def test_each_writable_source_reaches_every_other_target(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            project = root / "Project with spaces_v1.2"
            project.mkdir()
            agents = {name: registry.get(name, home=str(root / name)) for name in registry.writable_keys()
                      if name != "dsh" or find_spec("zstandard") is not None}
            turns = [ir.Turn(ir.USER, [ir.Block.text_block("第一问")]),
                     ir.Turn(ir.ASSISTANT, [ir.Block.text_block("first answer")]),
                     ir.Turn(ir.USER, [ir.Block.text_block("follow-up")]),
                     ir.Turn(ir.ASSISTANT, [ir.Block.text_block("第二答")])]
            expected = [(t.role, t.text()) for t in turns]
            with patch.dict(registry._CACHE, agents, clear=True), patch.dict(os.environ, {"RELAY_LOG_HOME": str(root / "logs")}):
                for source, reader in agents.items():
                    path = reader.write(ir.Conversation(turns=turns), cwd=str(project))
                    sid = next(row.id for row in reader.discover() if Path(row.path) == Path(path))
                    for target, writer in agents.items():
                        if source == target:
                            continue
                        with self.subTest(source=source, target=target):
                            plan = preview.conversion(source, sid, target, cwd=str(project))
                            result = registry.transfer(source, sid, target, cwd=str(project), preview_token=plan['token'])
                            dest = Path(result['to']['path'])
                            row = next(row for row in writer.discover() if Path(row.path) == dest)
                            self.assertEqual([(t.role, t.text()) for t in writer.read(row.id).turns], expected)
                            if target == 'codebuddy':
                                self.assertIn(project.name, dest.parent.name)
