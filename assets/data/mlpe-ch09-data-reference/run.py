"""9.1.1 실험 시나리오 실행기.

사용: KUBECONFIG=... SHARED_DIR=... python run.py {midrun|s2a|s2b|s2c|s2d|s3} ...
  KFP_HOST    KFP API 주소(기본 http://localhost:30008)
  S3_ENDPOINT importer 시나리오에서 SeaweedFS 에 올릴 때 쓰는 주소(기본 http://localhost:9000, port-forward)
  SESSION     파이프라인 이름 접미사(기본 실행 시각). 캐시 조회 범위가 파이프라인 이름이라
              접미사를 바꾸면 이전 실험의 캐시와 섞이지 않는다
출력 형식: [run 이름] run=<run 상태>  <단계>=<상태>[캐시], ...  report=<마지막 단계가 남긴 값>
  [캐시]는 그 단계의 driver 가 낸 cached-decision=true(실행 파드를 만들지 않음)다.
  다이제스트는 앞 8자만 보인다. 단계 나열 순서는 실행 순서와 관계없다.
"""
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time

import kfp

import pipelines as p

SHARED = os.environ["SHARED_DIR"]
SESSION = os.environ.get("SESSION", time.strftime("%m%d%H%M"))
client = kfp.Client(host=os.environ.get("KFP_HOST", "http://localhost:30008"))
EXP = "mlpe-w4"
TASKS = ("list-files", "stage-in", "download", "importer", "digest-path", "digest-dataset", "train",
         "validate-listed", "validate-dataset", "validate-pinned", "report", "report-pair")


def kubectl(*args):
    return subprocess.run(["kubectl", "-n", "kubeflow", *args], capture_output=True, text=True).stdout


def manifest(root):
    """컴포넌트와 같은 방식의 내용 다이제스트(앞 8자)."""
    if not os.path.isdir(root):
        return "없음"
    h = hashlib.sha256()
    for d, _, fs in sorted(os.walk(root)):
        for f in sorted(fs):
            q = os.path.join(d, f)
            h.update(os.path.relpath(q, root).encode())
            h.update(str(os.path.getsize(q)).encode())
            h.update(hashlib.sha256(open(q, "rb").read()).digest())
    return h.hexdigest()[:8]


def data(action):
    subprocess.run([sys.executable, "data.py", SHARED, action], check=True)
    ds = os.path.join(SHARED, "dataset")
    print(f"  · data.py {action} → 지금 내용 다이제스트 val {manifest(os.path.join(ds, 'val'))}, "
          f"데이터셋 전체 {manifest(ds)}")


def reported(tag):
    path = os.path.join(SHARED, "_reports", f"{tag}.txt")
    if not os.path.exists(path):
        return "-"
    return " ".join(v[:8] for v in open(path).read().split())


def workflow(run_id):
    return json.loads(kubectl("get", "wf", "-l", f"pipeline/runid={run_id}", "-o", "json"))["items"][0]


def cache_decisions(wf):
    """단계 이름 → driver 의 cached-decision."""
    out = {}
    for n in wf["status"]["nodes"].values():
        for prm in (n.get("outputs") or {}).get("parameters", []):
            if prm["name"] == "cached-decision" and n["displayName"].endswith("-driver"):
                out[n["displayName"][: -len("-driver")]] = prm.get("value") == "true"
    return out


def pod_log(wf, node_part, kind):
    """워크플로에서 노드 이름에 node_part 가 든 파드의 main 로그."""
    for n in wf["status"]["nodes"].values():
        if n.get("type") == "Pod" and node_part in n.get("name", ""):
            pod = f"{wf['metadata']['name']}-system-container-{kind}-{n['id'].rsplit('-', 1)[-1]}"
            return kubectl("logs", pod, "-c", "main")
    return ""


def failed_log(wf, task):
    """실패한 단계의 실행 파드 로그에서 파이썬 예외 줄."""
    log = pod_log(wf, f".{task}(0).executor", "impl").splitlines()
    return next((l.strip() for l in reversed(log) if re.match(r"^\w+(Error|Exception):", l)), "")


def input_artifact(wf, task):
    """단계 driver 로그에 찍힌 첫 입력 아티팩트의 이름(MLMD 아티팩트 ID). 캐시 키에 들어가는 값이다."""
    m = re.search(r'"artifacts": \[\s*\{\s*"name": "(\d+)"', pod_log(wf, f".{task}-driver(0)", "driver"))
    return m.group(1) if m else "-"


