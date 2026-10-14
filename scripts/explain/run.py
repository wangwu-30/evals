"""Thin local CLI runner using prompt-eval's single-shot pattern.

Never persists full CLI event streams, stderr, environment or auth files.
No tools, slash commands or external fetching are allowed in model requests.
Every completed generation/judgment is immutable. Holdout generation is attempted
exactly once per planned request; failures halt publication rather than reusing it.
"""
import argparse
import concurrent.futures as cf
import hashlib
import fcntl
import json
import os
import pathlib
import random
import re
import subprocess
import tempfile
import threading
import time
from checks import judge_prompt, validate_evidence

ROOT = pathlib.Path(__file__).resolve().parents[2]
ASSETS = ROOT/'data/evals/explain'
MODELS = ['codex:gpt-5.6-luna', 'claude:glm-5.3-flash[1m]']
# The second model is GLM via the existing Claude CLI route, not Anthropic.
# The attempted cross-vendor pilot was too costly at CLI-reported rates.
# One shared judge keeps the final matrix comparable and within reported budget.
# OpenAI candidate/judge share a nominal vendor: explicitly disclosed in report.
JUDGES = {m:'codex:gpt-6.1-sol' for m in MODELS}
JUDGMENT_FOLDER = 'judgments-shared'
lock = threading.Lock()


def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write('\n')


def load(path):
    return json.loads(path.read_text())


def digest(s):
    return hashlib.sha256(s.encode()).hexdigest()


def parse_json(s):
    s = s.strip()
    s = re.sub(r'^```(?:json)?\s*|\s*```$', '', s)
    return json.loads(s)


def parse_answers(s, expected, allow_partial=False):
    """Recover unescaped interior quotes in the known answers envelope only.

    Task-key boundaries are unambiguous and fixed by the request. This never
    asks a model to rewrite an answer and never alters its decoded characters.
    The original response remains in the immutable .call.json record.
    """
    try:
        decoded = parse_json(s)
        if 'answers' in decoded:
            return decoded['answers'], 'strict-json'
        if isinstance(decoded,dict) and decoded and set(decoded) <= set(expected) and all(isinstance(v,str) for v in decoded.values()):
            return decoded, 'flat task-key JSON recovered; no answer text changed'
        raise ValueError('Unknown JSON envelope')
    except ValueError:
        s = re.sub(r'^```(?:json)?\s*|\s*```$', '', s.strip())
        # Models occasionally omit the outer closing brace after a complete
        # final value. Only accept a strict parse containing every expected ID.
        for suffix in ('}', '}}'):
            try:
                recovered = json.loads(s+suffix)['answers']
                if set(recovered) == set(expected) or (allow_partial and recovered and set(recovered) < set(expected)):
                    return recovered, 'added missing outer JSON brace; no answer text changed'
            except (ValueError,KeyError,TypeError):
                pass
        if not re.match(r'^\{\s*"answers"\s*:\s*\{',s):
            raise ValueError('Unsupported answers envelope')
        pattern = r'"('+'|'.join(re.escape(k) for k in sorted(expected))+r')"\s*:\s*"'
        matches = list(re.finditer(pattern,s))
        seen = {m[1] for m in matches}
        if len(matches) != len(seen) or not matches or (seen != set(expected) and not (allow_partial and seen < set(expected))):
            raise ValueError('Ambiguous/missing answer boundaries')
        answers = {}
        for i,m in enumerate(matches):
            chunk = s[m.end():matches[i+1].start()] if i+1 < len(matches) else s[m.end():]
            if i+1 == len(matches):
                # Fixed field ends at its quote + JSON braces, optionally
                # followed by out-of-envelope commentary. Original kept.
                ending = re.search(r'"\s*,?\s*\}(?:\s*\})*(?:\s*$|\s*\n\n)',chunk)
                if not ending: raise ValueError('Missing final answer delimiter')
                chunk = chunk[:ending.start()+1]
            else:
                # Also recover repeated extra braces after each value.
                chunk = re.sub(r'[\s,}]+$', '', chunk)
            if not chunk.endswith('"'): raise ValueError('Missing final value delimiter')
            content = chunk[:-1]
            escaped = []
            slash_run = 0
            for pos,c in enumerate(content):
                if c == '"' and slash_run % 2 == 0: escaped.append('\\')
                # Latex-like literal backslashes sometimes arrive unescaped.
                # Escaping the backslash preserves the actual answer character.
                if c == '\\' and slash_run % 2 == 0 and (pos+1==len(content) or content[pos+1] not in '"\\/bfnrtu'):
                    escaped.append('\\')
                if c in '\n\r\t': escaped.append({'\n':'\\n','\r':'\\r','\t':'\\t'}[c])
                else: escaped.append(c)
                slash_run = slash_run+1 if c == '\\' else 0
            answers[m[1]] = json.loads('"'+''.join(escaped)+'"')
        return answers, 'fixed-task-boundary interior-quote recovery; original response preserved'


