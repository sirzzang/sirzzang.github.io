"""Throwaway: does a <=1000-row reference (auto chi-square/z-test) stop the same-distribution alarms?"""
import sys, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from evidently.report import Report
from evidently.metrics import DatasetDriftMetric, ColumnDriftMetric
cols = ["age","Workclass","fnlwgt","Education","edunum","Marital-Status","Occupation","Relationship","Race","Sex","cg","cl","hpw","Native_country","income"]
df = pd.read_csv(sys.argv[1], names=cols)
cats = ["Education","Marital-Status","Native_country","Occupation","Race","Relationship","Sex","Workclass"]
pool = df[cats].reset_index(drop=True)
rng = np.random.default_rng(3)
def run(ref, cur):
    r = Report(metrics=[DatasetDriftMetric()] + [ColumnDriftMetric(column_name=c) for c in cats])
    r.run(reference_data=ref, current_data=cur)
    return r.as_dict()["metrics"]
for n in (50, 100, 200):
    sh, per, tests = [], {c: 0 for c in cats}, {}
    R = 40
    for i in range(R):
        idx = rng.permutation(len(pool))
        ref = pool.iloc[idx[:1000]].reset_index(drop=True)
        cur = pool.iloc[idx[1000:1000+n]].reset_index(drop=True)
        m = run(ref, cur)
        sh.append(m[0]["result"]["share_of_drifted_columns"])
        for x in m[1:]:
            per[x["result"]["column_name"]] += int(x["result"]["drift_detected"])
            tests[x["result"]["column_name"]] = x["result"]["stattest_name"]
    s = np.array(sh)
    print(f"ref=1000 n={n:<4} mean_share={s.mean():.3f} max={s.max():.3f} dataset_drift_rate={(s>=.5).mean():.2f} per_col={ {k: round(v/R,2) for k,v in per.items()} }", flush=True)
print(tests)
