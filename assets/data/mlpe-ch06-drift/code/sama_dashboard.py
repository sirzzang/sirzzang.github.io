"""주행 태그 표를 영상 10개짜리 배치로 나눠 로컬 Evidently workspace에 쌓는다. 드리프트는 넣지 않았다."""
import sys, datetime
import numpy as np, pandas as pd
from evidently.report import Report
from evidently.metrics import DatasetDriftMetric, ColumnDriftMetric
from evidently.ui.workspace import Workspace
from evidently.ui.dashboards import DashboardPanelPlot, PanelValue, PlotType, ReportFilter
frames, path = sys.argv[1:3]
fr = pd.read_csv(frames, dtype=str, keep_default_na=False)
cols = ["timeofday","weather","traffic","vehicles","sign","traffic_light","pedestrian","opposite_lane"]
order = np.random.default_rng(5).permutation(fr.seq.unique())
ref_s, rest = order[:61], order[61:]
ref = fr[fr.seq.isin(ref_s)]
ws = Workspace.create(path)
project = ws.create_project("driving-tags", description="Sama Drives California tags, 10 sequences per batch, no drift injected")
flt = ReportFilter(metadata_values={}, tag_values=[])
project.dashboard.add_panel(DashboardPanelPlot(title="Share of drifted tags per batch", filter=flt, size=2, plot_type=PlotType.LINE,
    values=[PanelValue(metric_id="DatasetDriftMetric", field_path="share_of_drifted_columns", legend="share")]))
project.dashboard.add_panel(DashboardPanelPlot(title="Drift score by tag (threshold 0.1)", filter=flt, size=2, plot_type=PlotType.LINE,
    values=[PanelValue(metric_id="ColumnDriftMetric", metric_args={"column_name.name": c}, field_path="drift_score", legend=c) for c in ("timeofday","weather","vehicles","sign")]))
project.save()
base = datetime.datetime(2026, 1, 1)
for i in range(0, len(rest), 10):
    cur = fr[fr.seq.isin(rest[i:i + 10])]
    r = Report(metrics=[DatasetDriftMetric()] + [ColumnDriftMetric(column_name=c) for c in cols], timestamp=base + datetime.timedelta(days=i // 10))
    r.run(reference_data=ref[cols], current_data=cur[cols])
    m = r.as_dict()["metrics"]
    print(f"batch {i // 10:>2} frames {len(cur):>5} share {m[0]['result']['share_of_drifted_columns']:.3f} dataset_drift {m[0]['result']['dataset_drift']}")
    ws.add_report(project.id, r)
print("project", project.id)