def conditions():
    skill = (ASSETS/'source/SKILL.md').read_text()
    parts = re.split(r'(?m)(?=^## )', skill)
    return {'none': '', 'full': skill} | {f'-{i}': ''.join(p for j,p in enumerate(parts) if j != i) for i in range(1,len(parts))}


class Budget:
    """Cap reported CLI USD; unknown Codex billing is never treated as zero USD."""
    def __init__(self, root, cap):
        self.root, self.cap, self.reserved = root, cap, 0.
        self.spent = sum(load(p).get('cost_usd_reported') or 0 for p in root.rglob('*.call.json'))
        self.cv = threading.Condition()

    def reserve(self, amount):
        with self.cv:
            while self.spent + self.reserved + amount > self.cap and self.reserved:
                self.cv.wait(timeout=1)
            if self.spent + self.reserved + amount > self.cap:
                raise RuntimeError('Reported-cost budget exhausted; no more paid CLI calls')
            self.reserved += amount

    def release(self, amount, actual):
        with self.cv:
            self.reserved -= amount
            self.spent += actual or 0
            self.cv.notify_all()


class RouteSlot:
    """Cross-process concurrency limit for the configured GLM/Claude route."""
    def __init__(self,root,needed):self.root,self.needed,self.file=root,needed,None
    def __enter__(self):
        if not self.needed:return self
        slots=self.root/'.route-slots';slots.mkdir(parents=True,exist_ok=True)
        while self.file is None:
            for i in range(3):
                f=(slots/str(i)).open('a+')
                try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);self.file=f;break
                except BlockingIOError:f.close()
            if self.file is None:time.sleep(.3)
        return self
    def __exit__(self,*_):
        if self.file:
            fcntl.flock(self.file,fcntl.LOCK_UN);self.file.close()


def invoke(agent, prompt, call_path, budget, timeout=600):
    if call_path.exists():
        return load(call_path)
    kind, model = agent.split(':',1)
    reservation = 0.65 if kind == 'claude' else 0.
    budget.reserve(reservation)
    t = time.time()
    record = dict(requested_agent=agent, prompt_sha256=digest(prompt), rc=None,
                  cost_usd_reported=None, cost_basis='not-reported', actual_model=None)
    try:
        with tempfile.TemporaryDirectory(prefix='explain-eval-') as cwd:
            if kind == 'claude':
                cmd = ['claude','-p','--model',model,'--output-format','json','--tools','',
                       '--disable-slash-commands','--strict-mcp-config','--mcp-config','{"mcpServers":{}}',
                       '--system-prompt','You answer the supplied request directly. Do not use tools or access files.',
                       '--no-session-persistence','--max-budget-usd',str(reservation)]
            else:
                cmd = ['codex','exec','--ignore-user-config','--ephemeral','--skip-git-repo-check','--json',
                       '-C',cwd,'-o',cwd+'/answer.txt','-s','read-only','-m',model,
                       '-c','model_reasoning_effort="low"','-']
            env = dict(os.environ)
            env.pop('CLAUDECODE',None)
            with RouteSlot(budget.root,kind=='claude'):
                p = subprocess.run(cmd,input=prompt,capture_output=True,text=True,cwd=cwd,env=env,timeout=timeout)
            record['rc'] = p.returncode
            if kind == 'claude':
                try:
                    j = json.loads(p.stdout)
                except ValueError:
                    j = {}
                record.update(output=j.get('result',''), usage=j.get('usage',{}),
                              model_usage=j.get('modelUsage',{}), cost_usd_reported=j.get('total_cost_usd'),
                              cost_basis='CLI self-report; route costBasis unknown; not invoice verified',
                              actual_model=list((j.get('modelUsage') or {}).keys()),
                              cli_subtype=j.get('subtype'), cli_error=bool(j.get('is_error')))
            else:
                usage, tool_calls, errors = {}, 0, 0
                for line in p.stdout.splitlines():
                    try: e = json.loads(line)
                    except ValueError: continue
                    if e.get('type') == 'turn.completed':
                        for k,v in (e.get('usage') or {}).items():
                            if isinstance(v,(int,float)): usage[k] = usage.get(k,0)+v
                    item = e.get('item') or {}
                    if item.get('type') not in ('agent_message','reasoning',None): tool_calls += 1
                    errors += e.get('type') == 'error'
                out = pathlib.Path(cwd)/'answer.txt'
                record.update(output=out.read_text() if out.exists() else '', usage=usage, tool_call_count=tool_calls,
                              error_count=errors, actual_model=None, model_identity_basis='requested model only; CLI does not attest backend identity')
    except subprocess.TimeoutExpired:
        record.update(rc=-9,error='timeout; no stderr/event stream retained',output='',usage={})
    except Exception as ex:
        record.update(rc=-1,error=type(ex).__name__,output='',usage={})
    finally:
        record['latency_s'] = round(time.time()-t,3)
        dump(call_path,record)
        budget.release(reservation,record.get('cost_usd_reported'))
    if record.get('tool_call_count'):
        raise RuntimeError('Unexpected tool use: excluded from experiment')
    return record


