"""Evidently 인자가 드리프트 컬럼 비율을 실제로 바꾸는지와, reference 크기별 데이터셋 판정을 라이브러리로 직접 돌려 본다."""
import sys
import numpy as np, pandas as pd
from evidently.report import Report
from evidently.metrics import DatasetDriftMetric, ColumnDriftMetric

cols = ["age","Workclass","fnlwgt","Education","edunum","Marital-Status","Occupation","Relationship","Race","Sex","cg","cl","hpw","Native_country","income"]
cats = ["Education","Marital-Status","Native_country","Occupation","Race","Relationship","Sex","Workclass"]
df = pd.read_csv(sys.argv[1], names=cols)
clean = df[~df.isin([" ?"]).any(axis=1)].reset_index(drop=True)
ref, cur = clean[cats], clean[cats].head(100)


def share(metrics, a=ref, b=cur):
    r = Report(metrics=metrics); r.run(reference_data=a, current_data=b)
    return r.as_dict()["metrics"][0]["result"]


three = ("Education", "Native_country", "Occupation")
print("window = first 100 rows without missing values")
print(" default", share([DatasetDriftMetric()])["share_of_drifted_columns"])
m = share([DatasetDriftMetric()] + [ColumnDriftMetric(column_name=c, stattest_threshold=.3 if c in three else None) for c in cats])
print(" ColumnDriftMetric(stattest_threshold=0.3) on three columns ->", m["share_of_drifted_columns"], m["dataset_drift"])
m = share([DatasetDriftMetric(per_column_stattest_threshold={c: .3 for c in three})])
print(" DatasetDriftMetric(per_column_stattest_threshold) ->", m["share_of_drifted_columns"], m["dataset_drift"])
m = share([DatasetDriftMetric(drift_share=.7)])
print(" DatasetDriftMetric(drift_share=0.7) ->", m["share_of_drifted_columns"], m["dataset_drift"])
m = share([DatasetDriftMetric(stattest="chisquare")])
print(" DatasetDriftMetric(stattest='chisquare') ->", m["share_of_drifted_columns"], m["dataset_drift"])

rng = np.random.default_rng(17)
pool = df[cats].reset_index(drop=True)
print("\nno shift, dataset drift rate with the library, 300 windows")
print(f'{"n":>5}{"full reference, chisquare":>27}{"1000-row reference, default":>29}')
for n in (50, 100, 200):
    a = b = 0
    for _ in range(300):
        idx = rng.choice(len(pool), n, replace=False)
        a += share([DatasetDriftMetric(stattest="chisquare")], pool, pool.iloc[idx].reset_index(drop=True))["dataset_drift"]
        order = rng.permutation(len(pool))
        b += share([DatasetDriftMetric()], pool.iloc[order[:1000]].reset_index(drop=True), pool.iloc[order[1000:1000 + n]].reset_index(drop=True))["dataset_drift"]
    print(f"{n:>5}{a / 300:>27.1%}{b / 300:>29.1%}", flush=True)

p = df["Native_country"].value_counts(normalize=True)
print("\nNative_country categories", len(p), "below 1%:", int((p < .01).sum()))