def run(fn, tag, args=None, cache=None, mutate=None, show_input=None, suffix=""):
    """제출하고 끝날 때까지 기다린다.
    cache: None 이면 단계별 설정을 따르고, True/False 면 제출 시점에 모든 단계를 그 값으로 덮어쓴다.
    mutate: (단계 이름, 함수). 그 단계가 실행 중일 때 함수를 불러 데이터를 바꾼다."""
    pkg = os.path.join(tempfile.mkdtemp(), "pipeline.yaml")
    kfp.compiler.Compiler().compile(fn, pkg, pipeline_name=f"{fn.name}-{SESSION}{suffix}")
    rid = client.create_run_from_pipeline_package(
        pkg, arguments=dict(args or {}, tag=tag), run_name=tag, experiment_name=EXP, enable_caching=cache).run_id
    done = False
    while True:
        r = client.get_run(rid)
        tasks = (r.run_details.task_details if r.run_details else None) or []
        if mutate and not done and any(t.display_name == mutate[0] and t.state == "RUNNING" for t in tasks):
            time.sleep(10)
            mutate[1]()
            print(f"    ↑ {mutate[0]} 실행 중에 바꿨다")
            done = True
        if r.state in ("SUCCEEDED", "FAILED", "CANCELED"):
            time.sleep(5)  # 종료 직후에는 단계 상태가 덜 갱신돼 있다
            tasks = client.get_run(rid).run_details.task_details or []
            break
        time.sleep(3)
    wf = workflow(rid)
    cached = cache_decisions(wf)
    shown = sorted((t for t in tasks if t.display_name in TASKS), key=lambda t: t.create_time)
    states = ", ".join(f"{t.display_name}={t.state}{'[캐시]' if cached.get(t.display_name) else ''}" for t in shown)
    print(f"  [{tag}] run={r.state}  {states}  report={reported(tag)}")
    if show_input:
        print(f"    {show_input} 입력 아티팩트 ID = {input_artifact(wf, show_input)}")
    for t in shown:
        if t.state == "FAILED":
            print(f"    {t.display_name} 마지막 오류: {failed_log(wf, t.display_name)}")
    return r


def put_val_to_s3():
    """공유 디렉터리의 dataset/val/ 을 importer 가 가리킬 고정 URI 로 올린다(같은 객체 경로에 덮어쓴다)."""
    import boto3
    sec = json.loads(kubectl("get", "secret", "mlpipeline-minio-artifact", "-o", "json"))["data"]
    key = {k: base64.b64decode(v).decode() for k, v in sec.items()}
    s3 = boto3.client("s3", endpoint_url=os.environ.get("S3_ENDPOINT", "http://localhost:9000"),
                      aws_access_key_id=key["accesskey"], aws_secret_access_key=key["secretkey"])
    val = os.path.join(SHARED, "dataset", "val")
    for f in sorted(os.listdir(val)):
        s3.upload_file(os.path.join(val, f), "mlpipeline", f"datasets/toy-val/{f}")
    print("  · dataset/val/ → minio://mlpipeline/datasets/toy-val 업로드(같은 객체 경로에 덮어쓰기)")


def midrun():
    print("실행 중 데이터 변경 (run 전체 캐시 끔, train 실행 중에 바꾼다)")
    for change in ("reorg", "edit"):
        for fn, tag in ((p.s1_shared, "shared"), (p.s1_artifact, "artifact"), (p.s3_fingerprint, "digest")):
            data("reset")
            run(fn, f"mid-{change}-{tag}", args={"seconds": 60}, cache=False,
                mutate=("train", lambda c=change: data(c)))
    data("reset")
    put_val_to_s3()
    run(p.s2_importer_midrun, "mid-edit-importer", cache=False,
        mutate=("train", lambda: (data("edit"), put_val_to_s3())))
    data("reset")


def s2a():
    print("S2a 캐시를 켠 채 URL 의 내용만 바뀌면")
    data("reset")
    run(p.s2_download, "s2a-1")
    data("edit")
    run(p.s2_download, "s2a-2")
    run(p.s2_download, "s2a-3-run-nocache", cache=False)


def s2b():
    print("S2b importer 고정 URI: reimport=False(기본값)와 True")
    data("reset")
    put_val_to_s3()
    run(p.s2_importer_reuse, "s2b-reuse-1", show_input="digest-dataset")
    run(p.s2_importer_reimport, "s2b-reimport-1", show_input="digest-dataset")
    run(p.s2_importer_reimport, "s2b-reimport-1b-same", show_input="digest-dataset")
    data("edit")
    put_val_to_s3()
    run(p.s2_importer_reuse, "s2b-reuse-2", show_input="digest-dataset")
    run(p.s2_importer_reimport, "s2b-reimport-2", show_input="digest-dataset")


def s2c():
    print("S2c 같은 PVC 이름, 내용만 바뀌면")
    data("reset")
    run(p.s2_pvc, "s2c-1")
    data("edit")
    run(p.s2_pvc, "s2c-2")


def s2d():
    print("S2d 같은 컴포넌트·같은 인자, 파이프라인 이름만 다르면 (다른 시나리오와 캐시가 섞이지 않게 접미사 -d)")
    data("reset")
    run(p.s2_download, "s2d-1-original", suffix="-d")
    run(p.s2_download_renamed, "s2d-2-renamed", suffix="-d")
    run(p.s2_download, "s2d-3-original", suffix="-d")


def s3():
    print("S3 데이터셋 전체의 내용 다이제스트를 입력으로 올리기")
    data("reset")
    run(p.s3_fingerprint, "s3-1")
    run(p.s3_fingerprint, "s3-2-same")
    data("edit")
    run(p.s3_fingerprint, "s3-3-edit-val")
    data("edit-train")
    run(p.s3_fingerprint, "s3-4-edit-train")
    data("reset")
    print("  (제출 시점 enable_caching=True: 단계별로 끈 캐시를 덮어쓴다. 캐시를 끄고 돈 실행은 캐시에 기록되지 않으므로"
          " 첫 제출은 기록만 남기고, 데이터를 바꾼 뒤 두 번째 제출에서 결과가 드러난다)")
    run(p.s3_fingerprint, "s3-5-submit-cache-true", cache=True)
    data("edit")
    run(p.s3_fingerprint, "s3-6-submit-cache-true-edited", cache=True)
    data("reset")


if __name__ == "__main__":
    print(f"(SESSION={SESSION})")
    for name in sys.argv[1:]:
        globals()[name]()
