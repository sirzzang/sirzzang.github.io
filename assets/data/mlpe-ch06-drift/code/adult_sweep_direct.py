"""Adult 윈도 판정을 5000회로 다시 잰다. 40회인 01번 결과의 구간이 넓어, Evidently와 같은 거리를 직접 계산해 반복을 늘렸다."""
import sys
import numpy as np, pandas as pd
from scipy.spatial import distance
from scipy.stats import chi2
from evidently.report import Report
from evidently.metrics import DatasetDriftMetric, ColumnDriftMetric

cols = ["age","Workclass","fnlwgt","Education","edunum","Marital-Status","Occupation","Relationship","Race","Sex","cg","cl","hpw","Native_country","income"]
cats = ["Education","Marital-Status","Native_country","Occupation","Race","Relationship","Sex","Workclass"]
raw = pd.read_csv(sys.argv[1], names=cols)
clean = raw[~raw.isin([" ?"]).any(axis=1)].reset_index(drop=True)
R = 5000


def encode(frame):
    out = {}
    for c in cats:
        codes, uniq = pd.factorize(frame[c])
        out[c] = (codes, len(uniq))
    return out


def distances(enc, idx):
    d = []
    for c in cats:
        codes, k = enc[c]
        p = np.bincount(codes, minlength=k) / len(codes)
        q = np.bincount(codes[idx], minlength=k) / len(idx)
        d.append(distance.jensenshannon(p, q))
    return np.array(d)


# 직접 계산이 Evidently와 같은지 먼저 본다. 윈도 안의 값이라 reference와 윈도의 범주 합집합은 reference의 범주와 같다
rng = np.random.default_rng(7)
enc_raw, enc_clean = encode(raw[cats]), encode(clean[cats])
worst = 0.0
for _ in range(10):
    idx = rng.choice(len(raw), 100, replace=False)
    r = Report(metrics=[DatasetDriftMetric()] + [ColumnDriftMetric(column_name=c) for c in cats])
    r.run(reference_data=raw[cats], current_data=raw[cats].iloc[idx].reset_index(drop=True))
    m = r.as_dict()["metrics"][1:]
    worst = max(worst, np.abs(np.array([x["result"]["drift_score"] for x in m]) - distances(enc_raw, idx)).max())
print(f"max |direct - evidently| over 80 checks: {worst:.6f}")

print("\nreference=adult.data 32,561 rows, random windows, R=5000")
print(f'{"n":>5}{"mean share":>12}{"p5":>7}{"p95":>7}{"dataset rate":>14}  per-column alarm')
sims = {}
for n in (50, 100, 200, 500, 1000, 2000):
    share = np.empty(R); alarm = np.zeros(8); mean_d = np.zeros(8)
    for i in range(R):
        d = distances(enc_raw, rng.choice(len(raw), n, replace=False))
        share[i] = (d >= .1).mean(); alarm += d >= .1; mean_d += d
    sims[n] = mean_d / R
    per = " ".join(f"{c[:6]}={a / R:.2f}" for c, a in zip(cats, alarm))
    print(f"{n:>5}{share.mean():>12.3f}{np.quantile(share, .05):>7.3f}{np.quantile(share, .95):>7.3f}{(share >= .5).mean():>14.1%}  {per}", flush=True)

print("\nmean distance per column and the window where the simulated mean falls below 0.1")
print(f'{"column":<15}{"k":>3}{"sim50":>7}{"fml50":>7}{"sim100":>7}{"fml100":>7}{"12.5(k-1)":>10}{"sim<0.1 at":>11}')
for j, c in enumerate(cats):
    codes, k = enc_raw[c]
    p = np.bincount(codes, minlength=k) / len(codes)
    cross = None
    for n in list(range(5, 100, 5)) + list(range(100, 1001, 25)):
        draws = rng.multinomial(n, p, size=2000) / n
        m = np.mean([distance.jensenshannon(p, q) for q in draws])
        if m < .1:
            cross = n
            break
    print(f"{c:<15}{k:>3}{sims[50][j]:>7.3f}{(np.sqrt((k - 1) / 400)):>7.3f}{sims[100][j]:>7.3f}{(np.sqrt((k - 1) / 800)):>7.3f}{12.5 * (k - 1):>10.0f}{str(cross):>11}", flush=True)

print("\nreference=missing rows dropped 30,162 rows: distribution of the share over random windows, R=5000")
for n in (50, 100):
    share = np.array([(distances(enc_clean, rng.choice(len(clean), n, replace=False)) >= .1).mean() for _ in range(R)])
    vals, cnt = np.unique(share, return_counts=True)
    print(f"n={n:<4} mean={share.mean():.3f} dataset rate={(share >= .5).mean():.1%} " + " ".join(f"{v:.3f}:{c / R:.1%}" for v, c in zip(vals, cnt)), flush=True)

print("\ncolumn alarm rate: simulated vs chi-square prediction P(chi2(k-1) >= 8 n t^2), t=0.1")
print(f'{"column":<15}{"k":>3}' + "".join(f"{f'sim{n}':>8}{f'fml{n}':>8}" for n in (50, 100, 200)) + f'{"sim 5% at":>11}{"fml 5% at":>11}')
for c in cats:
    codes, k = enc_raw[c]
    p = np.bincount(codes, minlength=k) / len(codes)
    row = ""
    for n in (50, 100, 200):
        draws = rng.multinomial(n, p, size=4000) / n
        sim = np.mean([distance.jensenshannon(p, q) >= .1 for q in draws])
        row += f"{sim:>8.0%}{chi2.sf(8 * n * .01, k - 1):>8.0%}"
    at = None
    for n in list(range(10, 200, 10)) + list(range(200, 1500, 25)):
        draws = rng.multinomial(n, p, size=2000) / n
        if np.mean([distance.jensenshannon(p, q) >= .1 for q in draws]) <= .05:
            at = n
            break
    print(f"{c:<15}{k:>3}{row}{str(at):>11}{chi2.isf(.05, k - 1) / .08:>11.0f}", flush=True)

print("\nwindow 100 over one random order of the rows: sliding by one row, then non-overlapping windows")
order = rng.permutation(len(raw))
alarms = np.array([(distances(enc_raw, order[a:a + 100]) >= .1).mean() >= .5 for a in range(0, 8000)])
print(f"sliding: alarm {alarms.mean():.1%}, next window also alarms {alarms[1:][alarms[:-1]].mean():.1%}")
blocks = np.array([(distances(enc_raw, order[a:a + 100]) >= .1).mean() >= .5 for a in range(0, len(raw) - 100, 100)])


def run_rate(x, r):
    return np.mean([x[i:i + r].all() for i in range(len(x) - r + 1)])


for r in (3, 5, 10):
    print(f"  {r} in a row: sliding {run_rate(alarms, r):.1%}, non-overlapping {run_rate(blocks, r):.1%}")

print("\nsize of a distance of 0.1")
print("  50:50 vs 64:36 ->", round(float(distance.jensenshannon([.5, .5], [.64, .36])), 3))
print("  a 2% category disappears ->", round(float(distance.jensenshannon([.98, .02], [1, 0])), 3))
print("  a 5% category disappears ->", round(float(distance.jensenshannon([.95, .05], [1, 0])), 3))
print("  no overlap ->", round(float(distance.jensenshannon([1, 0], [0, 1])), 3))
