---
title:  "[Kubernetes] 쿠버네티스 스케줄링 - 4. 스케줄러 설정과 최적화"
excerpt: "NodeResourcesFit 전략, 리소스 단편화 문제, 스케줄러 성능 튜닝, 멀티 프로필 구성을 알아보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - Scheduler
  - Scheduling
  - KubeSchedulerConfiguration
  - NodeResourcesFit
  - Bin Packing
  - GPU
  - Fragmentation
---

<br>

# TL;DR

- 스케줄러 설정은 **프로세스 1개 : Configuration 1개 : Profile N개** 계층 구조를 가진다. Configuration은 글로벌 설정과 Profile 목록을 포함하며, 각 Profile이 extension point별 플러그인 구성을 담당한다.
- `KubeSchedulerConfiguration`을 통해 스케줄러의 플러그인 구성, 스코어링 전략, 성능 파라미터를 세밀하게 설정할 수 있다. `multiPoint` 필드로 플러그인을 모든 extension point에 일괄 등록하고, `*` 패턴으로 기본 플러그인을 전부 비활성화한 뒤 순서를 재배치할 수 있다.
- `NodeResourcesFit` 플러그인은 세 가지 스코어링 전략을 제공한다: `LeastAllocated`(기본, 리소스 분산), `MostAllocated`(bin packing, 노드 채우기), `RequestedToCapacityRatio`(커스텀 곡선).
- GPU 등 희소 리소스는 `LeastAllocated` 전략에서 **단편화(fragmentation)** 문제가 발생하기 쉽다. 여러 노드에 GPU가 분산 배치되어, 단일 노드에서 충분한 GPU를 확보하지 못하는 상황이다. `MostAllocated` 전략으로 완화할 수 있다.
- `percentageOfNodesToScore`로 대규모 클러스터에서의 스케줄링 지연을 줄일 수 있으며, 단일 kube-scheduler에서 여러 프로필을 운영하여 워크로드 성격에 맞는 스케줄링 정책을 적용할 수 있다.

<br>

# 들어가며

[이전 글들]({% post_url 2025-11-05-Kubernetes-Scheduling-01 %})에서 스케줄링의 개념, 프레임워크, 스케줄링 제어 설정까지 다뤘다. 이번 글에서는 **스케줄러 자체의 설정과 최적화**를 다룬다.

1. **KubeSchedulerConfiguration**: 설정 계층 구조(Configuration → Profile), 설정 전달 방법, 설정 파일 구조, 플러그인 활성화/비활성화 패턴(`multiPoint`, `*` 패턴)
2. **NodeResourcesFit 스코어링 전략**: LeastAllocated, MostAllocated, RequestedToCapacityRatio 세 전략의 동작 원리와 사용 시나리오
3. **리소스 단편화 문제**: 특히 GPU 환경에서 발생하는 단편화와 해결 방안
4. **스케줄러 성능 튜닝**: `percentageOfNodesToScore`와 대규모 클러스터 최적화
5. **멀티 프로필**: 워크로드 성격에 따라 서로 다른 스케줄링 정책을 적용하는 구성

> Extension Point의 결정권 분류, PreScore 역할, PodGroup 스케줄링 등 프레임워크 내부 동작은 [다음 글]({% post_url 2025-11-05-Kubernetes-Scheduling-05 %})에서 자세히 다룬다.

<br>

# KubeSchedulerConfiguration

## 설정 계층 구조

스케줄러 설정을 이해하려면 먼저 **스케줄러 프로세스, Configuration, Profile** 세 개념의 계층 관계를 잡아야 한다.

```
Scheduler 프로세스 (kube-scheduler 바이너리)
  └── Configuration (1개)
        ├── 글로벌 설정 (leaderElection, clientConnection, parallelism 등)
        └── Profiles[] (1개 이상)
              ├── Profile "default-scheduler"
              │     └── Extension Points
              │           ├── filter: [Plugin A, Plugin B, ...]
              │           ├── score: [Plugin C (weight:2), ...]
              │           └── ...
              └── Profile "gpu-scheduler"
                    └── Extension Points
                          ├── filter: [Plugin A, Plugin E, ...]
                          └── ...
```

