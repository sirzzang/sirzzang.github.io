# 데이터 참조와 캐시 실험 자료

학습 파이프라인이 데이터를 "이름"(경로, URI, PVC 이름, MLflow 데이터셋 정보)으로 가리킬 때, 데이터 내용이 바뀌면 무슨 일이 생기는지 확인한 코드와 결과다. 머신러닝 플랫폼 엔지니어링 스터디 4주차(책 7.2 데이터 전달, 8장 학습·검증 컴포넌트, 9.1 PVC)에서 출발했다.

| 시나리오 | 질문 | 결과 |
|---|---|---|
| midrun | 실행 중 데이터가 옮겨지거나(reorg) 내용만 바뀌면(edit). 공유 경로, run 전용 사본, 내용 다이제스트 고정, importer 비교 | `results/midrun.txt` |
| S2a | 캐시를 켠 채 URL의 내용만 바뀌면 | `results/s2a.txt` |
| S2b | importer로 같은 URI를 가리키면(`reimport=False`·`True`) | `results/s2b.txt` |
| S2c | 같은 PVC 이름 아래 내용만 바뀌면 | `results/s2c.txt` |
| S2d | 같은 컴포넌트·같은 인자를 이름만 다른 파이프라인으로 돌리면 | `results/s2d.txt` |
| S3 | 데이터셋 전체의 내용 다이제스트를 다음 단계의 입력 파라미터로 올리면. 제출 시점 `enable_caching=True` 덮어쓰기 포함 | `results/s3.txt` |
| S4 | MLflow 데이터셋 digest는 무엇을 보나. 로컬 SQLite 저장소의 데이터셋 레코드 | `results/s4_mlflow_digest.txt` |
| — | 내용 다이제스트 계산 비용 | `results/hash_cost.txt` |

## 결과 읽는 법

```text
  · data.py edit → 지금 내용 다이제스트 val e7943a3f, 데이터셋 전체 90450f6e
  [s2c-2] run=SUCCEEDED  report=SUCCEEDED, digest-path=SUCCEEDED[캐시]  report=e8d3825e
```

- `·` 줄은 실행기가 데이터를 바꾼 시점과 그 뒤의 실제 내용 다이제스트(호스트에서 계산)다. `↑ train 실행 중에 바꿨다`는 그 변경이 학습 단계 도중에 일어났다는 표시다.
- `[run 이름] run=<run 상태>  <단계>=<상태>, ...  report=<값>` 줄에서 단계 이름은 `pipelines.py` 함수 이름의 `_`를 `-`로 바꾼 것이다. 나열 순서는 실행 순서와 관계없다. 단계 상태 `None`은 앞 단계가 실패해 실행되지 않았다는 뜻이다.
- `[캐시]`는 그 단계의 driver 가 낸 `cached-decision=true`다. 실행 파드는 만들어지지 않았다. KFP API는 이 경우에도 `SUCCEEDED`를 낸다.
- 줄 끝 `report=`는 마지막 단계가 받아서 남긴 값(앞 8자)이고, 없으면 `-`다. 이 값과 `·` 줄의 실제 값을 비교하면 이전 결과를 재사용했는지 알 수 있다.
- 다이제스트는 모두 같은 방식이다: 하위 디렉터리까지 상대 경로 순으로 (상대 경로, 크기, 파일 내용의 SHA-256)을 이어 SHA-256 한 값. `train`은 정해진 시간만 기다리는 학습 대역이다.
- 각 run은 한 번씩 돌렸다. 결과가 정해진 동작(캐시 키 일치 여부)이라 반복하지 않았다.

## 구성

| 경로 | 내용 |
|---|---|
| `setup.sh` | kind 클러스터와 KFP standalone 2.17.3 설치 |
| `Dockerfile` | 컴포넌트 공용 이미지(kfp, boto3 미리 설치) |
| `infra.yaml` | 공유 디렉터리를 가리키는 PV·PVC, 같은 디렉터리를 HTTP로 내보내는 데이터 서버 |
| `data.py` | 토이 데이터 생성(`reset`), val·train 파일 하나 내용 변경(`edit`·`edit-train`), val 디렉터리 이동(`reorg`) |
| `pipelines.py` | 컴포넌트와 시나리오별 파이프라인 |
| `run.py` | 시나리오 실행기(제출, 실행 중 데이터 변경, 캐시 판정·결과 수집) |
| `s4_mlflow_digest.py` | S4. MLflow Dataset digest 비교와 로컬 SQLite 저장소의 데이터셋 레코드 |
| `hash_cost.py` | 내용 다이제스트 계산 시간. 만든 직후 읽으므로 페이지 캐시에 있을 가능성이 크다 |
| `results/` | 실행 출력 |

