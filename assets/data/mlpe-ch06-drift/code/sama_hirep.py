"""주행 태그 판정을 5000회로 다시 잰다. 40회인 20번 결과의 표본 오차가 커서, Evidently와 같은 거리를 직접 계산해 반복을 늘렸다."""
import sys
import numpy as np, pandas as pd
from scipy.spatial import distance
from evidently.report import Report
from evidently.metrics import ColumnDriftMetric

df = pd.read_csv(sys.argv[1], dtype=str, keep_default_na=False)
cols = ["timeofday", "weather", "traffic", "vehicles", "sign", "traffic_light", "pedestrian", "opposite_lane"]
show = ["timeofday", "weather", "vehicles", "sign"]
seqs = np.array(sorted(df.seq.unique()))
counts = {c: pd.crosstab(df.seq, df[c]).reindex(seqs).values.astype(float) for c in cols}
total = {c: counts[c].sum(0) for c in cols}
codes = {c: pd.factorize(df[c], sort=True)[0] for c in cols}
sizes = {c: int(codes[c].max()) + 1 for c in cols}
frames = df.groupby("seq").size().reindex(seqs).values
rng = np.random.default_rng(41)
R = 5000


def js(a, b):
    keep = (a + b) > 0
    return distance.jensenshannon(a[keep] / a.sum(), b[keep] / b.sum())


def batch_of_videos(m):
    pick = rng.choice(len(seqs), m, replace=False)
    d = {}
    for c in cols:
        b = counts[c][pick].sum(0)
        d[c] = js(total[c] - b, b)
    return d, frames[pick].sum()


def batch_of_frames(n):
    idx = rng.choice(len(df), n, replace=False)
    d = {}
    for c in cols:
        b = np.bincount(codes[c][idx], minlength=sizes[c]).astype(float)
        d[c] = js(np.bincount(codes[c], minlength=sizes[c]) - b, b)
    return d, n


# 직접 계산이 Evidently와 같은지 본다
worst = 0.0
for _ in range(20):
    pick = rng.choice(seqs, 10, replace=False)
    cur, ref = df[df.seq.isin(pick)], df[~df.seq.isin(pick)]
    ids = np.isin(seqs, pick)
    for c in ("timeofday", "weather", "vehicles", "sign"):
        r = Report(metrics=[ColumnDriftMetric(column_name=c)])
        r.run(reference_data=ref[[c]], current_data=cur[[c]])
        b = counts[c][ids].sum(0)
        worst = max(worst, abs(r.as_dict()["metrics"][0]["result"]["drift_score"] - js(total[c] - b, b)))
print(f"max |direct - evidently| over 80 checks: {worst:.6f}")

print(f"\nno shift, R={R}, reference = everything else")
print(f'{"batch":<14}{"frames":>8}{"dataset":>9}' + "".join(f"{c[:9]:>11}" for c in show) + f'{"mean d wx":>11}{"mean d tod":>12}')
for name, fn, arg in (("frames 1470", batch_of_frames, 1470), ("videos 10", batch_of_videos, 10), ("frames 2940", batch_of_frames, 2940), ("videos 20", batch_of_videos, 20),
                      ("frames 5880", batch_of_frames, 5880), ("videos 40", batch_of_videos, 40), ("videos 80", batch_of_videos, 80)):
    rows, fr = [], []
    for _ in range(R if "videos" in name else 1000):
        d, f = fn(arg); rows.append(d); fr.append(f)
    t = pd.DataFrame(rows)
    share = (t[cols] >= .1).mean(axis=1)
    print(f"{name:<14}{np.mean(fr):>8.0f}{(share >= .5).mean():>9.1%}" + "".join(f"{(t[c] >= .1).mean():>11.1%}" for c in show) + f'{t.weather.mean():>11.3f}{t.timeofday.mean():>12.3f}', flush=True)

print(f"\nbatch of contiguous videos in recording order vs shuffled videos, reference = everything else, R={R}")
print(f'{"videos":>7}{"wx shuffled":>13}{"wx contiguous":>15}{"tod shuffled":>14}{"tod contiguous":>16}')
for m in (10, 20, 40):
    d_mix = {"weather": [], "timeofday": []}; d_seq = {"weather": [], "timeofday": []}
    for _ in range(R):
        mix = rng.choice(len(seqs), m, replace=False); start = rng.integers(0, len(seqs) - m + 1); seq = np.arange(start, start + m)
        for c in d_mix:
            b = counts[c][mix].sum(0); d_mix[c].append(js(total[c] - b, b))
            b = counts[c][seq].sum(0); d_seq[c].append(js(total[c] - b, b))
    print(f"{m:>7}{np.mean(d_mix['weather']):>13.3f}{np.mean(d_seq['weather']):>15.3f}{np.mean(d_mix['timeofday']):>14.3f}{np.mean(d_seq['timeofday']):>16.3f}", flush=True)