| 개념 | 범위 | 뭘 설정하나 |
| --- | --- | --- |
| **Configuration** | 스케줄러 프로세스 전체 | 글로벌 설정 + Profile 목록 |
| **Profile** | 하나의 `schedulerName` 단위 | 어떤 extension point에 어떤 plugin을 켜고/끄고/weight를 줄지 |

하나의 스케줄러 프로세스는 하나의 Configuration을 가지며, 그 안에 여러 Profile을 포함할 수 있다. Pod의 `spec.schedulerName`이 Profile의 `schedulerName`과 매칭되어, 같은 프로세스 안에서 서로 다른 플러그인 구성으로 스케줄링할 수 있다([1편]({% post_url 2025-11-05-Kubernetes-Scheduling-01 %})의 멀티 프로필 참고).

<br>

## 설정 전달 방법

`kube-scheduler`는 별도의 바이너리로, `--config` CLI 인자를 통해 `KubeSchedulerConfiguration` 파일을 전달받는다. 실행 방식은 클러스터 구성에 따라 다르다.

| 클러스터 유형 | kube-scheduler 실행 방식 | 설정 전달 |
| --- | --- | --- |
| **kubeadm** (가장 일반적) | Static Pod (`/etc/kubernetes/manifests/kube-scheduler.yaml`) | Pod spec의 command에 `--config` 지정, hostPath로 마운트 |
| **RKE2** | Static Pod 또는 자체 관리 | `/var/lib/rancher/rke2/` 하위 경로에서 관리 |
| **systemd** | systemd unit file | `ExecStart=kube-scheduler --config ...` |

kubeadm 기준으로 Static Pod manifest는 다음과 같은 구조다.

```yaml
# /etc/kubernetes/manifests/kube-scheduler.yaml (Static Pod)
apiVersion: v1
kind: Pod
metadata:
  name: kube-scheduler
  namespace: kube-system
spec:
  containers:
  - command:
    - kube-scheduler
    - --config=/etc/kubernetes/scheduler-config.yaml  # KubeSchedulerConfiguration 파일 경로
    image: registry.k8s.io/kube-scheduler:v1.32.0
    volumeMounts:
    - mountPath: /etc/kubernetes/scheduler-config.yaml  # 컨테이너 내부 경로
      name: scheduler-config
      readOnly: true
  volumes:
  - hostPath:
      path: /etc/kubernetes/scheduler-config.yaml  # 호스트(control plane 노드) 경로
    name: scheduler-config
```

`--config`로 참조하는 파일이 바로 아래에서 다룰 `KubeSchedulerConfiguration`이다.

<br>

## 설정 파일 구조

`kube-scheduler`는 `--config` 플래그로 설정 파일을 전달받는다. 설정 파일은 `KubeSchedulerConfiguration` API 오브젝트로, 스케줄러의 동작을 세밀하게 제어한다.

```yaml
apiVersion: kubescheduler.config.k8s.io/v1
kind: KubeSchedulerConfiguration        # Configuration (전체 설정)
clientConnection:
  kubeconfig: /etc/srv/kubernetes/kube-scheduler/kubeconfig  # 글로벌 설정
profiles:                                # Profile 목록
  - schedulerName: default-scheduler     # Profile 이름 (Pod의 spec.schedulerName과 매칭)
    pluginConfig:                         # 플러그인별 상세 설정
      - name: NodeResourcesFit
        args:
          scoringStrategy:
            type: LeastAllocated
            resources:
              - name: cpu
                weight: 1
              - name: memory
                weight: 1
```

주요 설정 영역은 다음과 같다.

| 영역 | 설명 |
| --- | --- |
| `profiles` | 스케줄러 프로필 목록. 각 프로필은 고유한 `schedulerName`과 플러그인 구성을 가짐 |
| `profiles[].plugins` | extension point별 플러그인 활성화/비활성화 |
| `profiles[].pluginConfig` | 플러그인별 상세 설정 (스코어링 전략, 가중치 등) |
| `percentageOfNodesToScore` | 대규모 클러스터 성능 최적화 파라미터 |

## 플러그인 활성화/비활성화

각 extension point에서 기본 플러그인을 비활성화하거나 커스텀 플러그인을 활성화할 수 있다.

