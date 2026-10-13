"""Offline publication gate: matrix completeness, immutable provenance, privacy.

Potential secrets are reported by file/count only, never printed verbatim.
"""
import argparse
import hashlib
import pathlib
import re
from run import ROOT, ASSETS, MODELS, JUDGES, JUDGMENT_FOLDER, load, conditions, generation_prompt, digest, parse_answers
from checks import validate_evidence, combine


def verify_run(root,tasks):
    ids={t['id'] for t in tasks}
    for m in MODELS:
        for c,skill in conditions().items():
            for rep in range(5):
                gp=root/'generations'/m.replace(':','_')/c/f'{rep}.json'
                jp=root/JUDGMENT_FOLDER/m.replace(':','_')/c/f'{rep}.json'
                g,j=load(gp),load(jp)
                call=load(root/g['call_file'])
                assert call['requested_agent']==m and call['rc']==0 and not call.get('cli_error')
                assert call.get('tool_call_count',0)==0
                assert set(g['answers'])==ids
                assert g['skill_sha256']==digest(skill)
                assert g['prompt_sha256']==digest(generation_prompt(tasks,skill,20261013+rep))==call['prompt_sha256']
                parsed,_=parse_answers(call['output'],ids,allow_partial=True)
                assert g['answers']=={tid:parsed.get(tid,'') for tid in ids},'Stored answers differ from decoded raw response'
                assert j['judge_requested']==JUDGES[m]
                vv={v['id']:v for v in j['judgments']}
                assert set(vv)==ids and len(j['judgments'])==len(tasks)
                for t in tasks:
                    v=vv[t['id']]
                    validate_evidence(g['answers'][t['id']],v)
                    checks,score=combine(t,g['answers'][t['id']],v)
                    assert len(checks)==10 and score==sum(x=='PASS' for x in checks.values())/10


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--run-dir',required=True,type=pathlib.Path)
    ap.add_argument('--private-dir',type=pathlib.Path)
    args=ap.parse_args()
    provenance=load(ASSETS/'source/provenance.json')
    for fname,k in [('SKILL.md','skill_sha256'),('LICENSE','license_sha256')]:
        assert hashlib.sha256((ASSETS/'source'/fname).read_bytes()).hexdigest()==provenance[k]
    assert 'MIT License' in (ASSETS/'source/LICENSE').read_text()
    verify_run(args.run_dir/'public',load(ASSETS/'cases.json'))
    if args.private_dir and (args.private_dir/'freeze.json').exists():
        tasks=load(args.private_dir/'cases.json')
        verify_run(args.private_dir/'run',tasks)
        design=load(args.private_dir/'freeze.json')['design']
        assert design['planned_requests']==90 and design['reps']==5 and len(design['conds'])==9
        assert len((args.private_dir/'USAGE.log').read_text().splitlines())==1
        for name,k in [('checks.py','checks_sha256'),('run.py','runner_sha256')]:
            assert digest((ROOT/'scripts/explain'/name).read_text())==design[k],'Frozen code changed'
        assert digest((args.private_dir/'cases.json').read_text())==design['cases_sha256']
        assert digest((ASSETS/'cases.json').read_text())==design['public_cases_sha256']
        # Exact secret-case text must never appear in any committed asset.
        needles=[t[k] for t in tasks for k in ('prompt','oracle','reference')]
        for directory in [ROOT/'data',ROOT/'scripts/explain',ROOT/'docs']:
            for p in directory.rglob('*'):
                if not p.is_file() or '__pycache__' in p.parts:continue
                try:text=p.read_text()
                except UnicodeError:continue
                assert not any(n in text for n in needles),'Holdout text leaked into '+str(p.relative_to(ROOT))
    patterns=[r'gh[opusr]_[A-Za-z0-9]{20,}',r'sk-[A-Za-z0-9_-]{20,}',r'(?i)Bearer\s+[A-Za-z0-9._-]{16,}']
    hits=[]
    for directory in [ASSETS,ROOT/'data/evals/explain-validation',ROOT/'scripts/explain',ROOT/'docs']:
        for p in directory.rglob('*'):
            if not p.is_file() or '__pycache__' in p.parts:continue
            try:text=p.read_text()
            except UnicodeError:continue
            count=sum(len(re.findall(pattern,text)) for pattern in patterns)
            if count:hits.append((str(p.relative_to(ROOT)),count))
    if hits:raise RuntimeError('Potential credentials (values suppressed): '+repr(hits))
    print('PASS: exact skill/license hashes; n=5 complete matrices; prompt/output replay; one-section deletion; zero candidate tools; judge evidence; holdout isolation; credential scan.')


if __name__=='__main__':main()
