"""Append-only public archive; private receipt contains usage/cost, never text."""
import argparse
import hashlib
import json
import pathlib
import shutil
import time
from run import ROOT, ASSETS, MODELS, JUDGES, load, dump, digest, conditions
from summarize import ledger


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--run-dir',required=True,type=pathlib.Path)
    ap.add_argument('--private-dir',required=True,type=pathlib.Path)
    ap.add_argument('--summary',required=True,type=pathlib.Path)
    ap.add_argument('--batch',default='2026-10-13-explain-v1')
    args=ap.parse_args()
    destination=ASSETS/'artifacts/public'
    if destination.exists():raise RuntimeError('Archive already exists: append-only, use a new batch/archive name')
    shutil.copytree(args.run_dir/'public',destination)
    summary=load(args.summary)
    public_summary={k:v for k,v in summary.items() if k!='holdout'}
    # Only numerical usage receipts are public for private calls. No questions,
    # answers, oracles, scores, judgments, prompt body or usage log are exported.
    private_ledger=ledger([args.private_dir/'run'])
    receipt=dict(batch=args.batch,privacy='usage/cost metadata only; no holdout content or scores',**private_ledger)
    dump(ASSETS/'batches'/f'{args.batch}.private-costs.json',receipt)
    dump(ASSETS/'statistics.json',public_summary)
    hashes={name:digest((ROOT/'scripts/explain'/name).read_text()) for name in ['run.py','checks.py','summarize.py']}
    protocol=dict(batch=args.batch,source=load(ASSETS/'source/provenance.json'),models=MODELS,judges=JUDGES,
                  conditions=list(conditions()),reps=5,public_tasks=16,private_tasks=4,
                  public_answer_attempts=1440,private_answer_attempts=360,
                  score='passed checks / 10 per task, equal task mean per round, trim one min and max of five rounds',
                  ci='10000 paired crossed task/repetition bootstrap; Bonferroni public ablations family=28',
                  hashes=hashes,private_design_hash=digest(json.dumps(load(args.private_dir/'freeze.json')['design'],sort_keys=True)),
                  known_reported_cap_usd=29.5,cost_unknown_policy='missing USD is null, never zero; CLI report not invoice verified',
                  holdout_use_entries=len((args.private_dir/'USAGE.log').read_text().splitlines()),
                  recorded_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
                  cross_vendor_pilot='archived and billed; final common OpenAI-requested judge due reported-cost budget',
                  skill_edits=False,holdout_optimization=False)
    dump(ASSETS/'protocol.json',protocol)
    print('Archived public raw calls; exported private numerical cost receipts only.')


if __name__=='__main__':main()