```yaml
profiles:
  - schedulerName: default-scheduler
    plugins:
      score:
        disabled:
          - name: PodTopologySpread
        enabled:
          - name: MyCustomPlugin
            weight: 2
```

`enabled`로 추가한 플러그인은 기본 플러그인 **뒤에** 붙는다. 기본 플러그인 간의 순서를 바꾸거나, 커스텀 플러그인을 기본 플러그인 사이에 끼워넣으려면 아래의 `*` 패턴을 사용해야 한다.

<br>

### multiPoint

하나의 플러그인이 여러 extension point를 구현하는 경우가 많다(예: `NodeResourcesFit`은 PreFilter, Filter, PreScore, Score 네 곳에 등록된다). `multiPoint` 필드를 사용하면 해당 플러그인이 구현하는 **모든 extension point에 한 번에** 등록할 수 있다.

```yaml
profiles:
  - schedulerName: default-scheduler
    plugins:
      multiPoint:
        enabled:
          - name: NodeResourcesFit
            weight: 2
```

위 한 줄이 NodeResourcesFit을 PreFilter, Filter, PreScore, Score 네 곳에 동시에 등록한다. 플러그인이 어떤 인터페이스를 구현했는지는 스케줄러가 초기화 시점에 Go의 type assertion으로 자동 판별한다. 플러그인 구조체가 `FilterPlugin`, `ScorePlugin` 등의 인터페이스 메서드를 가지고 있으면, 해당 extension point에 자동 등록되는 구조다.

비활성화도 동일하게 동작한다.

```yaml
plugins:
  multiPoint:
    disabled:
      - name: TaintToleration  # Filter + PreScore + Score 전부에서 제거
```

K8s 기본 스케줄러 프로파일도 내부적으로 이 방식을 사용한다. 20개 이상의 기본 플러그인이 `multiPoint`로 등록되어, extension point별로 일일이 나열하지 않고도 깔끔하게 관리된다.

<br>

### multiPoint와 개별 설정의 우선순위

`multiPoint`로 전체를 등록한 뒤, 특정 extension point에서만 오버라이드할 수 있다. **개별 extension point 설정이 multiPoint보다 우선**한다.

```yaml
plugins:
  multiPoint:
    enabled:
      - name: MyPlugin    # MyPlugin이 구현하는 모든 곳에 등록
  score:
    disabled:
      - name: MyPlugin    # 단, Score에서만은 제외
```

<br>

### `*` 패턴: 전체 비활성화와 순서 재배치

`*`를 사용하면 해당 extension point의 모든 기본 플러그인을 한꺼번에 비활성화할 수 있다.

```yaml
profiles:
  - schedulerName: no-scoring-scheduler
    plugins:
      preScore:
        disabled:
          - name: '*'
      score:
        disabled:
          - name: '*'
```

| 패턴 | 의미 |
| --- | --- |
| `disabled: [{name: '*'}]` 만 | 해당 extension point의 기본 플러그인 전부 OFF |
| `disabled: [{name: '*'}]` + `enabled: [...]` | 슬레이트를 깨끗이 하고 원하는 플러그인만 원하는 순서로 등록 |
| `enabled: [...]` 만 | 기본 플러그인은 그대로 유지하고, 그 뒤에 추가 |

**플러그인 호출 순서를 완전히 제어**하고 싶을 때, `*`로 전부 끄고 `enabled`에서 원하는 순서로 다시 나열하면 된다.

```yaml
score:
  disabled:
    - name: '*'           # 기본 플러그인 전부 제거
  enabled:                # 원하는 순서로 다시 등록
    - name: MyCustomScorer
      weight: 5
    - name: NodeResourcesFit
      weight: 2
    - name: NodeAffinity
      weight: 1
    # TaintToleration 등은 아예 안 넣음 → 비활성화
```

이 패턴은 "기본 플러그인 중 일부만 선택적으로 쓰면서 순서도 바꾸고 싶다"는 요구에 유용하다.

<br>

# NodeResourcesFit 스코어링 전략

[2편]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %})에서 `NodeResourcesFit`은 Filter와 Score 양쪽에 등록되는 플러그인이라고 했다. Filter에서는 "리소스가 충분한가"를 판단하고, Score에서는 "충분한 노드들 중 어디가 더 적합한가"를 평가한다. 이 Score 단계의 동작을 결정하는 것이 **스코어링 전략(scoringStrategy)**이다.

