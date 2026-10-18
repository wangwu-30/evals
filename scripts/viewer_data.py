"""Public viewer projection. Source batches are immutable; never copy data wholesale."""
import collections
import copy
import hashlib
import json
import re
import statistics as st
from urllib.parse import quote, urlencode

FAIL_LABELS = {
    'model_timeout': '超时', 'model_no_answer': '没返回答案',
    'model_empty': '空回答', 'model_truncated': '被截断',
    'infra_api': '接口失败', 'infra_harness': '测试框架失败',
    'infra_not_sent': '请求没到模型',
}
SECRET_PATTERNS = {
    'api_key': re.compile(r'\b(?:sk-[\w-]{16,}|AKIA[A-Z0-9]{16}|AIza[\w-]{30,}|gh[pousr]_[\w]{20,}|github_pat_[\w]{20,}|xox[baprs]-[\w-]{15,})'),
    'bearer': re.compile(r'(?i)\bbearer\s+[A-Za-z0-9_~+./=-]{8,}'),
    'jwt': re.compile(r'\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}'),
    'private_key': re.compile(r'-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----'),
    'credential_assignment': re.compile(r'''(?ix)["']?\b(?:password|passwd|secret|api[_-]?key|refresh[_-]?token|access[_-]?token)["']?\s*[:=]\s*["']?[^\s"',;}]{4,}'''),
    'credential_file': re.compile(r'(?i)(?:auth\.json|(?:^|[\s/])\.env)\s*[:=\n{]|["\']tokens["\']\s*:\s*\{'),
}


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from strings(item)


def secret_categories(value):
    """Return category names only. Never include matched content in diagnostics."""
    texts = list(strings(value)) + [json.dumps(value, ensure_ascii=False)]
    return sorted({name for s in texts for name, pattern in SECRET_PATTERNS.items() if pattern.search(s)})


def restricted_eval(ev):
    text = ' '.join(str(ev.get(k, '')) for k in ('id', 'badge', 'scope', 'visibility')).lower()
    return ev.get('kind') == 'summary' or any(k in text for k in ('hpo', 'company', '公司'))


def hidden_record(ev, record, holdout_ids=()):
    raw = record.get('raw') or {}
    tags = list(strings([{k: record.get(k) for k in ('labels', 'tags', 'split', 'visibility')},
                         {k: raw.get(k) for k in ('labels', 'tags', 'split', 'visibility')}]))
    item = str(record.get('item', record.get('task_id', '')))
    if item in holdout_ids or re.search(r'holdout|留出集|保留题', item, re.I):
        return 'holdout'
    if any(re.search(r'holdout|留出集|保留集', t, re.I) for t in tags):
        return 'holdout'
    if ev.get('split') == 'holdout':
        return 'holdout'
    if 'teamrecall' in ev.get('id', '').lower() and any('private' in t.lower() for t in tags):
        return 'private'
    for answer in (record.get('raw') or {}).get('answers', []):
        reason = hidden_record(ev, answer, holdout_ids)
        if reason:
            return reason
    return None


def length_units(text):
    return len(re.findall(r'[\u3400-\u9fff\uf900-\ufaff]', text)) + len(re.findall(r"[A-Za-z0-9]+(?:['’.-][A-Za-z0-9]+)*", text))


def infer_failure(record, text=None, has_text=False):
    raw = record.get('raw') or {}
    if 'fail_type' in record or 'fail_type' in raw:
        failure = record.get('fail_type', raw.get('fail_type')) or ''
        if failure and failure not in FAIL_LABELS:
            raise ValueError('Invalid failure type')
        return failure, False
    stop = record.get('stop_reason', raw.get('stop_reason'))
    rc = record.get('rc', raw.get('rc'))
    latency = record.get('latency_s', raw.get('latency_s')) or 0
    cap = record.get('timeout_s', raw.get('timeout_s', 900)) or 900
    if stop in ('max_tokens', 'length'):
        return 'model_truncated', True
    if rc == -9 or latency >= cap:
        return 'model_timeout', True
    if rc not in (None, 0) or record.get('ok') is False:
        return 'model_no_answer', True
    if has_text and not (text or '').strip():
        return 'model_empty', True
    # Missing storage is not evidence of an empty model response.
    return '', False


def output_of(record):
    if 'text' in record:
        return record.get('text') or '', True
    raw = record.get('raw') or {}
    return raw.get('output') or '', 'output' in raw


def backfill(batches, target, source, required=None):
    by_id = {m['id']: rs for m, rs in batches}
    if target not in by_id:
        return {'target': target, 'matched': 0, 'total': 0}
    index = collections.defaultdict(list)
    key = lambda r: (r.get('model'), r.get('cond'), r.get('rep'), r.get('latency_s'))
    for r in by_id.get(source, []):
        if output_of(r)[1]:
            index[key(r)].append(r)
    matched = 0
    for r in by_id[target]:
        candidates = index[key(r)]
        if len(candidates) == 1 and key(r)[-1] is not None:
            r['text'] = output_of(candidates[0])[0]
            r['text_source'] = source
            matched += 1
    if required is not None and matched < required:
        raise ValueError(f'Backfill {target}: {matched}/{required}; refusing incomplete source match')
    return {'target': target, 'matched': matched, 'total': len(by_id[target])}


