"""대응 후보 검증. A: 시퀀스 1행으로 줄여 세기, B: 프레임 그대로 chi-square, C: 시퀀스 재표본 임곗값."""
import sys
import numpy as np, pandas as pd
from evidently.report import Report
from evidently.metrics import ColumnDriftMetric

df = pd.read_csv(sys.argv[1], dtype=str, keep_default_na=False)
rng = np.random.default_rng(13)
seqs = df.seq.unique()
video_level_cols = ["timeofday", "weather"]
allc = ["timeofday", "weather", "traffic", "vehicles", "sign", "traffic_light", "pedestrian", "opposite_lane"]

def col(ref, cur, c, stattest=None, thr=None):
    kw = {}
    if stattest: kw["stattest"] = stattest
    if thr is not None: kw["stattest_threshold"] = thr
    r = Report(metrics=[ColumnDriftMetric(column_name=c, **kw)])
    r.run(reference_data=ref[[c]], current_data=cur[[c]])
    x = r.as_dict()["metrics"][0]["result"]
    return x["drift_score"], x["drift_detected"], x["stattest_name"]

T = 200
print("A/B  no drift injected, batch = 20 sequences, reference = remaining. alarm rate over", T, "splits")
print(f'{"column":<11}{"JS frame":>10}{"chi2 frame":>12}{"default seq-row":>17}  test used on seq rows')
for c in video_level_cols:
    a = b = d = 0; name = ""
    for _ in range(T):
        pick = rng.choice(seqs, 20, replace=False)
        cur = df[df.seq.isin(pick)]; ref = df[~df.seq.isin(pick)]
        a += col(ref, cur, c)[1]
        b += col(ref, cur, c, stattest="chisquare")[1]
        rs = ref.groupby("seq", as_index=False).first(); cs = cur.groupby("seq", as_index=False).first()
        _, det, name = col(rs, cs, c); d += det
    print(f"{c:<11}{a / T:>10.0%}{b / T:>12.0%}{d / T:>17.0%}  {name}", flush=True)

print("\nC  thresholds from reference-only sequence resampling, then tested on held-out sequences")
perm = rng.permutation(seqs); ref_s, hold_s = perm[:120], perm[120:]
ref = df[df.seq.isin(ref_s)]
print("reference seqs", len(ref_s), "held-out seqs", len(hold_s), "| dark seqs in ref/hold:",
      (df[df.seq.isin(ref_s)].groupby("seq").timeofday.first() != "Day").sum(),
      (df[df.seq.isin(hold_s)].groupby("seq").timeofday.first() != "Day").sum())
for m in (10, 20):
    null = {c: [] for c in allc}
    for _ in range(300):
        pick = rng.choice(ref_s, m, replace=False)
        cur = ref[ref.seq.isin(pick)]; r2 = ref[~ref.seq.isin(pick)]
        for c in allc:
            null[c].append(col(r2, cur, c)[0])
    thr = {c: float(np.quantile(null[c], .95)) for c in allc}
    print(f"m={m} thresholds:", {c: round(v, 3) for c, v in thr.items()})
    fa = {c: 0 for c in allc}; fd = {c: 0 for c in allc}
    N = 200
    for _ in range(N):
        pick = rng.choice(hold_s, m, replace=False)
        cur = df[df.seq.isin(pick)]
        for c in allc:
            fa[c] += col(ref, cur, c, stattest="jensenshannon", thr=thr[c])[1]
            fd[c] += col(ref, cur, c, stattest="jensenshannon")[1]
    print("   no-drift alarm default 0.1 :", {c: f"{fd[c] / N:.0%}" for c in allc})
    print("   no-drift alarm calibrated  :", {c: f"{fa[c] / N:.0%}" for c in allc}, flush=True)
    s = df[df.seq.isin(hold_s)].groupby("seq").timeofday.first()
    dark, day = s[s != "Day"].index.values, s[s == "Day"].index.values
    for k in (2, 4, 6):
        k2 = min(k, len(dark))
        if k2 < k: continue
        det = 0; share = []
        for _ in range(N):
            pick = np.r_[rng.choice(dark, k2, replace=False), rng.choice(day, m - k2, replace=False)]
            cur = df[df.seq.isin(pick)]
            det += col(ref, cur, "timeofday", stattest="jensenshannon", thr=thr["timeofday"])[1]
            share.append((cur.timeofday != "Day").mean())
        print(f"   dark seqs {k}/{m} (dark frames {np.mean(share):.0%}) detection on timeofday: {det / N:.0%}", flush=True)