세 가지 전략이 있다.

## LeastAllocated (기본)

리소스 사용률이 **낮은** 노드에 높은 점수를 부여한다. 파드를 클러스터 전체에 **분산**시키는 방향이다.

```yaml
pluginConfig:
  - name: NodeResourcesFit
    args:
      scoringStrategy:
        type: LeastAllocated
        resources:
          - name: cpu
            weight: 1
          - name: memory
            weight: 1
```

노드별 점수는 아래 공식으로 계산된다. 노드의 전체 할당 가능 리소스(`allocatable`) 대비 배치 후 남는 여유 비율이 클수록 높은 점수를 받는다.

```
score = (allocatable - requested) / allocatable * MaxScore
```

여유가 많은 노드일수록 점수가 높다. 리소스가 여러 종류(CPU, Memory 등)인 경우, 각 리소스별 점수를 설정된 가중치로 가중 평균하여 최종 점수를 산출한다.

<details markdown="1">
<summary><b>계산 예시</b></summary>

cpu weight: 1, memory weight: 1인 상태에서 새 파드가 cpu 2, memory 256Mi를 요청한다고 가정한다.

**Node A** (여유 많음)

```
Available: cpu 8, memory 16Gi
Used:      cpu 1, memory 2Gi

cpu score   = (8 - (1+2)) / 8 * 100 = 62.5
memory score = (16Gi - (2Gi+256Mi)) / 16Gi * 100 ≈ 85.9
final score = (62.5 * 1 + 85.9 * 1) / (1 + 1) = 74.2
```

**Node B** (여유 적음)

```
Available: cpu 8, memory 16Gi
Used:      cpu 5, memory 12Gi

cpu score   = (8 - (5+2)) / 8 * 100 = 12.5
memory score = (16Gi - (12Gi+256Mi)) / 16Gi * 100 ≈ 23.4
final score = (12.5 * 1 + 23.4 * 1) / (1 + 1) = 18.0
```

Node A(74.2) > Node B(18.0)이므로, **여유가 많은 Node A가 선택**된다. 파드가 분산 배치되는 방향이다.

</details>

부하가 예측 불가능하고 급증할 수 있는 서비스(웹 서버, API 서버), 각 노드에 여유를 남겨 스파이크를 흡수해야 하는 환경, 노드 장애 시 다른 노드가 부하를 분담해야 하는 고가용성 환경에 적합하다.

다만, 모든 노드가 비슷하게 부분 점유되므로 "비어 있는 노드"가 줄어든다. 클러스터 오토스케일러와 함께 사용할 때 스케일 다운 대상 노드를 만들기 어렵고, GPU 등 희소 리소스에서는 단편화 문제가 발생할 수 있다.

<br>

## MostAllocated

리소스 사용률이 **높은** 노드에 높은 점수를 부여한다. 파드를 가능한 한 적은 수의 노드에 **몰아넣는**(bin packing) 방향이다.

```yaml
pluginConfig:
  - name: NodeResourcesFit
    args:
      scoringStrategy:
        type: MostAllocated
        resources:
          - name: cpu
            weight: 1
          - name: memory
            weight: 1
```

노드별 점수는 아래 공식으로 계산된다. 배치 후 노드의 사용률(`requested / allocatable`)이 높을수록 높은 점수를 받는다. LeastAllocated와 정확히 반대 방향이다.

```
score = requested / allocatable * MaxScore
```

LeastAllocated와 마찬가지로, 리소스가 여러 종류인 경우 각 리소스별 점수를 가중 평균하여 최종 점수를 산출한다.

<details markdown="1">
<summary><b>계산 예시</b></summary>

cpu weight: 1, memory weight: 1인 상태에서 새 파드가 cpu 2, memory 256Mi를 요청한다고 가정한다. 위 LeastAllocated 예시와 동일한 노드다.

**Node A** (여유 많음)

```
Available: cpu 8, memory 16Gi
Used:      cpu 1, memory 2Gi

cpu score   = (1+2) / 8 * 100 = 37.5
memory score = (2Gi+256Mi) / 16Gi * 100 ≈ 14.1
final score = (37.5 * 1 + 14.1 * 1) / (1 + 1) = 25.8
```

