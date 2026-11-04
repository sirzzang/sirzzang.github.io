"""Throwaway: (1) JS distance null vs sqrt((k-1)/(8n)); (2) frame-vs-sequence sample size; (3) report latency."""
import sys, time, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from scipy.spatial import distance
from scipy.stats import chi2_contingency
cols = ["age","Workclass","fnlwgt","Education","edunum","Marital-Status","Occupation","Relationship","Race","Sex","cg","cl","hpw","Native_country","income"]
df = pd.read_csv(sys.argv[1], names=cols)
cats = ["Sex","Race","Relationship","Marital-Status","Workclass","Occupation","Education","Native_country"]
rng = np.random.default_rng(11)
print("(1) mean JS distance on same-distribution windows, 2000 draws; formula = sqrt((k-1)/(8n))")
print(f'{"column":<16}{"k":>3}{"k_eff":>7}' + "".join(f'  n={n}:sim/fml' for n in (50,100,200,500)) + "   n@0.1(fml)")
for c in cats:
    vc = df[c].value_counts(normalize=True); p = vc.values; k = len(p)
    keff = 1/np.sum(p**2)
    line = f"{c:<16}{k:>3}{keff:>7.1f}"
    for n in (50,100,200,500):
        q = rng.multinomial(n, p, size=2000)/n
        d = np.array([distance.jensenshannon(p, x) for x in q])
        line += f"  {d.mean():.3f}/{np.sqrt((k-1)/(8*n)):.3f}"
    line += f"   {12.5*(k-1):.0f}"
    print(line)

print("\n(2) same process, tag fixed per sequence, F frames per sequence; alarm rates over 500 trials")
p = np.array([.45,.25,.15,.10,.05]); F=100; Sref=2000
def trial(Scur):
    a = rng.multinomial(Sref, p); b = rng.multinomial(Scur, p)
    pa, pb = a/a.sum(), b/b.sum()
    js = distance.jensenshannon(pa, pb)
    keep = (a+b) > 0
    p_seq = chi2_contingency(np.vstack([a[keep], b[keep]]))[1]
    p_frm = chi2_contingency(np.vstack([a[keep]*F, b[keep]*F]))[1]
    return js, p_seq, p_frm
print(f'{"sequences":>9}{"frames":>9}{"JS mean":>9}{"JS>=0.1":>9}{"chi2 by frame":>15}{"chi2 by seq":>13}')
for Scur in (20,50,100,200,1000):
    r = np.array([trial(Scur) for _ in range(500)])
    print(f"{Scur:>9}{Scur*F:>9}{r[:,0].mean():>9.3f}{(r[:,0]>=.1).mean():>9.2f}{(r[:,2]<.05).mean():>15.2f}{(r[:,1]<.05).mean():>13.2f}")

print("\n(2b) real but small shift, huge n: p -> p + 0.5pt on class 0")
p2 = p.copy(); p2[0]+=.005; p2[-1]-=.005
for n in (10_000, 100_000, 1_000_000):
    a = rng.multinomial(n, p); b = rng.multinomial(n, p2)
    print(f"  n={n:>9}  chi2 p={chi2_contingency(np.vstack([a,b]))[1]:.2e}  JS={distance.jensenshannon(a/a.sum(), b/b.sum()):.4f}")

print("\n(3) report.run cost with the repo's report definition")
from evidently.report import Report
from evidently.metrics import ColumnDriftMetric, ColumnSummaryMetric, DatasetDriftMetric, DatasetMissingValuesMetric
ref = df[cats].reset_index(drop=True)
def mk():
    m=[DatasetDriftMetric(), DatasetMissingValuesMetric()]
    for c in cats: m += [ColumnDriftMetric(column_name=c), ColumnSummaryMetric(column_name=c)]
    return Report(metrics=m)
for rows,name in ((len(ref),"full ref"),(1000,"1000-row ref")):
    R = ref.sample(rows, random_state=1).reset_index(drop=True)
    ts=[]
    for i in range(12):
        cur = ref.sample(100, random_state=i).reset_index(drop=True)
        r = mk(); t=time.perf_counter(); r.run(reference_data=R, current_data=cur); ts.append(time.perf_counter()-t)
    ts=np.array(ts[2:])
    print(f"  {name:<14} rows={rows:<6} median={np.median(ts)*1000:.0f}ms  max={ts.max()*1000:.0f}ms")
