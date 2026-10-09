import unittest

import test_native_import
from relay import diff, ir, registry


def conv(*pairs):
    return ir.Conversation(source='fixture', id='x', turns=[ir.Turn(role, [ir.Block.text_block(text)]) for role, text in pairs])


class DiffTests(unittest.TestCase):
    def test_identical_ignores_whitespace_and_system_turns(self):
        a = conv((ir.USER, 'hello   world'), (ir.ASSISTANT, 'ok\n'))
        b = conv((ir.USER, 'hello world'), (ir.ASSISTANT, 'ok'))
        b.turns.insert(0, ir.Turn(ir.SYSTEM, [ir.Block.text_block('ctx')]))
        res = diff.compare(a, b)
        self.assertTrue(res['identical'])
        self.assertEqual((res['matched'], res['ratio']), (2, 1.0))

    def test_missing_extra_and_changed_items(self):
        a = conv((ir.USER, 'q1'), (ir.ASSISTANT, 'a1'), (ir.USER, 'q2'), (ir.ASSISTANT, 'a2'))
        b = conv((ir.USER, 'q1'), (ir.ASSISTANT, 'a1 edited'), (ir.USER, 'q2'))
        res = diff.compare(a, b)
        self.assertFalse(res['identical'])
        self.assertEqual(res['changed'][0]['before']['text'], 'a1')
        self.assertEqual(res['changed'][0]['after']['text'], 'a1 edited')
        self.assertEqual([row['text'] for row in res['only_in_a_samples']], ['a2'])
        self.assertEqual(res['only_in_b'], 1)

    def test_tool_names_do_not_count_but_arguments_do(self):
        def tools(name, args):
            return ir.Conversation(turns=[ir.Turn(ir.ASSISTANT, [ir.Block.tool_call('1', name, args)]),
                                          ir.Turn(ir.USER, [ir.Block.tool_result('1', 'out')])])
        self.assertTrue(diff.compare(tools('Bash', '{"c":1}'), tools('shell', '{"c":1}'))['identical'])
        self.assertFalse(diff.compare(tools('Bash', '{"c":1}'), tools('Bash', '{"c":2}'))['identical'])

    def test_stats_delta_counts_thinking(self):
        a = ir.Conversation(turns=[ir.Turn(ir.ASSISTANT, [ir.Block.thinking_block('t'), ir.Block.text_block('x')])])
        b = ir.Conversation(turns=[ir.Turn(ir.ASSISTANT, [ir.Block.text_block('x')])])
        res = diff.compare(a, b)
        self.assertTrue(res['identical'])
        self.assertEqual(res['stats_delta']['thinking'], -1)


class MigrationRoundTripTests(unittest.TestCase):
    setUp = test_native_import.NativeImportTests.setUp

    def test_migrated_session_matches_its_source(self):
        source = conv((ir.USER, '你好'), (ir.ASSISTANT, '世界'), (ir.USER, '再来一次'), (ir.ASSISTANT, '好的'))
        source.cwd = str(self.cwd)
        self.targets['claude'].write(source, session_id='orig')
        registry.transfer('claude', 'orig', 'codex', cwd=str(self.cwd), session_id='copy')
        res = diff.compare(registry.read_conversation('claude', 'orig'), registry.read_conversation('codex', 'copy'))
        self.assertTrue(res['identical'], res)


if __name__ == '__main__':
    unittest.main()
