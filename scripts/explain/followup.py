"""Offline model × ablation tests and tokenizer sensitivity; never calls LLMs.

Public and private outputs are separate. A tokenizer is a documented reference,
not proof of the opaque CLI backend. See tokenizer-provenance.json.
"""
import argparse
import hashlib
import itertools
import json
import math
import pathlib
import random
import re
import statistics

import numpy as np
from run import ASSETS, MODELS, conditions, load
from summarize import score_runs, seed, trimmed, write, boot


def holm(ps):
    order = sorted(range(len(ps)), key=ps.__getitem__)
    adjusted = [None] * len(ps)
    previous = 0.
    for rank, i in enumerate(order):
        previous = max(previous, min(1., (len(ps)-rank)*ps[i]))
        adjusted[i] = previous
    return adjusted


def estimate(matrix):
    return trimmed([statistics.mean(r) for r in matrix])


def resample(matrices, draws, key, independent_models=False):
    """Shared tasks; paired conditions; independent repetitions across models.

    The ordinary two-matrix path preserves summarize.boot's RNG sequence.
    Models share tasks, not stochastic generation streams. Same repetition ID
    is insufficient evidence to pair random generation noise across models.
    """
    arrays = [np.asarray(a, dtype=float) for a in matrices]
    shape = arrays[0].shape
    if any(a.shape != shape for a in arrays) or shape[0] < 5:
        raise ValueError('Need matched matrices with at least five whole rounds')
    nr, nt = shape
    rng = random.Random(seed(key))
    rr, tt, second = [], [], []
    for _ in range(draws):
        rr.append([rng.randrange(nr) for _ in range(nr)])
        tt.append([rng.randrange(nt) for _ in range(nt)])
        if independent_models:
            second.append([rng.randrange(nr) for _ in range(nr)])
    rr, tt = np.asarray(rr), np.asarray(tt)
    second = np.asarray(second) if independent_models else rr
    stats = []
    for i, a in enumerate(arrays):
        reps = second if independent_models and i >= 2 else rr
        means = a[reps[:, :, None], tt[:, None, :]].mean(axis=2)
        stats.append(np.sort(means, axis=1)[:, 1:-1].mean(axis=1))
    # Two matrices: deletion-full. Four: (GLM deletion-full)-(GPT deletion-full).
    return stats[0]-stats[1] if len(stats) == 2 else (stats[2]-stats[3])-(stats[0]-stats[1])


def inference(observed, samples, key):
    # Null-centred, two-sided bootstrap test, not P(delta* has opposite sign).
    extreme = int(np.count_nonzero(np.abs(samples-observed) >= abs(observed)-1e-12))
    return dict(delta=float(observed), ci95=np.quantile(samples, [.025, .975]).tolist(),
                p_raw=(extreme+1)/(len(samples)+1), draws=len(samples), seed=seed(key))


def analyse_split(cells, split, marginal_draws=10000, interaction_draws=50000):
    rows = []
    for cond in conditions():
        if not cond.startswith('-'):
            continue
        matrices, marginals = [], []
        for model in MODELS:
            a = [cells[(model, cond)][r] for r in range(5)]
            b = [cells[(model, 'full')][r] for r in range(5)]
            key = 'delta'+split+model+cond
            marginal = dict(model=model, **inference(estimate(a)-estimate(b),
                resample([a,b], marginal_draws, key), key))
            # Preserve the published interval bit-for-bit. NumPy and the
            # standard-library summation differ at decimal rounding ties.
            marginal['ci95'] = boot(a,b,draws=marginal_draws,key=key)['ci95']
            marginals.append(marginal)
            matrices.extend([a,b])
        key = 'interaction-independent-reps:'+split+cond
        obs = marginals[1]['delta']-marginals[0]['delta']
        interaction = inference(obs, resample(matrices, interaction_draws, key, True), key)
        rows.append(dict(cond=cond, models=marginals, interaction=interaction))
    return rows


def adjust(rows, field):
    tests = [test for row in rows for test in (row['models'] if field == 'models' else [row['interaction']])]
    for test, p in zip(tests, holm([t['p_raw'] for t in tests])):
        test.update(p_holm=p, family=len(tests), significant=p < .05)


def token_counts(glm_path):
    import tiktoken
    import tiktoken.model
    import tokenizers
    provenance = load(ASSETS/'tokenizer-provenance.json')
    if hashlib.sha256(glm_path.read_bytes()).hexdigest() != provenance['glm']['tokenizer_sha256']:
        raise ValueError('GLM tokenizer does not match frozen reference')
    enc = tiktoken.get_encoding('o200k_base')
    # Fingerprint merge ranks, independent of filesystem cache names.
    fingerprint = hashlib.sha256()
    for token, rank in sorted(enc._mergeable_ranks.items(), key=lambda item:item[1]):
        fingerprint.update(len(token).to_bytes(4,'big')+token+rank.to_bytes(4,'big'))
    if fingerprint.hexdigest() != provenance['gpt']['merge_ranks_sha256']:
        raise ValueError('OpenAI reference encoding changed')
    glm = tokenizers.Tokenizer.from_file(str(glm_path))
    count = lambda s: [len(enc.encode(s, disallowed_special=())), len(glm.encode(s, add_special_tokens=False).ids)]
    variants = conditions()
    parts = re.split(r'(?m)(?=^## )', variants['full'])
    return dict(model_order=MODELS, reference_only=True,
        versions=dict(tiktoken=tiktoken.__version__, tokenizers=tokenizers.__version__),
        variants={c:count(s) for c,s in variants.items()},
        deleted_sections={f'-{i}':dict(heading=p.splitlines()[0], tokens=count(p),
            sha256=hashlib.sha256(p.encode()).hexdigest(),
            effective_reduction=[f-v for f,v in zip(count(variants['full']),count(variants[f'-{i}']))])
            for i,p in enumerate(parts) if i})


