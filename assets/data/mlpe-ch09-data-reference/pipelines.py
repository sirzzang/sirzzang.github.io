"""9.1.1 실험의 컴포넌트와 파이프라인.

데이터는 공유 디렉터리(PVC shared-data, 컨테이너 안 /data)에 있다.
- dataset/{train,val}/: data.py 가 만드는 토이 데이터
- _reports/: 각 run 의 마지막 report 단계가 받은 값을 남기는 곳
내용 다이제스트는 모든 컴포넌트가 같은 방식으로 계산한다: 하위 디렉터리까지 상대 경로 순으로
(상대 경로, 크기, 파일 내용의 SHA-256)을 이어 SHA-256 한 값(전체 hex).
경량 컴포넌트는 함수 본문만 직렬화되므로 이 계산을 컴포넌트마다 다시 적는다.
train 은 학습 대역이다. 정해진 시간만 기다리고 데이터를 읽지 않는다.
"""
import functools

from kfp import dsl, kubernetes
from kfp.dsl import Dataset, Input, Output

IMG = "mlpe-w4/py:1"  # kfp를 미리 설치한 이미지(Dockerfile). 실행 중 pip 설치를 하지 않는다
component = functools.partial(dsl.component, base_image=IMG, install_kfp_package=False)
URL = "http://data-server.kubeflow:8000/dataset/val/"
URI = "minio://mlpipeline/datasets/toy-val"


def mount(task):
    """PVC shared-data 를 /data 에 붙인다."""
    kubernetes.mount_pvc(task, pvc_name="shared-data", mount_path="/data")
    return task


def nocache(task):
    """이 단계의 캐시를 끈다."""
    task.set_caching_options(False)
    return task


# ---- 컴포넌트 ----

@component
def list_files(root: str) -> str:
    """학습을 시작할 때 데이터 목록을 만든다(데이터로더 구성에 해당)."""
    import json
    import os
    return json.dumps(sorted(os.path.relpath(os.path.join(d, f), root)
                             for d, _, fs in os.walk(root) for f in fs))


@component
def train(seconds: int, data_ref: str) -> str:
    """학습 대역. data_ref 는 어떤 데이터를 보고 도는지를 입력으로 드러내 캐시 키에 넣는다."""
    import time
    time.sleep(seconds)
    return f"model@{data_ref[:16]}"


@component
def validate_listed(root: str, files: str, model: str) -> str:
    """학습 시작 때 만든 목록대로 파일을 열어 내용 다이제스트를 낸다."""
    import hashlib
    import json
    import os
    h = hashlib.sha256()
    for rel in json.loads(files):
        p = os.path.join(root, rel)
        h.update(rel.encode())
        h.update(str(os.path.getsize(p)).encode())
        h.update(hashlib.sha256(open(p, "rb").read()).digest())
    return h.hexdigest()


@component
def stage_in(root: str, out: Output[Dataset]):
    """공유 경로의 데이터를 이 run 전용 아티팩트로 복사한다."""
    import shutil
    shutil.copytree(root, out.path)


@component
def validate_dataset(ds: Input[Dataset], model: str) -> str:
    """아티팩트로 받은 사본의 내용 다이제스트를 낸다."""
    import hashlib
    import os
    root, h = ds.path, hashlib.sha256()
    for d, _, fs in sorted(os.walk(root)):
        for f in sorted(fs):
            p = os.path.join(d, f)
            h.update(os.path.relpath(p, root).encode())
            h.update(str(os.path.getsize(p)).encode())
            h.update(hashlib.sha256(open(p, "rb").read()).digest())
    return h.hexdigest()


@component
def download(url: str, out: Output[Dataset]):
    """URL 의 디렉터리 목록을 읽어 파일을 모두 내려받는다(책 7.3.1의 다운로드 단계에 해당)."""
    import os
    import re
    import urllib.request
    os.makedirs(out.path, exist_ok=True)
    listing = urllib.request.urlopen(url).read().decode()
    for name in re.findall(r'href="([^"/?]+)"', listing):
        urllib.request.urlretrieve(url + name, os.path.join(out.path, name))


@component
def digest_dataset(ds: Input[Dataset]) -> str:
    """아티팩트의 내용 다이제스트."""
    import hashlib
    import os
    root, h = ds.path, hashlib.sha256()
    for d, _, fs in sorted(os.walk(root)):
        for f in sorted(fs):
            p = os.path.join(d, f)
            h.update(os.path.relpath(p, root).encode())
            h.update(str(os.path.getsize(p)).encode())
            h.update(hashlib.sha256(open(p, "rb").read()).digest())
    return h.hexdigest()


@component
def digest_path(root: str) -> str:
    """경로 아래 파일의 내용 다이제스트."""
    import hashlib
    import os
    h = hashlib.sha256()
    for d, _, fs in sorted(os.walk(root)):
        for f in sorted(fs):
            p = os.path.join(d, f)
            h.update(os.path.relpath(p, root).encode())
            h.update(str(os.path.getsize(p)).encode())
            h.update(hashlib.sha256(open(p, "rb").read()).digest())
    return h.hexdigest()