**Node B** (여유 적음)

```
Available: cpu 8, memory 16Gi
Used:      cpu 5, memory 12Gi

cpu score   = (5+2) / 8 * 100 = 87.5
memory score = (12Gi+256Mi) / 16Gi * 100 ≈ 76.6
final score = (87.5 * 1 + 76.6 * 1) / (1 + 1) = 82.0
```

Node B(82.0) > Node A(25.8)이므로, **이미 많이 사용된 Node B가 선택**된다. 파드가 한 노드에 집중 배치되는 bin packing 방향이다.

</details>

노드 수에 따라 비용이 발생하는 클라우드 환경에서 비용 최적화에 유리하며, 클러스터 오토스케일러와 함께 사용할 때 빈 노드를 만들어 스케일 다운을 유도할 수도 있다. 배치 작업이나 ML 학습 등 일시적 워크로드, GPU 등 희소 리소스의 단편화 방지에도 적합하다.

다만, 특정 노드에 부하가 집중되므로 해당 노드 장애 시 영향 범위가 커지고, 리소스 경합(CPU throttling, OOM 등)이 발생할 가능성이 높아진다.

<br>

## RequestedToCapacityRatio

가장 세밀한 제어가 가능한 전략이다. `shape` 파라미터로 **사용률-점수 매핑 곡선**을 직접 정의한다.

```yaml
pluginConfig:
  - name: NodeResourcesFit
    args:
      scoringStrategy:
        type: RequestedToCapacityRatio
        resources:
          - name: cpu
            weight: 1
          - name: memory
            weight: 1
          - name: nvidia.com/gpu
            weight: 5
        requestedToCapacityRatio:
          shape:
            - utilization: 0
              score: 0
            - utilization: 100
              score: 10
```

`shape`의 두 점을 선형 보간하여 점수를 계산한다. 위 예시는 사용률이 높을수록 점수가 높은 bin packing 동작이다. 반대로 설정하면 LeastAllocated와 유사하게 동작한다.

```yaml
# LeastAllocated와 유사한 동작
shape:
  - utilization: 0
    score: 10
  - utilization: 100
    score: 0
```

**핵심 활용: 리소스별 가중치 차등 적용**

`RequestedToCapacityRatio`의 가장 큰 장점은 **리소스별로 가중치를 차등** 적용할 수 있다는 것이다. 예를 들어 GPU 리소스에 높은 가중치를 주어, GPU를 최우선으로 bin packing하면서 CPU/Memory는 상대적으로 덜 중요하게 취급할 수 있다.

```yaml
resources:
  - name: nvidia.com/gpu
    weight: 10
  - name: cpu
    weight: 1
  - name: memory
    weight: 1
```

<br>

## 전략 비교 요약

| 전략 | 방향 | 점수 기준 | 주요 시나리오 |
| --- | --- | --- | --- |
| LeastAllocated | 분산 | 여유 많은 노드 선호 | 웹 서비스, 고가용성 |
| MostAllocated | 집중 (bin packing) | 사용률 높은 노드 선호 | 비용 최적화, 배치 작업 |
| RequestedToCapacityRatio | 커스텀 | 사용률-점수 곡선 정의 | GPU 워크로드, 세밀 제어 |

<br>

# 리소스 단편화 문제

## 단편화란

리소스 단편화(fragmentation)란 클러스터 전체로 보면 리소스 여유가 있지만, 개별 노드에서는 파드의 요구를 충족하지 못하는 상태를 말한다.

예를 들어, 4-GPU 노드 3대가 있는 클러스터에서:

```
Node A: 4 GPU 중 2 GPU 사용 중 (2 여유)
Node B: 4 GPU 중 2 GPU 사용 중 (2 여유)
Node C: 4 GPU 중 2 GPU 사용 중 (2 여유)
```

클러스터 전체로는 6 GPU가 여유지만, **4 GPU를 요청하는 파드**는 스케줄링할 수 없다. 어떤 노드에도 4 GPU 여유가 없기 때문이다.

## GPU 리소스에서 단편화가 심한 이유

CPU나 Memory와 달리, GPU는 다음과 같은 특성 때문에 단편화에 취약하다.

