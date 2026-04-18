---
title: "[NCCL] NCCL Communicator 초기화 시점: Lazy vs Eager Init"
excerpt: "같은 root cause가 Ray와 torchrun에서 다른 증상으로 나타난 이유에 대해 알아보자."
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - NCCL
  - PyTorch
  - Ray
  - Distributed-Training
  - MLOps
  - Troubleshooting
  - Lazy-Init
  - Kubernetes
---

<br>

# TL;DR

- **문제**: NCCL 통신 실패의 동일한 root cause(sm_120 커널 부재)가, 실행 환경(러너)에 따라 완전히 다른 두 가지 증상으로 나타났다.
- **원인**: PyTorch의 NCCL communicator 초기화 시점이 프레임워크마다 다르다. `torchrun`은 `init_process_group`에서 **즉시(eager)** 생성하고, Ray TorchTrainer는 첫 collective op까지 **지연(lazy)** 생성한다.
- **핵심**: Lazy init은 에러의 발현 지점과 원인 지점을 분리시킨다. 이것이 디버깅을 어렵게 만든 본질적 원인이다.
- **대안**: Ray TorchTrainer에서는 사용자 코드로 eager init을 강제할 수 없으므로, 플랫폼 레벨(K8s init container)에서 GPU↔NCCL 호환성을 사전 검사하는 것을 권장한다.

<br>

# 배경

이 글에서 반복적으로 등장하는 핵심 용어를 먼저 짚고 가자.

| 용어 | 설명 |
| --- | --- |
| **NCCL** | NVIDIA Collective Communications Library. GPU 간 데이터를 주고받기 위한 통신 라이브러리다 |
| **NCCL Communicator** | NCCL이 GPU 간 통신 채널을 추상화한 객체. `ncclCommInitRank` 함수로 생성하며, 이것이 만들어져야 `all_reduce` 같은 collective op을 실행할 수 있다 |
| **`init_process_group`** | PyTorch 분산학습의 진입점 함수(`torch.distributed.init_process_group`). 프로세스들을 하나의 통신 그룹으로 묶는다 |
| **collective op** | 그룹 내 모든 프로세스가 함께 참여하는 통신 연산. `all_reduce`(모든 rank의 텐서를 합산), `broadcast`(한 rank의 데이터를 전체에 전파) 등이 있다 |
| **`torchrun`** | PyTorch 기본 분산학습 런처. 프로세스를 띄우고 환경변수(`RANK`, `WORLD_SIZE` 등)를 설정해 준다 |
| **Ray TorchTrainer** | Ray 프레임워크의 분산학습 래퍼. 워커를 actor로 스폰하고, `init_process_group` 호출과 환경 설정을 자동으로 처리해 준다 |

<br>

[NCCL 트러블슈팅]({% post_url 2026-03-29-Articles-NCCL-Troubleshooting-Collaboration-Retrospective %})을 계속 진행하면서, 팀원이 겪은 증상(학습 중 `illegal memory access`)을 독립적으로 재현하려고 시도했다. 접근 방식은 **변인을 통제** — Ray라는 wrapper를 제거 — 하고, 다양한 GPU 통신 토폴로지(intra-node multi-GPU, inter-node multi-pod 1 GPU 등)에서 standalone `torchrun`으로 NCCL만 격리 테스트하는 것이었다.

결과는 예상과 달랐다. 어떤 토폴로지에서도 팀원의 증상이 재현되지 않았다. 대신 **다른 증상**이 나타났다 — `init_process_group`에서 silent hang. 처음에는 별개의 문제로 보였지만, 추적 결과 **동일한 root cause**에서 비롯된 것임을 확인했다.

| | 팀원 (Ray TorchTrainer) | 나 (standalone torchrun) |
| --- | --- | --- |
| 발현 시점 | 학습 중 첫 `all_reduce` | `init_process_group` |
| 증상 | `CUDA error: illegal memory access` (700) | silent hang |
| Root cause | NCCL 2.26.2가 CUDA 12.2로 빌드 → sm_120(RTX 5090) 커널 부재 | 동일 |

같은 root cause인데 증상이 갈린 이유는, **NCCL communicator의 생성 시점이 프레임워크마다 다르기 때문**이다.

<br>

# 같은 원인, 다른 증상

## PyTorch 분산학습 초기화의 두 단계

PyTorch 분산학습 초기화는 두 단계로 나뉜다. 아래는 `backend="nccl"`일 때의 경로다.

| 단계 | 역할 | 사용 라이브러리 |
| --- | --- | --- |
| **1. Rendezvous** (제어 평면) | 프로세스들이 서로 발견하고 연결 | gloo / c10d (TCPStore) |
| **2. Backend Init** (데이터 평면) | 실제 GPU↔GPU 고속 통신 채널(communicator) 생성 | NCCL (`ncclCommInitRank`) |

