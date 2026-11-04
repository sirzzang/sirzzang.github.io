"""Sama Drives California 라벨 -> 프레임 1행 태그 표. 이미지는 쓰지 않는다."""
import sys, glob, collections
import pandas as pd
import pyarrow.parquet as pq

def bucket(n):
    return "0" if n == 0 else "1-2" if n <= 2 else "3-5" if n <= 5 else "6+"

rec = []
for f in sorted(glob.glob(sys.argv[1] + "/*.parquet")):
    for r in pq.read_table(f, columns=["fname", "label"]).to_pylist():
        lab = r["label"]; labs = lab["labels"]
        cats = collections.Counter(l["category"] for l in labs)
        veh = sum(v for k, v in cats.items() if k.startswith("Vehicles"))
        dc = collections.Counter(
            (l["attributes"] or {}).get("drivingConditions") for l in labs)
        dc = {k: v for k, v in dc.items() if k in ("Light Traffic", "Moderate Traffic", "Heavy Traffic")}
        rec.append({
            "seq": r["fname"][:3],
            "timeofday": lab["attributes"]["timeofday"],
            "weather": lab["attributes"]["weather"],
            "traffic": max(dc, key=dc.get) if dc else "none",
            "vehicles": bucket(veh),
            "sign": "yes" if cats["Traffic | Signs"] else "no",
            "traffic_light": "yes" if cats["Traffic | Lights"] else "no",
            "pedestrian": "yes" if cats["Pedestrians"] else "no",
            "opposite_lane": "yes" if cats["Lanes | Opposite Lane"] else "no",
        })
df = pd.DataFrame(rec)
df.to_csv(sys.argv[2], index=False)
print("rows", len(df), "seq", df.seq.nunique())
cols = [c for c in df.columns if c != "seq"]
g = df.groupby("seq")
print(f'{"column":<15}{"k":>3}{"seq_constant":>14}  top values')
for c in cols:
    const = (g[c].nunique() == 1).mean()
    vc = df[c].value_counts(normalize=True).round(3)
    print(f"{c:<15}{df[c].nunique():>3}{const:>14.2f}  {dict(vc.head(4))}")
