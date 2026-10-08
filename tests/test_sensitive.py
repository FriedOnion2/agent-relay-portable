import unittest
from pathlib import Path

import test_native_import
from relay import ir, preview, registry, sensitive

# 测试用的假密钥在运行时拼接，避免源码里出现完整的密钥形态而触发仓库的密钥扫描。
OPENAI = 'sk-' + 'proj-' + 'AbCdEfGh1234567890XyZ'
GITHUB = 'gh' + 'p_' + 'A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8'
AWS = 'AK' + 'IA' + 'ABCDEFGHIJKLMNOP'
JWT = 'eyJ' + 'hbGciOiJIUzI1NiJ9.eyJ' + 'zdWIiOiIxMjM0NTY3ODkwIn0.dBjftJeZ4CVPmB92K27uhbUJU1p1r'


class ScanTextTests(unittest.TestCase):
    def kinds(self, text):
        return [row['kind'] for row in sensitive.scan_text(text)]

    def test_vendor_keys_are_detected(self):
        for kind, token in [('openai-key', OPENAI), ('github-token', GITHUB), ('aws-access-key', AWS), ('jwt', JWT)]:
            self.assertEqual(self.kinds('use ' + token + ' now'), [kind], kind)

    def test_private_key_block_and_url_credentials(self):
        pem = '-----BEGIN RSA PRIVATE KEY-----\nMIIEabc\n-----END RSA PRIVATE KEY-----'
        self.assertEqual(self.kinds('x\n' + pem + '\ny'), ['private-key'])
        self.assertEqual(self.kinds('git clone https://bob:hunter22pw@example.com/r.git'), ['url-credentials'])

    def test_assignments_with_real_values_only(self):
        self.assertEqual(self.kinds('API_KEY = "Zx81QwErTy99"'), ['secret-assignment'])
        self.assertEqual(self.kinds('密码：Qwer1234!x'), ['secret-assignment'])
        for harmless in ['password = os.environ["PASSWORD"]', 'token: <your-token-here>', 'api_key = "xxxxxxxxxxxx"',
                         'password=${DB_PASSWORD}', 'secret_key = None', 'the token budget is large']:
            self.assertEqual(self.kinds(harmless), [], harmless)

    def test_reports_never_expose_any_part_of_the_value(self):
        row = sensitive.scan_text('key ' + OPENAI)[0]
        self.assertEqual(row['length'], len(OPENAI))
        for start in range(0, len(OPENAI) - 4):
            self.assertNotIn(OPENAI[start:start + 5], str(row))

    def test_redact_text_replaces_only_the_secret_value(self):
        out = sensitive.redact_text('password=Zx81QwErTy99 and ' + GITHUB + ' ok')
        self.assertEqual(out, 'password=[REDACTED:secret-assignment] and [REDACTED:github-token] ok')
        self.assertEqual(sensitive.redact_text('nothing here at all'), 'nothing here at all')


def conversation():
    return ir.Conversation(source='fixture', turns=[
        ir.Turn(ir.USER, [ir.Block.text_block('my key is ' + OPENAI)]),
        ir.Turn(ir.ASSISTANT, [ir.Block.tool_call('c1', 'Bash', '{"cmd":"curl -H \\"Authorization: Bearer ' + 'a' * 5 + 'B' * 30 + '\\""}')]),
        ir.Turn(ir.USER, [ir.Block.tool_result('c1', 'AWS_KEY=' + AWS + ' and ' + AWS)])])


class ConversationTests(unittest.TestCase):
    def test_scan_counts_by_kind_with_locations(self):
        result = sensitive.scan_conversation(conversation())
        self.assertEqual({row['kind']: row['count'] for row in result['kinds']},
                         {'aws-access-key': 2, 'openai-key': 1, 'bearer-token': 1})
        self.assertEqual(result['total'], 4)
        for start in range(0, len(OPENAI) - 4):
            self.assertNotIn(OPENAI[start:start + 5], str(result))

    def test_redact_conversation_does_not_mutate_the_original(self):
        original = conversation()
        clean = sensitive.redact_conversation(original)
        self.assertEqual(sensitive.scan_conversation(clean)['total'], 0)
        self.assertEqual(sensitive.scan_conversation(original)['total'], 4)
        self.assertIn('[REDACTED:openai-key]', clean.turns[0].blocks[0].text)


class PreviewIntegrationTests(unittest.TestCase):
    setUp = test_native_import.NativeImportTests.setUp

    def write_source(self):
        conv = ir.Conversation(source='fixture', cwd=str(self.cwd), turns=[
            ir.Turn(ir.USER, [ir.Block.text_block('token ' + GITHUB)]),
            ir.Turn(ir.ASSISTANT, [ir.Block.text_block('ok')])])
        return Path(self.targets['claude'].write(conv, session_id='sec'))

    def test_report_warns_and_token_changes_with_redaction(self):
        self.write_source()
        plain = preview.conversion('claude', 'sec', 'codex', cwd=str(self.cwd))
        self.assertEqual(plain['findings']['total'], 1)
        self.assertTrue(any('疑似敏感信息' in w for w in plain['warnings']))
        self.assertNotIn(GITHUB, str(plain))
        redacted = preview.conversion('claude', 'sec', 'codex', cwd=str(self.cwd), redact_secrets=True)
        self.assertNotEqual(plain['token'], redacted['token'])
        with self.assertRaisesRegex(ValueError, '重新预览'):
            registry.transfer('claude', 'sec', 'codex', cwd=str(self.cwd), redact_secrets=True, preview_token=plain['token'])

    def test_transfer_with_redaction_writes_no_secret(self):
        self.write_source()
        plan = preview.conversion('claude', 'sec', 'codex', cwd=str(self.cwd), redact_secrets=True)
        result = registry.transfer('claude', 'sec', 'codex', cwd=str(self.cwd), redact_secrets=True, preview_token=plan['token'])
        written = Path(result['to']['path']).read_text(encoding='utf-8')
        self.assertNotIn(GITHUB, written)
        self.assertIn('[REDACTED:github-token]', written)

    def test_transfer_without_redaction_is_unchanged(self):
        self.write_source()
        result = registry.transfer('claude', 'sec', 'codex', cwd=str(self.cwd))
        self.assertIn(GITHUB, Path(result['to']['path']).read_text(encoding='utf-8'))

    def test_markdown_export_can_redact(self):
        self.write_source()
        self.assertIn(GITHUB, registry.export_markdown('claude', 'sec'))
        self.assertNotIn(GITHUB, registry.export_markdown('claude', 'sec', redact_secrets=True))


if __name__ == '__main__':
    unittest.main()
