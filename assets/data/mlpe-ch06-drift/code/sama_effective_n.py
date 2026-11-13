"""태그별 유효 표본 수를 거리에서 거꾸로 구한다.
같은 분포의 두 표본에서 Jensen-Shannon 발산의 평균은 약 (k-1)/8 * (1/n + 1/N)이다. 배치가 영상 m개이고 reference가 영상 M개이면 N = n*M/m로 두고 n을 푼다."""
import sys
import numpy as np, pandas as pd
from scipy.spatial import distance

df = pd.read_csv(sys.argv[1], dtype=str, keep_default_na=False)
cols = ["timeofday", "weather", "pedestrian", "opposite_lane", "traffic_light", "traffic", "vehicles", "sign"]
seqs = np.array(sorted(df.seq.unique()))
counts = {c: pd.crosstab(df.seq, df[c]).reindex(seqs).values.astype(float) for c in cols}
frames = df.groupby("seq").size().reindex(seqs).values
same = {c: (df.groupby("seq")[c].nunique() == 1).mean() for c in cols}
rng = np.random.default_rng(31)
R = 2000
print(f"videos {len(seqs)} frames {len(df)} trials {R}")
print(f'{"column":<15}{"k":>3}{"same in video":>15}' + "".join(f"{f'n_eff m={m}':>12}" for m in (10, 20, 40)))
for c in cols:
    k = counts[c].shape[1]; row = []
    for m in (10, 20, 40):
        jsd = []
        for _ in range(R):
            pick = rng.choice(len(seqs), m, replace=False); rest = np.setdiff1d(np.arange(len(seqs)), pick)
            a, b = counts[c][rest].sum(0), counts[c][pick].sum(0)
            jsd.append(distance.jensenshannon(a / a.sum(), b / b.sum()) ** 2)
        row.append((k - 1) / 8 * (1 + m / (len(seqs) - m)) / np.mean(jsd))
    print(f"{c:<15}{k:>3}{same[c]:>15.0%}" + "".join(f"{x:>12.0f}" for x in row), flush=True)
print("mean frames in a batch:", {m: int(frames.mean() * m) for m in (10, 20, 40)})
