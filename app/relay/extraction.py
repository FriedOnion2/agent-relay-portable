"""Deterministic, local workflow candidates. Drafts are evidence, not instructions to execute."""
import collections
import json
import re
import time
from pathlib import Path

from . import corpus, ir
from .adapters.base import ToolNameMap

MAX_SEGMENTS = 2000
MAX_COMPARISONS = 50000
PARAMETERS = {'command','cmd','path','file_path','pattern','query','cwd','timeout','content','old_string','new_string','url'}


def _call(block):
    name = block.get('name', '').split('.')[-1]
    aliases = {**{k.lower():v.lower() for k,v in ToolNameMap.TO_CANONICAL.items()},
               **{v.lower():k.lower() for k,v in ToolNameMap.TO_DSH.items()}}
    name = aliases.get(name.lower(), name.lower())
    # Never copy arbitrary command text, paths, environment variables or secret values.
    name = name if re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', name) else 'external-tool'
    try:
        args = json.loads(block.get('arguments') or '{}')
    except (ValueError, TypeError):
        args = {}
    shape = tuple(sorted((k, type(v).__name__) for k,v in args.items() if k in PARAMETERS)) if isinstance(args, dict) else ()
    return name, shape


def _segments(doc):
    prompt, calls, results = '', [], {}
    def finish():
        if len(calls) < 2 or not prompt:
            return None
        return dict(doc=doc, keywords=set(corpus.terms(prompt[:1000])), sequence=tuple(_call(b) for b in calls),
                    outcomes=[results.get(b.get('call_id'), 'unknown') for b in calls])
    for turn in doc['conversation']['turns']:
        # A tool-result user turn is not a new human request.
        request = '\n'.join(b.get('text','') for b in turn['blocks'] if b['kind'] == ir.TEXT)
        if turn['role'] == ir.USER and request:
            value = finish()
            if value:
                yield value
            prompt, calls, results = request, [], {}
        for b in turn['blocks']:
            if b['kind'] == ir.TOOL_CALL:
                calls.append(b)
            elif b['kind'] == ir.TOOL_RESULT:
                if b.get('call_id'):
                    results[b['call_id']] = 'error' if b.get('is_error') else 'nonempty' if b.get('output','').strip() else 'empty'
        if len(calls) > 64:
            # An oversized sequence is not shortened into apparently complete evidence.
            prompt, calls, results = '', [], {}
    value = finish()
    if value:
        yield value


def extract(store=None, progress=None, cancel=None, max_documents=500, max_seconds=60):
    if type(max_documents) is not int or not 1 <= max_documents <= 500 or not 0 < max_seconds <= 60:
        raise ValueError('提炼范围无效')
    store = store or corpus.Corpus()
    state = dict(ok=True, processed=0, segments=0, comparisons=0, candidates=[], limited=False, canceled=False)
    start = time.monotonic()
    def stop():
        state['canceled'] = bool(cancel and cancel.is_set())
        expired = time.monotonic() - start >= max_seconds
        state['limited'] |= expired
        return state['canceled'] or expired
    buckets = collections.defaultdict(list)
    if stop():
        return state
    for doc in store.evidence(max_documents + 1):
        if state['processed'] >= max_documents:
            state['limited'] = True
            break
        if stop():
            break
        state['processed'] += 1
        for segment in _segments(doc):
            if state['segments'] >= MAX_SEGMENTS or stop():
                state['limited'] = True
                break
            state['segments'] += 1
            buckets[segment['sequence']].append(segment)
        if progress:
            progress(dict(state))
        if state['segments'] >= MAX_SEGMENTS:
            break
    groups = []
    for sequence, segments in buckets.items():
        if stop() or state['comparisons'] >= MAX_COMPARISONS:
            break
        # Exact abstract tool sequence + similar request vocabulary. Every member
        # must resemble the seed; transitive chaining cannot join unrelated tasks.
        for seed in segments:
            if stop() or state['comparisons'] >= MAX_COMPARISONS:
                break
            evidence = {}
            for other in segments:
                if state['comparisons'] >= MAX_COMPARISONS:
                    state['limited'] = True
                    break
                state['comparisons'] += 1
                a, b = seed['keywords'], other['keywords']
                overlap = len(a & b) / max(1, min(len(a),len(b)))
                if overlap >= .6 and len(a & b) >= 2:
                    canonical = other['doc']['canonical']
                    evidence.setdefault(canonical, other)
            # Distinct native session IDs count once, including revised copies.
            independent = {}
            for item in evidence.values():
                d = item['doc']; native = re.sub(r'^(windows_|ubuntu_)','',d['source'])
                independent.setdefault(('claude' if native == 'claude_sdk' else native, d['conversation']['id']), item)
            members = list(independent.values())
            if len(members) < 3 or all(all(v == 'error' for v in m['outcomes']) for m in members):
                continue
            identity = corpus.digest([sequence, sorted(m['doc']['canonical'] for m in members)])
            if any(g['id'] == identity for g in groups):
                continue
            counts = collections.Counter(v for m in members for v in m['outcomes'])
            name = 'workflow-' + identity[:12]
            tools = ', '.join(dict.fromkeys(n for n,shape in sequence))
            description = '当需要复现包含 %s 的重复工作流时使用；先核对证据和项目约束。' % tools
            lines = ['---', 'name: ' + name, 'description: ' + json.dumps(description, ensure_ascii=False), '---', '',
                     '# 待审核的工作流草稿', '', '适用条件：用户任务与下列证据中的目标相同；请先补充明确的触发条件。', '',
                     '## 抽象流程', '']
            for i,(tool,shape) in enumerate(sequence,1):
                params = ', '.join('%s=<%s>' % (k,t) for k,t in shape) or '由用户提供并核对参数'
                lines.append('%d. 使用 `%s`；%s。检查返回状态，再决定下一步。' % (i,tool,params))
            lines.extend(['', '## 证据', ''])
            for m in members[:20]:
                d = m['doc']
                lines.append('- [%s / %s](http://127.0.0.1:8745/?document=%s) — %s' %
                             (d['source'], corpus.digest(d['sid'])[:12], d['key'], ', '.join(m['outcomes'])))
            lines.extend(['', '工具结果统计：' + ', '.join('%s=%d' % (k,counts[k]) for k in ('nonempty','error','empty','unknown')), '',
                          'nonempty 仅表示有非空且未标错的工具返回，不证明任务成功。', '', '## 待检查项', '',
                          '- [ ] 补充任务目标、适用条件及成功判据。', '- [ ] 核对所有证据，剔除失败步骤和不适用分支。',
                          '- [ ] 用占位参数替换设备路径；检查账号、密钥和个人信息。',
                          '- [ ] 在目标设备审核后另行安装；本工具不执行此草稿。', ''])
            groups.append(dict(id=identity, name=name, description=description, selected=False,
                               evidence_count=len(members), evidence=[m['doc']['key'] for m in members[:20]],
                               score=len(members) * len(sequence), outcomes=dict(counts), markdown='\n'.join(lines)))
    state['candidates'] = sorted(groups, key=lambda g:g['score'], reverse=True)[:30]
    state['score_note'] = '排序分 = 独立会话数 × 抽象步骤数，不是成功概率。最多扫描500份完整缓存会话。'
    if progress:
        progress(dict(state))
    return state


