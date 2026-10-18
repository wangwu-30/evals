"""Offline append-only import of the supplied public synthetic sweep export.

Usage: python3 scripts/import_minimax.py <directory containing mm1017-*>
Does not import or execute the original runners or call a model API.
"""
import collections
import hashlib
import json
from pathlib import Path
import sys
from viewer_data import secret_categories, infer_failure

FAMILIES = dict(none='不加话', idcard='虚构号码', name='姓名', role='角色',
                personality='性格', emoji='表情', rare_cjk='生僻字', garbage='不可见与特殊字符',
                special='特殊符号', repeat='重复文字', famous='名人')
MAGIC = dict(think='仔细思考', step='一步一步思考', lets='一起逐步思考', expert='顶级专家',
             career='职业生涯', tip='小费', breath='深呼吸', threat='答错的后果')


def import_one(source, dest, kind):
    if dest.exists():
        raise ValueError('Destination already exists; append-only import')
    read = lambda f: [json.loads(l) for l in (source / f).read_text().splitlines() if l.strip()]
    raw, grades = read('raw.jsonl'), read('raw_graded.jsonl')
    grades = {r['key']: r for r in grades}
    prompts = {p['sha256']: p for p in read('prompts.jsonl')}
    tasks = json.loads((source / 'shared/tasks.json').read_text())
    for p in prompts.values():
        assert hashlib.sha256(p['text'].encode()).hexdigest() == p['sha256'], 'Prompt hash mismatch'
    # The supplied task catalog omits two open questions and includes one unused
    # task. Recover only unanimous baseline prompts from the verified archive.
    items = {r['item'] for r in raw}
    for item in items - tasks.keys():
        values = {prompts[r['prompt_sha256']]['text'] for r in raw if r['item'] == item and r['cond'] == 'none'}
        assert len(values) == 1, 'Ambiguous baseline task prompt'
        tasks[item] = {'prompt': values.pop(), 'type': 'open'}
    tasks = {k: v for k, v in tasks.items() if k in items}
    labels, conditions, records, dropped = {}, {}, [], collections.Counter()
    for r in raw:
        cats = secret_categories([r, grades[r['key']], prompts[r['prompt_sha256']], tasks[r['item']]])
        if cats:
            dropped.update(cats)
            continue
        cond = r['cond'] + ('@t0' if r['arm'] == 't0' else '')
        fam = r['family']
        place = 'none' if r['cond'] == 'none' else ('suffix' if r['cond'].endswith('@suffix') else 'prefix')
        if kind == 'prefix':
            label = FAMILIES[fam] + (r['cond'][len(fam):] if fam != 'none' else '')
            family = FAMILIES[fam]
        else:
            label = '不加话' if fam == 'none' else ('中文' if fam.startswith('zh_') else '英文') + '·' + MAGIC[fam.split('_')[1]] + ('·题末' if place == 'suffix' else '·题前')
            family = '不加话' if fam == 'none' else MAGIC[fam.split('_')[1]]
        if r['arm'] == 't0':
            label += ' · 温度 0'
            family = '温度 0'
        labels[cond] = label
        conditions[cond] = dict(family=family, place=place, temp=r['temp'], arm=r['arm'])
        grade = grades[r['key']]
        record = {k: r.get(k) for k in ('item', 'family', 'arm', 'temp', 'rep', 'ok', 'text', 'thinking', 'usage', 'stop_reason', 'attempts', 'prompt_sha256', 'added_text')}
        record.update(model=r['resp_model'], cond=cond, correct=grade['correct'], note=grade['note'],
                      out_tok=grade['out_tok'], in_tok=grade['in_total'], score=grade['correct'], total=1,
                      fail_type=infer_failure(r, r['text'], True)[0], text_source='')
        records.append(record)
    assert len(records) == (4578 if kind == 'prefix' else 2520), 'Import scan/count failed; no files written'
    ordered = sorted(labels, key=lambda c: (c.endswith('@t0'), c != 'none', c))
    presets = [dict(label='名人', conds=['famous1', 'famous2'])] if kind == 'prefix' else [dict(label='一步一步思考', conds=['zh_step@suffix', 'zh_step@prefix'])]
    ev = dict(id=dest.name, title='MiniMax 前缀' if kind == 'prefix' else 'MiniMax 加一句话', kind='matrix',
              order=4 if kind == 'prefix' else 5, baseline='none', description='公开合成题，比较同一道题加不同的话后的回答。',
              cond_labels={c: labels[c] for c in ordered}, conditions=conditions, presets=presets,
              model_labels={}, check_labels={}, conclusion=(
                  '名人条件的回答长度有变化；各条件组的正确率差异未通过多重比较校正。' if kind == 'prefix' else
                  '中文「一步一步思考」放在题末，回答长度有变化；正确率差异未通过多重比较校正。'))
    batch = '2026-10-17-public'
    bd = dest / 'batches'
    bd.mkdir(parents=True)
    write = lambda path, obj: path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')
    write(dest / 'eval.json', ev)
    write(dest / 'tasks.json', {k: {'prompt': v['prompt'], 'type': v['type']} for k, v in tasks.items()})
    # Preserve the corrected analysis as a source artifact, not a fresh analysis.
    summary = json.loads((source / 'SUMMARY.json').read_text())
    assert not secret_categories(summary)
    write(dest / 'analysis.json', summary)
    write(bd / (batch + '.meta.json'), dict(id=batch, date='2026-10-17', models=['MiniMax-M3'],
          n_records=len(records), env='公开合成题', notes='离线导入；未重新调用模型。'))
    (bd / (batch + '.jsonl')).write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in records))
    used = {r['prompt_sha256'] for r in records}
    (bd / 'prompts.jsonl').write_text(''.join(json.dumps(prompts[h], ensure_ascii=False) + '\n' for h in sorted(used)))
    print(json.dumps(dict(eval=dest.name, scanned=len(raw), imported=len(records), dropped=dict(dropped), prompts=len(used))))


if __name__ == '__main__':
    for kind in ('prefix', 'magic'):
        import_one(Path(sys.argv[1]) / ('mm1017-' + kind), Path(__file__).resolve().parent.parent / 'data/evals' / ('mm1017-' + kind), kind)