1단계는 `backend="nccl"`이든 `backend="gloo"`이든 **항상 gloo / c10d(TCPStore)**가 담당한다. rank 번호, IP 주소 같은 소량의 제어 정보를 TCP로 교환하는 것이므로 GPU가 필요 없기 때문이다. `backend` 인자가 결정하는 것은 2단계 — 실제 데이터를 주고받는 통신 채널의 구현체다.

> `backend="gloo"`를 사용하면 2단계에서 NCCL 대신 gloo 자체 통신 채널이 생성된다. gloo는 CPU 기반이라 GPU 커널 로드가 없으므로, 이 글에서 다루는 sm_120 호환성 문제와 lazy init 이슈가 발생하지 않는다. 팀이 gloo로 전환하여 문제를 우회한 것([이전 글]({% post_url 2026-03-29-Articles-NCCL-Troubleshooting-Collaboration-Retrospective %}))도 이 때문이다.

`ncclCommInitRank`는 2단계에 해당하는 함수다. 모든 rank가 NCCL communicator를 만들어야 `all_reduce` 같은 collective op이 GPU 간 실제 데이터를 주고받을 수 있다.

**이 2단계를 "언제" 수행하느냐**가 프레임워크마다 다르다.

## 코드 경로 비교

팀원의 증상을 재현하기 위해 Ray 변수를 제거하고 standalone `torchrun`으로 NCCL만 격리 테스트했다. 아래 두 코드 경로는 각각 그 테스트 코드(torchrun)와 팀원이 실제로 사용한 학습 코드(Ray TorchTrainer)다.

### Standalone torchrun — eager init

내가 변인 통제를 위해 작성한 NCCL smoke test 코드다. 다양한 GPU 통신 토폴로지를 K8s Pod으로 구성해 `torchrun`으로 직접 실행했다.

```yaml
# intra-node 테스트: 단일 노드, 2 GPU
args:
  - |
    export NCCL_DEBUG=INFO
    export NCCL_DEBUG_SUBSYS=ALL
    torchrun --standalone --nproc_per_node=2 /tmp/test/nccl_smoke.py
```

```yaml
# inter-node 테스트: 2 노드, 각 1 GPU
args:
  - |
    export NCCL_DEBUG=INFO
    export NCCL_DEBUG_SUBSYS=ALL
    export NCCL_SOCKET_IFNAME=eth0
    timeout 300 torchrun \
      --nnodes=2 --nproc-per-node=1 \
      --rdzv-backend=c10d \
      --rdzv-endpoint=nccl-inter-0.nccl-svc.default.svc.cluster.local:29500 \
      --rdzv-id=nccl-inter-test \
      /tmp/test/nccl_smoke.py
```

smoke test 코드 자체는 단순하다.

```python
def main():
    # init_process_group 호출 시 ncclCommInitRank 즉시 실행
    dist.init_process_group(backend="nccl")   # ← 여기서 hang
    rank = dist.get_rank()
    dev = torch.device(f"cuda:{rank}")
    torch.cuda.set_device(dev)
    t = torch.ones(4, device=dev)
    dist.all_reduce(t)                        # ← 여기까지 도달 못함
```

어떤 토폴로지에서든 동일한 결과가 나왔다. `init_process_group` 내부에서 `ncclCommInitRank`가 동기적으로 호출되고, sm_120 커널을 로드하려다 실패하면 이 줄에서 바로 hang이 걸린다. NCCL 로그에 `Comm Config Blocking set to 1`이 찍히는 것을 확인했다.

### Ray TorchTrainer — lazy init

팀원이 실제로 사용한 학습 코드의 경로다. RayJob의 entrypoint에서 `TorchTrainer`를 구성하고 `trainer.fit()`을 호출한다.

```python
# driver에서 TorchTrainer 구성
trainer = TorchTrainer(
    train_loop_per_worker=train_func,
    train_loop_config=train_config,
    torch_config=TorchConfig(backend='nccl'),   # device_id 인터페이스 없음
    scaling_config=ScalingConfig(
        num_workers=8,
        use_gpu=True,
        resources_per_worker={'CPU': 4, 'GPU': 1},
    ),
    run_config=RunConfig(name=run_name),
)
result = trainer.fit()   # ← 워커 스폰, Ray가 init_process_group 자동 호출
```

`trainer.fit()`이 워커를 스폰하면 Ray가 내부적으로 `init_process_group`을 호출한 뒤, 사용자의 `train_func`을 실행한다. 이때 `TorchConfig`에는 `device_id`가 없으므로 PyTorch 기본값인 lazy init이 적용된다.