## 환경

| 항목 | 버전 |
|---|---|
| 호스트 | Apple Silicon Mac, Docker Desktop(엔진 29.9.2) |
| Kubernetes | kind v0.33.0, `kindest/node:v1.37.0`, 단일 노드 |
| KFP | 백엔드 2.17.3(`env/platform-agnostic`), SDK `kfp`·`kfp-kubernetes` 2.17.3 |
| MLflow | `mlflow-skinny` 3.18.0(+ SQLite 저장소용 `sqlalchemy`, `alembic`) |
| Python | 3.12(호스트 가상환경, 컴포넌트 이미지) |

공유 디렉터리는 hostPath라 호스트에서 바꾼 내용이 파드에 바로 보인다. NFS 같은 네트워크 파일시스템은 클라이언트의 속성 캐시 때문에 노드마다 잠시 다른 내용을 볼 수 있다.

## 다시 돌리기

```bash
# 1. 클러스터와 KFP. KUBECONFIG 는 새 파일로 지정해 기존 컨텍스트를 건드리지 않는다
export KUBECONFIG=$PWD/kubeconfig SHARED_DIR=$PWD/shared
# TLS 를 재서명하는 프록시 뒤라면 그 CA 파일을 EXTRA_CA 로 넘긴다
bash setup.sh

# 2. 컴포넌트 이미지(프록시 뒤라면 --secret id=ca,src=<CA 파일> 추가)
docker build -t mlpe-w4/py:1 . && kind load docker-image mlpe-w4/py:1 --name mlpe-w4

# 3. 공유 저장소, 데이터 서버, 토이 데이터
kubectl apply -f infra.yaml
python data.py "$SHARED_DIR" reset

# 4. 시나리오(importer 시나리오는 SeaweedFS 를 호스트에 연다)
pip install "kfp==2.17.3" "kfp-kubernetes==2.17.3" boto3 "mlflow-skinny==3.18.0" pandas sqlalchemy alembic
kubectl -n kubeflow port-forward svc/seaweedfs 19000:9000 &
S3_ENDPOINT=http://localhost:19000 SESSION=v2 python run.py midrun s2a s2b s2c s2d
SESSION=v2s3 python run.py s3
python s4_mlflow_digest.py
python hash_cost.py
```

`SESSION`은 파이프라인 이름 접미사다. KFP 캐시는 파이프라인 이름 단위로 조회되므로, 값을 바꾸면 이전 실행의 캐시와 섞이지 않는다. S2d는 접미사 `-d`를 더해 S2a와 캐시를 나눈다. `results/s3.txt`는 따로 돌린 회차(`v2s3`)다.

설치하며 달랐던 점 두 가지:

- 4.1.2편 환경과 같이 `kfp-metadata-writer` 이미지에는 arm64 항목이 없어 `setup.sh`가 amd64 digest로 고정한다.
- kubeflow 네임스페이스는 Pod Security `baseline`을 강제해 파드에 hostPath 볼륨을 직접 붙이지 못한다. 공유 디렉터리는 hostPath PV를 PVC로 붙인다.

## 확인한 소스

KFP 2.17.3(`https://github.com/kubeflow/pipelines/blob/2.17.3/backend/src/v2/`):

- 캐시 키 구성: `cacheutils/cache.go#L173-L229`, 이전 실행 조회: `cacheutils/cache.go#L105-L138`
- PVC 이름을 키에 넣는 이유와 조회 범위: `driver/cache.go#L80-L130`
- 캐시 기록은 캐시를 켜고 실행한 단계만: `component/launcher_v2.go#L300-L316`
- 입력 아티팩트 이름 = MLMD 아티팩트 ID: `metadata/converter.go#L186-L188`
- importer 재사용: `component/importer_launcher.go#L168-L184`, `metadata/client.go#L1303-L1347`
- 제출 시점 `enable_caching`이 모든 단계를 덮어씀: SDK `kfp/client/client.py`의 `_override_caching_options`

MLflow 3.18.0(`https://github.com/mlflow/mlflow/blob/v3.18.0/mlflow/`):

- `MetaDataset` digest: `data/meta_dataset.py`의 `_compute_digest`
- pandas digest: `data/digest_utils.py`의 `compute_pandas_digest`
- `log_input`이 digest를 그대로 남기는 경로: `tracking/fluent.py`의 `_create_dataset_input`, `data/dataset.py`의 `_to_mlflow_entity`
- 데이터셋 중복 제거와 digest 열 길이: `store/tracking/sqlalchemy_store.py`의 `_log_inputs_impl`, `store/tracking/dbmodels/models.py`의 `SqlDataset`
