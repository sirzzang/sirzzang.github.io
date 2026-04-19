---
title: "[EKS] EKS GPU 트러블슈팅: 3. 장애 재현 - 3. 분산학습과 NCCL 통신 - 1. 배경 및 재현 실험 설계"
excerpt: "분산학습의 원리, NCCL 통신 계층, EKS에서의 실험 설계까지 분산학습 장애 실험 설계의 배경에 대해 정리해보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - AWS
  - EKS
  - GPU
  - NCCL
  - Distributed-Training
  - PyTorch
  - torchrun
  - Troubleshooting
  - AWS-EKS-Workshop-Study
  - AWS-EKS-Workshop-Study-Week-5
---

*정영준님의 AWS EKS Workshop Study(AEWS) [5주차 학습 내용](https://devfloor9.github.io/engineering-playbook/slides/eks-debugging/)을 기반으로 합니다.*

<br>

# TL;DR

[이전 글]({% post_url 2026-04-09-Kubernetes-EKS-GPU-TroubleShooting-03-02-vLLM-TroubleShooting %})까지 인프라 층(Device Plugin)과 앱 층(vLLM) 장애를 각각 재현했다. 이번에는 **노드 간 네트워크 층** 장애를 다루기 위해, 먼저 분산학습과 NCCL 통신의 배경을 정리한다.

- **분산학습 3방식**: Data Parallel(DP), Tensor Parallel(TP), Pipeline Parallel(PP). 실무에서는 이들을 조합(3D parallelism)하고, DeepSpeed/Megatron-LM/FSDP가 추상화한다
- **init_process_group 초기화 4요소**: `RANK`, `WORLD_SIZE`, `MASTER_ADDR`, `MASTER_PORT`. 이 네 값이 환경변수로 주입되어야 프로세스 간 rendezvous가 이루어진다
- **초기화 시퀀스**: c10d TCPStore rendezvous → NCCL bootstrap → NCCL communicator. SG 차단은 **첫 번째 단계**(c10d)에서 먼저 막힐 수 있다
- **NCCL transport 우선순위**: NVLink → RDMA/EFA → TCP Socket. EKS 일반 인스턴스에서는 TCP Socket이 유일한 경로이고, 이것이 node SG의 ephemeral self-ref(1025-65535/tcp)를 타고 흐른다
- **실험 설계**: Training Operator나 Ray 대신 **Pod 2개 + headless Service**를 선택한다. webhook 간섭 없이 SG 차단의 효과만 격리해서 관찰하기 위함이다

<br>

# 분산학습 개요

## 분산학습의 필요성

단일 GPU 메모리에 담기지 않는 모델이 늘고 있다. LLaMA 65B weights가 약 130 GiB, GPT-3 175B weights가 약 350 GiB에 달하는데, 현존하는 단일 GPU 메모리(H100 80 GiB 기준)로는 이 규모의 모델을 그대로 올리기 어렵다. 분산학습(Distributed Training)은 **여러 GPU와 여러 노드에 모델이나 데이터를 나눠 담고, 매 step마다 gradient를 모아 다시 뿌리는** 반복 과정이다.

## 분산 방식 3가지

| 방식 | 원리 | NCCL 사용 패턴 |
| --- | --- | --- |
| **Data Parallel (DP)** | 같은 모델을 모든 GPU에 복제, 데이터 배치만 쪼개 분산. gradient를 `all_reduce`로 평균 내어 동기화 | step 종료 시 `all_reduce` 1회 |
| **Tensor Parallel (TP)** | 한 레이어 내부 행렬곱을 GPU 차원으로 쪼갬 | layer 내부 forward/backward 중에도 `all_reduce`/`all_gather` 발생 |
| **Pipeline Parallel (PP)** | 레이어 단위로 GPU를 나눔. 앞뒤 GPU 사이에 activation/gradient 전달 | point-to-point `send`/`recv` |

실무에서는 셋을 조합(3D parallelism)하고, DeepSpeed/Megatron-LM/FSDP 같은 프레임워크가 이를 추상화한다. 이 프레임워크들은 아래와 같이 PyTorch distributed 위에 올라가는 계층이고, 실제 GPU 간 통신은 결국 NCCL을 통해 이루어진다.

```text
DeepSpeed / Megatron-LM        ← 학습 최적화 프레임워크 (ZeRO, 3D parallelism)
FSDP / DDP                     ← PyTorch 내장 분산 전략
torch.distributed              ← PyTorch distributed API (init_process_group, c10d)
NCCL                           ← GPU 집합 통신 라이브러리 (all_reduce, all_gather)
```

따라서 이번 실험에서 재현하는 SG 차단(c10d/NCCL 층 장애)은 어떤 프레임워크를 쓰든 동일하게 발생한다. DP가 가장 흔하고, 본 실험에서도 DP(all_reduce) 기반 통신을 사용한다.

## 분산 프로세스 초기화 — 4가지 필수 요소

`torch.distributed.init_process_group(backend="nccl")` 한 줄이 실제로는 **프로세스들끼리 TCP로 만나 NCCL communicator를 구성하는** 과정이다. 이를 위해 아래 4가지(+1) 환경변수가 필요하다.

| 변수 | 의미 | 누가 주입하는가 |
| --- | --- | --- |
| `RANK` | 이 프로세스의 전역 번호 (0, 1, 2, ...) | 실행 환경 (torchrun, operator, 직접 env) |
| `WORLD_SIZE` | 전체 프로세스 수 | 위와 동일 |
| `LOCAL_RANK` | 한 노드 내의 번호 (0..nproc_per_node-1) | torchrun 자동 주입 |
| `MASTER_ADDR` | rank 0 프로세스가 떠있는 주소 | 실행 환경 |
| `MASTER_PORT` | rank 0 프로세스가 listen 중인 포트 | 실행 환경 |

## 초기화 시퀀스

`init_process_group` 호출 시 내부에서 진행되는 단계를 정리하면 다음과 같다.

1. **c10d TCPStore rendezvous**: rank 0이 `MASTER_PORT`(29500)에 TCPStore 서버(TCP listen)를 열고, 나머지 rank가 TCPStore 클라이언트로 connect한다. store-based barrier가 `WORLD_SIZE`개 프로세스의 접속을 대기하며, 각 rank는 자신의 네트워크 주소를 store에 등록한다. SG 차단 시 이 단계에서 timeout이 발생할 수 있다
2. **NCCL bootstrap**: `WORLD_SIZE`개 프로세스가 모두 store에 접속하여 barrier가 풀리면, 각 rank가 store에서 읽어온 peer 주소를 바탕으로 NCCL이 자체 peer-to-peer 연결(TCP 소켓 또는 RDMA)을 수립한다. 이때 별도의 ephemeral 포트를 사용한다
3. **NCCL communicator 구성 완료**: 이후 실제 `all_reduce`/`all_gather`는 NCCL 경로로 흐른다

이 시퀀스에서 중요한 점은, **1단계(c10d TCPStore)가 2단계(NCCL bootstrap)보다 먼저** 실행된다는 것이다. SG에서 ephemeral 포트(1025-65535) self-ref를 제거하면, NCCL bootstrap 이전에 c10d TCPStore connect가 먼저 막힐 수 있다. 이 경우 `NCCL_DEBUG=INFO`를 켜도 NCCL 로그는 한 줄도 출력되지 않는다. [다음 글]({% post_url 2026-04-09-Kubernetes-EKS-GPU-TroubleShooting-03-03-02-Distributed-Learning-Network-Failure %})에서 이 현상을 실측으로 확인한다.

<br>

# NCCL 통신 계층

## PyTorch distributed backend

PyTorch distributed는 **backend 추상**을 둔다.

| backend | 대상 | 비고 |
| --- | --- | --- |
| `gloo` | CPU | 저성능, 테스트용 |
| `mpi` | HPC | MPI 런타임 필요 |
| **`nccl`** | **GPU** | **NVIDIA 공식, GPU 학습이라면 사실상 유일한 선택** |

NCCL(NVIDIA Collective Communications Library)은 GPU 간 집합 통신(`all_reduce`, `all_gather`, `broadcast` 등)을 수행하는 라이브러리다. 실무 트러블슈팅 경험은 [NCCL 트러블슈팅 협업 회고]({% post_url 2026-03-29-Articles-NCCL-Troubleshooting-Collaboration-Retrospective %}) 글을 참고한다.

## NCCL transport 우선순위

NCCL은 통신 경로(transport)를 자동으로 선택한다. 우선순위가 높은 순서대로 시도하며, 사용 가능한 첫 번째 transport를 사용한다.

| 우선순위 | transport | 조건 | SG 영향 |
| --- | --- | --- | --- |
| 1 | **NVLink** | 같은 서버 내 GPU 간 | 무관 (호스트 내부) |
| 2 | **GPUDirect RDMA / InfiniBand** | EFA(AWS) 또는 IB NIC 필요 | EFA SG rule 필요 |
| 3 | **TCP Socket** | 위 둘이 없을 때 fallback | **node SG ephemeral self-ref 필요** |

EFA(Elastic Fabric Adapter)는 p4d.24xlarge(A100 × 8), p5.48xlarge(H100 × 8) 등 HPC/ML 전용 대형 인스턴스에만 장착된다. 본 실험의 g5.xlarge(A10G × 1)에는 NVLink도 EFA도 없다. 따라서 **TCP Socket이 유일한 노드 간 NCCL 경로**이고, 이 경로가 node SG의 `ingress_nodes_ephemeral`(1025-65535/tcp self-ref) rule을 통해 허용된다.

## NCCL 환경변수

본 실험에서 사용하는 NCCL 관련 환경변수의 의미를 정리한다.

| 변수 | 값 | 의미 |
| --- | --- | --- |
| `NCCL_SOCKET_IFNAME` | `eth0` | NCCL이 TCP Socket transport에 사용할 네트워크 인터페이스 지정. EKS VPC CNI 기본 인터페이스가 `eth0`이다 |
| `NCCL_IB_DISABLE` | `1` | IB/RDMA 시도 없이 곧바로 Socket으로 진행. EKS 일반 인스턴스에는 IB가 없으므로, 이 값을 주면 불필요한 IB probe 로그를 줄일 수 있다 |
| `NCCL_DEBUG` | `INFO` | NCCL 내부 로그 출력. 트러블슈팅 시 필수. `WARN`이 기본이라 transport 선택, 채널 구성 등의 정보가 보이지 않는다 |

<br>

# torchrun

`torchrun`은 PyTorch 2.x에 내장된 분산 실행 래퍼다. Python 스크립트 하나를 여러 프로세스로 띄우면서 `RANK`/`WORLD_SIZE`/`LOCAL_RANK`/`MASTER_ADDR`/`MASTER_PORT`를 환경변수로 주입한다.

```bash
torchrun --nnodes=2 --nproc-per-node=1 \
         --node-rank=0 --master-addr=nccl-master --master-port=29500 \
         script.py
```

내부적으로 elastic agent(`torch.distributed.elastic`)를 사용하며, rendezvous backend로 c10d(기본) 또는 etcd를 선택할 수 있다.

**장점**:
- 의존성 없음 (PyTorch에 내장)
- 단일 노드 multi-GPU, 멀티 노드 각 1 GPU 모두 동일 API
- rendezvous backend로 c10d를 쓰면 `MASTER_ADDR`이 rank 0 IP 역할

**한계**:
- 노드 간 Pod 스케줄링, 재시작, 장애 복구는 해주지 않는다. Kubernetes가 Pod를 올려주고, torchrun은 "이미 올라온 Pod 안에서 Python 프로세스 띄우기"까지만 담당
- `WORLD_SIZE`나 `RANK`를 외부에서 동적으로 주입해야 한다. Kubernetes YAML에서 env로 전달 필요

<br>

# 실무 분산학습 도구

실무에서는 torchrun 위에 Kubernetes-native한 오케스트레이션 도구를 얹어 분산학습을 관리한다. 본 실험에서는 이 도구들을 **쓰지 않는** 선택을 했는데, 그 이유를 이해하려면 각 도구가 무엇을 하는지 알아야 한다.

아래 세 도구는 **같은 레이어의 대안(peer alternatives)**이다. 모두 "Kubernetes 위에서 분산학습 Pod를 오케스트레이션하는 Operator" 위치에 있고, A가 B를 감싸거나 B 위에서 도는 상하 관계가 아니다. 차이는 오케스트레이션 모델과 포괄 범위에 있다.

```text
사용자 학습 스크립트
  │
  ├─ Training Operator (CRD: Master/Worker)  ─┐
  ├─ KubeRay (Actor: Head/Worker)             ├─ 같은 레이어 — 택 1
  └─ MPI Operator (mpirun + SSH)             ─┘
  │
torchrun / elastic agent
  │
torch.distributed (init_process_group, c10d)
  │
NCCL (all_reduce, all_gather, ...)
```

GPU collective 통신은 어떤 도구를 쓰든 결국 NCCL을 타므로, SG 차단에 의한 네트워크 장애는 도구 선택과 무관하게 동일하게 발생한다.

## Kubeflow Training Operator (PyTorchJob)

Kubernetes CRD로 "분산 학습 잡"을 선언하면, Operator가 Pod를 생성하고 `RANK`/`WORLD_SIZE`/`MASTER_ADDR`을 자동 주입한다.

```yaml
apiVersion: kubeflow.org/v1
kind: PyTorchJob
spec:
  pytorchReplicaSpecs:
    Master: { replicas: 1, template: ... }
    Worker: { replicas: 3, template: ... }
```

Operator가 하는 일:
1. Master Pod를 먼저 띄워 headless Service 자동 생성 (rank 0 `MASTER_ADDR` 확정)
2. Worker Pod에 `MASTER_ADDR`/`MASTER_PORT`/`RANK`/`WORLD_SIZE` env 자동 주입
3. Pod 실패 시 정책에 따라 전체 재시작 (`restartPolicy: OnFailure` / `ExitCode`)
4. `succeeded` / `failed` 상태를 CRD status로 집계
5. Gang scheduling (Volcano/Kueue 연동) 지원

**포괄 범위**: 학습 전용. **적합한 경우**: 실제 학습 잡. 시간이 오래 걸리고(hours~days), 실패 복구가 중요하고, 여러 팀/잡이 공유하는 클러스터.

**오버헤드**: CRD 설치 + training-operator Pod(cluster-wide) + ValidatingAdmissionWebhook + RBAC.

## Ray / KubeRay

범용 분산 프레임워크. 학습(Ray Train), 튜닝(Ray Tune), 서빙(Ray Serve), 데이터(Ray Data)까지 포괄한다. Actor 모델 기반이라 동적 워크로드에 강하다.

KubeRay operator가 `RayCluster` CRD를 관리하며, 내부적으로 GCS(Global Control Store), dashboard, object store, scheduler를 띄운다.

NCCL과의 관계: Ray 자체는 Ray RPC로 통신하지만, **GPU collective 만큼은 NCCL backend를 빌려 쓴다**(`ray.util.collective`). 결국 NCCL 레이어 이슈는 Ray에서도 동일하게 발생한다.

**포괄 범위**: 학습 + 튜닝 + 서빙 + 데이터(셋 중 가장 넓음). **적합한 경우**: 동적 워크로드(RL, hyperparam tuning, 추론+학습 혼합), Python 중심 팀.

**오버헤드**: head Pod + GCS + dashboard Pod + worker Pod 다수 + object spilling용 로컬 스토리지.

## MPI Operator / Horovod

Horovod 기반 학습을 위한 operator. `mpirun` + SSH로 Pod 간 프로세스를 포크한다. PyTorch 쪽은 native DDP/FSDP가 자리잡으면서 Horovod 비중이 줄었지만, TensorFlow 레거시와 전통 HPC 배경 팀에서는 여전히 사용한다.

**포괄 범위**: 학습 전용(allreduce 중심).

## 도구 비교

| 항목 | torchrun (단독) | Training Operator | Ray/KubeRay | MPI Operator |
| --- | --- | --- | --- | --- |
| 오케스트레이션 모델 | 없음 (Pod 안 프로세스만) | CRD (Master/Worker) | Actor (Head/Worker) | mpirun + SSH |
| 포괄 범위 | 프로세스 실행만 | 학습 전용 | 학습+튜닝+서빙+데이터 | 학습 전용(allreduce) |
| RANK/WORLD_SIZE 주입 | 수동 (env) | 자동 | 자동 | 자동 |
| 실패 재시작 | 없음 | 정책 기반 | 정책 기반 | 정책 기반 |
| 설치 오버헤드 | 0 | CRD + operator + webhook | CRD + head/worker + GCS | CRD + launcher Pod + SSH |
| Gang scheduling | 없음 | Volcano/Kueue 연동 | 내장 | Volcano 연동 |
| GPU collective | NCCL | NCCL | NCCL | NCCL 또는 MPI |
| 적합 케이스 | 단발 테스트, smoke test | 실무 학습 잡 | 동적/혼합 워크로드 | TF 레거시, HPC 팀 |

<br>

# 실험 설계: Pod + headless Service

## 실험 목적

[이전 글]({% post_url 2026-04-09-Kubernetes-EKS-GPU-TroubleShooting-03-02-vLLM-TroubleShooting %})까지는 단일 노드 내 장애였다. 이번 실험의 목적은 **"EKS node SG의 ephemeral self-ref가 제거되면 노드 간 분산학습 통신이 어떻게 실패하는가"**를 재현해 보는 것이다.

재현에 필요한 최소 요소:
- GPU 노드 2개에 분산된 Pod 2개
- rank 0/1이 서로의 `MASTER_ADDR`을 알고 `init_process_group`을 시도
- `NCCL_DEBUG=INFO` 로그가 stdout으로 나옴
- 한 번 실행 후 종료 (`restartPolicy: Never`)

## Operator를 쓰지 않은 이유

Training Operator든 KubeRay든, 이 실험에서는 Operator를 얹을 이유가 없다.

1. **자동화 이점이 없다**: Pod 2개, 한 번 실행 후 종료(`restartPolicy: Never`)가 전부다. RANK/WORLD_SIZE를 YAML에 하드코딩하면 충분하고, 자동 재시작은 오히려 "한 번 실패해서 로그 남기면 끝"이라는 실험 목적에 방해가 된다
2. **SG 차단 구간에 변인이 추가된다**: Operator는 자체 네트워크 통신 경로를 갖는다. Training Operator는 ValidatingAdmissionWebhook(API Server → webhook Pod, 9443 포트)이 있고, Ray는 GCS·dashboard·object store 간 통신이 있다. 이 실험에서 node SG의 ephemeral self-ref(1025-65535/tcp)를 의도적으로 제거하면, 이 경로들도 함께 막힐 수 있다. 그러면 분산학습이 실패했을 때 "NCCL 통신이 SG에 막힌 것인지" "operator 인프라가 SG에 막힌 것인지" 원인을 분리할 수 없다

## Pod + headless Service 구조

Pod 두 개에 각각 고정된 이름을 주고, headless Service(`clusterIP: None`)로 DNS A 레코드를 Pod IP로 직접 해석시키면 `MASTER_ADDR` 문제가 해결된다.

```yaml
# headless Service — rank 0 Pod에 고정 DNS 이름 부여
apiVersion: v1
kind: Service
metadata:
  name: nccl-master
spec:
  clusterIP: None
  selector:
    app: nccl-master
  ports:
    - port: 29500
---
# Master Pod (rank 0) — 핵심 env만 발췌
apiVersion: v1
kind: Pod
metadata:
  name: nccl-master-0
  labels:
    app: nccl-master
spec:
  containers:
    - name: pytorch
      image: nvcr.io/nvidia/pytorch:24.10-py3
      env:
        - { name: RANK, value: "0" }
        - { name: WORLD_SIZE, value: "2" }
        - { name: MASTER_ADDR, value: "nccl-master" }
        - { name: MASTER_PORT, value: "29500" }
        - { name: NCCL_SOCKET_IFNAME, value: "eth0" }
        - { name: NCCL_IB_DISABLE, value: "1" }
        - { name: NCCL_DEBUG, value: "INFO" }
      resources:
        limits:
          nvidia.com/gpu: 1
```

- `MASTER_ADDR`은 cluster DNS가 `nccl-master.default.svc.cluster.local`을 Master Pod IP로 직접 해석
- Worker Pod는 동일한 `MASTER_ADDR` 환경변수만 들고 있으면 된다
- `podAntiAffinity`로 두 Pod이 **다른 GPU 노드**에 떨어지도록 강제하여 cross-node NCCL 경로를 확보

이 구조는 **Operator 0개, CRD 0개, 추가 cluster-wide 리소스 0개**. 실험 본질(SG 차단이 분산학습 통신을 어떻게 끊는가)에 집중할 수 있다.

## 트레이드오프 요약

| 항목 | Pod+Service | Training Operator | Ray |
| --- | --- | --- | --- |
| 설치 비용 | 0 (매니페스트 1장) | CRD + operator Pod + webhook | CRD + head/worker Pod + GCS |
| RANK/WORLD_SIZE 주입 | YAML 하드코딩 | 자동 | 자동 |
| 실패 재시작 | 없음 (원하던 바) | 정책 기반 | 정책 기반 |
| 실험 원인 귀속의 명료함 | 높음 (다른 부품 없음) | 보통 (operator webhook 영향) | 낮음 (GCS 등 부품 다수) |
| 실무 분산학습 | 부적합 (확장성 없음) | 적합 | 적합 (동적 워크로드) |
| **SG 차단 실험** | **적합** | 보통 | 부적합 |

## 실무 전환 시점

이번 실험에서는 Pod+Service 방식이 적합하지만, 실제 모델 학습 단계로 넘어가면 PyTorchJob 또는 Ray Train으로 옮기는 것이 맞다. 해당 시점에서의 전환 기준은 아래와 같이 고려한다:

- 학습 시간이 30분을 넘는가 (실패 재시작 가치 상승)
- Pod가 3개 이상인가 (수동 YAML 유지 부담 상승)
- 여러 팀이 같은 클러스터를 공유하는가 (gang scheduling 필요)
- 관측/알림이 필요한가 (CRD status → Alertmanager)

EKS에서 PyTorchJob을 쓰려면 [Kubeflow training-operator helm chart](https://github.com/kubeflow/training-operator)를 설치하고, Kueue 또는 Volcano를 gang scheduler로 얹으면 시작점으로 충분하다.

<br>

# 정리

이번 글에서는 분산학습의 원리, NCCL 통신 계층 구조, EKS 환경에서의 실험 설계까지 정리했다.

| 항목 | 핵심 |
| --- | --- |
| 분산학습 | DP/TP/PP 3방식. 본 실험은 DP 기반 `all_reduce` 사용 |
| 초기화 4요소 | `RANK`, `WORLD_SIZE`, `MASTER_ADDR`, `MASTER_PORT` |
| 초기화 시퀀스 | **c10d TCPStore** → NCCL bootstrap → communicator. SG 차단 시 c10d에서 먼저 막힐 수 있다 |
| NCCL transport | EKS 일반 인스턴스에서는 TCP Socket이 유일한 경로. node SG ephemeral self-ref(1025-65535/tcp) 필요 |
| 실험 구조 | Pod 2개 + headless Service. Operator/Ray의 부수 효과 없이 SG 차단 효과만 격리 |

[다음 글]({% post_url 2026-04-09-Kubernetes-EKS-GPU-TroubleShooting-03-03-02-Distributed-Learning-Network-Failure %})에서는 이 설계를 바탕으로 실제 SG rule을 제거하고, 분산학습 네트워크 장애를 재현한다. 예상은 NCCL timeout이었지만, 실측은 그보다 앞단인 c10d TCPStore에서 먼저 실패했다.

<br>