def generation_prompt(tasks, skill, seed):
    ordered = list(tasks)
    random.Random(seed).shuffle(ordered)
    return (('Apply this explanation skill to each answer:\n'+skill+'\n\n' if skill else '') +
            'Do not use tools, files, other skills, or internet. Answer each request independently using only stable knowledge and the supplied context. Use the request language. Aim for a concise complete explanation, at most about 350 Chinese characters or 160 English words per answer; this is a soft target, accuracy takes priority.\n'
            'Return ONLY a JSON object {"answers":{"task-id":"explanation text",...}} containing all supplied task IDs. JSON is a transport envelope; each value is the actual explanation. Do not add commentary outside JSON.\nREQUESTS:\n'+
            json.dumps([{'id':t['id'],'request':t['prompt']} for t in ordered],ensure_ascii=False))


def check_call(call):
    if call['rc'] != 0 or call.get('cli_error') or not call.get('output'):
        raise RuntimeError('CLI failure; see sanitized call record')


def evaluate_items(agent,items,call_path,budget):
    """Invalid judge transport/evidence is retried in isolation, never scored.

    Original and replacement calls remain immutable and included in cost. A
    valid low score is never retried. Holdout ANSWERS are never regenerated.
    """
    call = invoke(agent,judge_prompt(items),call_path,budget)
    for attempt in range(3):
        try:
            check_call(call)
            break
        except RuntimeError:
            if attempt == 2:raise
            time.sleep(15)
            retry_path = call_path.with_name(call_path.stem+'.retry-'+str(attempt+1)+'.call.json')
            call = invoke(agent,judge_prompt(items),retry_path,budget)
    try:
        verdicts = parse_json(call['output'])['judgments']
        if len(verdicts) != len(items) or {v['id'] for v in verdicts} != {i['id'] for i in items}:
            raise ValueError('Missing or duplicate judgment IDs')
        byid = {v['id']:v for v in verdicts}
    except (ValueError,KeyError,TypeError):
        byid = {}
    accepted,repairs = [],[]
    for item in items:
        if not item['answer'].strip():
            accepted.append(dict(id=item['id'],bits='000000',reasons=['No answer submitted']*6,evidence=['']*6,
                                 judgment_source='deterministic missing-answer policy, not a model verdict'))
            continue
        v = byid.get(item['id'])
        valid = False
        if v is not None:
            try:
                validate_evidence(item['answer'],v)
                valid = True
            except (ValueError,TypeError,KeyError):
                pass
        for attempt in range(2):
            if valid: break
            repair_path = call_path.with_name(call_path.stem+'.repair-'+item['id']+'-'+str(attempt)+'.call.json')
            replacement = invoke(agent,judge_prompt([item]),repair_path,budget)
            check_call(replacement)
            repairs.append(repair_path.name)
            try:
                values = parse_json(replacement['output'])['judgments']
                assert len(values)==1 and values[0]['id']==item['id']
                v=values[0]
                validate_evidence(item['answer'],v)
                valid=True
            except (ValueError,TypeError,KeyError,AssertionError):
                continue
        if not valid: raise ValueError('Judge transport/evidence invalid after isolated retries: '+item['id'])
        accepted.append(v)
    return accepted,repairs


