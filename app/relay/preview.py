"""Side-effect-free migration reports and source/option consistency tokens."""

from .messages import text as message_text
import hashlib
import json
from pathlib import Path
from collections import Counter
from dataclasses import replace

from . import ir, sensitive
from .adapters.base import ToolNameMap


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode('utf-8')).hexdigest()


def check_token(expected, actual):
    if expected and expected != actual:
        raise ValueError(message_text('msg.the_source_target_directory_or_options_changed_preview_again_and_confirm'))


def prepare(conv, new_title=None):
    result = replace(conv, turns=[replace(turn, blocks=[
        ir.Block.text_block('[原始内容块]\n' + json.dumps(block.meta, ensure_ascii=False))
        if block.kind == ir.RAW else block for block in turn.blocks]) for turn in conv.turns])
    if new_title:
        result.title = new_title
    return result


def source_files(conv):
    """Bind hidden native fields and IDE referenced messages, not just IR text."""
    from . import archive
    if not conv.path or not Path(conv.path).is_file():
        return {}
    path = Path(conv.path)
    files = [path]
    if conv.meta.get('source_format') == 'codebuddy-ide-manifest':
        manifest = json.loads(archive.read_file(path).decode('utf-8'))
        for row in manifest.get('messages', []):
            from .paths import validate_session_id
            files.append(path.parent / 'messages' / (validate_session_id(row['id']) + '.json'))
        files.append(path.parent.parent / 'index.json')
    result = {}
    total = 0
    for item in files:
        raw = archive.read_file(item)
        total += len(raw)
        if total > archive.MAX_TOTAL or len(result) >= archive.MAX_FILES:
            raise ValueError(message_text('msg.the_source_file_for_the_preview_exceeds_the_package_limit'))
        result[str(item)] = hashlib.sha256(raw).hexdigest()
    return result


