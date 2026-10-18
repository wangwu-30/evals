import collections
import importlib.util
import json
import hashlib
from pathlib import Path
import tempfile
import unittest
import viewer_data as v
import build_site as build

ROOT = Path(__file__).resolve().parent.parent


def run(text='hello', score=1, **kw):
    return v.normalize(dict(model='m', cond='full', text=text, score=score, **kw))


class ScoringTests(unittest.TestCase):
    def test_all_runs_mean_and_infra_exclusion(self):
        rs = [run(rep=0), run('', rep=1), run('partial', rep=2, fail_type='model_truncated'), run(rep=3, fail_type='infra_api')]
        s = v.summarize(rs)
        self.assertEqual(s['mean_score'], 1/3)
        self.assertEqual((s['n_fail_model'], s['n_fail_infra']), (2, 1))
        self.assertEqual(s['mean_len_units'], 1)
        self.assertEqual(s['n_out'], 2)
        self.assertTrue(s['incomplete'])

    def test_ten_percent_not_incomplete(self):
        self.assertFalse(v.summarize([run(rep=i) for i in range(9)] + [run(fail_type='infra_harness')])['incomplete'])

    def test_all_infra(self):
        s = v.summarize([run(fail_type='infra_not_sent')])
        self.assertIsNone(s['mean_score'])
        self.assertIsNone(s['mean_len_units'])
        self.assertIsNone(s['default_rep'])
        self.assertIsNone(s['mean_out_tok'])

    def test_default_text_only_and_tie(self):
        rs = [run('', rep=0), run('a b', rep=1), run('a b c d', rep=2)]
        self.assertEqual(v.default_run(rs)['rep'], 1)
        self.assertEqual(v.summarize(rs)['mean_len_units'], 3)

    def test_units(self):
        self.assertEqual(v.length_units("你好 world 123 don't A-1"), 6)

    def test_missing_storage_is_not_empty(self):
        r = v.normalize(dict(model='m', cond='c', score=1, raw={}))
        self.assertEqual(r['fail_type'], '')
        self.assertTrue(r['text_missing'])
        self.assertEqual(run('')['fail_type'], 'model_empty')

    def test_legacy(self):
        for kwargs, kind in [({'rc': -9}, 'model_timeout'), ({'latency_s':900}, 'model_timeout'), ({'rc':1}, 'model_no_answer'), ({'stop_reason':'max_tokens'}, 'model_truncated')]:
            r = run(**kwargs)
            self.assertEqual(r['fail_type'], kind)
            self.assertTrue(r['legacy_failure'])
        self.assertIn('旧记录没写失败类型，按模型失败算', v.failure_copy(v.summarize([run('')])))

    def test_runner_explicit_infra_is_preserved(self):
        record=dict(model='m',cond='c',score=1,rc=1,raw={'output':'', 'fail_type':'infra_api'})
        normalized=v.normalize(record)
        self.assertEqual(normalized['fail_type'],'infra_api')
        self.assertFalse(normalized['legacy_failure'])
        self.assertIsNone(normalized['score'])

    def test_real_sonnet_backfill_and_scores(self):
        ev, batches = build.load(ROOT/'data/evals/daily-skill')
        a = v.backfill(batches, '2026-10-12-box-rescored','2026-10-12-box-pilot',165)
        b = v.backfill(batches, '2026-10-12-macmini-final','2026-10-12-macmini-cli-partial')
        self.assertEqual(a['matched'],165)
        self.assertEqual(b['matched'],103)
        records = next(rs for meta,rs in batches if meta['id']=='2026-10-12-macmini-final')
        for cond,score,failures in [('full',.60,2),('-4',.30,1)]:
            rs=[v.normalize(r) for r in records if r['model']=='claude:sonnet' and r['cond']==cond]
            s=v.summarize(rs)
            self.assertAlmostEqual(s['mean_score'],score,places=4)
            self.assertEqual(s['n_fail_model'],failures)

    def test_ambiguous_backfill_rejected(self):
        r=dict(model='m',cond='c',rep=0,latency_s=1,raw={'output':'a'})
        batches=[({'id':'source'},[r,r.copy()]),({'id':'target'},[dict(r,raw={})])]
        with self.assertRaises(ValueError):v.backfill(batches,'target','source',1)