def generate_one(root, tasks, model, cond, rep, budget, holdout):
    path = root/'generations'/model.replace(':','_')/cond/f'{rep}.json'
    if path.exists(): return
    prompt = generation_prompt(tasks,conditions()[cond],20261013+rep)
    call_path = path.with_suffix('.call.json')
    if holdout and call_path.exists() and not path.exists():
        # An interrupted process can reconstruct a successful recorded response,
        # but cannot issue a replacement holdout generation request.
        call = load(call_path)
    else:
        call = invoke(model,prompt,call_path,budget)
    # Retry only transient PUBLIC CLI failures, not legitimate missing/low
    # answers and never holdout generation. Preserve each excluded call.
    for attempt in range(3):
        try:
            check_call(call)
            break
        except RuntimeError:
            if holdout or attempt == 2:raise
            time.sleep(15)
            call_path = path.with_name(path.stem+'.retry-'+str(attempt+1)+'.call.json')
            call = invoke(model,prompt,call_path,budget)
    expected = {t['id'] for t in tasks}
    answers, parser = parse_answers(call['output'],expected,allow_partial=True)
    if not set(answers) <= expected or not all(isinstance(v,str) for v in answers.values()):
        raise ValueError('Malformed/unknown answers; generation is not silently retried')
    missing = sorted(expected-set(answers))
    answers = {t['id']:answers.get(t['id'],'') for t in tasks}
    dump(path,dict(model=model,cond=cond,rep=rep,answers=answers,call_file=str(call_path.relative_to(root)),
                   prompt_sha256=digest(prompt),skill_sha256=digest(conditions()[cond]),transport_parser=parser,missing_task_ids=missing))
    print('generated',model,cond,rep,'tasks',len(tasks),'reported USD',round(budget.spent,3),flush=True)


def judge_one(root, tasks, gen_path, budget):
    gen = load(gen_path)
    model,cond,rep = (gen[k] for k in ['model','cond','rep'])
    path = root/JUDGMENT_FOLDER/model.replace(':','_')/cond/f'{rep}.json'
    if path.exists(): return
    items = [{'id':t['id'],'request':t['prompt'],'kind':t['kind'],'oracle':t['oracle'],'answer':gen['answers'][t['id']]} for t in tasks]
    call_path = path.with_suffix('.call.json')
    verdicts,repairs = evaluate_items(JUDGES[model],items,call_path,budget)
    dump(path,dict(model=model,cond=cond,rep=rep,judge_requested=JUDGES[model],judgments=verdicts,
                   call_file=str(call_path.relative_to(root)),prompt_sha256=digest(judge_prompt(items)),isolated_repair_calls=repairs))
    print('judged',model,cond,rep,'reported USD',round(budget.spent,3),flush=True)


def calibrate(root,budget,observed=False):
    samples = load(ASSETS/('calibration-observed.json' if observed else 'calibration.json'))
    items = [dict(id=s['id'],request=s['task']['prompt'],kind=s['task']['kind'],oracle=s['task']['oracle'],answer=s['answer']) for s in samples]
    for judge in sorted(set(JUDGES.values())):
        path = root/('calibration-observed' if observed else 'calibration-v3')/f"{judge.replace(':','_')}.json"
        if path.exists(): continue
        def one(item):
            call_path = path.with_name(path.stem+'.'+item['id']+'.call.json')
            verdicts,repairs = evaluate_items(judge,[item],call_path,budget)
            return verdicts[0],str(call_path.relative_to(root)),repairs
        with cf.ThreadPoolExecutor(4) as ex:
            outputs=list(ex.map(one,items))
        dump(path,dict(judge_requested=judge,judgments=[o[0] for o in outputs],call_files=[o[1] for o in outputs],isolated_repair_calls=[p for o in outputs for p in o[2]]))
        print('calibrated',judge,flush=True)


