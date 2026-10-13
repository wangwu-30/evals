"""Re-score immutable CLI outputs and reproduce trimmed means/paired bootstrap.

Every cell's n is five whole-batch repetitions, NOT number of answers/checks.
Bootstrap jointly samples task IDs and repetition IDs, preserving matched IDs
across full/ablation. All statistics use the same trim-one-each estimator.
"""
import argparse
import collections
import hashlib
import json
import pathlib
import random
import statistics
from checks import combine, rules
from run import ASSETS, ROOT, MODELS, JUDGES, JUDGMENT_FOLDER, conditions, load


def trimmed(xs):
    xs = sorted(xs)
    if len(xs) < 5:
        raise ValueError('No published cell may have fewer than five repetitions')
    return statistics.mean(xs[1:-1])


def quantile(xs,p):
    x = (len(xs)-1)*p
    i = int(x)
    return xs[i] + (xs[min(i+1,len(xs)-1)]-xs[i])*(x-i)


def seed(key):
    return int(hashlib.sha256(key.encode()).hexdigest()[:12],16)


def boot(a,b=None,draws=10000,key='',family=1):
    # a,b: repetition × question matrices. Sample both clusters; same draws
    # preserve paired task and repetition IDs between conditions.
    rng = random.Random(seed(key))
    nrep,ntask = len(a),len(a[0])
    estimates = []
    for _ in range(draws):
        rs = [rng.randrange(nrep) for _ in range(nrep)]
        ts = [rng.randrange(ntask) for _ in range(ntask)]
        va = [sum(a[r][t] for t in ts)/ntask for r in rs]
        d = trimmed(va)
        if b is not None:
            vb = [sum(b[r][t] for t in ts)/ntask for r in rs]
            d -= trimmed(vb)
        estimates.append(d)
    estimates.sort()
    return dict(ci95=[quantile(estimates,.025),quantile(estimates,.975)],
                simultaneous_ci=[quantile(estimates,.025/family),quantile(estimates,1-.025/family)],
                draws=draws,seed=seed(key),family=family)


def score_runs(root,tasks,split,batch):
    wanted = [t for t in tasks if t['split']==split]
    rows,cells = [],collections.defaultdict(dict)
    for gp in sorted((root/'generations').glob('*/*/*.json')):
        if gp.name.endswith('.call.json'): continue
        g = load(gp)
        jp = root/JUDGMENT_FOLDER/g['model'].replace(':','_')/g['cond']/f"{g['rep']}.json"
        j = load(jp)
        verdicts = {v['id']:v for v in j['judgments']}
        raw = []
        for t in wanted:
            answer = g['answers'][t['id']]
            checks,score = combine(t,answer,verdicts[t['id']])
            raw.append(dict(task_id=t['id'],output=answer,checks=checks,score=score,judge=verdicts[t['id']]))
        call = load(root/g['call_file'])
        jc = load(root/j['call_file'])
        checks = {f"{r['task_id']}:{k}":v for r in raw for k,v in r['checks'].items()}
        score = sum(v=='PASS' for v in checks.values())/len(checks)
        row = dict(eval={'dev':'explain','validation':'explain-validation','holdout':'explain-holdout'}[split],batch=batch,model=g['model'],
                   cond=g['cond'],rep=g['rep'],split=split,score=score,checks=checks,raw=dict(answers=raw),
                   # Cost belongs to a shared dev+validation request; do not
                   # duplicate it in both dashboard batches.
                   cost_usd=call.get('cost_usd_reported') if split=='dev' else None,
                   cost_allocation='generation only, all public tasks; judge/cost ledger separate' if split=='dev' else 'shared generation charged in explain dev batch',
                   latency_s=call['latency_s'],model_actual=call.get('actual_model'),judge_requested=j['judge_requested'],
                   judge_actual=jc.get('actual_model'),generation_call=g['call_file'],judge_call=j['call_file'],
                   prompt_sha256=g['prompt_sha256'],skill_sha256=g['skill_sha256'])
        rows.append(row)
        if g['rep'] in cells[(g['model'],g['cond'])]: raise ValueError('duplicate repetition')
        cells[(g['model'],g['cond'])][g['rep']] = [r['score'] for r in raw]
    for model in MODELS:
        for cond in conditions():
            assert sorted(cells[(model,cond)])==list(range(5)), (model,cond,'missing reps')
    return rows,cells


def stats(cells,split,draws):
    result=[]
    family=28 if split in ('dev','validation') else 14
    for (model,cond),byrep in sorted(cells.items()):
        a=[byrep[r] for r in range(5)]
        scores=[statistics.mean(x) for x in a]
        row=dict(model=model,cond=cond,n=5,n_tasks=len(a[0]),rep_scores=scores,trimmed_mean=trimmed(scores),
                 raw_mean=statistics.mean(scores),**boot(a,draws=draws,key=split+model+cond))
        if cond!='full':
            b=[cells[(model,'full')][r] for r in range(5)]
            row['delta_vs_full']=trimmed(scores)-trimmed([statistics.mean(x) for x in b])
            row['delta_bootstrap']=boot(a,b,draws=draws,key='delta'+split+model+cond,family=family if cond.startswith('-') else 1)
        result.append(row)
    return result


