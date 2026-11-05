"""Throwaway: mock rows vs Adult after dropping missing rows; exact lab window."""
import sys, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from evidently.report import Report
from evidently.metrics import DatasetDriftMetric, ColumnDriftMetric
cols = ["age","Workclass","fnlwgt","Education","edunum","Marital-Status","Occupation","Relationship","Race","Sex","cg","cl","hpw","Native_country","income"]
df = pd.read_csv(sys.argv[1], names=cols)
mock = pd.read_csv(sys.argv[2])
clean = df[~df.isin([" ?"]).any(axis=1)].reset_index(drop=True)
k = ["Workclass","Education","Occupation"]
print("mock vs no-missing head, identical rows:", int((clean[k].head(len(mock)).values == mock[k].values).all(axis=1).sum()), "of", len(mock))
cats = ["Education","Marital-Status","Native_country","Occupation","Race","Relationship","Sex","Workclass"]
def run(ref, cur):
    r = Report(metrics=[DatasetDriftMetric()] + [ColumnDriftMetric(column_name=c) for c in cats])
    r.run(reference_data=ref.reset_index(drop=True), current_data=cur.reset_index(drop=True))
    return r.as_dict()["metrics"]
ref = clean[cats]
m = run(ref, ref.head(100))
print("ref=no-missing all, window=mock's 100 rows: share", m[0]["result"]["share_of_drifted_columns"], "dataset_drift", m[0]["result"]["dataset_drift"])
for x in m[1:]:
    r = x["result"]; print(f'  {r["column_name"]:<16} {r["stattest_name"]} score={r["drift_score"]:.4f} drifted={r["drift_detected"]}')
print("window 50 sliding over those rows:", [round(run(ref, ref.iloc[a:a+50])[0]["result"]["share_of_drifted_columns"],3) for a in range(0,51,10)])
