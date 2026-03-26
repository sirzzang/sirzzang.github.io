---
title:  "[Kubernetes] 쿠버네티스 스케줄링 - 3. 스케줄링 제어"
excerpt: "파드가 실행될 노드를 제어하기 위한 다양한 설정과 스케줄링 게이트에 대해 알아보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - Scheduler
  - Scheduling
  - Node Affinity
  - Pod Affinity
  - Taint
  - Toleration
  - Scheduling Gate
  - Topology Spread Constraints
---

<br>

# TL;DR

- 파드가 실행될 노드를 **제어**하기 위한 설정으로 `nodeSelector`, Node Affinity, Pod Affinity/Anti-Affinity, Topology Spread Constraints, Taints/Tolerations 등이 있다. 이 설정들은 스케줄링 프레임워크의 Filter와 Score 단계에서 플러그인을 통해 평가된다.
- **Scheduling Gate**(v1.30 GA)는 파드의 스케줄링 자체를 보류하는 메커니즘이다. 게이트가 설정된 파드는 스케줄러의 큐에 진입하지 않으며(`SchedulingGated` 상태), 모든 게이트가 제거되어야 스케줄링이 시작된다.
- `nodeSelector`는 단순 라벨 매칭, Node Affinity는 표현식 기반의 유연한 노드 선택, Pod Affinity/Anti-Affinity는 다른 파드와의 관계 기반 배치를 제어한다.
- Taints/Tolerations는 노드가 특정 파드를 거부하는 메커니즘이고, Topology Spread Constraints는 토폴로지(zone, node 등) 기준 파드 분산을 제어한다.

<br>

# 들어가며

[이전 글]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %})에서 스케줄링 프레임워크의 전체 extension point와 플러그인 동작 원리를 살펴보았다. 스케줄러가 Filter → Score → Bind 과정을 거쳐 노드를 선택한다는 것을 알았으니, 이번 글에서는 **그 과정에 영향을 주는 파드/노드 설정**을 다룬다.

1. **Scheduling Gate**: 스케줄링 자체를 보류하는 메커니즘
2. **nodeSelector**: 가장 단순한 노드 선택 방법
3. **Node Affinity**: 표현식 기반의 유연한 노드 선택
4. **Pod Affinity / Anti-Affinity**: 다른 파드와의 관계 기반 배치
5. **Topology Spread Constraints**: 토폴로지 기준 파드 분산
6. **Taints and Tolerations**: 노드 기반의 파드 거부 메커니즘

각 설정이 스케줄링 프레임워크의 어떤 단계(Filter/Score)에서 어떤 플러그인에 의해 평가되는지도 함께 정리한다.

<br>

# Scheduling Gate

## 개념

[Scheduling Gate](https://kubernetes.io/docs/concepts/scheduling-eviction/pod-scheduling-readiness/)(v1.26 alpha, **v1.30 GA**)는 파드의 스케줄링을 의도적으로 **보류**하는 메커니즘이다. 파드의 `spec.schedulingGates` 필드에 하나 이상의 게이트를 설정하면, 해당 파드는 `SchedulingGated` 상태가 되어 스케줄러가 아예 스케줄링을 시도하지 않는다.

[이전 글]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %})에서 다룬 프레임워크 기준으로 보면, Scheduling Gate는 **PreEnqueue** extension point에서 동작한다. 게이트가 설정된 파드는 Active Queue에 진입하지 못하므로, 스케줄링 사이클 자체가 시작되지 않는다.

## 동작 방식

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: gated-pod
spec:
  schedulingGates:
  - name: example.com/wait-for-gpu-node
  - name: example.com/wait-for-license
  containers:
  - name: ml-training
    image: ml-training:latest
