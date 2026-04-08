---
title:  "[Dev] Kubernetes 공유 메모리: PyTorch DataLoader shm 부족 트러블슈팅"
excerpt: "Kubernetes에서 PyTorch DataLoader의 shared memory 부족 문제를 emptyDir 볼륨으로 해결한다."
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - PyTorch
  - DataLoader
  - shared-memory
  - emptyDir
  - Argo-Workflow
---

<br>

# TL;DR

- Kubernetes 환경에서 PyTorch DataLoader를 멀티 프로세스(`num_workers > 0`)로 실행하면, 공유 메모리(shared memory) 부족으로 `Bus error`가 발생할 수 있다
- 컨테이너의 `/dev/shm` 기본 크기가 64MiB로 제한되어 있기 때문이다
- `medium: Memory` 타입의 `emptyDir` 볼륨을 `/dev/shm`에 마운트하면 해결된다

<br>

# 문제

Kubernetes 환경에서 [YOLOX](https://github.com/Megvii-BaseDetection/YOLOX)(객체 탐지 모델) 학습을 위한 컨테이너를 실행했다. [Argo Workflow](https://argoproj.github.io/workflows/)(Kubernetes 네이티브 워크플로우 엔진)를 이용해 데이터 추출, 전처리 등의 파이프라인이 순차적으로 실행되고, 마지막 단계에서 모델 학습 컨테이너가 시작되는 구조다.

![kubernetes-pytorch-dataloader-shm-error]({{site.url}}/assets/images/kubernetes-pytorch-dataloader-shm-error.png){: .align-center}

학습 컨테이너가 시작된 직후, 공유 메모리(shared memory) 부족으로 컨테이너가 종료되었다.

> RuntimeError: DataLoader worker (pid 229) is killed by signal: Bus error. It is possible that dataloader's workers are out of shared memory. Please try to raise your shared memory limit.

에러 메시지를 분석하면 다음과 같다.

- `Bus error`: 프로세스가 접근 불가능한 메모리 영역에 쓰기를 시도했다는 신호
- `dataloader's workers are out of shared memory`: DataLoader 워커 프로세스들이 데이터를 공유하는 데 사용하는 공유 메모리 공간이 부족하다
- `raise your shared memory limit`: 공유 메모리 크기를 늘려야 한다

<br>

# 원인

## PyTorch DataLoader의 멀티 프로세스 데이터 로딩

PyTorch [DataLoader](https://pytorch.org/docs/stable/data.html#torch.utils.data.DataLoader)는 `num_workers` 파라미터가 1 이상이면 [멀티 프로세스 데이터 로딩](https://pytorch.org/docs/stable/data.html#multi-process-data-loading)을 수행한다. 각 워커 프로세스가 별도의 프로세스로 데이터를 로드하고, 메인 프로세스와 공유 메모리(shared memory)를 통해 데이터를 전달한다.

## /dev/shm과 컨테이너의 기본 제한

`/dev/shm`은 Linux에서 POSIX 공유 메모리를 위해 제공되는 tmpfs(메모리 기반 파일시스템) 마운트 포인트다. 프로세스 간 데이터 공유를 위해 사용되며, PyTorch DataLoader의 워커 프로세스들도 이 영역을 통해 텐서 데이터를 주고받는다.

Docker 컨테이너의 `/dev/shm` 기본 크기는 **64MiB**다. Kubernetes에서 실행되는 컨테이너도 컨테이너 런타임의 이 기본값을 그대로 사용하므로, 별도 설정이 없으면 `/dev/shm`이 64MiB로 제한된다. 대규모 데이터셋이나 배치 크기가 큰 학습의 경우, DataLoader 워커들이 이 제한을 쉽게 초과한다.

<br>

# 해결

## 선택지 비교

| 방법 | 설명 | 적합 여부 |
|------|------|-----------|
| Dataset 크기/변환 최적화 | 데이터 파이프라인을 경량화하여 공유 메모리 사용량 자체를 줄인다 | 노드 자원이 충분한 상황에서 굳이 성능을 희생할 필요 없다 |
| `num_workers` 값 축소 | 워커 수를 줄여 공유 메모리 사용량을 낮춘다 | 마찬가지로 노드 자원이 충분하므로 불필요한 트레이드오프다 |
| Docker `--shm-size` | 컨테이너의 `/dev/shm` 크기를 직접 지정한다 | Docker 실행 시 사용 가능하지만, Kubernetes Pod 스펙에서는 이 옵션을 직접 지정할 수 없다 |
| Docker `--ipc=host` | 호스트의 IPC 네임스페이스를 컨테이너와 공유한다 | 보안 격리가 깨지므로 프로덕션 환경에서는 권장하지 않는다 |
| **emptyDir(`medium: Memory`)** | **메모리 기반 emptyDir 볼륨을 `/dev/shm`에 마운트한다** | **Kubernetes 네이티브 방식으로, Pod 스펙만으로 설정 가능하다** |

노드 자원이 충분하고 Kubernetes 환경이므로, `emptyDir` 볼륨을 사용하는 것이 가장 적합하다.

<br>

## emptyDir로 /dev/shm 확장

`emptyDir`은 Pod와 수명 주기를 같이 하는 임시 볼륨으로, 빈 디렉토리로 시작한다. `medium`을 `Memory`로 설정하면 디스크 대신 메모리(tmpfs)에 데이터를 저장한다. 이 볼륨을 컨테이너의 `/dev/shm`에 마운트하면 기본 64MiB 제한을 원하는 크기로 확장할 수 있다.

```yaml
# emptyDir(medium: Memory)을 /dev/shm에 마운트하는 기본 패턴
apiVersion: v1
kind: Pod
metadata:
  name: example-pod
spec:
  containers:
  - name: example-container
    image: your_docker_image
    volumeMounts:
    - mountPath: /dev/shm  # 기본 64MiB /dev/shm을 대체
      name: dshm
  volumes:
  - name: dshm
    emptyDir:
      medium: Memory   # tmpfs(메모리 기반) 사용
      sizeLimit: 4Gi   # 공유 메모리 상한
```

이 패턴을 실제 Argo Workflow 매니페스트에 적용한 결과는 다음과 같다.

<details markdown="1">
<summary><b>Argo Workflow 매니페스트 전체</b></summary>

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Workflow
metadata:
  generateName: training-pipeline-eb042ap-d-231122-
  namespace: argo-workflow
spec:
  entrypoint: training-pipeline
  imagePullSecrets:
  - name: docker-pull-secret
  serviceAccountName: argo-workflow-argo-workflows-workflow-controller
  templates:
  - dag:
      tasks:
      - name: train-model
        template: model-trainer
    name: training-pipeline
  - container:
      args:
      - main.py
      - --config
      - yolox_config.ini
      - --mode
      - train
      command:
      - python3
      image: sir0123/neo-mlops:model-trainer-0.0.1
      imagePullPolicy: Always
      volumeMounts:
      - mountPath: /app/datasets/COCO  # 학습 데이터 PVC
        name: train-data
        readOnly: true
      - mountPath: /dev/shm  # emptyDir을 /dev/shm에 마운트
        name: shm-empty-dir
    name: model-trainer
  volumes:
  - name: train-data
    persistentVolumeClaim:
      claimName: train-data-pvc
  - emptyDir:
      medium: Memory   # tmpfs 사용
      sizeLimit: 2Gi   # 학습 데이터 규모에 맞게 설정
    name: shm-empty-dir
```

</details>

## 주의사항

- **`sizeLimit` 설정 필수**: `sizeLimit`을 설정하지 않으면 노드 메모리를 무한정 소비할 수 있다. 학습 데이터 규모와 배치 크기를 고려해 적절한 값을 설정해야 한다
- **Pod 메모리 limit과의 관계**: `medium: Memory`로 생성한 emptyDir의 사용량은 Pod의 메모리 limit에 포함된다. `/dev/shm` 사용량이 커지면 컨테이너가 OOM Kill 당할 수 있으므로, `resources.limits.memory`를 충분히 잡아야 한다
- **Pod 삭제 시 데이터 소멸**: emptyDir은 Pod와 수명 주기를 같이 하므로, Pod가 삭제되면 볼륨도 함께 사라진다. `/dev/shm` 확장 용도에서는 문제가 되지 않는다

<br>

# 정리

- Kubernetes에서 PyTorch DataLoader를 멀티 프로세스로 실행할 때 `Bus error`가 발생하면, `/dev/shm` 크기 부족을 의심해야 한다
- `emptyDir`에 `medium: Memory`를 설정하고 `/dev/shm`에 마운트하면, Kubernetes 네이티브 방식으로 공유 메모리 크기를 확장할 수 있다
- `sizeLimit`과 Pod의 메모리 limit을 함께 고려하여 설정해야 한다
- emptyDir 볼륨에 대한 자세한 내용은 [Pod 볼륨 - emptyDir]({% post_url 2026-04-05-Kubernetes-Pod-Volume-02-emptyDir %}) 포스트를 참고한다

<br>

