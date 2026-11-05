"""보고서 HTML 두 개: 실습 윈도(Adult 100행), 드리프트를 넣지 않은 주행 배치(영상 10개)."""
import sys
import numpy as np, pandas as pd
from evidently.report import Report
from evidently.metric_preset import DataDriftPreset
adult, frames, out = sys.argv[1:4]
names = ["Age","Workclass","fnlwgt","Education","Education-Num","Marital-Status","Occupation","Relationship","Race","Sex","Capital-Gain","Capital-Loss","Hours-per-week","Native_country","Income"]
df = pd.read_csv(adult, names=names)
clean = df[~df.isin([" ?"]).any(axis=1)].reset_index(drop=True)
cats = ["Education","Marital-Status","Native_country","Occupation","Race","Relationship","Sex","Workclass"]
r = Report(metrics=[DataDriftPreset()]); r.run(reference_data=clean[cats], current_data=clean[cats].head(100))
r.save_html(out + "/report_adult_window100.html")
print("adult share", r.as_dict()["metrics"][0]["result"]["share_of_drifted_columns"])
fr = pd.read_csv(frames, dtype=str, keep_default_na=False)
cols = ["timeofday","weather","traffic","vehicles","sign","traffic_light","pedestrian","opposite_lane"]
seqs = fr.seq.unique(); rng = np.random.default_rng(3)
pick = rng.choice(seqs, 10, replace=False)
cur, ref = fr[fr.seq.isin(pick)], fr[~fr.seq.isin(pick)]
r = Report(metrics=[DataDriftPreset()]); r.run(reference_data=ref[cols], current_data=cur[cols])
r.save_html(out + "/report_sama_batch10.html")
res = r.as_dict()["metrics"][0]["result"]
print("sama frames", len(cur), "share", res["share_of_drifted_columns"], "dataset_drift", res["dataset_drift"])