```

```bash
kubectl get pod gated-pod
# NAME        READY   STATUS            RESTARTS   AGE
# gated-pod   0/1     SchedulingGated   0          7s
```

- 게이트는 **파드 생성 시에만** 추가할 수 있다. 생성 후 새 게이트를 추가하는 것은 불가능하다.
- 각 게이트는 순서와 관계없이 **개별적으로 제거**할 수 있다. 외부 컨트롤러나 운영자가 조건이 충족되면 해당 게이트를 제거한다.
- **모든** 게이트가 제거되어야 파드가 Active Queue에 진입하여 스케줄링이 시작된다.

## 게이트가 설정된 동안의 변경

Scheduling Gate가 설정된 상태에서는 파드의 스케줄링 지시자(scheduling directives)를 **제한적으로 변경**할 수 있다. 핵심 원칙은 "조건을 더 좁히는 방향으로만 변경 가능"이라는 것이다.

- `spec.nodeSelector`: 추가만 가능 (삭제 불가)
- `spec.affinity.nodeAffinity.requiredDuringScheduling`: `matchExpressions`, `fieldExpressions`에 조건 추가만 가능
- `spec.affinity.nodeAffinity.preferredDuringScheduling`: 자유롭게 변경 가능

## 유스케이스

아래와 같은 시나리오에 Scheduling Gate를 도입해 볼 수 있다.

| 시나리오 | 설명 |
| --- | --- |
| 장비 추가 전 파드 사전 생성 | GPU 노드가 아직 준비되지 않았지만, 파드를 미리 생성해 두고 노드 준비 후 게이트 제거 |
| 외부 승인 워크플로우 | 비용 승인, 라이선스 확인 등 외부 시스템의 승인을 받은 후에만 스케줄링 |
| 리소스 쿼터 관리 | 클러스터 리소스가 확보될 때까지 스케줄링을 보류하여 불필요한 스케줄링 시도 방지 |
| CI/CD 파이프라인 연동 | 배포 파이프라인에서 특정 단계가 완료된 후에만 파드 스케줄링 |
| 동적 스케줄링 조건 설정 | 게이트가 설정된 동안 nodeSelector나 affinity를 조건에 맞게 설정한 뒤 게이트 제거 |

Scheduling Gate의 핵심 이점은, 스케줄링 불가능한 파드가 스케줄러의 큐에서 반복적으로 시도되는 것을 방지한다는 것이다. 게이트가 없으면 파드는 Active Queue → 스케줄링 실패 → Backoff/Unschedulable Queue → 다시 Active Queue 순환을 반복하며 스케줄러에 불필요한 부하를 준다. Cluster Autoscaler 등 외부 컴포넌트도 이러한 파드를 "스케줄링 불가능"으로 인식하여 불필요한 스케일링 판단을 할 수 있다.

<br>

# nodeSelector

가장 단순한 노드 선택 방법이다. 파드에 `spec.nodeSelector`를 설정하면, 해당 라벨을 가진 노드에만 스케줄링된다.

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: gpu-pod
spec:
  nodeSelector:
    accelerator: nvidia-tesla-v100
  containers:
  - name: cuda
    image: cuda-app:latest
```

- **프레임워크 평가**: `NodeAffinity` 플러그인이 Filter 단계에서 평가
- **동작**: AND 조건. 모든 라벨이 일치해야 통과
- **한계**: 단순 equality 매칭만 가능. OR 조건, 부정 조건(not in), 소프트 조건(preferred) 등은 표현할 수 없음

<br>

# Node Affinity

