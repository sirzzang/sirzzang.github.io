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

- `KubeSchedulerConfiguration`을 통해 스케줄러의 플러그인 구성, 스코어링 전략, 성능 파라미터를 세밀하게 설정할 수 있다.
- `NodeResourcesFit` 플러그인은 세 가지 스코어링 전략을 제공한다: `LeastAllocated`(기본, 리소스 분산), `MostAllocated`(bin packing, 노드 채우기), `RequestedToCapacityRatio`(커스텀 곡선).
- GPU 등 희소 리소스는 `LeastAllocated` 전략에서 **단편화(fragmentation)** 문제가 발생하기 쉽다. 여러 노드에 GPU가 분산 배치되어, 단일 노드에서 충분한 GPU를 확보하지 못하는 상황이다. `MostAllocated` 전략으로 완화할 수 있다.
- `percentageOfNodesToScore`로 대규모 클러스터에서의 스케줄링 지연을 줄일 수 있으며, 단일 kube-scheduler에서 여러 프로필을 운영하여 워크로드 성격에 맞는 스케줄링 정책을 적용할 수 있다.

<br>

# 들어가며

[이전 글들]({% post_url 2025-11-05-Kubernetes-Scheduling-01 %})에서 스케줄링의 개념, 프레임워크, 스케줄링 제어 설정까지 다뤘다. 이번 글에서는 **스케줄러 자체의 설정과 최적화**를 다룬다.

1. **KubeSchedulerConfiguration**: 스케줄러 설정 파일의 구조와 주요 필드
2. **NodeResourcesFit 스코어링 전략**: LeastAllocated, MostAllocated, RequestedToCapacityRatio 세 전략의 동작 원리와 사용 시나리오
3. **리소스 단편화 문제**: 특히 GPU 환경에서 발생하는 단편화와 해결 방안
4. **스케줄러 성능 튜닝**: `percentageOfNodesToScore`와 대규모 클러스터 최적화
5. **멀티 프로필**: 워크로드 성격에 따라 서로 다른 스케줄링 정책을 적용하는 구성

<br>

# KubeSchedulerConfiguration

## 설정 파일 구조

`kube-scheduler`는 `--config` 플래그로 설정 파일을 전달받는다. 설정 파일은 `KubeSchedulerConfiguration` API 오브젝트로, 스케줄러의 동작을 세밀하게 제어한다.

```yaml
apiVersion: kubescheduler.config.k8s.io/v1
kind: KubeSchedulerConfiguration
clientConnection:
  kubeconfig: /etc/srv/kubernetes/kube-scheduler/kubeconfig
profiles:
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

`multiPoint` 필드를 사용하면 하나의 플러그인을 해당 플러그인이 지원하는 모든 extension point에 한 번에 활성화할 수 있다.

```yaml
profiles:
  - schedulerName: default-scheduler
    plugins:
      multiPoint:
        enabled:
          - name: MyPlugin
```

`*`를 사용하면 해당 extension point의 모든 기본 플러그인을 비활성화할 수 있다.

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

점수 계산:

```
score = (allocatable - requested) / allocatable * MaxScore
```

여유가 많은 노드일수록 점수가 높다. 리소스가 여러 종류인 경우, 각 리소스별 점수를 가중 평균하여 최종 점수를 산출한다.

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

**적합한 시나리오:**
- 부하가 예측 불가능하고 급증할 수 있는 서비스 (웹 서버, API 서버)
- 각 노드에 여유를 남겨 스파이크를 흡수해야 하는 환경
- 노드 장애 시 다른 노드가 부하를 분담해야 하는 고가용성 환경

**한계:**
- 모든 노드가 비슷하게 부분 점유되므로, "비어 있는 노드"가 줄어듦
- 클러스터 오토스케일러와 함께 사용 시, 스케일 다운 대상 노드를 만들기 어려움
- GPU 등 희소 리소스에서 단편화 문제 발생 가능

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

점수 계산:

```
score = requested / allocatable * MaxScore
```

사용률이 높은 노드일수록 점수가 높다. LeastAllocated와 마찬가지로, 리소스별 점수를 가중 평균하여 최종 점수를 산출한다.

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

**적합한 시나리오:**
- 노드 수에 따라 비용이 발생하는 클라우드 환경 (비용 최적화)
- 클러스터 오토스케일러와 함께 사용 시, 빈 노드를 만들어 스케일 다운 유도
- 배치 작업, ML 학습 등 일시적 워크로드
- GPU 등 희소 리소스의 단편화 방지

**한계:**
- 특정 노드에 부하가 집중되어, 해당 노드 장애 시 영향 범위가 큼
- 리소스 경합(CPU throttling, OOM 등)이 발생할 가능성이 높아짐

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

GPU 단편화를 줄이려면, 스코어링 전략을 bin packing 방향으로 전환하여 GPU 파드를 가능한 한 적은 수의 노드에 집중시켜야 한다.

**방법 1: MostAllocated**

```yaml
profiles:
  - schedulerName: default-scheduler
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

