"""Throwaway: the lab replays mock_request_data.csv. Are those rows the head of Adult, and does that window give the lab's 0.5?"""
import sys, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from evidently.report import Report
from evidently.metrics import DatasetDriftMetric, ColumnDriftMetric
cols = ["age","Workclass","fnlwgt","Education","edunum","Marital-Status","Occupation","Relationship","Race","Sex","cg","cl","hpw","Native_country","income"]
df = pd.read_csv(sys.argv[1], names=cols)
mock = pd.read_csv(sys.argv[2])
same = (df[["Workclass","Education","Occupation"]].head(len(mock)).values == mock[["Workclass","Education","Occupation"]].values).all(axis=1)
print("mock rows", len(mock), "identical to first rows of Adult:", int(same.sum()))
cats = ["Education","Marital-Status","Native_country","Occupation","Race","Relationship","Sex","Workclass"]
def run(ref, cur):
    r = Report(metrics=[DatasetDriftMetric()] + [ColumnDriftMetric(column_name=c) for c in cats])
    r.run(reference_data=ref.reset_index(drop=True), current_data=cur.reset_index(drop=True))
    return r.as_dict()["metrics"]
full = df[cats]
clean = df[~df.isin([" ?"]).any(axis=1)][cats]
refs = {"full 32561": full, f"no-missing {len(clean)}": clean, "first 80%": full.iloc[:int(len(full)*.8)]}
for name, ref in refs.items():
    m = run(ref, full.iloc[:100])
    d = [x["result"]["column_name"] for x in m[1:] if x["result"]["drift_detected"]]
    print(f"ref={name:<18} window=rows 0-99  share={m[0]['result']['share_of_drifted_columns']:.3f} dataset_drift={m[0]['result']['dataset_drift']} drifted={d}")
print("\nsliding window of 50 over the same head rows (book text: window 50), ref=full")
vals = []
for a in range(0, 51, 5):
    m = run(full, full.iloc[a:a+50]); vals.append(m[0]["result"]["share_of_drifted_columns"])
print(" start:", list(range(0, 51, 5))); print(" share:", [round(v,3) for v in vals])
print("\nlarge batch vs same reference (lab's two 0 points are likely batch runs)")
for n in (5000, 30000):
    m = run(full, full.sample(n, random_state=0)); print(f" n={n} share={m[0]['result']['share_of_drifted_columns']}")