def export_draft(markdown, directory, confirmed=False):
    if confirmed is not True:
        raise ValueError('请先编辑审核并明确确认导出草稿')
    if not isinstance(markdown, str) or len(markdown.encode('utf-8')) > 1024 * 1024:
        raise ValueError('草稿为空或超过 1 MiB')
    match = re.match(r'\A---\r?\n(.*?)\r?\n---\r?\n', markdown, re.S)
    if not match:
        raise ValueError('草稿需要有效的 name / description frontmatter')
    fields = {}
    for line in match.group(1).splitlines():
        if ':' not in line:
            raise ValueError('frontmatter 仅支持单行字段')
        key, value = line.split(':',1)
        if key.strip() not in ('name','description') or key.strip() in fields:
            raise ValueError('frontmatter 只允许唯一的 name 和 description')
        value = value.strip()
        if value.startswith('"'):
            try:
                value = json.loads(value)
            except ValueError:
                raise ValueError('frontmatter 引号无效')
        elif value.startswith("'") and value.endswith("'"):
            value = value[1:-1].replace("''", "'")
        elif any(c in value for c in ':#{}[]&*!|>@`'):
            raise ValueError('description 含 YAML 特殊字符时请使用 JSON 双引号')
        fields[key.strip()] = value
    name, description = fields.get('name',''), fields.get('description','')
    if not isinstance(name,str) or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', name) or len(name)>64:
        raise ValueError('name 需要不超过64字符的小写字母数字和单连字符')
    archive_name = name + '/SKILL.md'
    from .archive import safe_name
    safe_name(archive_name)
    if not isinstance(description,str) or not description.strip() or len(description)>1024:
        raise ValueError('description 必须是非空单行说明，最多1024字符')
    if '\n' in description or '\r' in description:
        raise ValueError('description 必须是单行')
    # Canonical YAML strings avoid bare names/descriptions such as null/true/123
    # becoming non-string YAML values in the target software.
    markdown = '---\nname: ' + json.dumps(name) + '\ndescription: ' + json.dumps(description,ensure_ascii=False) + '\n---\n' + markdown[match.end():]
    if not isinstance(directory,str) or not directory:
        raise ValueError('请选择导出目录')
    parent = Path(directory).expanduser()
    if not parent.is_absolute() or not parent.is_dir():
        raise ValueError('导出父目录必须是本机存在的绝对目录')
    target = parent.resolve() / name
    target.mkdir()  # Exclusive, never replace an installed or earlier Skill.
    try:
        with (target / 'SKILL.md').open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(markdown)
    except Exception:
        # Remove only files created by this operation, never recursively delete.
        path = target / 'SKILL.md'
        if path.is_file():
            path.unlink()
        target.rmdir()
        raise
    return dict(ok=True, path=str(target / 'SKILL.md'), name=name)