def normalize(record):
    text, present = output_of(record)
    failure, inferred = infer_failure(record, text, present)
    raw = record.get('raw') or {}
    checks = record.get('checks') or raw.get('checks') or {}
    checks = {k: v if isinstance(v, bool) else str(v).startswith('PASS') for k, v in checks.items()}
    why = record.get('why') or {k: [str(v), ''] for k, v in (raw.get('checks') or {}).items()}
    score = record.get('score', record.get('correct'))
    if failure.startswith('model_'):
        score = 0
    if failure.startswith('infra_'):
        score = None
    return {
        'item': record.get('item', 'task'), 'model': record['model'], 'cond': record['cond'],
        'batch': record.get('batch', ''), 'rep': record.get('rep', 0),
        'fail_type': failure, 'legacy_failure': inferred, 'text_source': record.get('text_source', ''),
        'text': text, 'text_missing': not present, 'thinking': record.get('thinking', ''),
        'len_units': length_units(text), 'lang': 'zh' if re.search(r'[\u3400-\u9fff]', text) else 'en',
        'correct': record.get('correct'), 'note': record.get('note', ''),
        'score': score, 'total': record.get('total', 1), 'checks': checks, 'why': why,
        'out_tok': record.get('out_tok', record.get('tokens_out')),
        'in_tok': record.get('in_tok', record.get('tokens_in')),
        'stop_reason': record.get('stop_reason', raw.get('stop_reason', '')),
        'added_text': record.get('added_text', ''),
        'prompt_sha256': record.get('prompt_sha256', raw.get('prompt_sha256', '')),
    }


def summarize(runs):
    eligible = [r for r in runs if not r['fail_type'].startswith('infra_')]
    outputs = [r for r in eligible if r['text'].strip()]
    scores = [0 if r['fail_type'].startswith('model_') else r['score'] for r in eligible if r['score'] is not None or r['fail_type'].startswith('model_')]
    counts = collections.Counter(r['fail_type'] for r in runs if r['fail_type'])
    n_infra = sum(v for k, v in counts.items() if k.startswith('infra_'))
    n_model = sum(v for k, v in counts.items() if k.startswith('model_'))
    avg = lambda xs: st.mean(xs) if xs else None
    lengths = [r['len_units'] for r in outputs]
    sorted_scores = sorted(scores)
    return dict(n=len(runs), n_out=len(outputs), n_fail_model=n_model, n_fail_infra=n_infra,
                incomplete=n_infra > len(runs) * .1, mean_len_units=avg(lengths),
                mean_score=avg(scores), n_scored=len(scores),
                mean_out_tok=avg([r['out_tok'] for r in eligible if r['out_tok'] is not None]),
                trimmed_score=avg(sorted_scores[1:-1]) if len(scores) >= 3 else None,
                failures=dict(counts), legacy_failure=any(r.get('legacy_failure') for r in runs),
                n_correct=sum(r.get('correct') == 1 and not r['fail_type'] for r in eligible),
                default_rep=default_run(outputs)['rep'] if outputs else None)


def default_run(runs):
    outputs = [r for r in runs if r['text'].strip() and not r['fail_type'].startswith('infra_')]
    if not outputs:
        return None
    mean = st.mean(r['len_units'] for r in outputs)
    return min(outputs, key=lambda r: (abs(r['len_units'] - mean), r['rep']))


def failure_copy(summary):
    counts = summary['failures']
    detail = '、'.join(f'{FAIL_LABELS[k]} {v}' for k, v in counts.items() if k.startswith('model_'))
    line = f'失败分类：模型失败 {summary["n_fail_model"]} 次（{detail + "，" if detail else ""}已按 0 分算进平均）· 基础设施失败 {summary["n_fail_infra"]} 次（不算进平均）'
    if summary.get('legacy_failure'):
        line += '；旧记录没写失败类型，按模型失败算'
    return line


def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')


def url(ev, model=None, cond=None, rep=None, batch=None):
    base = ev.get('baseline', ev.get('null_cond', 'full'))
    other = ev.get('null_cond') or next((c for p in ev.get('presets', []) for c in p['conds'] if c != base), None)
    other = other or next((c for c in ev.get('cond_labels', {}) if c != base), base)
    selected = [base, cond if cond and cond != base else other]
    params = {'c': ','.join(dict.fromkeys(selected))}
    if model:
        params['m'] = model
    if rep is not None:
        params['r'] = ','.join(str(rep) if c == cond else 'auto' for c in dict.fromkeys(selected))
    if batch:
        params['b'] = batch
    return ev['id'] + '.html?' + urlencode(params)


