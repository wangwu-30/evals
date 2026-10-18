"""Tests for inference choices that could invent a cross-model disagreement."""
import unittest
import numpy as np
from followup import holm, resample, inference, ranks, correlation
from summarize import boot


class FollowupTests(unittest.TestCase):
    def test_marginal_matches_original_cluster_bootstrap(self):
        a=[[.2,.8],[.4,.7],[.3,.9],[.1,.6],[.5,1]]
        b=[[.1,.7],[.2,.7],[.2,.5],[.3,.4],[.1,.9]]
        expected=boot(a,b,draws=400,key='compatibility')['ci95']
        actual=inference(0,resample([a,b],400,'compatibility'),'compatibility')['ci95']
        np.testing.assert_allclose(actual,expected,atol=1e-14)

    def test_conditions_pair_but_model_noise_is_independent(self):
        a=[[v,v] for v in [.1,.2,.3,.4,.5]]
        b=[[0,0]]*5
        samples=resample([a,b,a,b],1000,'independent',True)
        self.assertGreater(float(np.std(samples)),0)
        zero=resample([a,a,b,b],100,'same-conditions',True)
        np.testing.assert_allclose(zero,0)

    def test_interaction_sign_and_null_centering(self):
        a=[[.8]*3]*5;b=[[.5]*3]*5
        c=[[.6]*3]*5;d=[[.5]*3]*5
        samples=resample([a,b,c,d],400,'sign',True)
        np.testing.assert_allclose(samples,-.2)
        self.assertAlmostEqual(inference(-.2,samples,'sign')['p_raw'],1/401)
        self.assertEqual(inference(0,np.zeros(400),'null')['p_raw'],1)

    def test_holm_monotonicity_and_original_order(self):
        np.testing.assert_allclose(holm([.04,.001,.03]),[.06,.003,.06])

    def test_ties_and_exact_permutation(self):
        self.assertEqual(ranks([3,1,1]),[3,1.5,1.5])
        self.assertEqual(ranks([.1,.1+1e-15,.2]),[1.5,1.5,3])
        r=correlation([1,2,3,4],[1,2,3,4])
        self.assertAlmostEqual(r['r'],1)
        self.assertEqual(r['permutations'],24)
        self.assertAlmostEqual(r['p_raw'],2/24)
        self.assertIsNone(correlation([1,1,1],[1,2,3])['r'])


if __name__ == '__main__':unittest.main()
