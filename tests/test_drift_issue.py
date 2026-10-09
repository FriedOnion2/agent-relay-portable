import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SPEC = importlib.util.spec_from_file_location('drift_issue', Path(__file__).resolve().parents[1] / 'scripts' / 'drift_issue.py')
drift_issue = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(drift_issue)

ARGS = ['--workflow', 'Real client compatibility', '--run-url', 'https://github.com/o/r/actions/runs/1']
TITLE = '兼容性计划任务失败：Real client compatibility'


class DriftIssueTests(unittest.TestCase):
    def calls(self, existing):
        seen = []

        def fake(*args, check=True):
            seen.append(args)
            if args[:2] == ('issue', 'list'):
                return json.dumps(existing)
            return 'https://github.com/o/r/issues/9\n'

        with mock.patch.object(drift_issue, 'gh', fake):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(drift_issue.main(ARGS), 0)
        return seen

    def test_creates_a_labelled_issue_when_none_is_open(self):
        seen = self.calls([])
        create = [c for c in seen if c[:2] == ('issue', 'create')]
        self.assertEqual(len(create), 1)
        self.assertIn(TITLE, create[0])
        self.assertIn('format-drift', create[0])
        self.assertFalse([c for c in seen if c[:2] == ('issue', 'comment')])

    def test_comments_instead_of_duplicating_an_open_issue(self):
        seen = self.calls([{'number': 7, 'title': TITLE}, {'number': 8, 'title': '别的 issue'}])
        self.assertFalse([c for c in seen if c[:2] == ('issue', 'create')])
        comment = [c for c in seen if c[:2] == ('issue', 'comment')]
        self.assertEqual(comment[0][2], '7')

    def test_similar_title_does_not_count_as_the_same_issue(self):
        seen = self.calls([{'number': 3, 'title': TITLE + ' (旧)'}])
        self.assertTrue([c for c in seen if c[:2] == ('issue', 'create')])

    def test_body_includes_run_url_and_details(self):
        text = drift_issue.body('wf', 'https://x/run', '| 软件 |\n|---|')
        self.assertIn('https://x/run', text)
        self.assertIn('| 软件 |', text)
        self.assertNotIn('<details>', drift_issue.body('wf', 'https://x/run', '  '))

    def test_details_file_is_read(self):
        with tempfile.NamedTemporaryFile('w', suffix='.md', delete=False, encoding='utf-8') as handle:
            handle.write('表格内容')
        seen = []
        with mock.patch.object(drift_issue, 'gh', lambda *a, check=True: seen.append(a) or '[]'):
            with contextlib.redirect_stdout(io.StringIO()):
                drift_issue.main(ARGS + ['--details-file', handle.name])
        Path(handle.name).unlink()
        self.assertIn('表格内容', [c for c in seen if c[:2] == ('issue', 'create')][0][-1])


if __name__ == '__main__':
    unittest.main()