def calibration(root,observed=False):
    samples=load(ASSETS/('calibration-observed.json' if observed else 'calibration.json'))
    gold={s['id']:s for s in samples}
    results=[]
    for p in sorted((root/('calibration-observed' if observed else 'calibration-v3')).glob('*.json')):
        if p.name.endswith('.call.json'):continue
        d=load(p);matches=0;exact=0;bycheck=[0]*6;disagreements=[]
        for v in d['judgments']:
            s=gold[v['id']]
            assert len(v['bits'])==6
            same=[x==y for x,y in zip(s['expected_bits'],v['bits'])]
            matches+=sum(same);exact+=all(same)
            bycheck=[a+b for a,b in zip(bycheck,same)]
            if not all(same):disagreements.append(dict(id=v['id'],expected=s['expected_bits'],judged=v['bits'],manual_reasons=s['manual_reasons'],judge_reasons=v['reasons']))
        results.append(dict(judge=d['judge_requested'],samples=len(gold),semantic_decisions=len(gold)*6,matched_decisions=matches,
                            agreement=matches/(len(gold)*6),exact_sample_matches=exact,exact_agreement=exact/len(gold),by_check_matches=bycheck,
                            disagreements=disagreements,annotation_mode=('agent-manual-style-observed' if observed else 'agent-manual-style-seeded')+'; not independent human annotation'))
    return results


def ledger(roots):
    rows=[]
    seen=set()
    for root in roots:
        for p in sorted(root.rglob('*.call.json')):
            if p.resolve() in seen:continue
            seen.add(p.resolve());d=load(p)
            u=d.get('usage') or {}
            rows.append(dict(file=str(p.relative_to(root)),scope=root.name,agent=d['requested_agent'],actual_model=d.get('actual_model'),
                             input_tokens=u.get('input_tokens'),output_tokens=u.get('output_tokens'),
                             cached_input_tokens=u.get('cached_input_tokens',u.get('cache_read_input_tokens',0)),
                             cache_creation_input_tokens=u.get('cache_creation_input_tokens',u.get('cache_write_input_tokens',0)),
                             cost_usd_reported=d.get('cost_usd_reported'),cost_basis=d.get('cost_basis'),latency_s=d.get('latency_s'),rc=d.get('rc'),
                             cli_error=d.get('cli_error',False)))
    return ledger_from_rows(rows)


def ledger_from_rows(rows):
    totals=dict(calls=len(rows),reported_cost_usd=sum(r['cost_usd_reported'] or 0 for r in rows),
                unknown_cost_calls=sum(r['cost_usd_reported'] is None for r in rows),
                input_tokens=sum(r['input_tokens'] or 0 for r in rows),output_tokens=sum(r['output_tokens'] or 0 for r in rows),
                cached_input_tokens=sum(r['cached_input_tokens'] or 0 for r in rows),
                cache_creation_input_tokens=sum(r['cache_creation_input_tokens'] or 0 for r in rows))
    return dict(totals=totals,calls=rows)


def write(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--run-dir',required=True,type=pathlib.Path)
    ap.add_argument('--private-dir',required=True,type=pathlib.Path)
    ap.add_argument('--out-dir',required=True,type=pathlib.Path)
    ap.add_argument('--draws',default=10000,type=int)
    ap.add_argument('--batch',default='2026-10-13-explain-v1')
    args=ap.parse_args()
    args.out_dir.mkdir(parents=True,exist_ok=True)
    pub=args.run_dir/'public'
    public=load(ASSETS/'cases.json')
    result=dict(design=dict(models=MODELS,judges=JUDGES,reps=5,public_tasks=16,private_tasks=4,
                           public_conditions=list(conditions()),holdout_conditions=list(conditions()),
                           ci_method='paired crossed task/repetition cluster percentile bootstrap, trimmed-one-each statistic',
                           ablation_family_public=28,seed_method='first 12 SHA256 hex digits of split/model/condition',draws=args.draws),
                calibration=calibration(pub),calibration_observed=calibration(pub,observed=True))
    for split in ('dev','validation'):
        rows,cells=score_runs(pub,public,split,args.batch)
        result[split]=stats(cells,split,args.draws)
        dest=args.out_dir/f'{split}.jsonl'
        with dest.open('w') as f:
            for r in rows:f.write(json.dumps(r,ensure_ascii=False)+'\n')
    if (args.private_dir/'run/generations').exists():
        private=load(args.private_dir/'cases.json')
        rows,cells=score_runs(args.private_dir/'run',private,'holdout',args.batch)
        result['holdout']=stats(cells,'holdout',args.draws)
        with (args.private_dir/'scored.jsonl').open('w') as f:
            for r in rows:f.write(json.dumps(r,ensure_ascii=False)+'\n')
    result['cost_ledger']=ledger([pub,args.private_dir/'run'])
    receipt=ASSETS/'batches'/f'{args.batch}.private-costs.json'
    if not (args.private_dir/'run').exists() and receipt.exists():
        result['cost_ledger']=ledger_from_rows(result['cost_ledger']['calls']+load(receipt)['calls'])
    write(args.out_dir/'summary.json',result)
    print(json.dumps(result['cost_ledger']['totals'],ensure_ascii=False))


if __name__=='__main__':
    main()