GPU 가중치를 높게 설정하면, GPU 사용률이 높은 노드를 강하게 선호하여 GPU를 먼저 채우는 방향으로 스케줄링한다.

**방법 2: RequestedToCapacityRatio (더 세밀한 제어)**

```yaml
profiles:
  - schedulerName: default-scheduler
    pluginConfig:
      - name: NodeResourcesFit
        args:
          scoringStrategy:
            type: RequestedToCapacityRatio
            resources:
              - name: nvidia.com/gpu
                weight: 10
              - name: cpu
                weight: 1
              - name: memory
                weight: 1
            requestedToCapacityRatio:
              shape:
                - utilization: 0
                  score: 0
                - utilization: 100
                  score: 10
```

GPU에 가중치 10을 주면, 점수 계산에서 GPU가 지배적이 되어 GPU 사용률이 높은 노드를 강하게 선호한다. CPU/Memory는 가중치 1이므로 점수에 미치는 영향이 상대적으로 작다.

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

<br>

# 정리

이 글에서 다룬 핵심 내용을 정리한다.

1. **`KubeSchedulerConfiguration`으로 스케줄러를 세밀하게 설정할 수 있다.** 프로필별 플러그인 활성화/비활성화, 플러그인별 상세 설정(스코어링 전략, 가중치), 성능 파라미터 등을 제어한다.
2. **`NodeResourcesFit`은 세 가지 스코어링 전략을 제공한다.** `LeastAllocated`(기본)는 리소스를 분산, `MostAllocated`는 노드를 채우는 bin packing, `RequestedToCapacityRatio`는 리소스별 가중치와 사용률-점수 곡선을 커스텀으로 정의한다.
3. **GPU 리소스는 단편화에 취약하다.** 노드당 수량이 적고 단위가 크기 때문에, `LeastAllocated` 전략에서 모든 노드가 부분 점유되어 큰 GPU 요청을 수용하지 못하는 문제가 발생한다. `MostAllocated`로 전환하거나, GPU 가중치를 높인 `RequestedToCapacityRatio`를 사용하여 bin packing을 적용한다.
4. **`percentageOfNodesToScore`로 대규모 클러스터의 스케줄링 속도를 개선할 수 있다.** 기본값은 클러스터 규모에 따라 자동 조정되며, 100노드 이하에서는 따로 설정할 필요가 없다.
5. **멀티 프로필로 워크로드 성격에 맞는 스케줄링 정책을 적용할 수 있다.** 일반 워크로드에는 `LeastAllocated`, GPU 워크로드에는 `MostAllocated`를 적용하는 식으로 프로필을 분리한다.

이 글까지 포함하여 스케줄링 시리즈에서 다룬 내용을 종합하면:

| 편 | 핵심 |
| --- | --- |
| [1편]({% post_url 2025-11-05-Kubernetes-Scheduling-01 %}) | 스케줄링 개념, 스케줄러, 판단 기준, 수동 스케줄링, DaemonSet, 큐 |
| [2편]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %}) | 스케줄링 프레임워크, Extension Point, 플러그인, 선점 |
| [3편]({% post_url 2025-11-05-Kubernetes-Scheduling-03 %}) | Scheduling Gate, nodeSelector, Affinity, Topology Spread, Taint/Toleration |
| 4편 (이 글) | KubeSchedulerConfiguration, NodeResourcesFit 전략, GPU 단편화, 멀티 프로필 |

<br>

# 참고 링크

- [Scheduler Configuration - Kubernetes 공식 문서](https://kubernetes.io/docs/reference/scheduling/config/)
- [Resource Bin Packing - Kubernetes 공식 문서](https://kubernetes.io/docs/concepts/scheduling-eviction/resource-bin-packing/)
- [Scheduler Performance Tuning - Kubernetes 공식 문서](https://kubernetes.io/docs/concepts/scheduling-eviction/scheduler-perf-tuning/)
- [kube-scheduler Configuration (v1) API Reference](https://kubernetes.io/docs/reference/config-api/kube-scheduler-config.v1/)
- [Practical Tips for Preventing GPU Fragmentation - NVIDIA Technical Blog](https://developer.nvidia.com/blog/practical-tips-for-preventing-gpu-fragmentation-for-volcano-scheduler/)
