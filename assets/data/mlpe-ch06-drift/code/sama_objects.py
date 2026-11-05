import sys, glob, collections
import pandas as pd
import pyarrow.parquet as pq
files = sorted(glob.glob(sys.argv[1] + "/*.parquet"))
cat = collections.Counter(); dc = collections.Counter(); lc = collections.Counter()
rec = []
for f in files:
    for r in pq.read_table(f, columns=["fname", "label"]).to_pylist():
        labs = r["label"]["labels"]
        c = collections.Counter(l["category"] for l in labs)
        cat.update(c)
        for l in labs:
            a = l["attributes"] or {}
            dc[a.get("drivingConditions")] += 1
            lc[a.get("laneChange")] += 1
        row = {"fname": r["fname"]}
        row.update({f"n_{k}": v for k, v in c.items()})
        rec.append(row)
print("categories", cat.most_common(40))
print("drivingConditions", dc.most_common(12))
print("laneChange", lc.most_common(12))
df = pd.DataFrame(rec).fillna(0)
df["seq"] = df.fname.str.slice(0, 3)
cols = [c for c in df.columns if c.startswith("n_")]
print(df[cols].describe().T[["mean", "max"]].round(2).to_string())
df.to_csv(sys.argv[2], index=False)
