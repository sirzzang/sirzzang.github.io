"""판정 방식 네 가지를 같은 분할 위에서 비교한다. 영상을 절반씩 나눠 한쪽을 reference, 다른 쪽을 평가 배치의 재료로 쓴다.
영상별 범주 수를 미리 세어 거리와 chi-square를 직접 계산하고, 앞부분에서 Evidently 결과와 대조한다."""
import sys
import numpy as np, pandas as pd
from scipy.spatial import distance
from scipy.stats import chisquare, chi2_contingency
from evidently.report import Report
from evidently.metrics import ColumnDriftMetric

df = pd.read_csv(sys.argv[1], dtype=str, keep_default_na=False)
cols = ["timeofday", "weather", "traffic", "vehicles", "sign", "traffic_light", "pedestrian", "opposite_lane"]
seqs = np.array(sorted(df.seq.unique()))
counts = {c: pd.crosstab(df.seq, df[c]).reindex(seqs).values.astype(float) for c in cols}
index = {s: i for i, s in enumerate(seqs)}
dark = np.array([s for s, t in df.groupby("seq").timeofday.first().items() if t != "Day"])
day = np.array([s for s in seqs if s not in set(dark)])
rng = np.random.default_rng(21)


def js(c, ref_ids, cur_ids):
    a = counts[c][ref_ids].sum(0); b = counts[c][cur_ids].sum(0)
    keep = (a + b) > 0
    return distance.jensenshannon(a[keep] / a.sum(), b[keep] / b.sum())


def chi_frames(c, ref_ids, cur_ids):
    """Evidently의 chi-square와 같은 계산. 프레임을 행으로 센다."""
    a = counts[c][ref_ids].sum(0); b = counts[c][cur_ids].sum(0)
    keep = (a + b) > 0
    return chisquare(b[keep], a[keep] * (b.sum() / a.sum()))[1]


def chi_videos(c, ref_ids, cur_ids):
    """영상당 1행. 영상 안에서 값이 하나인 컬럼에만 쓴다."""
    a = (counts[c][ref_ids] > 0).sum(0).astype(float); b = (counts[c][cur_ids] > 0).sum(0).astype(float)
    keep = (a + b) > 0
    return chisquare(b[keep], a[keep] * (b.sum() / a.sum()))[1]


def chi_two_sample(c, ref_ids, cur_ids):
    """영상당 1행. reference도 표본으로 보는 두 표본 chi-square."""
    a = (counts[c][ref_ids] > 0).sum(0).astype(float); b = (counts[c][cur_ids] > 0).sum(0).astype(float)
    keep = (a + b) > 0
    return chi2_contingency(np.vstack([a[keep], b[keep]]), correction=False)[1]


# 직접 계산한 거리와 Evidently 값 대조
worst = 0.0
for _ in range(20):
    pick = rng.choice(seqs, 10, replace=False)
    cur = df[df.seq.isin(pick)]; ref = df[~df.seq.isin(pick)]
    ids = np.array([index[s] for s in pick]); rest = np.setdiff1d(np.arange(len(seqs)), ids)
    for c in ("timeofday", "weather", "vehicles"):
        r = Report(metrics=[ColumnDriftMetric(column_name=c)])
        r.run(reference_data=ref[[c]], current_data=cur[[c]])
        worst = max(worst, abs(r.as_dict()["metrics"][0]["result"]["drift_score"] - js(c, rest, ids)))
print(f"max |direct - evidently| over 60 checks: {worst:.4f}")

# 직접 계산한 chi-square와 Evidently 값 대조
worst = 0.0
for _ in range(20):
    pick = rng.choice(seqs, 10, replace=False)
    cur = df[df.seq.isin(pick)]; ref = df[~df.seq.isin(pick)]
    ids = np.array([index[s] for s in pick]); rest = np.setdiff1d(np.arange(len(seqs)), ids)
    for c in ("timeofday", "weather"):
        r = Report(metrics=[ColumnDriftMetric(column_name=c, stattest="chisquare")])
        r.run(reference_data=ref[[c]], current_data=cur[[c]])
        worst = max(worst, abs(r.as_dict()["metrics"][0]["result"]["drift_score"] - chi_frames(c, rest, ids)))
print(f"max |direct - evidently| chi-square over 40 checks: {worst:.6f}")

