"""Behavioral checks, including causal-prefix equality on actual market data."""
import unittest
import numpy as np
import baseline as b


class BaselineTests(unittest.TestCase):
    def make(self, events):
        a=np.zeros(len(events),dtype=b.DT)
        for i,(seconds,action,qty,seq,flags) in enumerate(events):
            a[i]['ts_event']=b.START+int(seconds*b.NS)
            a[i]['action']=action.encode(); a[i]['size']=qty
            a[i]['sequence']=seq; a[i]['flags']=flags
            a[i]['order_id']=1; a[i]['side']=b'B'; a[i]['price']=100*10**9
        return a

    def test_execution_not_voluntary_cancel(self):
        a=self.make([(-1,'T',1,1,0),(0,'A',100,2,0),(10,'F',40,3,0),
                     (10,'C',40,3,0),(20,'C',60,4,0)])
        rows,audit=b.extract(a,end=b.START+60*b.NS)
        self.assertEqual(audit['execution_count'],1)
        self.assertEqual(audit['cancel_count'],1)
        self.assertAlmostEqual(rows[0]['log_cancel_qty'],np.log1p(60))

    def test_snapshot_has_no_birth_age_or_add_activity(self):
        a=self.make([(-1,'T',1,1,0),(0,'A',100,2,32),(10,'C',100,3,0)])
        rows,audit=b.extract(a,end=b.START+60*b.NS)
        self.assertEqual(rows[0]['log_add_count'],0)
        self.assertTrue(np.isnan(rows[0]['log_cancel_age_median_ms']))

    def test_replacement_is_separate(self):
        a=self.make([(0,'A',100,1,0),(10,'C',100,2,0),(10,'A',200,2,0)])
        _,audit=b.extract(a,end=b.START+60*b.NS)
        self.assertEqual(audit['replace_count'],1)
        self.assertEqual(audit['cancel_count'],0)

    def test_scaler_frozen_and_constant_feature_safe(self):
        x=np.zeros((40,len(b.FEATURES)))
        model=b.RobustBaseline().fit(x)
        before=model.median.copy()
        model.score(np.ones((2,len(b.FEATURES)))*1e5)
        np.testing.assert_array_equal(before,model.median)
        self.assertTrue(np.all(model.scale>=.02))
        self.assertTrue(np.isfinite(model.score(x)).all())

    def test_real_data_causal_prefix(self):
        a=b.load_dbn(b.ROOT/'work/viac23.dbn')
        cutoff=b.START+3*60*b.NS
        stop=int(np.searchsorted(a['ts_event'],cutoff,side='left'))
        prefix,_=b.extract(a[:stop],end=cutoff)
        longer,_=b.extract(a,end=cutoff+60*b.NS)
        np.testing.assert_allclose(b.matrix(prefix),b.matrix(longer[:3]),equal_nan=True)


if __name__=='__main__':
    unittest.main(verbosity=2)
