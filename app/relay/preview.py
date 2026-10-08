"""Side-effect-free migration reports and source/option consistency tokens."""
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
        raise ValueError('源内容、目标目录或选项已变化，请重新预览后确认')


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
            raise ValueError('预览源文件超过存储包限制')
        result[str(item)] = hashlib.sha256(raw).hexdigest()
    return result


def report(conv, target, options, destination, native=False):
    counts = {key:Counter() for key in ('preserved', 'degraded', 'dropped', 'unknown')}
    warnings = list(conv.meta.get('notes', []))
    blockers = []
    if conv.truncated:
        blockers.append('源会话不完整，不能迁移')
    if not conv.turns and not native:
        blockers.append('源会话没有可迁移的内容（文件为空或无法解析）')
    if native:
        counts['preserved']['原生记录（保留原始格式）'] = len(conv.turns)
        counts['degraded']['当前项目元数据映射到新目录'] = 1
        counts['unknown']['附件、旁路子代理、应用数据库与完整续聊状态'] = 1
        warnings += ['历史正文和工具参数内的旧路径不自动重写。', '同 ID 拒绝覆盖；目标软件实际续聊需单独核对。']
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
                category, label = 'preserved', {ir.TEXT:'正文', ir.TOOL_CALL:'工具调用',
                    ir.TOOL_RESULT:'工具结果', ir.THINKING:'思考', ir.IMAGE:'图像', ir.RAW:'原始块'}.get(b.kind, b.kind)
                if target != 'dsh' and turn.role not in (ir.USER, ir.ASSISTANT):
                    category, label = 'dropped', '来源系统上下文'
                elif b.kind == ir.RAW:
                    category, label = 'degraded', '未知内容块转带标注文本'
                elif target != 'dsh' and turn.role == ir.USER and b.kind not in (ir.TEXT, ir.IMAGE):
                    category, label = 'dropped', '用户轮中的 ' + b.kind
                elif b.kind == ir.THINKING:
                    if not options.get('include_thinking', True):
                        category, label = 'dropped', '思考（按选项排除）'
                    else:
                        category, label = 'degraded', '可读思考文本；签名及加密状态不保留'
                elif b.kind == ir.IMAGE:
                    if target == 'dsh' or (turn.role == ir.USER and b.text):
                        category, label = 'degraded', '图片描述/元数据；不保留原生图片功能'
                    else:
                        category, label = 'dropped', '图片与二进制图像内容'
                elif target == 'dsh' and b.kind in (ir.TOOL_CALL, ir.TOOL_RESULT) and id(b) not in paired:
                    category, label = 'degraded', '未配对或重复工具记录转历史文本'
                elif target == 'dsh' and turn.role == ir.SYSTEM:
                    category, label = 'degraded', '来源系统上下文转带标注消息'
                elif b.kind == ir.TOOL_CALL and ToolNameMap.convert(b.name, target, options.get('remap_tools', True)) != b.name:
                    category, label = 'degraded', '工具名映射；参数不转换'
                elif b.kind not in (ir.TEXT, ir.TOOL_CALL, ir.TOOL_RESULT):
                    category, label = 'unknown', '未知块 ' + b.kind
                counts[category][label] += 1
        enc = (conv.meta or {}).get('encrypted_reasoning', 0)
        if enc:
            counts['dropped']['加密思考（来源已加密，无法读取）'] += enc
        counts['unknown']['fork / subagent、厂商隐藏状态与原生续聊兼容性'] = 1
        warnings += ['预览描述文件转换效果，不会安装工具或执行历史调用。', '工具名映射不代表工具参数与接口兼容。']
        if target == 'codex':
            warnings.append('不会更新 Codex Desktop SQLite 索引。')
        if target == 'claude':
            warnings.append('思考签名、计费信息和客户端隐藏字段不会原生保真。')
    secrets = sensitive.scan_conversation(conv)
    if secrets['total']:
        if options.get('redact_secrets'):
            warnings.append('检测到 %d 处疑似敏感信息（%s），写入时将替换为 [REDACTED:类型]。' % (secrets['total'], sensitive.summary_line(secrets)))
        elif native:
            warnings.append('检测到 %d 处疑似敏感信息（%s）：原生迁移原样复制会话文件，不支持脱敏。' % (secrets['total'], sensitive.summary_line(secrets)))
        else:
            warnings.append('检测到 %d 处疑似敏感信息（%s）：迁移会原样复制到目标软件。可勾选「脱敏密钥」或加 --redact-secrets。' % (secrets['total'], sensitive.summary_line(secrets)))
    evidence = conv.to_dict()
    return dict(ok=True, mode='native' if native else 'convert', source=conv.source, id=conv.id, target=target,
                title=conv.title, secrets=secrets, target_cwd=options.get('cwd') or conv.cwd, blockers=blockers,
                token=fingerprint({'conversation':evidence, 'files':source_files(conv), 'options':options, 'target':target, 'destination':destination}),
                warnings=list(dict.fromkeys(warnings)),
                **{key:[{'item':label, 'count':count} for label,count in values.items()] for key,values in counts.items()})