def reference_validate(root,tasks,budget):
    """Every new public item has a good authored answer and a broken counterpart.

    Gold reference checks should all pass; broken one-sentence answers must fail
    at least one semantic check. Failures are reported, never silently relabeled.
    """
    items = []
    for t in tasks:
        for suffix, answer in [('good',t['reference']),('bad',t['keywords'][0]+('很重要。' if t['language']=='zh' else ' is important.'))]:
            items.append(dict(id=t['id']+'-'+suffix,request=t['prompt'],kind=t['kind'],oracle=t['oracle'],answer=answer))
    for judge in sorted(set(JUDGES.values())):
        path = root/'reference-validation-v3'/f"{judge.replace(':','_')}.json"
        if path.exists(): continue
        call_path = path.with_suffix('.call.json')
        verdicts,repairs=evaluate_items(judge,items,call_path,budget)
        dump(path,dict(judge_requested=judge,judgments=verdicts,call_file=str(call_path.relative_to(root)),isolated_repair_calls=repairs))
        print('reference-validated',judge,flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('stage',choices=['calibrate','calibrate-observed','references','generate','judge'])
    ap.add_argument('--run-dir',type=pathlib.Path,required=True)
    ap.add_argument('--private-dir',type=pathlib.Path)
    ap.add_argument('--holdout',action='store_true')
    ap.add_argument('--conds',default='all')
    ap.add_argument('--reps',type=int,default=5)
    ap.add_argument('--workers',type=int,default=4)
    ap.add_argument('--reported-cap-usd',type=float,default=27)
    args = ap.parse_args()
    # One shared cost ledger includes public and private calls, but no holdout
    # text is copied to the public run directory.
    budget = Budget(args.run_dir,args.reported_cap_usd)
    public = load(ASSETS/'cases.json')
    tasks = load(args.private_dir/'cases.json') if args.holdout else public
    root = args.run_dir/'holdout' if args.holdout else args.run_dir/'public'
    if args.holdout:
        if not args.private_dir: raise ValueError('--private-dir required')
        root = args.private_dir/'run'
        budget.spent += sum(load(p).get('cost_usd_reported') or 0 for p in root.rglob('*.call.json'))
    if args.stage == 'calibrate': return calibrate(root,budget)
    if args.stage == 'calibrate-observed': return calibrate(root,budget,observed=True)
    if args.stage == 'references': return reference_validate(root,tasks,budget)
    if args.stage == 'generate':
        conds = list(conditions()) if args.conds == 'all' else args.conds.split(',')
        jobs = [(m,c,r) for r in range(args.reps) for c in conds for m in MODELS]
        # Fixed randomized scheduling to avoid confounding conditions with time.
        random.Random(20261013).shuffle(jobs)
        if args.holdout:
            usage = args.private_dir/'USAGE.log'
            manifest = args.private_dir/'freeze.json'
            frozen = dict(skill_commit=load(ASSETS/'source/provenance.json')['commit'],
                          skill_sha256=digest((ASSETS/'source/SKILL.md').read_text()),
                          cases_sha256=digest((args.private_dir/'cases.json').read_text()),
                          checks_sha256=digest((ROOT/'scripts/explain/checks.py').read_text()),
                          runner_sha256=digest((ROOT/'scripts/explain/run.py').read_text()),
                          public_cases_sha256=digest((ASSETS/'cases.json').read_text()),
                          models=MODELS,judges=JUDGES,conds=conds,reps=args.reps,planned_requests=len(jobs))
            if manifest.exists():
                assert load(manifest)['design'] == frozen, 'Frozen holdout design changed'
            else:
                dump(manifest,dict(design=frozen,started_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())))
                with usage.open('a') as f:
                    f.write(time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())+' | ljg-explain 1.0.2 '+frozen['skill_commit']+' | '+','.join(MODELS)+' | Codex agent | one frozen benchmark, all conditions × 5 repeats, no skill optimization | requests='+str(len(jobs))+'\n')
        with cf.ThreadPoolExecutor(args.workers) as ex:
            list(ex.map(lambda j: generate_one(root,tasks,*j,budget,args.holdout),jobs))
    elif args.stage == 'judge':
        paths = sorted((root/'generations').glob('*/*/*.json'))
        paths = [p for p in paths if not p.name.endswith('.call.json')]
        with cf.ThreadPoolExecutor(args.workers) as ex:
            list(ex.map(lambda p: judge_one(root,tasks,p,budget),paths))


if __name__ == '__main__':
    main()