def pearson(x,y):
    xc = [v-statistics.mean(x) for v in x]
    yc = [v-statistics.mean(y) for v in y]
    denom = math.sqrt(sum(v*v for v in xc)*sum(v*v for v in yc))
    return sum(a*b for a,b in zip(xc,yc))/denom if denom else None


def ranks(x):
    # Scores are rational multiples of 1/(tasks*10*3); subtraction can leave
    # floating noise on mathematically tied effects. Do not invent rank order.
    x = [round(v,12) for v in x]
    return [1+sum(v<t for v in x)+(sum(v==t for v in x)-1)/2 for t in x]


def correlation(x,y):
    observed = pearson(x,y)
    if observed is None:
        return dict(r=None,p_raw=None,permutations=0)
    values = [pearson(x,p) for p in itertools.permutations(y)]
    return dict(r=observed,p_raw=sum(abs(v)>=abs(observed)-1e-12 for v in values)/len(values),
                permutations=len(values))


def correlations(splits, tokens):
    out = []
    full = tokens['variants']['full']
    for split, rows in splits.items():
        y = [row['interaction']['delta'] for row in rows]
        reductions = [tokens['deleted_sections'][row['cond']]['effective_reduction'] for row in rows]
        predictors = dict(raw_reduction_gap=[b-a for a,b in reductions],
            relative_reduction_gap=[b/full[1]-a/full[0] for a,b in reductions])
        for predictor, x in predictors.items():
            for method in ('Pearson','Spearman'):
                xx,yy = (ranks(x),ranks(y)) if method == 'Spearman' else (x,y)
                out.append(dict(split=split,predictor=predictor,method=method,n=len(x),
                    condition_order=[r['cond'] for r in rows],x=x,y=y,**correlation(xx,yy)))
    valid = [r for r in out if r['p_raw'] is not None]
    for r,p in zip(valid,holm([r['p_raw'] for r in valid])):
        r.update(p_holm=p,family=len(valid),significant=p < .05)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--glm-tokenizer',type=pathlib.Path,required=True)
    ap.add_argument('--output',type=pathlib.Path,required=True)
    ap.add_argument('--private-dir',type=pathlib.Path)
    ap.add_argument('--private-output',type=pathlib.Path)
    ap.add_argument('--interaction-draws',type=int,default=50000)
    args = ap.parse_args()
    public = load(ASSETS/'cases.json')
    root = ASSETS/'artifacts/public'
    splits = {}
    for split in ('dev','validation'):
        _,cells = score_runs(root,public,split,'2026-10-13-explain-v1')
        splits[split] = analyse_split(cells,split,interaction_draws=args.interaction_draws)
    rows = sum(splits.values(),[])
    adjust(rows,'models'); adjust(rows,'interaction')
    tokens = token_counts(args.glm_tokenizer)
    result = dict(design=dict(interaction='(GLM deletion-full)-(GPT deletion-full)',
        bootstrap='shared task clusters, independent model repetition clusters; conditions paired within model; trim-one-each',
        test='two-sided null-centred bootstrap: (1+count(abs(T*-T)>=abs(T)))/(B+1)',
        correction='Holm: 28 public marginal tests, 14 public interactions, 8 exploratory correlations as separate families',
        alpha=.05,marginal_draws=10000,interaction_draws=args.interaction_draws,numpy_version=np.__version__,
        generation_calls=0,incremental_evaluation_cost_usd=0),
        splits=splits,tokens=tokens,correlations=correlations(splits,tokens))
    write(args.output,result)
    if args.private_dir:
        if not args.private_output:
            ap.error('--private-output required with --private-dir')
        # Never allow a holdout output inside the repository.
        from run import ROOT
        if args.private_output.resolve().is_relative_to(ROOT.resolve()):
            ap.error('private output must stay outside repository')
        _,cells = score_runs(args.private_dir/'run',load(args.private_dir/'cases.json'),'holdout','reference-only')
        rows = analyse_split(cells,'holdout',interaction_draws=args.interaction_draws)
        adjust(rows,'models'); adjust(rows,'interaction')
        write(args.private_output,dict(reference_only=True,rows=rows))
    print('Wrote offline follow-up; zero new generation/judge calls:',args.output)


if __name__ == '__main__':
    main()
