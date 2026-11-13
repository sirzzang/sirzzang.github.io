"""Throwaway check: same-distribution windows vs Evidently 0.5.0 default drift decision."""
import sys, time, warnings, json
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from evidently.report import Report
from evidently.metrics import DatasetDriftMetric, ColumnDriftMetric

cols = ["age","Workclass","fnlwgt","Education","edunum","Marital-Status","Occupation","Relationship","Race","Sex","cg","cl","hpw","Native_country","income"]
df = pd.read_csv(sys.argv[1], names=cols, skipinitialspace=False)
cats = ["Education","Marital-Status","Native_country","Occupation","Race","Relationship","Sex","Workclass"]
ref = df[cats].reset_index(drop=True)
print("ref rows", len(ref), {c: ref[c].nunique() for c in cats})

def run(cur, ref=ref):
    r = Report(metrics=[DatasetDriftMetric()] + [ColumnDriftMetric(column_name=c) for c in cats])
    r.run(reference_data=ref, current_data=cur)
    return r.as_dict()["metrics"]

m = run(ref.sample(100, random_state=0).reset_index(drop=True))
print("dataset:", {k: m[0]["result"][k] for k in ("number_of_columns","number_of_drifted_columns","share_of_drifted_columns","dataset_drift")})
for x in m[1:]:
    res = x["result"]
    print(f'  {res["column_name"]:<16} test={res["stattest_name"]:<34} thr={res["stattest_threshold"]} score={res["drift_score"]:.4f} drifted={res["drift_detected"]}')

rng = np.random.default_rng(7)
rows = []
for n in (50, 100, 200, 500, 1000, 2000, 5000):
    shares, per = [], {c: 0 for c in cats}
    R = 40
    for i in range(R):
        idx = rng.choice(len(ref), n, replace=False)
        m = run(ref.iloc[idx].reset_index(drop=True))
        shares.append(m[0]["result"]["share_of_drifted_columns"])
        for x in m[1:]:
            per[x["result"]["column_name"]] += int(x["result"]["drift_detected"])
    s = np.array(shares)
    rows.append((n, s.mean(), s.min(), s.max(), (s >= 0.5).mean(), {k: round(v/R, 2) for k, v in per.items()}))
    print(f"n={n:<5} mean_share={s.mean():.3f} min={s.min():.3f} max={s.max():.3f} dataset_drift_rate={(s>=0.5).mean():.2f}  per_col={rows[-1][5]}", flush=True)