| 특성 | CPU/Memory | GPU |
| --- | --- | --- |
| 노드당 수량 | 수십~수백 코어, GB 단위 | 보통 2~8개 |
| 단위 크기 | 작음 (1 밀리코어, 1 MiB) | 큼 (1 GPU 단위) |
| 파드당 요청량 | 전체 대비 작은 비율 | 전체 대비 큰 비율 (1~8 GPU) |
| 분할 가능성 | 자유롭게 분할 | 기본적으로 정수 단위 |

GPU가 4개인 노드에서 GPU 1개짜리 파드 2개가 다른 노드에 분산 배치되면, GPU 4개짜리 파드는 어디에도 들어갈 수 없게 된다. **기본 전략인 `LeastAllocated`가 정확히 이 상황을 만든다**. 리소스를 고르게 분산시키므로, 모든 노드가 "부분 점유" 상태가 된다.

## 해결: MostAllocated 또는 RequestedToCapacityRatio

GPU 단편화를 줄이려면, 스코어링 전략을 bin packing 방향으로 전환하여 GPU 파드를 가능한 한 적은 수의 노드에 집중시켜야 한다. 위에서 다룬 두 전략을 활용한다.

- **MostAllocated**: `resources`에 `nvidia.com/gpu`를 추가하고 가중치를 높게(예: 5) 설정한다. GPU 사용률이 높은 노드를 강하게 선호하여, GPU를 먼저 채우는 방향으로 스케줄링한다.
- **RequestedToCapacityRatio**: GPU 가중치를 CPU/Memory보다 크게(예: 10) 주고, `shape`를 사용률이 높을수록 점수가 높은 곡선으로 설정한다. 점수 계산에서 GPU가 지배적이 되어, GPU 사용률이 높은 노드를 강하게 선호한다. CPU/Memory보다 세밀한 제어가 필요할 때 유리하다.

핵심은 공통적으로 **GPU 리소스의 가중치를 CPU/Memory보다 높게 설정**하여, 점수 계산에서 GPU bin packing이 우선되도록 하는 것이다.

## 단편화 방지 설계 가이드

단편화를 방지하기 위한 설계 포인트를 정리한다.

| 방법 | 설명 |
| --- | --- |
| bin packing 전략 | `MostAllocated` 또는 `RequestedToCapacityRatio`로 GPU를 집중 배치 |
| 노드 풀 분리 | GPU 노드와 일반 노드를 taint/toleration으로 분리하여, GPU 노드에는 GPU 워크로드만 배치 |
| 멀티 프로필 | GPU 워크로드 전용 프로필에만 bin packing 적용, 일반 워크로드는 LeastAllocated 유지 |
| 전용 스케줄러 | Volcano, Kueue 등 GPU 토폴로지 인식 스케줄러 사용 |

<br>

# 스케줄러 성능 튜닝

## percentageOfNodesToScore

대규모 클러스터에서 스케줄링 지연을 줄이기 위한 파라미터다. [2편]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %})의 Filter 단계에서 설명했듯, 스케줄러는 모든 노드를 평가하지 않고 충분한 수의 적합 노드를 찾으면 Score 단계로 넘어간다. 이 "충분한 수"를 결정하는 것이 `percentageOfNodesToScore`다.

```yaml
apiVersion: kubescheduler.config.k8s.io/v1
kind: KubeSchedulerConfiguration
percentageOfNodesToScore: 50
```

### 기본값

명시하지 않으면 클러스터 규모에 따라 자동 조정된다.

| 클러스터 규모 | 기본 비율 |
| --- | --- |
| 100 노드 이하 | 100% (모든 노드 평가) |
| 100 노드 | ~50% |
| 5,000 노드 | ~10% |
| 최소값 | 5% (어떤 규모에서도 5% 이상 평가) |

### 트레이드오프

| 값 | 스케줄링 속도 | 스케줄링 품질 |
| --- | --- | --- |
| 높음 (100%) | 느림 | 최적 (모든 노드 비교) |
| 낮음 (10~30%) | 빠름 | 차선 (일부 노드만 비교) |

대규모 클러스터에서 30% 정도가 속도와 품질 사이의 합리적인 균형점으로 알려져 있다. 100노드 이하의 소규모 클러스터에서는 이 파라미터를 따로 설정할 필요가 없다.