`nodeSelector`의 확장 버전으로, 표현식 기반의 유연한 노드 선택이 가능하다. [공식 문서](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/#node-affinity)

## requiredDuringSchedulingIgnoredDuringExecution

**반드시** 조건을 만족하는 노드에만 스케줄링된다. Filter 단계에서 평가되며, 조건을 만족하지 않는 노드는 탈락한다.

```yaml
spec:
  affinity:
    nodeAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
        nodeSelectorTerms:
        - matchExpressions:
          - key: topology.kubernetes.io/zone
            operator: In
            values:
            - ap-northeast-2a
            - ap-northeast-2c
```

- `nodeSelectorTerms`는 **OR** 관계: 하나라도 만족하면 통과
- `matchExpressions` 내부는 **AND** 관계: 모든 조건을 만족해야 통과
- 지원 연산자: `In`, `NotIn`, `Exists`, `DoesNotExist`, `Gt`, `Lt`

## preferredDuringSchedulingIgnoredDuringExecution

조건을 만족하면 **선호**하지만, 만족하지 않아도 스케줄링 가능하다. Score 단계에서 평가되며, 조건을 만족하는 노드에 더 높은 점수를 부여한다.

```yaml
spec:
  affinity:
    nodeAffinity:
      preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 80
        preference:
          matchExpressions:
          - key: node-type
            operator: In
            values:
            - high-memory
      - weight: 20
        preference:
          matchExpressions:
          - key: disk-type
            operator: In
            values:
            - ssd
```

- `weight`는 1~100 범위이며, 조건을 만족하는 노드에 해당 가중치가 Score에 더해진다

> **`IgnoredDuringExecution`의 의미**: 파드가 이미 노드에서 실행 중일 때 노드 라벨이 변경되어도 파드를 축출하지 않는다는 뜻이다. 스케줄링 시점에만 조건을 평가한다.

<br>

# Pod Affinity / Anti-Affinity

노드의 속성이 아니라, **해당 노드에서 이미 실행 중인 다른 파드**를 기준으로 배치를 제어한다. [공식 문서](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/#inter-pod-affinity-and-anti-affinity)

## Pod Affinity

특정 파드와 **같은 토폴로지 도메인**에 배치하고 싶을 때 사용한다.

```yaml
spec:
  affinity:
    podAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
      - labelSelector:
          matchExpressions:
          - key: app
            operator: In
            values:
            - cache
        topologyKey: kubernetes.io/hostname
```

위 예시는 `app=cache` 라벨을 가진 파드가 실행 중인 노드와 같은 `kubernetes.io/hostname`(즉, 같은 노드)에 배치한다.

## Pod Anti-Affinity

특정 파드와 **다른 토폴로지 도메인**에 배치하고 싶을 때 사용한다. 고가용성을 위해 같은 애플리케이션의 레플리카를 서로 다른 노드/zone에 분산하는 데 자주 사용된다.

```yaml
spec:
  affinity:
    podAntiAffinity:
      preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 100
        podAffinityTerm:
          labelSelector:
            matchExpressions:
            - key: app
              operator: In
              values:
              - web-frontend
          topologyKey: topology.kubernetes.io/zone
```

- **프레임워크 평가**: `InterPodAffinity` 플러그인이 Filter(`required`)와 Score(`preferred`) 단계에서 평가
- `topologyKey`는 노드 라벨의 키를 지정. 같은 키-값 쌍을 가진 노드들이 하나의 토폴로지 도메인을 형성

<br>

# Topology Spread Constraints

파드를 **토폴로지 도메인 간 균일하게 분산**하는 제약이다. Pod Anti-Affinity보다 세밀한 분산 제어가 가능하다. [공식 문서](https://kubernetes.io/docs/concepts/scheduling-eviction/topology-spread-constraints/)

```yaml
spec:
  topologySpreadConstraints:
  - maxSkew: 1
    topologyKey: topology.kubernetes.io/zone
    whenUnsatisfiable: DoNotSchedule
    labelSelector:
      matchLabels:
        app: web
```

- `maxSkew`: 토폴로지 도메인 간 파드 수 차이의 최대 허용치. 1이면 각 zone 간 파드 수 차이가 최대 1
- `topologyKey`: 분산 기준이 되는 노드 라벨 키
- `whenUnsatisfiable`:
  - `DoNotSchedule`: 제약을 만족하지 못하면 스케줄링하지 않음 (Filter 동작)
  - `ScheduleAnyway`: 제약을 가능한 한 만족하도록 노력하되, 불가능하면 스케줄링 허용 (Score 동작)
- **프레임워크 평가**: `PodTopologySpread` 플러그인이 Filter(`DoNotSchedule`)와 Score(`ScheduleAnyway`) 단계에서 평가

<br>

# Taints and Tolerations

Node Affinity가 "이 노드에 배치해 달라"는 **파드 측의 요청**이라면, Taints/Tolerations는 "이 파드는 받지 않겠다"는 **노드 측의 거부**다. [공식 문서](https://kubernetes.io/docs/concepts/scheduling-eviction/taint-and-toleration/)

## Taint

노드에 설정하는 속성이다. taint가 설정된 노드에는 해당 taint를 tolerate하지 않는 파드가 스케줄링되지 않는다.

```bash
kubectl taint nodes node1 gpu=true:NoSchedule
```

taint의 effect는 세 가지다.

| Effect | 동작 |
| --- | --- |
| `NoSchedule` | toleration이 없는 파드는 스케줄링하지 않음 (기존 파드는 유지) |
| `PreferNoSchedule` | 가능하면 스케줄링하지 않지만, 다른 노드가 없으면 허용 |
| `NoExecute` | toleration이 없는 파드는 스케줄링하지 않고, **이미 실행 중인 파드도 축출** |

## Toleration

파드에 설정하는 속성이다. 특정 taint를 "허용"하여 해당 노드에 스케줄링될 수 있게 한다.

```yaml
spec:
  tolerations:
  - key: "gpu"
    operator: "Equal"
    value: "true"
    effect: "NoSchedule"
```

- `operator: Equal`: key, value, effect가 모두 일치해야 tolerate
- `operator: Exists`: key와 effect가 일치하면 tolerate (value 무시)
- key가 비어 있고 `operator: Exists`이면 모든 taint를 tolerate

## 프레임워크 평가

- `TaintToleration` 플러그인이 Filter(NoSchedule, NoExecute)와 Score(PreferNoSchedule, taint가 적은 노드 선호) 단계에서 평가
- Score 가중치는 기본 3으로, 다른 Score 플러그인보다 높다

> **참고**: `NoExecute` taint는 스케줄링뿐만 아니라 이미 실행 중인 파드에도 영향을 준다. 파드에 `tolerationSeconds`를 설정하면, taint가 추가된 후 해당 시간이 지나면 축출된다. 노드 장애 시 자동 설정되는 `node.kubernetes.io/not-ready`와 `node.kubernetes.io/unreachable` taint가 대표적인 예이다.

<br>

# 스케줄링 제어 설정 요약

각 설정이 스케줄링 프레임워크의 어떤 단계에서 어떤 플러그인에 의해 평가되는지 정리한다.

| 설정 | 플러그인 | Filter (required) | Score (preferred) |
| --- | --- | --- | --- |
| Scheduling Gate | (PreEnqueue) | 큐 진입 차단 | - |
| nodeSelector | NodeAffinity | O | - |
| Node Affinity (required) | NodeAffinity | O | - |
| Node Affinity (preferred) | NodeAffinity | - | O |
| Pod Affinity (required) | InterPodAffinity | O | - |
| Pod Affinity (preferred) | InterPodAffinity | - | O |
| Topology Spread (DoNotSchedule) | PodTopologySpread | O | - |
| Topology Spread (ScheduleAnyway) | PodTopologySpread | - | O |
| Taint (NoSchedule/NoExecute) | TaintToleration | O | - |
| Taint (PreferNoSchedule) | TaintToleration | - | O |

<br>

# 정리

이 글에서 다룬 핵심 내용을 정리한다.

1. **Scheduling Gate는 스케줄링 자체를 보류한다.** 파드가 `SchedulingGated` 상태로 큐에 진입하지 않으므로, 스케줄러 부하 없이 외부 조건이 충족될 때까지 대기할 수 있다. 게이트가 설정된 동안 스케줄링 조건을 좁히는 방향으로 변경할 수도 있다.
2. **nodeSelector와 Node Affinity는 노드 속성 기반의 배치 제어다.** nodeSelector는 단순 라벨 매칭, Node Affinity는 표현식 기반으로 더 유연하다. `required`는 Filter에서, `preferred`는 Score에서 평가된다.
3. **Pod Affinity/Anti-Affinity는 파드 간 관계 기반의 배치 제어다.** 같은 노드/zone에 함께 배치하거나 분리할 수 있다. 고가용성 확보에 Anti-Affinity가 자주 사용된다.
4. **Topology Spread Constraints는 토폴로지 기준의 균일 분산을 제어한다.** `maxSkew`로 도메인 간 파드 수 차이를 제한하며, Pod Anti-Affinity보다 세밀한 분산이 가능하다.
5. **Taints/Tolerations는 노드 측의 거부 메커니즘이다.** 파드의 요청(affinity)과 노드의 거부(taint)를 조합하여 정교한 배치 제어가 가능하다. `NoExecute`는 이미 실행 중인 파드에도 영향을 준다.

[이전 글들]({% post_url 2025-11-05-Kubernetes-Scheduling-01 %})에서 다룬 스케줄러의 개념, 프로세스와 함께 이 글의 스케줄링 제어 설정을 이해하면, 파드가 왜 특정 노드에 배치되었는지(또는 배치되지 않았는지)를 체계적으로 파악할 수 있다. [다음 글]({% post_url 2025-11-05-Kubernetes-Scheduling-04 %})에서는 스케줄러 설정과 최적화(NodeResourcesFit 전략, GPU 단편화, 멀티 프로필 등)를 다룬다.

<br>