"""Deterministic, local workflow candidates. Drafts are evidence, not instructions to execute."""

from .messages import text as message_text, lang_text
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


def extract(store=None, progress=None, cancel=None, max_documents=500, max_seconds=60, lang='zh'):
    def t(code, **params):
        return lang_text(lang, code, **params)

    if type(max_documents) is not int or not 1 <= max_documents <= 500 or not 0 < max_seconds <= 60:
        raise ValueError(message_text('err.invalid_extraction_scope'))
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
            description = t('msg.draft_description', tools=tools)
            lines = ['---', 'name: ' + name, 'description: ' + json.dumps(description, ensure_ascii=False), '---', '',
                     t('msg.draft_title'), '', t('msg.draft_conditions'), '',
                     t('msg.draft_steps_heading'), '']
            for i,(tool,shape) in enumerate(sequence,1):
                params = ', '.join('%s=<%s>' % (k,t) for k,t in shape) or t('msg.draft_params_default')
                lines.append(t('msg.draft_step', index=i, tool=tool, params=params))
            lines.extend(['', t('msg.draft_evidence_heading'), ''])
            for m in members[:20]:
                d = m['doc']
                lines.append('- [%s / %s](http://127.0.0.1:8745/?document=%s) — %s' %
                             (d['source'], corpus.digest(d['sid'])[:12], d['key'], ', '.join(m['outcomes'])))
            lines.extend(['', t('msg.draft_result_stats', stats=', '.join('%s=%d' % (k,counts[k]) for k in ('nonempty','error','empty','unknown'))), '',
                          t('msg.draft_nonempty_note'), '', t('msg.draft_checklist_heading'), '',
                          t('msg.draft_check_goal'), t('msg.draft_check_evidence'),
                          t('msg.draft_check_privacy'),
                          t('msg.draft_check_install'), ''])
            groups.append(dict(id=identity, name=name, description=description, selected=False,
                               evidence_count=len(members), evidence=[m['doc']['key'] for m in members[:20]],
                               score=len(members) * len(sequence), outcomes=dict(counts), markdown='\n'.join(lines)))
    state['candidates'] = sorted(groups, key=lambda g:g['score'], reverse=True)[:30]
    state['score_note'] = t('msg.draft_score_note')
    if progress:
        progress(dict(state))
    return state


def export_draft(markdown, directory, confirmed=False):
    if confirmed is not True:
        raise ValueError(message_text('err.edit_review_and_explicitly_confirm_the_draft_before_exporting'))
    if not isinstance(markdown, str) or len(markdown.encode('utf-8')) > 1024 * 1024:
        raise ValueError(message_text('err.draft_is_empty_or_exceeds_1_mib'))
    match = re.match(r'\A---\r?\n(.*?)\r?\n---\r?\n', markdown, re.S)
    if not match:
        raise ValueError(message_text('err.draft_requires_valid_name_description_frontmatter'))
    fields = {}
    for line in match.group(1).splitlines():
        if ':' not in line:
            raise ValueError(message_text('err.frontmatter_only_supports_single_line_fields'))
        key, value = line.split(':',1)
        if key.strip() not in ('name','description') or key.strip() in fields:
            raise ValueError(message_text('err.frontmatter_only_allows_unique_name_and_description_fields'))
        value = value.strip()
        if value.startswith('"'):
            try:
                value = json.loads(value)
            except ValueError as exc:
                raise ValueError(message_text('err.invalid_frontmatter_quotes')) from exc
        elif value.startswith("'") and value.endswith("'"):
            value = value[1:-1].replace("''", "'")
        elif any(c in value for c in ':#{}[]&*!|>@`'):
            raise ValueError(message_text('err.use_json_double_quotes_when_description_contains_yaml_special_characters'))
        fields[key.strip()] = value
    name, description = fields.get('name',''), fields.get('description','')
    if not isinstance(name,str) or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', name) or len(name)>64:
        raise ValueError(message_text('err.name_requires_lowercase_letters_digits_and_single_hyphens_at_most_64_characters'))
    archive_name = name + '/SKILL.md'
    from .archive import safe_name
    safe_name(archive_name)
    if not isinstance(description,str) or not description.strip() or len(description)>1024:
        raise ValueError(message_text('err.description_must_be_a_nonempty_single_line_of_at_most_1024_characters'))
    if '\n' in description or '\r' in description:
        raise ValueError(message_text('err.description_must_be_a_single_line'))
    # Canonical YAML strings avoid bare names/descriptions such as null/true/123
    # becoming non-string YAML values in the target software.
    markdown = '---\nname: ' + json.dumps(name) + '\ndescription: ' + json.dumps(description,ensure_ascii=False) + '\n---\n' + markdown[match.end():]
    if not isinstance(directory,str) or not directory:
        raise ValueError(message_text('err.select_an_export_directory'))
    parent = Path(directory).expanduser()
    if not parent.is_absolute() or not parent.is_dir():
        raise ValueError(message_text('err.export_parent_must_be_an_existing_absolute_local_directory'))
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
