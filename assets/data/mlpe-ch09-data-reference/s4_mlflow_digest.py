"""S4: MLflow 데이터셋 digest는 무엇을 보고 계산되는가.

(a) 같은 경로의 파일 내용이 바뀌어도 MetaDataset digest가 같은가
(b) pandas 표에서 앞 1만 행 이후의 값만 바꾸면 digest가 같은가
(c) 생성자에 내용 다이제스트를 넘기면 내용 변경이 digest에 드러나는가
(d) 로컬 SQLite 추적 저장소에 두 run을 log_input 하면 데이터셋 레코드가 어떻게 남는가
    (같은 경로, run 사이에 내용만 바꿈. 기본 digest 와 내용 다이제스트를 각각 시험)
digest 열은 36자라(`dbmodels/models.py` SqlDataset.digest) 내용 다이제스트는 앞 32자를 넘긴다.
"""
import hashlib
import os
import sqlite3
import tempfile
import warnings

import pandas as pd

warnings.filterwarnings("ignore")
os.environ["MLFLOW_DISABLE_AGENT_HINT"] = "1"
import mlflow  # noqa: E402
from mlflow.data.dataset_source_registry import resolve_dataset_source  # noqa: E402
from mlflow.data.meta_dataset import MetaDataset  # noqa: E402
from mlflow.data.pandas_dataset import from_pandas  # noqa: E402


def manifest_digest(root):
    """파이프라인 컴포넌트와 같은 방식의 내용 다이제스트(전체 hex)."""
    h = hashlib.sha256()
    for d, _, fs in sorted(os.walk(root)):
        for f in sorted(fs):
            p = os.path.join(d, f)
            h.update(os.path.relpath(p, root).encode())
            h.update(str(os.path.getsize(p)).encode())
            h.update(hashlib.sha256(open(p, "rb").read()).digest())
    return h.hexdigest()


def meta(root, digest=None):
    return MetaDataset(source=resolve_dataset_source(root), name="val", digest=digest)


with tempfile.TemporaryDirectory() as tmp:
    root = os.path.join(tmp, "val")
    os.makedirs(root)
    path = os.path.join(root, "img_000.bin")
    open(path, "wb").write(b"A" * 1024)
    before = meta(root).digest, meta(root, manifest_digest(root)[:32]).digest
    open(path, "wb").write(b"B" * 1024)  # 같은 이름·같은 크기, 내용만 바꾼다
    after = meta(root).digest, meta(root, manifest_digest(root)[:32]).digest
    print(f"(a) MetaDataset 기본 digest   변경 전 {before[0]}  변경 후 {after[0]}  같음={before[0] == after[0]}")
    print(f"(c) digest=내용 다이제스트     변경 전 {before[1][:8]}  변경 후 {after[1][:8]}  같음={before[1] == after[1]}")

    df = pd.DataFrame({"x": range(20_000), "y": ["a"] * 20_000})
    base = from_pandas(df, name="t").digest
    for label, row in [("앞 1만 행 안(5행)", 5), ("1만 행 이후(15000행)", 15_000)]:
        changed = df.copy()
        changed.loc[row, "x"] = -1
        d = from_pandas(changed, name="t").digest
        print(f"(b) pandas {label} 값 변경   {base} → {d}  같음={base == d}")

    db = os.path.join(tmp, "mlflow.db")
    mlflow.set_tracking_uri(f"sqlite:///{db}")
    for label, use_content in (("기본 digest", False), ("내용 다이제스트", True)):
        mlflow.set_experiment(f"s4-{'content' if use_content else 'default'}")
        for i, body in enumerate((b"A", b"B")):
            open(path, "wb").write(body * 1024)
            ds = meta(root, manifest_digest(root)[:32] if use_content else None)
            with mlflow.start_run(run_name=f"run-{i + 1}"):
                mlflow.log_input(ds, context="validation")
        exp_id = mlflow.get_experiment_by_name(f"s4-{'content' if use_content else 'default'}").experiment_id
        con = sqlite3.connect(db)
        n_ds = con.execute("select count(*) from datasets where experiment_id=?", (exp_id,)).fetchone()[0]
        n_in = con.execute("select count(*) from inputs i join runs r on i.destination_id=r.run_uuid "
                           "where r.experiment_id=?", (exp_id,)).fetchone()[0]
        con.close()
        print(f"(d) {label}: 내용이 다른 run 2개 → 데이터셋 레코드 {n_ds}개, run 입력 연결 {n_in}개")