### 프로필별 설정 (v1.26+)

v1.26부터는 글로벌 설정뿐만 아니라 프로필별로도 `percentageOfNodesToScore`를 설정할 수 있다. 멀티 프로필 환경에서 워크로드 성격에 따라 다른 값을 적용할 수 있다.

<br>

# 멀티 프로필

[1편]({% post_url 2025-11-05-Kubernetes-Scheduling-01 %})에서 단일 kube-scheduler에서 여러 프로필을 운영할 수 있다고 했다. 여기서는 이를 활용한 구체적인 구성 예시를 다룬다.

## 워크로드 성격에 따른 프로필 분리

일반 서비스와 GPU/배치 워크로드에 서로 다른 스코어링 전략을 적용하는 예시다.

```yaml
apiVersion: kubescheduler.config.k8s.io/v1
kind: KubeSchedulerConfiguration
profiles:
  # 프로필 1: 일반 워크로드 (리소스 분산)
  - schedulerName: default-scheduler
    pluginConfig:
      - name: NodeResourcesFit
        args:
          scoringStrategy:
            type: LeastAllocated
            resources:
              - name: cpu
                weight: 1
              - name: memory
                weight: 1

  # 프로필 2: GPU 워크로드 (bin packing)
  - schedulerName: gpu-binpack-scheduler
    pluginConfig:
      - name: NodeResourcesFit
        args:
          scoringStrategy:
            type: MostAllocated
            resources:
              - name: cpu
                weight: 1
              - name: memory
                weight: 1
              - name: nvidia.com/gpu
                weight: 5
```

파드 배포 시 `spec.schedulerName`으로 프로필을 선택한다.

```yaml
# 일반 서비스: default-scheduler 사용 (기본값)
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web-service
spec:
  template:
    spec:
      containers:
        - name: web
          image: nginx
          resources:
            requests:
              cpu: 500m
              memory: 256Mi
---
# GPU 워크로드: gpu-binpack-scheduler 사용
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ml-training
spec:
  template:
    spec:
      schedulerName: gpu-binpack-scheduler
      containers:
        - name: trainer
          image: ml-trainer:latest
          resources:
            requests:
              nvidia.com/gpu: 2
            limits:
              nvidia.com/gpu: 2
```

## 멀티 프로필의 제약

- 모든 프로필이 **동일한 `queueSort` 플러그인**을 사용해야 한다. 스케줄러 내부적으로 Pending 파드 큐는 하나이기 때문이다.
- 프로필별로 `schedulerName`이 **고유**해야 한다.
- `schedulerName`을 지정하지 않은 파드는 항상 `default-scheduler` 프로필이 처리한다.

## 프로필과 Event 추적

멀티 프로필 환경에서 "어떤 프로필이 이 Pod을 처리했는가"를 확인하려면 Kubernetes Event의 `reportingController` 필드를 보면 된다. 스케줄러는 이벤트 종류에 따라 다른 값을 `reportingController`에 넣는다.

| 이벤트 종류 | `reportingController` 값 | 이유 |
| --- | --- | --- |
| **Pod 스케줄링** | 해당 Pod의 `spec.schedulerName` | 어떤 profile이 처리했는지 추적 |
| **Leader election** | `profiles[0].schedulerName` | 프로세스 전체 대표값 필요 → 첫 번째 profile 사용 |

Pod 스케줄링 이벤트의 경우, 해당 Pod의 `schedulerName`이 그대로 `reportingController`에 들어간다.

```yaml
# schedulerName: gpu-scheduler인 Pod의 스케줄링 Event
apiVersion: events.k8s.io/v1
kind: Event
reportingController: gpu-scheduler   # Pod의 schedulerName이 그대로 들어감
reason: Scheduled
note: "Successfully assigned default/my-pod to node-3"
```

Leader election 이벤트는 프로세스 전체 단위의 동작이므로 특정 profile에 귀속되지 않는다. 프로세스를 대표하는 별도 이름이 없기 때문에, 관례적으로 `profiles` 배열의 **첫 번째** profile 이름을 사용한다.