same = {c: np.mean([df[df.seq == a][c].iloc[0] == df[df.seq == b][c].iloc[0] for a, b in zip(seqs[:-1], seqs[1:])]) for c in ("timeofday", "weather")}
runs = {c: 1 + int(np.sum([df[df.seq == a][c].iloc[0] != df[df.seq == b][c].iloc[0] for a, b in zip(seqs[:-1], seqs[1:])])) for c in ("timeofday", "weather")}
print("neighbouring videos with the same value:", {k: round(float(v), 2) for k, v in same.items()}, "runs:", runs)

print("\nrecording order: thresholds resampled inside the first 60 videos, batches of 10 after them")
first = np.arange(60); order_rows = []
for c in cols:
    vals = []
    for _ in range(2000):
        pick = rng.choice(first, 10, replace=False)
        vals.append(js(counts[c][np.setdiff1d(first, pick)].sum(0), counts[c][pick].sum(0)))
    order_rows.append(np.quantile(vals, .95))
thr60 = dict(zip(cols, order_rows)); print({c: round(float(v), 3) for c, v in thr60.items()})
print(f'{"videos":<10}{"frames":>7}{"over default":>14}{"over resampled":>16}  columns over resampled')
for a in range(60, len(seqs), 10):
    ids = np.arange(a, min(a + 10, len(seqs)))
    d = {c: js(counts[c][first].sum(0), counts[c][ids].sum(0)) for c in cols}
    over = [c for c in cols if d[c] >= thr60[c]]
    print(f"{seqs[ids[0]]}-{seqs[ids[-1]]:<6}{frames[ids].sum():>7}{sum(v >= .1 for v in d.values()):>14}{len(over):>16}  {' '.join(over)}", flush=True)

print(f"\ndark videos fixed in the batch, reference = half of the videos, batch of 20 from the other half, R={R}")
s = df.groupby("seq").timeofday.first()
dark = np.flatnonzero(s.reindex(seqs).values != "Day"); day = np.flatnonzero(s.reindex(seqs).values == "Day")
print("dark videos", len(dark), "of", len(seqs))
print(f'{"dark in batch":<15}{"dark frames":>12}{"timeofday":>11}{"dataset":>9}')
rows, share_dark = [], []
for _ in range(R):
    dk, dy = rng.permutation(dark), rng.permutation(day)
    ref_i = np.r_[dk[len(dk) // 2:], dy[len(dy) // 2:]]
    pool = np.r_[dk[: len(dk) // 2], dy[: len(dy) // 2]]
    pick = rng.choice(pool, 20, replace=False)
    rows.append({c: js(counts[c][ref_i].sum(0), counts[c][pick].sum(0)) for c in cols})
    share_dark.append(frames[np.intersect1d(pick, dark)].sum() / frames[pick].sum())
t0 = pd.DataFrame(rows); share0 = (t0[cols] >= .1).mean(axis=1)
print(f"{'random':<15}{np.mean(share_dark):>12.0%}{(t0.timeofday >= .1).mean():>11.1%}{(share0 >= .5).mean():>9.1%}", flush=True)
for k in (3, 6, 10, 12):
    rows, share_dark = [], []
    for _ in range(R):
        dk, dy = rng.permutation(dark), rng.permutation(day)
        ref_i = np.r_[dk[len(dk) // 2:], dy[len(dy) // 2:]]
        pick = np.r_[dk[: len(dk) // 2][:k], dy[: len(dy) // 2][: 20 - min(k, len(dk) // 2)]]
        d = {c: js(counts[c][ref_i].sum(0), counts[c][pick].sum(0)) for c in cols}
        rows.append(d); share_dark.append(frames[np.intersect1d(pick, dark)].sum() / frames[pick].sum())
    t = pd.DataFrame(rows); share = (t[cols] >= .1).mean(axis=1)
    print(f"{k}/20{'':<11}{np.mean(share_dark):>12.0%}{(t.timeofday >= .1).mean():>11.1%}{(share >= .5).mean():>9.1%}", flush=True)