```python
# Ray가 워커 진입 전에 자동 실행
# - 환경변수 RANK, LOCAL_RANK, WORLD_SIZE 등 설정
# - init_process_group(backend='nccl') 호출 (rendezvous만 완료, communicator 미생성)

def train_func(config):
    # 이 시점에 init_process_group은 이미 끝남

    from mmengine.config import Config    # import 수십 초
    runner = Runner.from_cfg(cfg)         # 모델 빌드 수십 초
    runner._init_model_weights()          # 가중치 초기화
    runner.train()
    # → DDP wrapping → DataLoader → 첫 forward pass
    # → 첫 dist.all_reduce()             ← 여기서 비로소 ncclCommInitRank 호출
    #                                     → sm_120 커널 부재 → illegal memory access (700)
```

`init_process_group` 시점에는 rendezvous(1단계)만 끝내고 NCCL communicator는 만들지 않는다. 첫 collective op이 호출되는 순간 비로소 `ncclCommInitRank`가 실행되고, 그때 sm_120 커널 부재로 crash가 발생한다.

## 비교 요약

|  | torchrun (standalone) | Ray TorchTrainer |
| --- | --- | --- |
| NCCL communicator 생성 시점 | `init_process_group` 내부 (eager) | 첫 `all_reduce` 시점 (lazy) |
| sm_120 커널 부재 시 증상 | init 단계 hang | 학습 중 crash |
| 에러 메시지 | (silent hang, timeout) | `illegal memory access` (CUDA 700) |
| 사용자 코드 | 동일 | 동일 |

사용자 코드(init_process_group → DDP → backward)는 **동일**하다. 차이는 "그 코드를 누가 어떻게 감싸서 실행하느냐"에 있다.

## 드라이버 레벨에서의 증거

사용자 레벨의 `illegal memory access`(CUDA error 700)는 드라이버 레벨(dmesg)에서는 XID 에러로 남는다. Ray TorchTrainer 환경에서 crash가 발생했을 때의 dmesg 로그가 이를 보여준다.

```
NVRM: Xid (PCI:0000:2a:00): 13, Graphics SM Warp Exception on (GPC 0, TPC 0, SM 0): Out Of Range Address
NVRM: Xid (PCI:0000:2a:00): 13, Graphics SM Global Exception on (GPC 0, TPC 0, SM 0): Multiple Warp Errors
NVRM: Xid (PCI:0000:2a:00): 43, pid=1238258, name=ray::_RayTrainW, channel 0x00000002
```

- **Xid 13**: GPU SM(Streaming Multiprocessor)에서 잘못된 메모리 주소에 접근했다는 뜻이다. 사용자 레벨의 CUDA error 700과 동일 사건이다.
- **Xid 43**: 해당 channel을 강제 리셋하여 복구를 시도한다.
- Xid 43 리셋 이후 GR 엔진 카운터가 100%에 고정되고, DCGM exporter가 이 값을 그대로 리포트하면서 Grafana에서 GPU utilization이 100%로 보이는 현상이 발생한다.

사용자 레벨과 드라이버 레벨의 매핑을 정리하면 다음과 같다.

| 사용자 (Python/CUDA) | 드라이버 (dmesg) |
| --- | --- |
| `CUDA error: an illegal memory access was encountered` (err 700) | `Xid 13 Out Of Range Address` |
| `ProcessGroupNCCL.cpp:3356` NCCL collective 실패 | `Xid 43 channel reset, name=ray::_RayTrainW` |

동일 사건의 두 얼굴이다. 근본 원인(NCCL이 CUDA 12.2로 빌드되어 sm_120 커널이 없음)에 대한 상세 분석은 [이전 글]({% post_url 2026-03-29-Articles-NCCL-Troubleshooting-Collaboration-Retrospective %})을 참고한다.

<br>

# Lazy Init이 디버깅을 어렵게 만든 이유

> **에러의 발현 지점과 원인 지점이 분리된 것** — 이것이 lazy init의 본질적 운영 비용이다.

## 에러 발현 지점과 원인 지점의 분리

