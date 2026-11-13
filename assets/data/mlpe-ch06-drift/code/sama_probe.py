import sys, glob, json, collections
import pyarrow.parquet as pq
files = sorted(glob.glob(sys.argv[1] + "/*.parquet"))
print(pq.read_schema(files[0]).remove_metadata().to_string()[:1400])
rows = []
for f in files:
    t = pq.read_table(f, columns=["fname", "label"])
    rows += t.to_pylist()
print("rows", len(rows))
r0 = rows[0]
lab = r0["label"]
if isinstance(lab, str):
    lab = json.loads(lab)
print("example keys", list(lab.keys()) if isinstance(lab, dict) else type(lab))
print(json.dumps({k: (v if k != "labels" else (v[:1] if isinstance(v, list) else v)) for k, v in lab.items()}, default=str)[:900])
