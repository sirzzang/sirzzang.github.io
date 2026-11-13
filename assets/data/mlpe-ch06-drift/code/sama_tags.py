import sys, glob, re
import pandas as pd
import pyarrow.parquet as pq
files = sorted(glob.glob(sys.argv[1] + "/*.parquet"))
rec = []
for f in files:
    for r in pq.read_table(f, columns=["fname", "label"]).to_pylist():
        a = r["label"]["attributes"]
        cats = {l["category"] for l in r["label"]["labels"]}
        rec.append({"fname": r["fname"], "timeofday": a["timeofday"], "weather": a["weather"], "ncat": len(cats)})
df = pd.DataFrame(rec)
df["seq"] = df.fname.str.extract(r"^(\d+)-")[0]
df["idx"] = df.fname.str.extract(r"-(\d+)\.")[0].astype(float)
print(df.head(3).to_string())
print("rows", len(df), "seq", df.seq.nunique())
print(df.groupby("seq").size().describe().round(1).to_string())
for c in ("timeofday", "weather"):
    print(df[c].value_counts(dropna=False).to_string())
g = df.groupby("seq")
for c in ("timeofday", "weather"):
    n = g[c].nunique(dropna=False)
    print(c, "seq with single value:", (n == 1).sum(), "of", len(n))
seq = g.agg(n=("fname", "size"), tod=("timeofday", "first"), wx=("weather", "first"))
print(pd.crosstab(seq.tod, seq.wx).to_string())
df.to_csv(sys.argv[2], index=False)