실제 lazy init 시나리오에서 에러가 `dist.all_reduce()`에서 나오면, 가장 자연스러운 가설은 "all_reduce를 호출하는 코드에 문제가 있다"이다. [이전 글의 디버깅 타임라인]({% post_url 2026-03-29-Articles-NCCL-Troubleshooting-Collaboration-Retrospective %}#디버깅-타임라인)에서 팀원의 시도가 이를 잘 보여준다.

| 시도 | 가설 | 방향 | 결과 |
| --- | --- | --- | --- |
| 2 | `reduce_mean` collective mismatch | 모델 코드 수정 | 트리거 안 됨 |
| 4 | `CUDA_LAUNCH_BLOCKING=1` | 디버깅 | 에러 위치 특정에 성공 |
| 5 | `all_reduce` 자체 제거 | 모델 코드 수정 | 다른 곳에서 crash |
| 6 | gloo backend 전환 | 인프라 | 성공 |

에러가 `all_reduce`에서 발생했으므로, 팀원은 `reduce_mean`을 수정하고 collective op 불일치를 의심하고 심지어 `all_reduce`를 아예 제거하는 시도까지 했다. 해당 에러 메시지 하에서는 **합리적인 디버깅 경로**였다.

만약 eager init이었다면 어떠했을까.

```python
init_process_group(backend='nccl')
  → ncclCommInitRank → sm_120 커널 없음 → hang (또는 timeout)
  → 로그: "Comm Config Blocking set to 1" + NCCL WARN
  → 결론: "NCCL 초기화 자체가 안 됨" → 인프라 문제 명확
```

`init_process_group` 시점에서 바로 hang/에러가 나고, `all_reduce`까지 도달하지 않았을 것이다. "NCCL 초기화 자체가 안 되네" → "인프라 문제"라는 결론에 시도 1~5 없이 바로 도달했을 가능성이 높다.

## Fail-fast 실패와 GPU-hour 낭비

lazy init 경로에서 `init_process_group`부터 첫 `all_reduce`까지의 타임라인을 보면, 낭비 규모가 드러난다.

```python
init_process_group (lazy, "성공")
  → PYTHONPATH 설정
  → MMEngine/MMDet3D import           ← 수십 초
  → Hook 등록
  → Config 로드, 오버라이드
  → Runner.from_cfg()                 ← 모델 빌드 수십 초
  → runner._init_model_weights()      ← 가중치 초기화
  → runner.train()
    → DataLoader 구성
    → 첫 batch 로드                    ← 데이터 I/O
    → 첫 forward pass
    → 첫 dist.all_reduce()            ← 드디어 에러 발견
```

`init_process_group`부터 첫 `all_reduce`까지 최소 수 분이 소요된다. 8 GPU worker x 수 분 = 상당한 GPU-hour 낭비다. 게다가 에러 후 원인 분석 → 코드 수정 → 이미지 빌드 → 재배포 → 다시 수 분 대기의 루프를 여러 시도에 걸쳐 반복한 것이다.

eager init이었다면 `init_process_group` 시점(워커 진입 직후, 모델 빌드 전)에 실패하므로, **실패까지의 대기 시간이 초 단위로 줄어든다**.

## 환경마다 다른 증상, 재현의 어려움

내가 standalone torchrun을 선택한 이유는 "Ray 변수를 제거하고 NCCL만 격리 테스트"하기 위해서였다. 그런데 이 **변수 제거가 역설적으로 증상 자체를 바꿔버렸다**. "crash를 재현하려 했는데 hang이 나온다" → "같은 문제인지 다른 문제인지?"라는 추가 분석이 필요했다.

재현의 어려움을 만든 구조적 원인을 되짚어 보자:

1. NCCL communicator의 eager/lazy 여부가 **프레임워크에 의해 암묵적으로 결정**된다 — 사용자가 제어하는 인터페이스가 아니다
2. 같은 `init_process_group(backend='nccl')` 호출이 프레임워크 컨텍스트에 따라 다른 내부 경로를 탄다 — **API 표면은 동일하지만 행동이 다르다**
3. 에러 메시지가 root cause를 가리키지 않는다 — "illegal memory access"도 "silent hang"도 "sm_120 커널 없음"을 알려주지 않는다

결국 "변인을 통제해서 재현한다"는 트러블슈팅의 기본 전략이, lazy/eager라는 보이지 않는 축 때문에 오히려 혼란을 키운 셈이다. 재현 환경을 바꾸면 증상까지 바뀌므로, root cause가 같다는 사실을 확인하기 위해 프레임워크 내부의 초기화 경로까지 추적해야 했다.

<br>

# 왜 Ray는 Lazy인가

결론부터 말하면, Ray의 의도적 설계라기보단 **PyTorch의 역사적 기본값을 그대로 받은 것**에 가깝다.

## PyTorch의 역사적 기본값이 lazy였다

`torch.distributed`는 오래전부터 NCCL communicator 생성을 첫 collective op까지 미루는 게 default였다.

- **Multi-process group 지원**: 한 프로세스에서 여러 process group을 만들 수 있다 (data parallel + tensor parallel 등). 각 group이 실제로 쓰일 때 communicator를 만드는 게 합리적이다 — 안 쓰면 안 만들면 된다.

- **Device 결정 시점 문제**: `init_process_group()` 시점에는 PyTorch가 이 rank가 어느 GPU를 쓸지 아직 모를 수 있다. 사용자가 보통 `init_process_group` 후에 `torch.cuda.set_device(local_rank)`를 호출하기 때문이다. NCCL communicator는 device 바인딩이 필요하므로, 첫 collective op(텐서가 GPU에 있을 때)까지 미루면 device 정보가 확실해진다.

- **시작 시간 단축**: NCCL communicator 생성은 비싸고(수 초~수십 초), 모든 rank가 모여야 한다. "어차피 학습 시작하면 만들 거니까 미루자"는 lazy 철학이다.

## Ray TorchTrainer의 현재 상태

Ray `TorchConfig`는 `backend`, `init_method`, `timeout_s` 세 가지 인터페이스만 노출한다. **`device_id`를 전달하는 인터페이스가 없다** ([Ray 2.54.1 docs](https://docs.ray.io/en/latest/train/api/doc/ray.train.torch.TorchConfig.html)).

```python
# Ray TorchConfig의 인터페이스 — device_id 옵션 없음
class TorchConfig:
    backend: str = "nccl"
    init_method: str = "env"
    timeout_s: int = 1800
```

PyTorch에서 eager init을 활성화하려면 `init_process_group(..., device_id=torch.device(f"cuda:{local_rank}"))`를 호출해야 하는데, Ray가 이를 내부적으로 호출하면서 `device_id`를 지정하지 않기 때문에 PyTorch 기본값(lazy)이 그대로 적용된다.

> PyTorch maintainer wconstab의 코멘트: *"adding device_id into init_process_group opts you into 'eager init' for nccl. Without eager init, you get lazy init which means nccl establishes its connections on the first collective."* — [pytorch/pytorch#142356](https://github.com/pytorch/pytorch/issues/142356)

Ray가 `device_id`를 노출하지 않는 이유를 추측하면, Ray TorchTrainer의 setup hook이 사용자 코드 **전에** `init_process_group`을 호출하는데, 이 시점에 사용자가 어떤 device 전략(FSDP? DDP? mixed device?)을 쓸지 모르기 때문에 보수적으로 `device_id`를 미지정한 것으로 보인다. 다만 이는 Ray 측의 명시적 디자인 문서로 확인된 내용은 아니다.

## PyTorch의 방향 전환

PyTorch 커뮤니티도 lazy init의 디버깅 비용을 인지하고 있다. 최근 몇 가지 움직임을 보면:

- **PyTorch 2.3+**: `init_process_group(..., device_id=...)` 인자가 추가되어 **eager init을 명시적으로 켤 수 있게** 됐다. 공식 문서는 다음과 같이 안내한다: *"[device_id] has two effects, only under NCCL: the communicator is immediately formed... If you want to know NCCL initialization error early, you can also use this field."*
- **Non-blocking API 기본값화**: `ncclCommInitRank`의 blocking 여부를 non-blocking으로 전환하여 hang 시 bail out할 수 있도록 하는 RFC가 진행 중이다 ([pytorch/pytorch#117749](https://github.com/pytorch/pytorch/issues/117749), [#137007](https://github.com/pytorch/pytorch/issues/137007)).
- **Eager init 기반 P2P 최적화**: P2P communicator 생성을 eager init 전제로 최적화하는 설계가 진행 중이다 ([pytorch/pytorch#129140](https://github.com/pytorch/pytorch/issues/129140)).
- **torchcomms**: PyTorch의 차세대 통신 API인 torchcomms는 eager init을 기본 설계 원칙으로 채택했다. *"Current approaches, such as lazy initialization... constrain scalability within libraries like NCCL. Torchcomms introduces eager initialization (where backend resources are explicitly managed by the user)... paving the way for truly massive distributed jobs."* — [PyTorch torchcomms 블로그](https://pytorch.org/blog/torchcomms/)

단, `device_id`로 eager init을 켠다고 무조건 안전한 것은 아니다. [pytorch/pytorch#153960](https://github.com/pytorch/pytorch/issues/153960)에서 `device_id`를 전달하면 NCCL이 간헐적으로 hang하는 PyTorch 2.7 regression이 보고되었고, 2.7.1에서 수정되었다. production 도입 시 충분한 사전 테스트가 필요하다.

<br>

# 플랫폼 레벨 대안

지금까지의 분석을 정리하면, lazy init 환경에서 NCCL 호환성 문제는 **학습이 한참 진행된 뒤에야 발견**되고, 에러 메시지는 root cause를 가리키지 않는다. 이 문제를 해결하려면 NCCL communicator 생성 전에 GPU↔NCCL 호환성을 먼저 검증하거나, 최소한 실패 시점을 앞당겨야 한다.

## 왜 학습 코드 변경으로는 안 되는가

가장 직관적인 해결책은 학습 코드에서 eager init을 강제하는 것이다.

```python
# 이론적으로는 이렇게 하면 된다
dist.init_process_group(
    backend="nccl",
    device_id=torch.device(f"cuda:{local_rank}"),  # eager init 강제
)
```

이 방법은 두 가지 이유로 현실적이지 않다.

**첫째, Ray TorchTrainer에서는 기술적으로 불가능하다.** Ray가 워커 진입 전에 `init_process_group`을 이미 호출하기 때문이다. `train_func`이 실행되는 시점에 이미 default process group이 초기화되어 있다. 사용자가 `train_func` 내부에서 다시 `init_process_group`을 호출하면 PyTorch는 `RuntimeError: trying to initialize the default process group twice!`를 던진다. `dist.destroy_process_group()` 후 재초기화하는 우회 방법이 기술적으로 가능하긴 하지만, Ray의 내부 상태(actor handle, heartbeat 등)가 기존 process group에 바인딩되어 있어 race condition 위험이 크다. 권장하지 않는다.

**둘째, 조직적으로도 부담이 크다.** 설사 `torchrun` 환경이라 코드 수정이 기술적으로 가능하더라도, ML 엔지니어 전원에게 학습 코드의 `init_process_group` 호출을 일괄 변경해 달라고 요청해야 한다. 인프라 호환성 문제를 학습 코드에 전가하는 셈이고, 코드 변경이 누락되거나 새 프로젝트에서 빠지면 다시 같은 문제가 발생한다. 이건 강건하지 않은 해결책이다.

따라서 **ML 엔지니어의 코드를 건드리지 않고, 플랫폼 레벨에서 문제를 감지하는 접근**이 필요하다. 문제를 빨리 감지할수록 좋다.

## 대안 1. 빌드 타임 — CI/CD에서 호환성 검증

이미지를 빌드할 때 "이 NCCL 바이너리가 타겟 GPU를 지원하는가?"를 검증한다.

```dockerfile
# Dockerfile 마지막 스테이지 — 빌드 타임 GPU 호환성 게이트
RUN NCCL_LIB=$(python3 -c "import nvidia.nccl, os; \
      print(os.path.join(os.path.dirname(nvidia.nccl.__file__), 'lib/libnccl.so.2'))") && \
    NCCL_ARCHS=$(cuobjdump -lelf "$NCCL_LIB" | grep -oP 'sm_\d+' | sort -u | tr '\n' ' ') && \
    TARGET_SM="sm_120" && \
    echo "NCCL SASS architectures: $NCCL_ARCHS" && \
    if echo "$NCCL_ARCHS" | grep -q "$TARGET_SM"; then \
      echo "PASS: NCCL has native $TARGET_SM kernel"; \
    else \
      echo "FAIL: NCCL missing $TARGET_SM kernel (has: $NCCL_ARCHS)" && exit 1; \
    fi
```

**장점**: GPU를 할당하지 않고도 검증 가능하다. 배포 전에 차단할 수 있다.

**한계**: 타겟 GPU SM 값을 빌드 시 하드코딩해야 한다. 여러 GPU 종류를 지원하는 이미지에서는 유연성이 필요하다.

## 대안 2. 배포 타임 — K8s Init Container (권장)

K8s init container로 실제 GPU와 NCCL 바이너리의 호환성을 런타임에 검증한다. 학습 컨테이너가 뜨기 전에 실행된다.

```yaml
# Ray workerGroupSpec의 template에 추가
initContainers:
  - name: gpu-compat-check
    image: registry.example.com/ml-training:latest  # 학습과 동일 이미지
    command: ["python3", "-c"]
    args:
      - |
        import subprocess, sys, os

        # 1. GPU compute capability 확인
        import torch
        cap = torch.cuda.get_device_capability(0)
        gpu_sm = f"sm_{cap[0] * 10 + cap[1]}"
        gpu_name = torch.cuda.get_device_name(0)

        # 2. NCCL 바이너리의 SASS 아키텍처 확인
        import nvidia.nccl
        nccl_lib = os.path.join(
            os.path.dirname(nvidia.nccl.__file__), "lib/libnccl.so.2"
        )
        result = subprocess.run(
            ["cuobjdump", "-lelf", nccl_lib],
            capture_output=True, text=True
        )
        sass_archs = sorted(set(
            line.split(".")[-1].replace(".cubin", "")
            for line in result.stdout.splitlines()
            if ".cubin" in line
        ))

        # 3. 판정
        print(f"GPU: {gpu_name} ({gpu_sm})")
        print(f"NCCL SASS: {', '.join(sass_archs)}")

        if gpu_sm in sass_archs:
            print(f"PASS: NCCL has native kernel for {gpu_sm}")
            sys.exit(0)

        max_sass = max(sass_archs, key=lambda s: int(s.replace("sm_", "")))
        print(f"FAIL: NCCL has no kernel for {gpu_sm} (max: {max_sass})")
        print(f"  → NCCL needs to be rebuilt with CUDA that supports {gpu_sm}")
        sys.exit(1)
    resources:
      limits:
        nvidia.com/gpu: 1
        cpu: "1"
        memory: "2Gi"
```

**장점**:

- 학습 코드 변경이 필요 없다
- 학습 시작 전에 초 단위로 판정한다 (모델 로딩, 데이터 I/O 없음)
- 에러 메시지가 root cause를 직접 가리킨다 (`NCCL has no kernel for sm_120`)
- GPU가 실제로 할당된 상태에서 검사하므로 빌드 타임보다 정확하다

**한계**: GPU를 수 초간 점유한다. 하지만 학습에서 수 분 낭비하는 것보다 훨씬 저렴하다.

## 대안 3. 런타임 — 환경변수 + 타임아웃 (최소 변경)

Ray 워커의 환경변수로 blocking init을 강제하고, 타임아웃을 짧게 설정한다.

```yaml
# workerGroupSpec containers env
env:
  - name: TORCH_NCCL_USE_COMM_NONBLOCKING
    value: "0"                    # blocking init 강제
  - name: NCCL_DEBUG
    value: "INFO"                 # init 과정 로그
  - name: NCCL_DEBUG_SUBSYS
    value: "INIT,NET"             # 커널 로드 단계 로그
```

```python
# TorchConfig에서 timeout 단축
TorchConfig(backend='nccl', timeout_s=120)  # 30분 → 2분
```

**효과**: sm_120 커널 부재 시, 학습 코드 진입 전에 init에서 hang → 2분 후 timeout으로 프로세스 종료. `NCCL_DEBUG=INFO`로 커널 로드 시도 로그가 남아서 진단할 수 있다.

**한계**: 여전히 "hang → timeout → 종료"이지 "즉시 에러"가 아니다. 에러 메시지도 timeout이지 "sm_120 커널 없음"이 아니다.

## 비교

|  | 빌드 타임 (CI/CD) | 배포 타임 (Init Container) | 런타임 (env var) |
| --- | --- | --- | --- |
| 감지 시점 | 이미지 빌드 시 | Pod 시작 시 (학습 전) | `init_process_group` 시 |
| 학습 코드 변경 | 없음 | 없음 | 없음 (TorchConfig만) |
| 에러 메시지 명확도 | 높음 | 높음 | 낮음 (timeout) |
| GPU 점유 | 없음 | 수 초 | 2분 (timeout 대기) |
| 이종 GPU 대응 | 수동 (SM 하드코딩) | 자동 (실제 GPU 감지) | 해당 없음 |
| Manifest 변경 | Dockerfile | Pod spec | Pod spec + TorchConfig |

**Init Container(대안 2)를 우선 적용**하고, **CI/CD 체크(대안 1)를 후속으로 추가**하는 것을 권장한다. 런타임 env var(대안 3)는 추가 안전망으로 같이 넣어도 좋지만, 단독으로는 진단 품질이 낮다.

> 세 가지 대안 모두 ML 엔지니어의 학습 코드를 수정하지 않는다. 그중 init container를 우선 권장하는 이유는 **root cause를 직접 가리키는 에러 메시지**(`NCCL has no kernel for sm_120`)와 **실제 GPU 기반의 자동 감지**를 동시에 제공하기 때문이다. GPU 종류가 바뀌거나 NCCL 버전이 바뀌어도 별도 수정 없이 대응된다.

<br>

# 정리

> **Lazy init은 "다 잘 동작할 때"는 시작 시간과 유연성 면에서 이득이지만, "환경이 망가졌을 때"는 디버깅 비용을 폭발시킨다.**

이번 케이스에서 배운 것을 일반화하면:

- **Lazy**: "init 성공 → 학습 시작 → 첫 step crash" → "코드 문제인가? OOM인가?" 같은 잘못된 가설로 시간 낭비
- **Eager**: "init에서 즉시 hang/error" → 통신 스택 문제임이 명확

프레임워크 설계 철학(lazy vs eager)이 단순한 성능 최적화 문제가 아니라 **운영 가시성과 디버깅 효율에 직접 영향을 미친다**는 것이 핵심 교훈이다. PyTorch 자체도 torchcomms를 통해 eager init을 기본 원칙으로 채택하는 방향으로 움직이고 있다.

그리고 플랫폼 엔지니어 관점에서, 프레임워크가 fail-fast를 보장하지 않는 영역은 **인프라 레벨에서 커버해야 한다**. K8s init container로 GPU↔NCCL 호환성을 사전 검사하는 것은, 학습 코드를 건드리지 않으면서 이 문제를 해결하는 가장 실용적인 접근이다.

<br>

# 참고: 새 GPU 도입 시 NCCL 호환성 검증 체크리스트</summary>

## 빌드 타임

**NCCL 빌드 CUDA 버전 확인:**

```bash
# NCCL이 어떤 CUDA 버전으로 빌드되었는지 확인
strings $(python -c "import nvidia.nccl, os; \
  print(os.path.dirname(nvidia.nccl.__file__))")/lib/libnccl.so.2 \
  | grep "compiled with"
```

<br>

**타겟 GPU compute capability가 빌드 CUDA에서 지원되는지 확인:**
- Hopper(sm_90): CUDA 12.0+
- Blackwell(sm_100 / sm_120): **CUDA 12.8+ 필요** — NVIDIA 엔지니어 ptrblck: *"Blackwell GPUs require CUDA 12.8+. All of our stable releases starting with PyTorch 2.7.0 use CUDA 12.8 or newer and already support Blackwell."* ([PyTorch 포럼](https://discuss.pytorch.org/t/solved-rtx-5090-sm-120-training-segfault-ddp-was-the-cause/224584))

<br>

**NCCL 바이너리에 타겟 SASS 포함 확인:**

```bash
# NCCL 바이너리의 SASS 아키텍처 목록 확인
cuobjdump -lelf libnccl.so.2 | grep sm_
```

<br>

## 배포 타임

- Init container로 GPU↔NCCL 호환성 사전 검사 (학습 코드 진입 전에 fail)
- GPU device plugin이 init / main container에 동일 device를 할당하는지 확인

## 런타임

- NCCL 디버그 로그 활성화: `NCCL_DEBUG=INFO`, `NCCL_DEBUG_SUBSYS=INIT,NET`
- Init timeout 단축: Ray `TorchConfig(timeout_s=120)`, torchrun `timeout=timedelta(minutes=2)`
- 사용자가 직접 `init_process_group`을 호출하는 경우 `device_id` 옵션 고려 (PyTorch 2.3+)

## 진단 시 신호 매핑

| 증상 | 가능한 원인 | 확인 방법 |
| --- | --- | --- |
| `init_process_group`에서 silent hang | NCCL 커널 로드 실패 (eager init 경로) | `cuobjdump -lelf libnccl.so.2` |
| 학습 중 `illegal memory access` (CUDA 700) | 같은 원인이 lazy init으로 지연 발현 | dmesg `Xid 13`, GPU sm vs NCCL SASS 비교 |
| `Comm Config Blocking set to 1` 로그 후 hang | Blocking init + 커널 부재 | `TORCH_NCCL_USE_COMM_NONBLOCKING` 환경변수 확인 |

<br>

# 참고 자료

- [pytorch/pytorch#142356](https://github.com/pytorch/pytorch/issues/142356) — `device_id`와 eager/lazy init 관계 (wconstab 코멘트)
- [pytorch/pytorch#136248](https://github.com/pytorch/pytorch/issues/136248) — 첫 collective op에서의 lazy init blocking (wconstab 코멘트)
- [pytorch/pytorch#137007](https://github.com/pytorch/pytorch/issues/137007) — ProcessGroupNCCL non-blocking API 기본값화 RFC
- [pytorch/pytorch#129140](https://github.com/pytorch/pytorch/issues/129140) — eager init 기반 P2P communicator 최적화 RFC
- [pytorch/pytorch#152780](https://github.com/pytorch/pytorch/issues/152780) — RTX 5090 + DDP + NCCL illegal memory access
- [pytorch/pytorch#153960](https://github.com/pytorch/pytorch/issues/153960) — `device_id` 전달 시 NCCL hang regression (2.7 → 2.7.1 수정)
- [PyTorch torchcomms 블로그](https://pytorch.org/blog/torchcomms/) — eager init을 기본 설계 원칙으로 채택
- [Ray TorchConfig docs](https://docs.ray.io/en/latest/train/api/doc/ray.train.torch.TorchConfig.html) — `device_id` 인터페이스 부재 확인

<br>