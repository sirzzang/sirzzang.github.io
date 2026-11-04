"""reference가 작을 때 Evidently의 chi-square가 5%보다 자주 울리는 이유를 나눠 본다.
기대 빈도를 reference 표본 비율로 만들면 reference의 오차가 그대로 판정에 들어간다."""
import sys
import numpy as np, pandas as pd
from scipy.stats import chisquare, chi2_contingency
from scipy.spatial import distance

cols = ["age","Workclass","fnlwgt","Education","edunum","Marital-Status","Occupation","Relationship","Race","Sex","cg","cl","hpw","Native_country","income"]
df = pd.read_csv(sys.argv[1], names=cols)
rng = np.random.default_rng(11)


def evidently_style(ref, cur):
    keys = sorted(set(ref) | set(cur))
    rc, cc = pd.Series(ref).value_counts(), pd.Series(cur).value_counts()
    k_norm = len(cur) / len(ref)
    f_exp = np.array([rc.get(k, 0) * k_norm for k in keys])
    f_obs = np.array([cc.get(k, 0) for k in keys], float)
    return chisquare(f_obs, f_exp)[1], f_exp


cats = ["Education", "Marital-Status", "Native_country", "Occupation", "Race", "Relationship", "Sex", "Workclass"]
print("(0) full reference 32,561 rows, stattest=chisquare for every column, no shift, 2000 windows")
codes = {c: pd.factorize(df[c])[0] for c in cats}
for n in (50, 100, 200):
    share = np.empty(2000); col = np.zeros(8)
    for i in range(2000):
        idx = rng.choice(len(df), n, replace=False); hits = []
        for c in cats:
            a = np.bincount(codes[c]).astype(float); b = np.bincount(codes[c][idx], minlength=len(a)).astype(float)
            keep = (a + b) > 0
            hits.append(chisquare(b[keep], a[keep] * (n / a.sum()))[1] < .05)
        share[i] = np.mean(hits); col += hits
    print(f"n={n:<4} dataset {np.mean(share >= .5):.1%} " + " ".join(f"{c[:6]}={x / 2000:.0%}" for c, x in zip(cats, col)), flush=True)

print("\n(0b) reference 1000 rows, no shift, window growing: Relationship (no rare category)")
pool = df["Relationship"].values
for n in (50, 200, 500, 1000):
    hit = 0
    for _ in range(3000):
        idx = rng.permutation(len(pool)); hit += evidently_style(pool[idx[:1000]], pool[idx[1000:1000 + n]])[0] < .05
    print(f"n={n:<5} alarm {hit / 3000:.1%}", flush=True)

R = 3000
print("\n(1) reference 1000 rows, no shift, alarm rate at p<0.05")
print(f'{"column":<15}{"n":>5}{"Evidently style":>17}{"expected from full data":>25}{"no unseen value":>17}{"trials":>8}{"expected<1":>12}')
for col in ("Race", "Workclass", "Education", "Native_country"):
    pool = df[col].values; pop = df[col].value_counts(normalize=True)
    for n in (50, 100, 200):
        hit = hit_pop = hit_none = none = 0; low = []
        for _ in range(R):
            idx = rng.permutation(len(pool)); ref, cur = pool[idx[:1000]], pool[idx[1000:1000 + n]]
            p, fe = evidently_style(ref, cur)
            hit += p < .05
            if not set(cur) - set(ref):
                none += 1; hit_none += p < .05; low.append((fe < 1).mean())
            fo = pd.Series(cur).value_counts().reindex(pop.index, fill_value=0).values.astype(float)
            hit_pop += chisquare(fo, pop.values * n)[1] < .05
        print(f"{col:<15}{n:>5}{hit / R:>17.1%}{hit_pop / R:>25.1%}{hit_none / max(none, 1):>17.1%}{none:>8}{np.mean(low) if low else 0:>12.0%}", flush=True)

print("\n(2) five categories, reference 1000 rows, no shift, Evidently style test on a large current")
p = np.array([.45, .25, .15, .10, .05])
for n in (1000, 10_000, 100_000):
    hit = 0
    for _ in range(2000):
        a, b = rng.multinomial(1000, p), rng.multinomial(n, p)
        hit += chisquare(b, a * (n / 1000))[1] < .05
    print(f"current {n:>7}: alarm {hit / 2000:.1%}", flush=True)

print("\n(3) five categories, 0.5pt moved between two categories, two samples of size n, chi2_contingency, 1000 runs")
p2 = p.copy(); p2[0] += .005; p2[-1] -= .005
print(f"population Jensen-Shannon distance {distance.jensenshannon(p, p2):.4f}")
for n in (10_000, 100_000, 1_000_000):
    ps, js = [], []
    for _ in range(1000):
        a, b = rng.multinomial(n, p), rng.multinomial(n, p2)
        ps.append(chi2_contingency(np.vstack([a, b]))[1]); js.append(distance.jensenshannon(a / a.sum(), b / b.sum()))
    ps, js = np.array(ps), np.array(js)
    print(f"n={n:<8} median p={np.median(ps):.1e} share p<0.05={np.mean(ps < .05):.1%} mean distance={js.mean():.4f}", flush=True)
ps = [chi2_contingency(np.vstack([rng.multinomial(10 ** 6, p), rng.multinomial(10 ** 6, p)]))[1] for _ in range(1000)]
print(f"no shift, n=1000000: share p<0.05={np.mean(np.array(ps) < .05):.1%}")
