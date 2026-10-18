"""Tests for scoring/transport/statistics invariants that can change conclusions."""
import unittest
from checks import rules, combine, validate_evidence
from run import parse_answers, conditions
from summarize import trimmed, boot


class ExplainTests(unittest.TestCase):
    def test_trim_estimator(self):
        self.assertAlmostEqual(trimmed([0,.2,.3,.4,1]),.3)
        with self.assertRaises(ValueError): trimmed([0,.2,.3,1])

    def test_bootstrap_of_same_paired_matrix_is_zero(self):
        a=[[.2,.8],[.4,.7],[.3,.9],[.1,.6],[.5,1]]
        result=boot(a,a,draws=400,key='paired-test',family=28)
        self.assertEqual(result['ci95'],[0,0])
        self.assertEqual(result['simultaneous_ci'],[0,0])

    def test_constant_bootstrap_and_seed(self):
        a=[[.7,.7]]*5
        x=boot(a,draws=200,key='constant')
        self.assertEqual(x,boot(a,draws=200,key='constant'))
        for v in x['ci95']:self.assertAlmostEqual(v,.7)

    def test_delta_sign(self):
        a=[[.8]*3]*5;b=[[.5]*3]*5
        for v in boot(a,b,draws=200,key='direction')['ci95']:self.assertAlmostEqual(v,.3)

    def test_transport_only_recovery(self):
        text='{"answers":{"d01":"first \\"quote\\"","v01":"second"}}'
        self.assertEqual(parse_answers(text,{'d01','v01'})[0],{'d01':'first "quote"','v01':'second'})
        self.assertEqual(parse_answers(text[:-1],{'d01','v01'})[0],parse_answers(text,{'d01','v01'})[0])
        broken='{"answers":{"d01":"first "quote"","v01":"second"}}'
        self.assertEqual(parse_answers(broken,{'d01','v01'})[0],{'d01':'first "quote"','v01':'second'})
        with self.assertRaises(ValueError):parse_answers('{"answers":{"d01":"partial"}',{'d01','v01'})

    def test_one_section_deleted(self):
        cs=conditions()
        self.assertEqual(len(cs),9)
        self.assertEqual(cs['full'].count('\n## '),7)
        for k,v in cs.items():
            if k.startswith('-'):self.assertEqual(v.count('\n## '),6)

    def test_quote_cannot_be_borrowed(self):
        verdict={'bits':'100000','reasons':['x']*6,'evidence':['someone else']+['']*5}
        with self.assertRaises(ValueError):validate_evidence('this answer',verdict)
        verdict['evidence'][0]='this answer'
        validate_evidence('this answer',verdict)

    def test_rules_and_denominator(self):
        task={'language':'zh','keywords':['似然']}
        a='似然固定数据比较假设。'
        checks,score=combine(task,a,{'bits':'000000'})
        self.assertEqual(len(checks),10)
        self.assertEqual(score,.4)
        self.assertEqual(rules(task,'好的，我们讲似然。')['A1'],'FAIL')
        self.assertEqual(rules(task,'似然不是后验，而是数据概率。')['A2'],'FAIL')
        self.assertEqual(rules(task,a+'自评90分。')['A3'],'FAIL')
        self.assertEqual(rules(task,'似然为1/100。方差例子中scores 68,70,72。')['A3'],'PASS')
        self.assertEqual(rules(task,'似然计算正确，你已经完全掌握了。')['A3'],'FAIL')
        self.assertEqual(rules(task,'似然很高不代表你已经掌握了。')['A3'],'PASS')
        blank,score=combine(task,'',{'bits':'111111'})
        self.assertEqual(score,0)
        self.assertTrue(all(v=='FAIL' for v in blank.values()))


if __name__=='__main__':unittest.main()
