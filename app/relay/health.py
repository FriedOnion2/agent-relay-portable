"""Honest, offline format checks; never equate fixtures with vendor resume."""

from .messages import text as message_text, error_text
import html
import json
import platform
import tempfile
from pathlib import Path

from . import ir
from .paths import iso


def check(agent):
    from .registry import _ADAPTERS
    from .adapters.claude import ClaudeAdapter
    from .adapters.workbuddy import WorkBuddyAdapter
    cls = _ADAPTERS[agent]
    row = {'agent':agent, 'label':cls.label, 'api_version':cls.api_version,
           'coverage':message_text('msg.codebuddy_cli_jsonl_no_ide') if agent == 'codebuddy' else
                      message_text('msg.dsh_generated_v0_seed_not_every_generation') if agent == 'dsh' else message_text('msg.jsonl_produced_by_the_current_writer'),
           'evidence':'synthetic-roundtrip', 'fixture_version':1, 'client_version':None,
           'latest_client':'unknown', 'native_resume':'not-tested', 'write':bool(cls.can_write)}
    try:
        with tempfile.TemporaryDirectory(prefix='relay-health-') as temporary:
            root = Path(temporary)
            home = root / 'agent'
            conv = ir.Conversation(source='fixture', title='格式自检样本', cwd=str(root),
                                   created_at='2026-01-01T00:00:00Z', turns=[
                ir.Turn(ir.USER, [ir.Block.text_block('health fixture request')]),
                ir.Turn(ir.ASSISTANT, [ir.Block.text_block('health fixture response'),
                    ir.Block.tool_call('call-health', 'Bash', '{"command":"echo fixture"}')]),
                ir.Turn(ir.ASSISTANT, [ir.Block.tool_result('call-health', 'fixture result')])])
            adapter = cls(home=str(home))
            writer = (ClaudeAdapter(home=str(home)) if agent == 'claude_sdk' else
                      WorkBuddyAdapter(home=str(home)) if agent == 'codebuddy' else adapter)
            writer.write(conv, cwd=str(root), session_id='11111111-1111-4111-8111-111111111111')
            discovered = list(adapter.discover())
            if len(discovered) != 1 or not discovered[0].readable:
                raise ValueError(message_text('msg.the_self_check_listing_did_not_return_exactly_one_readable_session'))
            restored = adapter.read(discovered[0].id)
            content = '\n'.join(turn.text() for turn in restored.turns)
            if not all(value in content for value in ('health fixture request', 'health fixture response', 'fixture result')):
                raise ValueError(message_text('msg.the_self_check_read_lost_expected_content'))
            if restored.truncated or restored.stats()['tool_call'] != 1:
                raise ValueError(message_text('msg.wrong_tool_call_count_or_truncated_session_in_the_self_check'))
            row.update(status='passed', read='passed', native_file_roundtrip='passed', error='')
    except ImportError as exc:
        row.update(status='unavailable', read='not-tested', native_file_roundtrip='not-tested', error=error_text(exc))
    except Exception as exc:
        row.update(status='failed', read='failed', native_file_roundtrip='failed', error=error_text(exc))
    return row


def report():
    from . import registry, plugins
    rows = [check(agent) for agent in registry._ADAPTERS]
    for name in plugins.entries:
        rows.append({'agent':name, 'label':message_text('msg.community_name', name=name), 'status':'not-tested',
                     'evidence':'none', 'client_version':None, 'latest_client':'unknown',
                     'native_resume':'not-tested', 'read':'not-tested', 'write':False,
                     'error':message_text('msg.community_plugins_must_supply_their_own_samples_the_built_in_self_check_does_not')})
    return {'ok':all(row['status'] == 'passed' for row in rows[:len(registry._ADAPTERS)]), 'checked_at':iso(),
            'system':platform.system(), 'architecture':platform.machine(), 'adapters':rows,
            'plugin_errors':list(plugins.errors),
            'note':message_text('msg.only_temporary_synthetic_samples_are_used_to_verify_format_reading_and_file_read')}


def export(result, directory):
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    (root / 'health.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    rows = ''.join('<tr>' + ''.join('<td>' + html.escape(str(row.get(key) if row.get(key) is not None else message_text('ui.unknown'))) + '</td>'
                                  for key in ('label','status','evidence','coverage','client_version','native_resume','error')) + '</tr>'
                   for row in result['adapters'])
    document = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>AgentRelay 格式回归</title>'
    document += '<style>body{font:16px system-ui;max-width:1100px;margin:32px auto;padding:16px}td,th{padding:12px;border:1px solid #ccc}table{border-collapse:collapse}</style>'
    document += '<h1>格式健康度：样本回归</h1><p>' + html.escape(result['note']) + '</p><p>'
    document += html.escape(result['checked_at'] + ' / ' + result['system'] + ' / ' + result['architecture']) + '</p>'
    document += '<table><tr><th>来源</th><th>样本状态</th><th>证据</th><th>覆盖</th><th>客户端版本</th><th>真实续聊</th><th>错误</th></tr>' + rows + '</table></html>'
    (root / 'index.html').write_text(document, encoding='utf-8')
    return str(root.resolve())
