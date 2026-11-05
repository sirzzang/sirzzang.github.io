"""reference를 1000행으로 줄였을 때 Native_country 오경보가 왜 늘어나는지 본다.
Evidently의 chi-square는 reference 비율로 기대 빈도를 만든다. current에만 있는 범주는 기대 빈도가 0이라 p값이 0이 된다."""
import sys
import numpy as np, pandas as pd
from evidently.report import Report
from evidently.metrics import ColumnDriftMetric

cols = ["age","Workclass","fnlwgt","Education","edunum","Marital-Status","Occupation","Relationship","Race","Sex","cg","cl","hpw","Native_country","income"]
df = pd.read_csv(sys.argv[1], names=cols)
pool = df[["Native_country"]].reset_index(drop=True)
rng = np.random.default_rng(3)
print(f'{"n":>4}{"alarm":>7}{"unseen in ref":>15}{"alarm|unseen":>14}{"alarm|none":>12}')
for n in (50, 100, 200):
    alarm = unseen = both = none_alarm = 0
    R = 200
    for _ in range(R):
        idx = rng.permutation(len(pool))
        ref = pool.iloc[idx[:1000]].reset_index(drop=True)
        cur = pool.iloc[idx[1000:1000 + n]].reset_index(drop=True)
        r = Report(metrics=[ColumnDriftMetric(column_name="Native_country")])
        r.run(reference_data=ref, current_data=cur)
        hit = r.as_dict()["metrics"][0]["result"]["drift_detected"]
        new = bool(set(cur.Native_country) - set(ref.Native_country))
        alarm += hit; unseen += new; both += hit and new; none_alarm += hit and not new
    print(f"{n:>4}{alarm / R:>7.0%}{unseen / R:>15.0%}{both / max(unseen, 1):>14.0%}{none_alarm / max(R - unseen, 1):>12.0%}", flush=True)
