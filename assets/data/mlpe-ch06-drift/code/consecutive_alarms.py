"""겹치지 않는 윈도의 연속 판정을 행 순서 300개로 잰다. 08번의 값은 행 순서 한 번의 결과라 구간이 넓다."""
import sys
import numpy as np, pandas as pd
from scipy.spatial import distance

cols = ["age","Workclass","fnlwgt","Education","edunum","Marital-Status","Occupation","Relationship","Race","Sex","capgain","caploss","hours","Native_country","income"]
cats = ["Education","Marital-Status","Native_country","Occupation","Race","Relationship","Sex","Workclass"]
raw = pd.read_csv(sys.argv[1], names=cols)
WINDOW, ORDERS = 100, 300
enc = []
for c in cats:
    codes, uniq = pd.factorize(raw[c])
    enc.append((codes, len(uniq), np.bincount(codes, minlength=len(uniq)) / len(codes)))


def alarm(idx):
    d = [distance.jensenshannon(p, np.bincount(codes[idx], minlength=k) / len(idx)) for codes, k, p in enc]
    return (np.array(d) >= .1).mean() >= .5


def run_rate(x, r):
    return np.mean([x[i:i + r].all() for i in range(len(x) - r + 1)])


rng = np.random.default_rng(11)
rates = {1: [], 3: [], 5: [], 10: []}
for _ in range(ORDERS):
    order = rng.permutation(len(raw))
    x = np.array([alarm(order[a:a + WINDOW]) for a in range(0, len(raw) - WINDOW, WINDOW)])
    for r in rates:
        rates[r].append(run_rate(x, r))
print(f"window {WINDOW}, non-overlapping, {ORDERS} row orders, {len(x)} windows per order")
for r, v in rates.items():
    v = np.array(v)
    print(f"  {r:>2} in a row: mean {v.mean():.1%}, 5-95% over orders {np.quantile(v, .05):.1%}~{np.quantile(v, .95):.1%}")