SPLITS, NULLS, EVAL = 100, 400, 200
print(f"{SPLITS} random half splits of the videos, {NULLS} resamples for thresholds, {EVAL} batches per split")
for m, ks in ((10, (1, 3, 6)), (20, (3, 6, 10))):
    alarm_default = {c: [] for c in cols}; alarm_cal = {c: [] for c in cols}; thr = {c: [] for c in cols}
    alarm_chi = {c: [] for c in cols[:2]}; alarm_video = {c: [] for c in cols[:2]}; alarm_two = {c: [] for c in cols[:2]}
    detect_default = {k: [] for k in ks}; detect_cal = {k: [] for k in ks}; spread = {k: [] for k in ks}
    detect_video = {k: [] for k in ks}; detect_two = {k: [] for k in ks}
    any_default, any_cal, any_bonf = [], [], []
    for _ in range(SPLITS):
        while True:  # 어두운 영상 비중을 맞추지 않고 나눈다. 평가에 쓸 어두운 영상이 모자란 분할만 다시 뽑는다
            shuffled = rng.permutation(seqs)
            ref_s, hold_s = shuffled[: len(seqs) // 2], shuffled[len(seqs) // 2:]
            hold_dk, hold_dy = hold_s[np.isin(hold_s, dark)], hold_s[np.isin(hold_s, day)]
            if len(hold_dk) >= max(ks):
                break
        ref_i = np.array([index[s] for s in ref_s]); hold_i = np.array([index[s] for s in hold_s])
        t = {}; t_bonf = {}
        for c in cols:
            vals = []
            for _ in range(NULLS):
                pick = rng.choice(ref_i, m, replace=False)
                vals.append(js(c, np.setdiff1d(ref_i, pick), pick))
            t[c] = np.quantile(vals, .95); thr[c].append(t[c]); t_bonf[c] = np.quantile(vals, 1 - .05 / len(cols))
        batches = [rng.choice(hold_i, m, replace=False) for _ in range(EVAL)]
        all_d = np.array([[js(c, ref_i, x) for c in cols] for x in batches])
        any_default.append((all_d >= .1).any(axis=1).mean())
        any_cal.append((all_d >= np.array([t[c] for c in cols])).any(axis=1).mean())
        any_bonf.append((all_d >= np.array([t_bonf[c] for c in cols])).any(axis=1).mean())
        for c in cols:
            picks = [rng.choice(hold_i, m, replace=False) for _ in range(EVAL)]
            d = np.array([js(c, ref_i, x) for x in picks])
            alarm_default[c].append((d >= .1).mean()); alarm_cal[c].append((d >= t[c]).mean())
            if c in alarm_chi:
                alarm_chi[c].append(np.mean([chi_frames(c, ref_i, x) < .05 for x in picks]))
                alarm_video[c].append(np.mean([chi_videos(c, ref_i, x) < .05 for x in picks]))
                alarm_two[c].append(np.mean([chi_two_sample(c, ref_i, x) < .05 for x in picks]))
        dk_i = np.array([index[s] for s in hold_dk]); dy_i = np.array([index[s] for s in hold_dy])
        for k in ks:
            picks = [np.r_[rng.choice(dk_i, k, replace=False), rng.choice(dy_i, m - k, replace=False)] for _ in range(EVAL)]
            d = np.array([js("timeofday", ref_i, x) for x in picks])
            detect_video[k].append(np.mean([chi_videos("timeofday", ref_i, x) < .05 for x in picks]))
            detect_two[k].append(np.mean([chi_two_sample("timeofday", ref_i, x) < .05 for x in picks]))
            detect_default[k].append((d >= .1).mean()); detect_cal[k].append((d >= t["timeofday"]).mean()); spread[k].append((d.mean(), d.std(), t["timeofday"]))
    print(f"\nbatch = {m} videos, reference about 85 videos")
    print(f'{"column":<15}{"thr median":>11}{"default alarm":>15}{"calibrated alarm":>18}')
    for c in cols:
        print(f"{c:<15}{np.median(thr[c]):>11.3f}{np.mean(alarm_default[c]):>15.0%}{np.mean(alarm_cal[c]):>18.0%}")
    print(f"at least one of {len(cols)} columns over its threshold: default {np.mean(any_default):.0%}, calibrated {np.mean(any_cal):.0%}, calibrated at 1-0.05/{len(cols)} {np.mean(any_bonf):.0%}")
    print("same splits: frames chi-square / one row per video chi-square / one row per video two-sample chi-square")
    for c in alarm_chi:
        print(f"  {c:<12}{np.mean(alarm_chi[c]):>6.0%} /{np.mean(alarm_video[c]):>5.0%} /{np.mean(alarm_two[c]):>5.0%}")
    print("dark videos in batch -> detection on timeofday: default / calibrated / per video chi-square / per video two-sample, then mean distance, sd, threshold")
    for k in ks:
        mean_d, sd_d, thr_d = np.mean(spread[k], axis=0)
        print(f"  {k}/{m} ({k / m:.0%}): {np.mean(detect_default[k]):.0%} / {np.mean(detect_cal[k]):.0%} / {np.mean(detect_video[k]):.0%} / {np.mean(detect_two[k]):.0%}   d={mean_d:.3f} sd={sd_d:.3f} thr={thr_d:.3f}", flush=True)