@component
def validate_pinned(root: str, expected: str, model: str) -> str:
    """검증을 시작할 때 내용 다이제스트를 다시 계산해, 학습 전에 고정한 값과 다르면 실패한다."""
    import hashlib
    import os
    h = hashlib.sha256()
    for d, _, fs in sorted(os.walk(root)):
        for f in sorted(fs):
            p = os.path.join(d, f)
            h.update(os.path.relpath(p, root).encode())
            h.update(str(os.path.getsize(p)).encode())
            h.update(hashlib.sha256(open(p, "rb").read()).digest())
    actual = h.hexdigest()
    if actual != expected:
        raise RuntimeError(f"manifest mismatch: 고정 다이제스트 {expected[:8]}, 현재 {actual[:8]}")
    return actual


@component
def report(tag: str, value: str):
    """받은 값을 /data/_reports/<tag>.txt 에 남긴다."""
    import os
    os.makedirs("/data/_reports", exist_ok=True)
    open(f"/data/_reports/{tag}.txt", "w").write(value + "\n")


@component
def report_pair(tag: str, first: str, second: str):
    """두 값을 한 줄로 남긴다."""
    import os
    os.makedirs("/data/_reports", exist_ok=True)
    open(f"/data/_reports/{tag}.txt", "w").write(f"{first} {second}\n")


# ---- 실행 중 데이터 변경 ----

@dsl.pipeline(name="s1-shared-path")
def s1_shared(seconds: int = 60, tag: str = "s1-shared"):
    files = mount(list_files(root="/data/dataset/val"))
    model = train(seconds=seconds, data_ref=files.output)
    val = mount(validate_listed(root="/data/dataset/val", files=files.output, model=model.output))
    mount(report(tag=tag, value=val.output))


@dsl.pipeline(name="s1-artifact")
def s1_artifact(seconds: int = 60, tag: str = "s1-artifact"):
    staged = mount(stage_in(root="/data/dataset/val"))
    model = train(seconds=seconds, data_ref="staged")
    val = validate_dataset(ds=staged.outputs["out"], model=model.output)
    mount(report(tag=tag, value=val.output))


@dsl.pipeline(name="s2-importer-midrun")
def s2_importer_midrun(seconds: int = 60, tag: str = "s2b-midrun"):
    """importer 출력을 두 단계가 각자 내려받는다. 그 사이에 같은 경로의 객체를 바꾼다."""
    imp = dsl.importer(artifact_uri=URI, artifact_class=Dataset, reimport=False)
    first = digest_dataset(ds=imp.output)
    model = train(seconds=seconds, data_ref=first.output)
    second = validate_dataset(ds=imp.output, model=model.output)
    mount(report_pair(tag=tag, first=first.output, second=second.output))


# ---- 실행 사이 데이터 변경(캐시) ----

def _download(url, tag):
    dl = download(url=url)
    d = digest_dataset(ds=dl.outputs["out"])
    mount(nocache(report(tag=tag, value=d.output)))


@dsl.pipeline(name="s2-download")
def s2_download(url: str = URL, tag: str = "s2a"):
    _download(url, tag)


@dsl.pipeline(name="s2-download-renamed")  # 이름만 다른 같은 파이프라인
def s2_download_renamed(url: str = URL, tag: str = "s2d"):
    _download(url, tag)


@dsl.pipeline(name="s2-importer-reuse")
def s2_importer_reuse(tag: str = "s2b-reuse"):
    imp = dsl.importer(artifact_uri=URI, artifact_class=Dataset, reimport=False)
    d = digest_dataset(ds=imp.output)
    mount(nocache(report(tag=tag, value=d.output)))


@dsl.pipeline(name="s2-importer-reimport")
def s2_importer_reimport(tag: str = "s2b-reimport"):
    imp = dsl.importer(artifact_uri=URI, artifact_class=Dataset, reimport=True)
    d = digest_dataset(ds=imp.output)
    mount(nocache(report(tag=tag, value=d.output)))


@dsl.pipeline(name="s2-pvc")
def s2_pvc(tag: str = "s2c"):
    d = mount(digest_path(root="/data/dataset/val"))
    mount(nocache(report(tag=tag, value=d.output)))


# ---- 내용 다이제스트를 입력으로 ----

@dsl.pipeline(name="s3-fingerprint")
def s3_fingerprint(seconds: int = 5, tag: str = "s3"):
    fp = mount(nocache(digest_path(root="/data/dataset")))      # 다이제스트 단계는 캐시를 끈다
    model = train(seconds=seconds, data_ref=fp.output)           # 다이제스트가 같을 때만 캐시가 적중한다
    val = mount(nocache(validate_pinned(root="/data/dataset", expected=fp.output, model=model.output)))
    mount(nocache(report(tag=tag, value=val.output)))