def conversion(source, sid, target, cwd=None, session_id=None, remap_tools=True, include_thinking=True, new_title=None, redact_secrets=False):
    from . import registry
    src, dst = registry.get(source), registry.get(target)
    if not dst.can_write:
        raise ValueError('目标不支持通用写入')
    options = dict(cwd=cwd, session_id=session_id, remap_tools=remap_tools, include_thinking=include_thinking, new_title=new_title)
    if redact_secrets:
        options['redact_secrets'] = True
    result = report(src.read(sid), target, options, dst.home)
    if source.startswith(('windows_', 'ubuntu_')) and not cwd:
        result['blockers'].append('跨系统迁移必须指定本机项目目录')
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
            result['blockers'].append('DSH 仅接受完整 v4 或有效 v0 seed；先在源软件升级')
        if header.get('origin') == 'subagent':
            result['blockers'].append('DSH 子代理不能单独迁入')
        if header.get('parentSession'):
            result['warnings'].append('先迁入父会话并保留其 ID。')
    if conv.meta.get('source_format') == 'codebuddy-ide-manifest':
        result['warnings'].append('CodeBuddy IDE 必须已在目标项目创建唯一原生工作区。')
    return result


def package(package_path, cwd, session_id=None, dsh_compression='zstd'):
    from . import archive, session_store, registry
    manifest, files = archive.read_package(package_path, session_store.KIND)
    agent = manifest.get('agent')
    if agent not in registry._ADAPTERS:
        raise ValueError('未知的原生存储包来源')
    count, session = manifest.get('root_count'), manifest.get('session')
    if type(count) is not int or count not in (1, 2) or not isinstance(session, dict) or not isinstance(session.get('id'), str):
        raise ValueError('会话包元数据无效')
    entry = archive.safe_name(manifest.get('entry'))
    if entry not in files or any(not any(name.startswith('root%d/' % i) for i in range(count)) for name in files):
        raise ValueError('会话包入口或 Agent 根目录声明无效')
    import platform
    if platform.system() == 'Windows':
        from . import native_import
        native_import._windows_cwd(cwd)
    elif not cwd or not Path(cwd).is_absolute() or not Path(cwd).is_dir():
        raise ValueError('恢复需要当前设备上存在的绝对项目目录')
    options = dict(cwd=cwd, session_id=session_id, dsh_compression=dsh_compression)
    token = fingerprint({'manifest':manifest, 'options':options, 'destination':registry.get(agent).home})
    return {'ok':True, 'mode':'native-package', 'target':agent, 'target_cwd':cwd, 'token':token, 'blockers':[],
            'preserved':[{'item':'已校验的原生会话文件', 'count':len(manifest['files'])}],
            'degraded':[{'item':'项目元数据映射到新目录', 'count':1}], 'dropped':[],
            'unknown':[{'item':'附件、子代理旁路文件、Desktop 索引与实际续聊', 'count':1}],
            'warnings':['同 ID 不覆盖；源包不含账号配置，历史正文和工具参数中的路径保持原样。',
                        '执行时仍检查原生格式、目标工作区与 ID 冲突；预览成功不代表所有恢复条件已满足。']}
