"""공개 주행 데이터(Sama) 태그 표로 Evidently 드리프트 판정을 재현한다.
 E1 무작위 프레임 윈도(책의 방식), E2 시퀀스 묶음(배치), E3 양성 대조(야간 비중 증가)."""
import sys, time
import numpy as np, pandas as pd
from evidently.report import Report
from evidently.metrics import DatasetDriftMetric, ColumnDriftMetric

df = pd.read_csv(sys.argv[1], dtype=str, keep_default_na=False)
cols = ["timeofday", "weather", "traffic", "vehicles", "sign", "traffic_light", "pedestrian", "opposite_lane"]
seqs = df.seq.unique()
rng = np.random.default_rng(7)
T = int(sys.argv[2]) if len(sys.argv) > 2 else 40

def judge(ref, cur):
    r = Report(metrics=[DatasetDriftMetric()] + [ColumnDriftMetric(column_name=c) for c in cols])
    r.run(reference_data=ref[cols], current_data=cur[cols])
    m = r.as_dict()["metrics"]
    res = {"share": m[0]["result"]["share_of_drifted_columns"], "dataset": m[0]["result"]["dataset_drift"]}
    for c, x in zip(cols, m[1:]):
        res[c] = x["result"]["drift_score"]; res[c + "_d"] = x["result"]["drift_detected"]
        res["test"] = x["result"]["stattest_name"]
    return res

def summary(name, rows, frames=None):
    t = pd.DataFrame(rows)
    fr = f"{np.mean(frames):>8.0f}" if frames is not None else f"{'':>8}"
    print(f"{name:<14}{fr}{t.share.mean():>7.3f}{t.share.min():>6.2f}{t.share.max():>6.2f}{t.dataset.mean():>7.0%}"
          f"{t.timeofday.mean():>7.3f}{t.weather.mean():>7.3f}{t.vehicles.mean():>7.3f}{t.sign.mean():>7.3f}"
          f"{t.timeofday_d.mean():>6.0%}{t.weather_d.mean():>6.0%}{t.vehicles_d.mean():>6.0%}{t.sign_d.mean():>6.0%}", flush=True)
    return t

hdr = f'{"case":<14}{"frames":>8}{"share":>7}{"min":>6}{"max":>6}{"dset":>7}{"JS tod":>7}{"JS wx":>7}{"JS veh":>7}{"JS sign":>7}{"d tod":>6}{"d wx":>6}{"d veh":>6}{"d sgn":>6}'
t0 = time.time()
x = judge(df, df.sample(100, random_state=1))
print("stattest:", x["test"], "| one run sec:", round(time.time() - t0, 2))

print("\nE1 random frames from the whole table (reference = all frames)"); print(hdr)
for n in (50, 100, 200, 500, 1000, 5000):
    rows = [judge(df, df.sample(n, random_state=int(rng.integers(1e9)))) for _ in range(T)]
    summary(f"n={n}", rows, [n])

print("\nE2 batch = m whole sequences, reference = remaining sequences (no drift injected)"); print(hdr)
for m in (3, 5, 10, 20, 40, 80):
    rows, fr = [], []
    for _ in range(T):
        pick = rng.choice(seqs, m, replace=False)
        cur = df[df.seq.isin(pick)]; ref = df[~df.seq.isin(pick)]
        rows.append(judge(ref, cur)); fr.append(len(cur))
    summary(f"m={m}", rows, fr)

print("\nE2b same frame counts as E2, frames drawn at random across sequences (split frames, not sequences)"); print(hdr)
for m, n in ((5, 735), (10, 1470), (20, 2940), (40, 5880)):
    rows = []
    for _ in range(T):
        idx = rng.choice(df.index.values, n, replace=False)
        cur = df.loc[idx]; ref = df.drop(idx)
        rows.append(judge(ref, cur))
    summary(f"m~{m}", rows, [n])

print("\nE3 positive control: reference = half of sequences, current = 20 sequences from the other half with a chosen dark share"); print(hdr)
s = df.groupby("seq").timeofday.first()
dark_all = s[s != "Day"].index.values; day_all = s[s == "Day"].index.values
print("dark sequences:", len(dark_all), "day sequences:", len(day_all))
for p in (0.14, 0.30, 0.50, 0.70):
    rows, fr, real = [], [], []
    for _ in range(T):
        dk = rng.permutation(dark_all); dy = rng.permutation(day_all)
        pool_dk, pool_dy = dk[: len(dk) // 2], dy[: len(dy) // 2]
        ref = df[df.seq.isin(np.r_[dk[len(dk) // 2:], dy[len(dy) // 2:]])]
        k = int(round(p * 20))
        pick = np.r_[pool_dk[:k], pool_dy[: 20 - min(k, len(pool_dk))]]
        cur = df[df.seq.isin(pick)]
        rows.append(judge(ref, cur)); fr.append(len(cur)); real.append((cur.timeofday != "Day").mean())
    summary(f"dark={p:.0%}", rows, fr)
    print(f"   realized dark frame share {np.mean(real):.2f}", flush=True)
print("total sec", round(time.time() - t0))