디버깅 시 `reportingController` 필드로 이벤트를 필터링하면, 어떤 프로필이 어떤 Pod을 처리했는지 빠르게 확인할 수 있다.

```bash
kubectl get events --field-selector reportingController=gpu-scheduler
```

<br>

# 정리

이 글에서 다룬 핵심 내용을 정리한다.

1. **스케줄러 설정은 프로세스 → Configuration → Profile 계층 구조다.** 하나의 스케줄러 프로세스가 하나의 Configuration을 가지고, 그 안에 여러 Profile을 포함한다. `kube-scheduler`는 `--config` 플래그로 Configuration 파일을 전달받으며, 클러스터 유형에 따라 Static Pod, systemd 등 방식이 다르다.
2. **`multiPoint`로 플러그인을 일괄 등록하고, `*` 패턴으로 순서를 재배치할 수 있다.** `multiPoint`는 플러그인이 구현하는 모든 extension point에 자동 등록하며, 개별 extension point 설정이 `multiPoint`보다 우선한다. `*` disable 후 `enabled`로 재등록하면 플러그인 호출 순서를 완전히 제어할 수 있다.
3. **`NodeResourcesFit`은 세 가지 스코어링 전략을 제공한다.** `LeastAllocated`(기본)는 리소스를 분산, `MostAllocated`는 노드를 채우는 bin packing, `RequestedToCapacityRatio`는 리소스별 가중치와 사용률-점수 곡선을 커스텀으로 정의한다.
4. **GPU 리소스는 단편화에 취약하다.** 노드당 수량이 적고 단위가 크기 때문에, `LeastAllocated` 전략에서 모든 노드가 부분 점유되어 큰 GPU 요청을 수용하지 못하는 문제가 발생한다. `MostAllocated`로 전환하거나, GPU 가중치를 높인 `RequestedToCapacityRatio`를 사용하여 bin packing을 적용한다.
5. **`percentageOfNodesToScore`로 대규모 클러스터의 스케줄링 속도를 개선할 수 있다.** 기본값은 클러스터 규모에 따라 자동 조정되며, 100노드 이하에서는 따로 설정할 필요가 없다.
6. **멀티 프로필로 워크로드 성격에 맞는 스케줄링 정책을 적용할 수 있다.** 일반 워크로드에는 `LeastAllocated`, GPU 워크로드에는 `MostAllocated`를 적용하는 식으로 프로필을 분리한다.

이 글까지 포함하여 스케줄링 시리즈에서 다룬 내용을 종합하면:

| 편 | 핵심 |
| --- | --- |
| [1편]({% post_url 2025-11-05-Kubernetes-Scheduling-01 %}) | 스케줄링 개념, 스케줄러, 판단 기준, 수동 스케줄링, DaemonSet, 큐 |
| [2편]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %}) | 스케줄링 프레임워크, Extension Point, 플러그인, 선점 |
| [3편]({% post_url 2025-11-05-Kubernetes-Scheduling-03 %}) | Scheduling Gate, nodeSelector, Affinity, Topology Spread, Taint/Toleration |
| 4편 (이 글) | 설정 계층 구조, 플러그인 설정 패턴, NodeResourcesFit 전략, GPU 단편화, 멀티 프로필 |
| [5편]({% post_url 2025-11-05-Kubernetes-Scheduling-05 %}) | Extension Point 심화, PreScore 역할, PodGroup 스케줄링, 멀티 스케줄러 아키텍처 |

<br>

# 참고 링크

- [Scheduler Configuration - Kubernetes 공식 문서](https://kubernetes.io/docs/reference/scheduling/config/)
- [Resource Bin Packing - Kubernetes 공식 문서](https://kubernetes.io/docs/concepts/scheduling-eviction/resource-bin-packing/)
- [Scheduler Performance Tuning - Kubernetes 공식 문서](https://kubernetes.io/docs/concepts/scheduling-eviction/scheduler-perf-tuning/)
- [kube-scheduler Configuration (v1) API Reference](https://kubernetes.io/docs/reference/config-api/kube-scheduler-config.v1/)
- [Practical Tips for Preventing GPU Fragmentation - NVIDIA Technical Blog](https://developer.nvidia.com/blog/practical-tips-for-preventing-gpu-fragmentation-for-volcano-scheduler/)

<br>