def report(conv, target, options, destination, native=False):
    counts = {key:Counter() for key in ('preserved', 'degraded', 'dropped', 'unknown')}
    warnings = list(conv.meta.get('notes', []))
    blockers = []
    if conv.truncated:
        blockers.append(message_text('msg.the_source_session_is_incomplete_and_cannot_be_migrated'))
    if not conv.turns and not native:
        blockers.append(message_text('msg.the_source_session_has_nothing_to_migrate_the_file_is_empty_or_cannot_be_parsed'))
    if native:
        counts['preserved'][message_text('msg.native_records_original_format_kept')] = len(conv.turns)
        counts['degraded'][message_text('msg.project_metadata_mapped_to_the_new_directory')] = 1
        counts['unknown'][message_text('msg.attachments_side_channel_subagents_app_databases_and_full_resume_state')] = 1
        warnings += [message_text('msg.old_paths_inside_history_text_and_tool_arguments_are_not_rewritten_automatically'), message_text('msg.an_existing_id_is_never_overwritten_resuming_in_the_target_app_must_be_checked_s')]
    else:
        pending, paired, used = {}, set(), set()
        if target == 'dsh':
            for turn in conv.turns:
                for b in turn.blocks:
                    if turn.role == ir.ASSISTANT and b.kind == ir.TOOL_CALL and b.call_id and b.name and b.call_id not in used:
                        pending[b.call_id] = b
                        used.add(b.call_id)
                    elif b.kind == ir.TOOL_RESULT and b.call_id in pending:
                        paired.add(id(pending.pop(b.call_id)))
                        paired.add(id(b))
        for turn in conv.turns:
            for b in turn.blocks:
                category, label = 'preserved', {ir.TEXT:message_text('msg.text'), ir.TOOL_CALL:message_text('msg.tool_calls'),
                    ir.TOOL_RESULT:message_text('ui.tool_result'), ir.THINKING:message_text('msg.thinking'), ir.IMAGE:message_text('msg.images'), ir.RAW:message_text('msg.raw_blocks')}.get(b.kind, b.kind)
                if target != 'dsh' and turn.role not in (ir.USER, ir.ASSISTANT):
                    category, label = 'dropped', message_text('msg.source_system_context')
                elif b.kind == ir.RAW:
                    category, label = 'degraded', message_text('msg.unknown_content_blocks_turned_into_annotated_text')
                elif target != 'dsh' and turn.role == ir.USER and b.kind not in (ir.TEXT, ir.IMAGE):
                    category, label = 'dropped', message_text('msg.kind_in_user_turns', kind=b.kind)
                elif b.kind == ir.THINKING:
                    if not options.get('include_thinking', True):
                        category, label = 'dropped', message_text('msg.thinking_excluded_by_option')
                    else:
                        category, label = 'degraded', message_text('msg.readable_thinking_text_signatures_and_encrypted_state_are_not_kept')
                elif b.kind == ir.IMAGE:
                    if target == 'dsh' or (turn.role == ir.USER and b.text):
                        category, label = 'degraded', message_text('msg.image_description_metadata_native_image_features_are_not_kept')
                    else:
                        category, label = 'dropped', message_text('msg.images_and_binary_image_content')
                elif target == 'dsh' and b.kind in (ir.TOOL_CALL, ir.TOOL_RESULT) and id(b) not in paired:
                    category, label = 'degraded', message_text('msg.unpaired_or_duplicate_tool_records_turned_into_history_text')
                elif target == 'dsh' and turn.role == ir.SYSTEM:
                    category, label = 'degraded', message_text('msg.source_system_context_turned_into_annotated_messages')
                elif b.kind == ir.TOOL_CALL and ToolNameMap.convert(b.name, target, options.get('remap_tools', True)) != b.name:
                    category, label = 'degraded', message_text('msg.tool_names_mapped_arguments_are_not_converted')
                elif b.kind not in (ir.TEXT, ir.TOOL_CALL, ir.TOOL_RESULT):
                    category, label = 'unknown', message_text('msg.unknown_block_kind', kind=b.kind)
                counts[category][label] += 1
        enc = (conv.meta or {}).get('encrypted_reasoning', 0)
        if enc:
            counts['dropped'][message_text('msg.encrypted_thinking_encrypted_at_the_source_cannot_be_read')] += enc
        counts['unknown'][message_text('msg.fork_subagent_vendor_hidden_state_and_native_resume_compatibility')] = 1
        warnings += [message_text('msg.the_preview_describes_the_file_conversion_it_installs_no_tools_and_runs_no_histo'), message_text('msg.mapped_tool_names_do_not_mean_the_arguments_and_interfaces_are_compatible')]
        if target == 'codex':
            warnings.append(message_text('msg.the_codex_desktop_sqlite_index_is_not_updated'))
        if target == 'claude':
            warnings.append(message_text('msg.thinking_signatures_billing_info_and_client_hidden_fields_are_not_preserved_nati'))
    findings = sensitive.scan_conversation(conv)
    if findings['total']:
        if options.get('redact_secrets'):
            warnings.append(message_text('msg.detected_value_suspected_secrets_value2_writes_will_replace_them_with_redacted_type', value=findings['total'], value2=sensitive.summary_line(findings)))
        elif native:
            warnings.append(message_text('msg.detected_value_suspected_secrets_value2_native_migration_copies_session_files_unchanged_an', value=findings['total'], value2=sensitive.summary_line(findings)))
        else:
            warnings.append(message_text('msg.detected_value_suspected_secrets_value2_migration_copies_them_into_the_target_app_unchange', value=findings['total'], value2=sensitive.summary_line(findings)))
    evidence = conv.to_dict()
    return dict(ok=True, mode='native' if native else 'convert', source=conv.source, id=conv.id, target=target,
                title=conv.title, findings=findings, target_cwd=options.get('cwd') or conv.cwd, blockers=blockers,
                token=fingerprint({'conversation':evidence, 'files':source_files(conv), 'options':options, 'target':target, 'destination':destination}),
                warnings=list(dict.fromkeys(warnings)),
                **{key:[{'item':label, 'count':count} for label,count in values.items()] for key,values in counts.items()})