class SafetyTests(unittest.TestCase):
    def test_secret_true_positives(self):
        # Deliberately synthetic strings, never usable credentials.
        cases = [('api_key','sk-'+'x'*24),('api_key','AKIA'+'A'*16),('api_key','AIza'+'x'*32),
                 ('api_key','ghp_'+'x'*24),('api_key','github_pat_'+'x'*24),('api_key','xoxb-'+'x'*24),
                 ('bearer','Bearer '+'x'*20),('jwt','eyJ'+'x'*12+'.'+'x'*12+'.'+'x'*12),
                 ('private_key','-----BEGIN PRIVATE KEY-----'),('credential_assignment','password="example-value"'),
                 ('credential_assignment',{'refresh_token':'example-value'}),('credential_file','auth.json: {'),
                 ('credential_file','.env\nSECRET=example-value')]
        for category, value in cases:
            with self.subTest(category=category):self.assertIn(category,v.secret_categories(value))

    def test_false_positives(self):
        for text in ['The token count is 42.', '身份证号：110105199003077651', '3f786850e387550fdab836ed7e6dc881de23001b', 'api_key_env=EXAMPLE_API_KEY', 'Use an environment variable for your password.', 'Read auth.json securely.', 'prompt_sha256', '刷新 token 并不是答案']:
            self.assertEqual(v.secret_categories(text),[])

    def test_scope_filters(self):
        for ev in [dict(id='hpo-test'),dict(id='company-example'),dict(id='test',badge='公司侧'),dict(id='s',kind='summary')]:self.assertTrue(v.restricted_eval(ev))
        self.assertEqual(v.hidden_record({'id':'x'},{'item':'h01'},['h01']),'holdout')
        self.assertEqual(v.hidden_record({'id':'x'},{'item':'holdout-1'}),'holdout')
        self.assertEqual(v.hidden_record({'id':'x'},{'split':'留出集'}),'holdout')
        self.assertEqual(v.hidden_record({'id':'teamrecall-replay'},{'labels':['private']}),'private')
        self.assertEqual(v.hidden_record({'id':'teamrecall-replay'},{'raw':{'labels':['private']}}),'private')
        self.assertEqual(v.hidden_record({'id':'x'},{'raw':{'answers':[{'task_id':'h01'}]}},['h01']),'holdout')
        self.assertIsNone(v.hidden_record({'id':'teamrecall-replay'},{'labels':['public']}))

    def test_entire_record_dropped_if_reason_or_prompt_secret(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            ed=Path(tmp);(ed/'batches').mkdir()
            ev={'id':'public','kind':'matrix'}
            audit=dict(scanned=0,dropped_records=0,dropped=collections.Counter(),backfills=[])
            r=dict(model='m',cond='c',text='safe',score=1,why={'x':['Bearer '+'z'*20,'']})
            batches,_=v.prepare(ev,[({'id':'one'},[r])],ed,audit)
            self.assertEqual(batches[0][1],[])
            self.assertEqual(audit['dropped_records'],1)

    def test_nested_prompt_reference_scanned(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            ed=Path(tmp);(ed/'batches').mkdir()
            prompt='Bearer '+'z'*20
            sha=hashlib.sha256(prompt.encode()).hexdigest()
            (ed/'batches/prompts.jsonl').write_text(json.dumps({'sha256':sha,'text':prompt})+'\n')
            r=dict(model='m',cond='c',score=1,raw={'output':'safe','prompt_sha256':sha})
            audit=dict(scanned=0,dropped_records=0,dropped=collections.Counter(),backfills=[])
            batches,_=v.prepare({'id':'public'},[({'id':'one'},[r])],ed,audit)
            self.assertEqual(batches[0][1],[])
            self.assertEqual(audit['dropped']['bearer'],1)

    def test_noindex_and_public_scope(self):
        self.assertIn('name="robots" content="noindex',build.page('x','x'))
        self.assertIn('name="robots" content="noindex"',(ROOT/'scripts/viewer/shell.html').read_text())
        if (ROOT/'site').exists():
            for path in (ROOT/'site').rglob('*.html'):
                self.assertIn('name="robots" content="noindex',path.read_text())
            self.assertEqual((ROOT/'site/robots.txt').read_text(),'User-agent: *\nDisallow: /\n')
            self.assertFalse((ROOT/'site/data/splits.json').exists())
            self.assertFalse(any((ROOT/'site/data').rglob('artifacts')))
            self.assertFalse(any((ROOT/'site/c').glob('company*')))


if __name__=='__main__':unittest.main()
