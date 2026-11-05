import numpy as np
from scipy.stats import chi2_contingency

rng = np.random.default_rng(11)
p = np.array([.45, .25, .15, .10, .05])
Sref = 2000
print("F Scur by_frame by_seq")
for F in (50, 100, 200, 400):
    for Scur in (20, 50, 100, 200, 1000):
        fr = sq = 0
        for _ in range(500):
            a = rng.multinomial(Sref, p)
            b = rng.multinomial(Scur, p)
            keep = (a + b) > 0
            sq += chi2_contingency(np.vstack([a[keep], b[keep]]))[1] < .05
            fr += chi2_contingency(np.vstack([a[keep] * F, b[keep] * F]))[1] < .05
        print(F, Scur, f"{fr / 500:.3f}", f"{sq / 500:.3f}")