def conversion(source, sid, target, cwd=None, session_id=None, remap_tools=True, include_thinking=True, new_title=None, redact_secrets=False):
    from . import registry
    src, dst = registry.get(source), registry.get(target)
    if not dst.can_write:
        raise ValueError(message_text('msg.the_target_does_not_support_generic_writes'))
    options = dict(cwd=cwd, session_id=session_id, remap_tools=remap_tools, include_thinking=include_thinking, new_title=new_title)
    if redact_secrets:
        options['redact_secrets'] = True
    result = report(src.read(sid), target, options, dst.home)
    if source.startswith(('windows_', 'ubuntu_')) and not cwd:
        result['blockers'].append(message_text('msg.a_cross_system_migration_needs_a_project_directory_on_this_machine'))
    return result


def native(agent, sid, mode, cwd, session_id=None, project_path=None, dsh_compression='zstd'):
    from . import native_import
    source, target, cwd, target_name, target_os = native_import.context(mode, agent, cwd, project_path)
    conv = source.read(sid)
    options = dict(cwd=cwd, session_id=session_id, dsh_compression=dsh_compression)
    result = report(conv, target_name, options, target.home, native=True)
    result['target_os'] = target_os
    if source.source == 'dsh':
        header = conv.meta.get('header') or {}
        if header.get('version') not in (0, 4):
            result['blockers'].append(message_text('msg.dsh_only_accepts_a_complete_v4_or_a_valid_v0_seed_upgrade_in_the_source_app_firs'))
        if header.get('origin') == 'subagent':
            result['blockers'].append(message_text('msg.a_dsh_subagent_cannot_be_migrated_on_its_own'))
        if header.get('parentSession'):
            result['warnings'].append(message_text('msg.migrate_the_parent_session_first_and_keep_its_id'))
    if conv.meta.get('source_format') == 'codebuddy-ide-manifest':
        result['warnings'].append(message_text('msg.codebuddy_ide_needs_exactly_one_native_workspace_already_created_for_the_target_'))
    return result


def package(package_path, cwd, session_id=None, dsh_compression='zstd'):
    from . import archive, session_store, registry
    manifest, files = archive.read_package(package_path, session_store.KIND)
    agent = manifest.get('agent')
    if agent not in registry._ADAPTERS:
        raise ValueError(message_text('msg.unknown_native_package_source'))
    count, session = manifest.get('root_count'), manifest.get('session')
    if type(count) is not int or count not in (1, 2) or not isinstance(session, dict) or not isinstance(session.get('id'), str):
        raise ValueError(message_text('msg.invalid_session_package_metadata'))
    entry = archive.safe_name(manifest.get('entry'))
    if entry not in files or any(not any(name.startswith('root%d/' % i) for i in range(count)) for name in files):
        raise ValueError(message_text('msg.invalid_session_package_entry_or_agent_root_declaration'))
    import platform
    if platform.system() == 'Windows':
        from . import native_import
        native_import._windows_cwd(cwd)
    elif not cwd or not Path(cwd).is_absolute() or not Path(cwd).is_dir():
        raise ValueError(message_text('msg.restoring_needs_an_absolute_project_directory_that_exists_on_this_device'))
    options = dict(cwd=cwd, session_id=session_id, dsh_compression=dsh_compression)
    token = fingerprint({'manifest':manifest, 'options':options, 'destination':registry.get(agent).home})
    return {'ok':True, 'mode':'native-package', 'target':agent, 'target_cwd':cwd, 'token':token, 'blockers':[],
            'preserved':[{'item':message_text('msg.verified_native_session_files'), 'count':len(manifest['files'])}],
            'degraded':[{'item':message_text('msg.project_metadata_mapped_to_the_new_directory_2'), 'count':1}], 'dropped':[],
            'unknown':[{'item':message_text('msg.attachments_subagent_side_files_the_desktop_index_and_real_resume'), 'count':1}],
            'warnings':[message_text('msg.an_existing_id_is_never_overwritten_the_source_package_has_no_account_config_and'),
                        message_text('msg.native_format_target_workspace_and_id_clashes_are_still_checked_when_it_runs_a_s')]}
