"""영상 번호(=녹화 순서)대로 배치를 자른다. 앞 60개 영상이 reference다. 인위적 변경 없음."""
import sys
import pandas as pd
from evidently.report import Report
from evidently.metrics import DatasetDriftMetric, ColumnDriftMetric
fr = pd.read_csv(sys.argv[1], dtype=str, keep_default_na=False)
cols = ["timeofday","weather","traffic","vehicles","sign","traffic_light","pedestrian","opposite_lane"]
order = sorted(fr.seq.unique())
ref = fr[fr.seq.isin(order[:60])]
print("videos", len(order), "first", order[0], "last", order[-1], "reference frames", len(ref))
print(f'{"videos":<10}{"frames":>7}{"share":>7}{"dset":>6}{"JS tod":>8}{"JS wx":>8}  dominant tags')
for i in range(60, len(order), 10):
    ids = order[i:i + 10]
    cur = fr[fr.seq.isin(ids)]
    r = Report(metrics=[DatasetDriftMetric()] + [ColumnDriftMetric(column_name=c) for c in cols])
    r.run(reference_data=ref[cols], current_data=cur[cols])
    m = r.as_dict()["metrics"]; d = {c: x["result"]["drift_score"] for c, x in zip(cols, m[1:])}
    print(f'{ids[0]}-{ids[-1]:<6}{len(cur):>7}{m[0]["result"]["share_of_drifted_columns"]:>7.3f}{str(m[0]["result"]["dataset_drift"]):>6}'
          f'{d["timeofday"]:>8.3f}{d["weather"]:>8.3f}  {cur.timeofday.mode()[0]}/{cur.weather.mode()[0]}')