def prepare(ev, batches, ed, audit, holdout_ids=()):
    """Filter complete source records before either aggregate or raw publication."""
    batches = copy.deepcopy(batches)
    if ev['id'] == 'daily-skill':
        for target, source, required in (
            ('2026-10-12-box-rescored', '2026-10-12-box-pilot', 165),
            ('2026-10-12-macmini-final', '2026-10-12-macmini-cli-partial', None),
        ):
            result = backfill(batches, target, source, required)
            audit['backfills'].append(result)
            print('backfill', json.dumps(result))
    prompts = {}
    for path in (ed / 'batches').glob('*prompts.jsonl'):
        for line in path.read_text().splitlines():
            p = json.loads(line)
            if hashlib.sha256(p['text'].encode()).hexdigest() != p['sha256']:
                raise ValueError('Prompt hash mismatch')
            prompts[p['sha256']] = p['text']
    accepted = []
    for meta, records in batches:
        clean = []
        for r in records:
            audit['scanned'] += 1
            reason = hidden_record(ev, r, holdout_ids)
            if reason:
                audit['dropped'][reason] += 1
                continue
            prompt_hash = r.get('prompt_sha256', (r.get('raw') or {}).get('prompt_sha256'))
            categories = secret_categories([r, prompts.get(prompt_hash, '')])
            if categories:
                audit['dropped_records'] += 1
                audit['dropped'].update(categories)
                continue
            r['batch'] = meta['id']
            r['_viewer'] = normalize(r)
            r['_viewer']['prompt_text'] = prompts.get(r['_viewer']['prompt_sha256'], '')
            r['score'] = r['_viewer']['score']
            clean.append(r)
        accepted.append((meta, clean))
    return accepted, prompts


def emit(ev, batches, ed, out, prompts, holdout_ids=()):
    if restricted_eval(ev) or ev['kind'] != 'matrix':
        return None
    tasks_file = ed / 'tasks.json'
    tasks = json.loads(tasks_file.read_text()) if tasks_file.exists() else {'task': {'prompt': (ed / ev['task_file']).read_text() if ev.get('task_file') else ev['description']}}
    tasks = {k: {'prompt': v['prompt']} for k, v in tasks.items() if not hidden_record(ev, {'item': k}, holdout_ids)}
    if secret_categories(tasks):
        raise ValueError('Unsafe task metadata; refusing viewer publication')
    latest = {}
    for meta, records in batches:
        for r in records:
            latest[r['model']] = meta['id']
    groups = collections.defaultdict(list)
    history = collections.defaultdict(list)
    for meta, records in batches:
        for record in records:
            r = record['_viewer']
            assert not hidden_record(ev, r, holdout_ids), 'Holdout item reached public projection'
            history[(meta['id'], r['model'], r['item'], r['cond'])].append(r)
            if latest[r['model']] == meta['id']:
                groups[(r['model'], r['item'], r['cond'])].append(r)
    if not any(r['text'] for runs in history.values() for r in runs):
        return None
    index = dict(id=ev['id'], title=ev['title'], baseline=ev.get('baseline', 'full'),
                 default_cond=ev.get('null_cond'), cond_labels=ev.get('cond_labels', {}),
                 model_labels=ev.get('model_labels', {}), check_labels=ev.get('check_labels', {}),
                 conditions=ev.get('conditions', {}), presets=ev.get('presets', []),
                 tasks=tasks, models=sorted(latest), latest=latest, selections={}, history={},
                 has_current_text=any(r['text'] for runs in groups.values() for r in runs))
    for mapping, is_history in ((groups, False), (history, True)):
        for key, runs in mapping.items():
            if is_history and key[0] == latest[key[1]]:
                continue  # The current batch uses the ordinary selection URL.
            parts = list(key)
            if is_history:
                parts = ['batches'] + parts
            rel = '/'.join(quote(str(x), safe='') for x in parts) + '.json'
            payload = {'summary': summarize(runs), 'runs': runs}
            # Prefix/magic prompts need only the condition-related added text. The
            # whole hash-verified prompt remains in the source, never in a shell.
            if len(json.dumps(payload, ensure_ascii=False).encode()) > 48000:
                metadata = []
                for r in runs:
                    run_rel = rel[:-5] + '.runs/' + quote(str(r['rep']), safe='') + '.json'
                    dump(out / 'c' / ev['id'] / run_rel, r)
                    light = {k: value for k, value in r.items() if k not in ('text', 'thinking', 'why', 'model', 'item', 'cond', 'batch', 'prompt_sha256', 'prompt_text')}
                    light.update(text='', thinking='', why={}, has_text=bool(r['text'].strip()), text_url=ev['id'] + '/' + quote(run_rel, safe='/'))
                    metadata.append(light)
                payload['runs'] = metadata
            dump(out / 'c' / ev['id'] / rel, payload)
            target = index['history'] if is_history else index['selections']
            target['|'.join(map(str, key))] = {'path': ev['id'] + '/' + quote(rel, safe='/'), 'summary': {'mean_len_units': payload['summary']['mean_len_units']}}
    dump(out / 'c' / (ev['id'] + '.index.json'), index)
    return index
