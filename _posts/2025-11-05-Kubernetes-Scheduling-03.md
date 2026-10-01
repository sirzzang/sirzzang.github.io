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
last_modified_at: 2026-10-01
---

<br>

# TL;DR

- 파드가 실행될 노드를 **제어**하기 위한 설정으로 `nodeSelector`, Node Affinity, Pod Affinity/Anti-Affinity, Topology Spread Constraints, Taints/Tolerations 등이 있다. 이 설정들은 스케줄링 프레임워크의 Filter와 Score 단계에서 플러그인을 통해 평가된다.
- 제어 설정은 두 방향으로 나뉜다. `nodeSelector`·Node Affinity·Pod Affinity는 **파드가 배치를 요구**하는 쪽이고, Taints/Tolerations는 **노드가 파드를 거부**하는 쪽이다.
- **Scheduling Gate**(v1.26 alpha, v1.30 GA)는 파드의 스케줄링 자체를 보류하는 메커니즘이다. 게이트가 설정된 파드는 스케줄러의 큐에 진입하지 않으며(`SchedulingGated` 상태), 모든 게이트가 제거되어야 스케줄링이 시작된다.
- `nodeSelector`는 단순 라벨 매칭, Node Affinity는 표현식 기반의 유연한 노드 선택, Pod Affinity/Anti-Affinity는 다른 파드와의 관계 기반 배치를 제어한다.
- Topology Spread Constraints는 토폴로지(zone, node 등) 기준 파드 분산을 제어한다. `maxSkew`는 도메인 쌍 간 차이가 아니라 **대상 도메인과 전역 최솟값의 차이**다.

<br>

# 들어가며

[2편]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %})에서 스케줄링 프레임워크의 전체 extension point와 플러그인 동작 원리를 살펴보았다. 스케줄러가 Filter → Score → Bind 과정을 거쳐 노드를 선택한다는 것을 알았으니, 이번 글에서는 **그 과정에 영향을 주는 파드/노드 설정**을 다룬다.

1. **Scheduling Gate**: 스케줄링 자체를 보류하는 메커니즘
2. **파드 측 배치 요청**: `nodeSelector`, Node Affinity, Pod Affinity / Anti-Affinity
3. **노드 측 거부와 토폴로지 분산**: Taints and Tolerations, Topology Spread Constraints

각 설정이 스케줄링 프레임워크의 어떤 단계(Filter/Score)에서 어떤 플러그인에 의해 평가되는지도 함께 정리한다.

<br>

# Scheduling Gate

## 개념

[Scheduling Gate](https://kubernetes.io/docs/concepts/scheduling-eviction/pod-scheduling-readiness/)(v1.26 alpha, **v1.30 GA**)는 파드의 스케줄링을 의도적으로 **보류**하는 메커니즘이다. 파드의 `spec.schedulingGates` 필드에 하나 이상의 게이트를 설정하면, 해당 파드는 `SchedulingGated` 상태가 되어 스케줄러가 아예 스케줄링을 시도하지 않는다.

[2편]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %}#preenqueue)에서 다룬 프레임워크 기준으로 보면, Scheduling Gate는 **PreEnqueue** extension point에서 `SchedulingGates` 플러그인이 처리한다. 게이트가 설정된 파드는 Active Queue에 진입하지 못하므로, 스케줄링 사이클 자체가 시작되지 않는다.

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
- 게이트가 남아 있는 동안에는 [Binding 오브젝트]({% post_url 2025-11-05-Kubernetes-Scheduling-01 %}#binding이-거부되는-조건)로 수동 배치하는 것도 거부된다.

## 게이트가 설정된 동안의 변경

Scheduling Gate가 설정된 상태에서는 파드의 스케줄링 지시자(scheduling directives)를 **제한적으로 변경**할 수 있다. 핵심 원칙은 "조건을 더 좁히는 방향으로만 변경 가능"이라는 것이다.

- `spec.nodeSelector`: 추가만 가능 (삭제 불가)
- `spec.affinity.nodeAffinity.requiredDuringSchedulingIgnoredDuringExecution`: `nodeSelectorTerms`의 `matchExpressions`와 `matchFields`에 조건 추가만 가능
- `spec.affinity.nodeAffinity.preferredDuringSchedulingIgnoredDuringExecution`: 자유롭게 변경 가능

> 공식 문서는 두 번째 항목을 "additions of `NodeSelectorRequirements` to `matchExpressions` or `fieldExpressions`"라고 기술한다. 여기서 `fieldExpressions`는 문서상의 표현이고, 실제 API 필드명은 [아래에서 다룰](#사례-daemonset의-nodeaffinity-위임) `matchFields`다.

## 유스케이스

아래와 같은 시나리오에 Scheduling Gate를 도입해 볼 수 있다.

| 시나리오 | 설명 |
| --- | --- |
| 장비 추가 전 파드 사전 생성 | GPU 노드가 아직 준비되지 않았지만, 파드를 미리 생성해 두고 노드 준비 후 게이트 제거 |
| 외부 승인 워크플로우 | 비용 승인, 라이선스 확인 등 외부 시스템의 승인을 받은 후에만 스케줄링 |
| 리소스 쿼터 관리 | 클러스터 리소스가 확보될 때까지 스케줄링을 보류하여 불필요한 스케줄링 시도 방지. [Kueue](https://kueue.sigs.k8s.io/)가 이 방식으로 큐 정책을 구현한다 |
| CI/CD 파이프라인 연동 | 배포 파이프라인에서 특정 단계가 완료된 후에만 파드 스케줄링 |
| 동적 스케줄링 조건 설정 | 게이트가 설정된 동안 nodeSelector나 affinity를 조건에 맞게 설정한 뒤 게이트 제거 |

Scheduling Gate의 핵심 이점은, 스케줄링 불가능한 파드가 스케줄러의 큐에서 반복적으로 시도되는 것을 방지한다는 것이다. 게이트가 없으면 파드는 Active Queue → 스케줄링 실패 → Backoff/Unschedulable Queue → 다시 Active Queue 순환을 반복하며 스케줄러에 불필요한 부하를 준다. Cluster Autoscaler 등 외부 컴포넌트도 이러한 파드를 "스케줄링 불가능"으로 인식하여 불필요한 스케일링 판단을 할 수 있다.

Kueue가 이 메커니즘으로 fair-share·borrowing 같은 큐 정책을 구현하는 방식은 [5편 - Volcano vs Kueue]({% post_url 2025-11-05-Kubernetes-Scheduling-05 %}#volcano-vs-kueue-접근-방식의-차이)에서 다룬다.

<br>

# 파드 측 배치 요청

파드가 스스로 "이런 노드에 배치해 달라"고 요구하는 설정들이다. 선택 기준을 먼저 정리하면 다음과 같다.

- 라벨 하나로 노드를 고정하면 충분하다 → `nodeSelector`
- OR 조건, 부정 조건, 소프트 조건(선호)이 필요하다 → **Node Affinity**
- 기준이 노드의 속성이 아니라 그 노드에 이미 떠 있는 파드다 → **Pod Affinity / Anti-Affinity**

셋 모두 파드가 요구하는 쪽이고, 노드가 파드를 거부하는 쪽은 [노드 측 거부와 토폴로지 분산](#노드-측-거부와-토폴로지-분산)에서 다룬다.

<br>

## nodeSelector

가장 단순한 노드 선택 방법이다. 파드에 `spec.nodeSelector`를 설정하면, 해당 라벨을 가진 노드에만 스케줄링된다.

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: gpu-pod
spec:
  nodeSelector:
    accelerator: nvidia-tesla-v100  # 이 라벨이 붙은 노드에만 배치
  containers:
  - name: cuda
    image: cuda-app:latest
```

- **프레임워크 평가**: `NodeAffinity` 플러그인이 Filter 단계에서 평가
- **동작**: AND 조건. 모든 라벨이 일치해야 통과
- **한계**: 단순 equality 매칭만 가능. OR 조건, 부정 조건(not in), 소프트 조건(preferred) 등은 표현할 수 없음

`nodeSelector`와 Node Affinity의 `required` 조건은 **같은 플러그인이 같은 Filter 단계에서 평가**한다. 표현력이 더 좋은 Node Affinity가 있는데도 `nodeSelector`가 남아 있는 이유와 선택 기준은 다음과 같다.

| 항목 | `nodeSelector` | Node Affinity `required` |
| --- | --- | --- |
| 표현력 | equality 매칭만 | `In`, `NotIn`, `Exists`, `DoesNotExist`, `Gt`, `Lt` |
| OR 조건 | 불가 | `nodeSelectorTerms`를 여러 개 두면 OR |
| 필드 매칭 | 불가 | `matchFields`로 파드 객체 필드 매칭 가능 |
| YAML 분량 | 2~3줄 | 8줄 이상 |
| 언제 쓰나 | 라벨 한두 개로 노드가 확정될 때 | 조건이 복합적이거나 선호 배치가 필요할 때 |

`nodeSelector`는 초기부터 있던 필드이고, 단순한 경우에 YAML이 훨씬 짧다. 조건이 하나뿐이면 `nodeSelector`를, 그 이상이면 Node Affinity를 쓰는 편이 적절하다.

<br>

## Node Affinity

`nodeSelector`의 확장 버전으로, 표현식 기반의 유연한 노드 선택이 가능하다. ([공식 문서](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/#node-affinity))

### requiredDuringSchedulingIgnoredDuringExecution

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
            - ap-northeast-2a   # 두 zone 중 하나면 통과
            - ap-northeast-2c
```

- `nodeSelectorTerms`는 **OR** 관계: 하나라도 만족하면 통과
- `matchExpressions` 내부는 **AND** 관계: 모든 조건을 만족해야 통과
- 지원 연산자: `In`, `NotIn`, `Exists`, `DoesNotExist`, `Gt`, `Lt`

### preferredDuringSchedulingIgnoredDuringExecution

조건을 만족하면 **선호**하지만, 만족하지 않아도 스케줄링 가능하다. Score 단계에서 평가되며, 조건을 만족하는 노드에 더 높은 점수를 부여한다.

```yaml
spec:
  affinity:
    nodeAffinity:
      preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 80              # 이 조건에 부합하면 80만큼 가산
        preference:
          matchExpressions:
          - key: node-type
            operator: In
            values:
            - high-memory
      - weight: 20              # 이 조건에 부합하면 20만큼 가산
        preference:
          matchExpressions:
          - key: disk-type
            operator: In
            values:
            - ssd
```

- `weight`는 1~100 범위이며, 조건을 만족하는 노드에 해당 가중치가 가산된다

여기서 `weight`와 [2편의 Score 플러그인 기본 가중치]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %}#기본-score-플러그인)를 혼동하기 쉽다. 둘은 곱해지는 관계다.

1. 파드에 적은 `weight`(위 예시의 80, 20)로 `NodeAffinity` 플러그인이 **자기 내부 점수**를 계산한다. 두 조건을 모두 만족하는 노드는 100, `high-memory`만 만족하면 80이 된다.
2. 플러그인 내부 점수를 NormalizeScore가 0~100으로 정규화한다.
3. 정규화된 점수에 **플러그인 가중치**(`NodeAffinity`는 기본 2)를 곱한다.
4. 다른 Score 플러그인의 가중 점수와 합산한다.

즉 파드의 `weight`는 "같은 플러그인 안에서 조건들 사이의 상대적 중요도"이고, 플러그인 가중치는 "다른 플러그인 대비 이 플러그인의 영향력"이다.

> **`IgnoredDuringExecution`의 의미**: 파드가 이미 노드에서 실행 중일 때 노드 라벨이 변경되어도 파드를 축출하지 않는다는 뜻이다. 스케줄링 시점에만 조건을 평가한다.

### 사례: DaemonSet의 NodeAffinity 위임

[1편 - DaemonSet의 수동 → 스케줄러 위임 전환]({% post_url 2025-11-05-Kubernetes-Scheduling-01 %}#사례-daemonset의-수동--스케줄러-위임-전환)에서 다룬 것처럼, DaemonSet은 v1.12부터 `kube-scheduler`에 스케줄링을 위임한다. DaemonSet Controller는 `spec.nodeName`을 직접 설정하지 않고, 파드 생성 시 `spec.affinity.nodeAffinity`에 `matchFields`를 사용하여 특정 노드를 지정한다.

```yaml
spec:
  affinity:
    nodeAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
        nodeSelectorTerms:
        - matchFields:
          - key: metadata.name
            operator: In
            values:
            - worker-1  # 이 노드에만 스케줄링
```

`kube-scheduler`가 이 NodeAffinity를 평가하여 해당 노드에 파드를 바인딩한다. 위에서 본 일반 Node Affinity가 [`matchExpressions`로 **노드 라벨**을 평가하는 것](#requiredduringschedulingignoredduringexecution)과 달리, DaemonSet은 `matchFields`로 **노드 객체의 필드**(`metadata.name`)를 직접 매칭한다.

`matchFields`로 노드 이름이 확정되면 `NodeAffinity` 플러그인은 [PreFilter 단계]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %}#prefilter)에서 그 노드만 후보로 반환한다. 전체 노드를 순회하지 않으므로 대규모 클러스터에서도 DaemonSet 파드의 스케줄링 비용이 낮게 유지된다.

> **참고**: DaemonSet Controller가 `kubernetes.io/hostname` 라벨 대신 `metadata.name` 필드를 사용하는 이유는, hostname과 node name이 항상 일치하지 않을 수 있기 때문이다. `matchFields`로 `metadata.name`을 직접 참조하여 확실하게 노드를 특정한다.

<br>

## Pod Affinity / Anti-Affinity

노드의 속성이 아니라, **해당 노드에서 이미 실행 중인 다른 파드**를 기준으로 배치를 제어한다. ([공식 문서](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/#inter-pod-affinity-and-anti-affinity))

### Pod Affinity

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
        topologyKey: kubernetes.io/hostname  # 같은 노드에 배치
```

위 예시는 `app=cache` 라벨을 가진 파드가 실행 중인 노드와 같은 `kubernetes.io/hostname`(즉, 같은 노드)에 배치한다.

### Pod Anti-Affinity

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
          topologyKey: topology.kubernetes.io/zone  # zone 단위로 분산
```

- **프레임워크 평가**: `InterPodAffinity` 플러그인이 Filter(`required`)와 Score(`preferred`) 단계에서 평가
- `topologyKey`는 노드 라벨의 키를 지정. 같은 키-값 쌍을 가진 노드들이 하나의 토폴로지 도메인을 형성

### 스케줄링 비용

Pod Affinity/Anti-Affinity는 다른 제어 설정보다 계산 비용이 크다. 노드의 라벨만 보면 되는 Node Affinity와 달리, **각 노드마다 그 노드(또는 토폴로지 도메인)에 이미 떠 있는 파드들을 순회하며 labelSelector와 대조**해야 하기 때문이다. 공식 문서도 이 점을 명시한다.

> Inter-pod affinity and anti-affinity require substantial amount of processing which can slow down scheduling in large clusters significantly. We do not recommend using them in clusters larger than several hundred nodes.

비용을 줄이는 방향은 `topologyKey`를 넓게 잡는 것이다. `kubernetes.io/hostname`은 노드 수만큼 도메인이 생기지만, `topology.kubernetes.io/zone`은 zone 수만큼만 생긴다. 도메인 수가 줄면 대조 횟수도 준다. 다만 이것은 **제약의 의미 자체를 바꾸는 것**(노드 단위 분산 → zone 단위 분산)이므로 성능만 보고 바꿀 수는 없다.

단순한 균등 분산이 목적이라면 [Topology Spread Constraints](#topology-spread-constraints)를 쓰는 편이 낫다. 아래 [선택 기준](#pod-anti-affinity와-topology-spread-선택-기준)에서 정리한다.

> 위 노드 수 기준은 공식 문서의 권고를 옮긴 것이고, 실제 임계값은 파드 수·라벨 카디널리티·`topologyKey`에 따라 달라진다. 이 글에서 측정해 검증한 범위는 아니다.

<br>

# 노드 측 거부와 토폴로지 분산

앞 절의 설정들이 파드가 요구하는 쪽이라면, 이 절의 Taints/Tolerations는 노드가 거부하는 쪽이다. 두 방향을 조합하면 "이 노드에는 이 파드만 들어올 수 있다"를 표현할 수 있다. Topology Spread Constraints는 방향이 아니라 분포를 제어하는 설정이지만, Pod Anti-Affinity와의 선택 기준을 함께 보는 편이 좋아 이 절에 둔다.

<br>

## Taints and Tolerations

Node Affinity가 "이 노드에 배치해 달라"는 **파드 측의 요청**이라면, Taints/Tolerations는 "이 파드는 받지 않겠다"는 **노드 측의 거부**다. ([공식 문서](https://kubernetes.io/docs/concepts/scheduling-eviction/taint-and-toleration/))

### Taint

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

### Toleration

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

**toleration은 허가일 뿐 요청이 아니다.** GPU 노드에 taint를 걸고 파드에 toleration만 달면, 그 파드는 GPU 노드에 갈 수 있게 되는 것이지 GPU 노드에 가게 되는 것이 아니다. 일반 노드에도 배치될 수 있다. 실무에서는 두 방향을 함께 쓴다.

```yaml
# GPU 노드에만 배치하고 싶은 학습 파드
spec:
  nodeSelector:
    accelerator: nvidia-a100     # 파드 측 요청: GPU 노드로 보내 달라
  tolerations:                   # 노드 측 거부 통과: GPU 노드의 taint를 허용
  - key: "nvidia.com/gpu"
    operator: "Exists"
    effect: "NoSchedule"
  containers:
  - name: trainer
    image: ml-trainer:latest
    resources:
      limits:
        nvidia.com/gpu: 2
```

GPU 노드에 taint를 거는 이유는 **일반 워크로드가 값비싼 GPU 노드의 CPU/Memory를 잠식하는 것을 막기 위해서**다. taint가 없으면 GPU를 요청하지 않는 파드도 GPU 노드에 배치될 수 있고, 그 노드의 CPU/Memory가 소진되면 정작 GPU 파드가 [`NodeResourcesFit`]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %}#filter)에서 탈락한다.

> GPU 파드가 GPU 노드에 뜨지 않을 때는 위 두 설정 외에 **노드가 GPU를 실제로 광고하고 있는지**도 확인해야 한다. `kubectl describe node <node>`의 `Allocatable`에 `nvidia.com/gpu`가 0이거나 아예 없으면 device plugin 쪽 문제이고, 스케줄링 설정을 고쳐도 해결되지 않는다. GPU가 extended resource로 노출되는 구조는 [NVIDIA GPU 동작 메커니즘]({% post_url 2024-07-23-Dev-Kubernetes-NVIDIA-GPU-Mechanism %}#extended-resource로서의-gpu)에서 다룬다.

### 프레임워크 평가

- `TaintToleration` 플러그인이 Filter(`NoSchedule`, `NoExecute`)와 Score(`PreferNoSchedule`, taint가 적은 노드 선호) 단계에서 평가
- Score 가중치는 기본 3으로, 다른 Score 플러그인보다 높다

### NoExecute와 tolerationSeconds

`NoExecute` taint는 스케줄링뿐만 아니라 이미 실행 중인 파드에도 영향을 준다. 파드에 `tolerationSeconds`를 설정하면, taint가 추가된 후 해당 시간이 지나면 축출된다.

```yaml
spec:
  tolerations:
  - key: "node.kubernetes.io/not-ready"
    operator: "Exists"
    effect: "NoExecute"
    tolerationSeconds: 300   # taint 부착 후 300초 버티다가 축출
```

노드 장애 시 자동으로 부여되는 taint가 이 메커니즘을 쓴다. 자동 부여되는 taint는 다음과 같다.

| Taint | 부여 시점 | Effect |
| --- | --- | --- |
| `node.kubernetes.io/not-ready` | 노드의 `Ready` condition이 `False`가 됐을 때 | `NoSchedule` / `NoExecute` |
| `node.kubernetes.io/unreachable` | 노드의 `Ready` condition이 `Unknown`이 됐을 때 (kubelet이 응답하지 않음) | `NoSchedule` / `NoExecute` |
| `node.kubernetes.io/unschedulable` | 노드에 `spec.unschedulable`이 설정됐을 때 (`kubectl cordon`) | `NoSchedule` |
| `node.kubernetes.io/disk-pressure` | 노드의 `DiskPressure` condition이 `True`가 됐을 때 | `NoSchedule` |
| `node.kubernetes.io/memory-pressure` | 노드의 `MemoryPressure` condition이 `True`가 됐을 때 | `NoSchedule` |
| `node.kubernetes.io/pid-pressure` | 노드의 `PIDPressure` condition이 `True`가 됐을 때 | `NoSchedule` |
| `node.kubernetes.io/network-unavailable` | 노드의 `NetworkUnavailable` condition이 `True`가 됐을 때 | `NoSchedule` |

위 표에서 뒤쪽 네 개는 **condition에서 파생되는 taint**다. 조건이 해소되면 taint도 자동으로 제거된다.

노드가 응답하지 않을 때 파드가 사라지기까지의 흐름은 다음과 같다.

```
kubelet 하트비트 중단
    ↓ (node-monitor-grace-period 경과)
노드 Ready condition → Unknown
    ↓
node.kubernetes.io/unreachable:NoExecute taint 부착
    ↓ (tolerationSeconds 경과)
해당 노드의 파드 축출
```

`tolerationSeconds`를 명시하지 않으면 API Server가 위 두 taint에 대해 기본값 300초를 자동으로 주입한다. 즉 노드가 죽었다고 판정된 뒤 약 5분이 더 지나야 파드가 축출된다. 이 값을 줄이면 장애 감지 후 복구가 빨라지지만, 일시적인 네트워크 단절에도 파드가 축출되므로 트레이드오프가 있다.

### cordon의 기술적 의미

위 표의 세 번째 taint가 `kubectl cordon`과 연결된다. cordon은 노드에 `spec.unschedulable: true`를 설정하는 명령이고, 이것이 **두 경로로** 스케줄링을 막는다.

| 경로 | 적용 주체 | 단계 |
| --- | --- | --- |
| `node.spec.unschedulable`을 직접 확인 | `NodeUnschedulable` 플러그인 | Filter |
| `node.kubernetes.io/unschedulable:NoSchedule` taint 자동 부착 | node lifecycle controller가 부착 → `TaintToleration` 플러그인이 평가 | Filter |

즉 cordon은 "스케줄러의 판단에서 노드를 아예 제외"하는 것이 아니라, **Filter 단계에서 두 플러그인이 각각 탈락시키는 것**이다. `NodeUnschedulable`이 반환하는 상태는 `UnschedulableAndUnresolvable`이며, 이는 "클러스터 상태가 바뀌지 않으면 재시도해도 소용없다"는 뜻이어서 파드가 [Unschedulable Queue]({% post_url 2025-11-05-Kubernetes-Scheduling-01 %}#스케줄러-큐)로 분류된다. cordon이 해제되는 노드 변경 이벤트가 와야 Active Queue로 돌아온다.

두 경로가 모두 Filter라는 점이 중요한 결과를 낳는다. **`spec.nodeName`을 직접 지정해 스케줄러를 우회하면 cordon은 무력화된다.** 이 동작과 활용·주의점은 [1편 - cordon된 노드에 nodeName을 지정하면]({% post_url 2025-11-05-Kubernetes-Scheduling-01 %}#cordon된-노드에-nodename을-지정하면)에서 다룬다.

<br>

### 노드 압박과 스케줄링

디스크·메모리가 부족해지는 노드 압박(node-pressure) 상황도 cordon과 같은 2단 구조로 스케줄링에 영향을 준다. 다만 여기서는 **축출과 스케줄링 차단이 서로 다른 주체가 수행하는 별개 동작**이라는 점을 구분해야 한다.

```
kubelet이 디스크 여유가 임계값 아래로 떨어진 것을 감지
    │
    ├─ [축출] kubelet이 직접 Pod을 축출한다
    │         BestEffort → Burstable → Guaranteed 순
    │         스케줄러는 관여하지 않는다
    │
    └─ [스케줄링 차단] kubelet이 노드의 DiskPressure condition을 True로 설정
              ↓
          node lifecycle controller가 condition을 보고
          node.kubernetes.io/disk-pressure:NoSchedule taint 부착
              ↓
          TaintToleration 플러그인이 Filter에서 그 노드를 탈락
```

왼쪽 가지가 **축출**이고 오른쪽 가지가 **스케줄링 차단**이다. 축출은 kubelet이 자기 노드의 Pod을 직접 종료하는 것이므로 `kube-scheduler`와 무관하다. 스케줄러가 관여하는 것은 오른쪽 가지뿐이고, 그 경로는 [cordon](#cordon의-기술적-의미)과 동일하다 — condition 또는 노드 스펙에서 파생된 `NoSchedule` taint를 Filter에서 평가하는 것이다.

이 구분이 실무에서 중요한 이유는, 두 동작이 겹치면 **빠져나오기 어려운 상태**가 만들어지기 때문이다.

1. 디스크가 임계값을 넘는다 → kubelet이 Pod을 축출한다
2. 동시에 `disk-pressure` taint가 붙어 그 노드가 Filter에서 탈락한다
3. 축출된 Pod을 ReplicaSet 등이 다시 만든다
4. 새 Pod도 같은 노드에 배치되지 못한다. 다른 노드에 여유가 없으면 Pending에 머문다
5. 모든 Pod의 우선순위가 같으면 선점으로 공간을 만들 수도 없다([2편 - 선점이 동작하는 조건]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %}#선점이-동작하는-조건))

이때 Pending Pod은 [Unschedulable Queue]({% post_url 2025-11-05-Kubernetes-Scheduling-01 %}#스케줄러-큐)에 들어간다. 복귀 조건은 "클러스터 이벤트"인데, 여기서 그 이벤트는 **디스크를 비워 `DiskPressure`가 해소되고 taint가 걷히는 노드 변경**이다. 즉 스케줄링 설정을 아무리 손봐도 풀리지 않고, 디스크를 확보해야 풀린다.

> **임계값은 배포본마다 다르다.** 업스트림 kubelet의 hard eviction 기본값은 `nodefs.available<10%`, `imagefs.available<15%`지만, 배포본이 이를 덮어쓰는 경우가 있다. 예를 들어 K3s는 `nodefs.available`과 `imagefs.available`을 모두 5%로 낮춰 둔다. 축출이 예상보다 이르거나 늦게 일어난다면 해당 배포본의 kubelet 설정을 확인해야 한다.

실제로 이 경로를 탄 사례는 [MinIO existingClaim 트러블슈팅]({% post_url 2026-02-24-Dev-Minio-Custom-PVC-Troubleshooting %}#같은-노드의-label-studio-pod가-남긴-증거)에 정리해 두었다. K3s 클러스터의 루트 파티션이 차면서 `BestEffort` Pod이 축출되고, 재생성된 Pod들이 13일간 Pending에 머물렀던 기록이다.

<br>

## Topology Spread Constraints

파드를 **토폴로지 도메인 간 균일하게 분산**하는 제약이다. ([공식 문서](https://kubernetes.io/docs/concepts/scheduling-eviction/topology-spread-constraints/))

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

- `maxSkew`: **대상 도메인의 매칭 파드 수와 전역 최솟값(global minimum) 사이의 최대 허용 차이.** 전역 최솟값은 적격 도메인 중 매칭 파드 수가 가장 적은 값이다
- `topologyKey`: 분산 기준이 되는 노드 라벨 키
- `whenUnsatisfiable`:
  - `DoNotSchedule`: 제약을 만족하지 못하면 스케줄링하지 않음 (Filter 동작)
  - `ScheduleAnyway`: 제약을 가능한 한 만족하도록 노력하되, 불가능하면 스케줄링 허용 (Score 동작)
- **프레임워크 평가**: `PodTopologySpread` 플러그인이 Filter(`DoNotSchedule`)와 Score(`ScheduleAnyway`) 단계에서 평가

`maxSkew`를 "도메인 쌍 간 차이"로 읽으면 안 된다. 기준은 항상 **전역 최솟값과의 차이**다. 예를 들어 zone A에 3개, zone B에 1개, zone C에 1개 파드가 있고 `maxSkew: 1`이면, 전역 최솟값은 1이므로 zone A는 이미 차이가 2로 위반 상태다. 새 파드는 B나 C에만 들어갈 수 있다.

### 함께 쓰이는 필드

위 네 필드만으로는 의도한 분산이 되지 않는 경우가 있어, 보조 필드들이 추가되었다.

| 필드 | 역할 |
| --- | --- |
| `minDomains` | 적격 도메인 수의 최솟값. 실제 도메인 수가 이보다 적으면 전역 최솟값을 0으로 취급해, 도메인이 채워지기 전에 한쪽으로 몰리는 것을 막는다 (v1.27 beta) |
| `matchLabelKeys` | `labelSelector`에 더해, 지정한 라벨 키의 **값이 같은 파드끼리만** 세도록 한다. 롤링 업데이트 시 구버전 파드와 신버전 파드를 같이 세는 문제를 막는 데 쓴다(`pod-template-hash` 등) (v1.27 beta) |
| `nodeAffinityPolicy` | 스큐 계산에서 파드의 nodeSelector/nodeAffinity를 반영할지 여부(`Honor` / `Ignore`) (v1.26 beta) |
| `nodeTaintsPolicy` | 스큐 계산에서 노드의 taint를 반영할지 여부(`Honor` / `Ignore`) (v1.26 beta) |

`matchLabelKeys`가 특히 실무에서 자주 필요하다. 없으면 Deployment를 업데이트할 때 구버전 파드가 이미 도메인을 채우고 있는 상태로 스큐를 계산하므로, 신버전 파드가 배치되지 못해 롤아웃이 멈출 수 있다.

### Pod Anti-Affinity와 Topology Spread 선택 기준

두 설정 모두 파드를 흩뿌리지만, 표현할 수 있는 것이 다르다.

| 기준 | Pod Anti-Affinity | Topology Spread |
| --- | --- | --- |
| 표현하는 것 | "같은 도메인에 두지 마라" (배타) | "도메인 간 개수 차이를 N 이하로" (균등) |
| 도메인당 허용 개수 | `required`면 실질적으로 1개 | `maxSkew`로 조절 |
| 레플리카가 도메인 수보다 많을 때 | `required`는 배치 불가로 막힘 | 균등하게 나눠 배치 |
| 계산 비용 | 높음 (파드 순회) | 상대적으로 낮음 |
| 언제 쓰나 | "이 두 파드는 절대 같은 노드에 두면 안 된다" | "3개 zone에 고르게 깔아라" |

레플리카 수가 도메인 수보다 많아질 수 있으면 Topology Spread가 맞고, 특정 파드 조합의 공존 자체를 금지해야 하면 Anti-Affinity가 맞다.

<br>

# 스케줄링 제어 설정 요약

각 설정이 스케줄링 프레임워크의 어떤 단계에서 어떤 플러그인에 의해 평가되는지 정리한다.

| 설정 | 플러그인 | Filter (required) | Score (preferred) |
| --- | --- | --- | --- |
| Scheduling Gate | SchedulingGates (PreEnqueue) | 큐 진입 차단 | - |
| nodeSelector | NodeAffinity | O | - |
| Node Affinity (required) | NodeAffinity | O | - |
| Node Affinity (preferred) | NodeAffinity | - | O |
| Pod Affinity (required) | InterPodAffinity | O | - |
| Pod Affinity (preferred) | InterPodAffinity | - | O |
| Topology Spread (DoNotSchedule) | PodTopologySpread | O | - |
| Topology Spread (ScheduleAnyway) | PodTopologySpread | - | O |
| Taint (NoSchedule/NoExecute) | TaintToleration | O | - |
| Taint (PreferNoSchedule) | TaintToleration | - | O |
| cordon (`spec.unschedulable`) | NodeUnschedulable + TaintToleration | O | - |
| 노드 압박 (`DiskPressure` 등 condition) | TaintToleration | O | - |

<br>

# 정리

이 글에서 다룬 핵심 내용을 정리한다.

1. **Scheduling Gate는 스케줄링 자체를 보류한다.** 파드가 `SchedulingGated` 상태로 큐에 진입하지 않으므로, 스케줄러 부하 없이 외부 조건이 충족될 때까지 대기할 수 있다. 게이트가 설정된 동안 스케줄링 조건을 좁히는 방향으로 변경할 수도 있다.
2. **제어 설정은 파드의 요청과 노드의 거부, 두 방향으로 나뉜다.** `nodeSelector`·Node Affinity·Pod Affinity가 전자이고 Taints/Tolerations가 후자다. toleration은 허가일 뿐 요청이 아니므로, 특정 노드에만 배치하려면 두 방향을 함께 써야 한다.
3. **nodeSelector와 Node Affinity는 같은 플러그인·같은 단계에서 평가된다.** 조건이 하나면 `nodeSelector`, 복합적이거나 선호 배치가 필요하면 Node Affinity를 쓴다. 파드에 적는 `weight`와 플러그인 기본 가중치는 곱해지는 관계다.
4. **Pod Affinity/Anti-Affinity는 계산 비용이 크다.** 노드마다 기존 파드를 순회해야 하므로, 공식 문서는 수백 노드 이상 클러스터에서 사용을 권하지 않는다. 단순 균등 분산이면 Topology Spread가 낫다.
5. **Topology Spread의 `maxSkew`는 전역 최솟값과의 차이다.** 도메인 쌍 간 차이가 아니다. 롤링 업데이트에서는 `matchLabelKeys`가 없으면 롤아웃이 멈출 수 있다.
6. **cordon은 Filter 단계의 두 플러그인으로 구현된다.** `NodeUnschedulable`이 `spec.unschedulable`을 보고, node lifecycle controller가 붙인 taint를 `TaintToleration`이 본다. 둘 다 Filter이므로 `spec.nodeName` 직접 지정으로 우회된다.
7. **`NoExecute`는 이미 실행 중인 파드에도 영향을 준다.** 노드 장애 시 자동 부여되는 taint와 `tolerationSeconds` 기본값 300초가 조합되어, 노드가 죽은 뒤 약 5분 후 파드가 축출된다.
8. **노드 압박은 축출과 스케줄링 차단이 별개 동작이다.** 축출은 kubelet이 직접 하고, 스케줄링 차단은 condition에서 파생된 `NoSchedule` taint를 Filter가 평가해 이뤄진다. 둘이 겹치면 축출 → 재생성 → 배치 실패가 반복되며, 디스크를 비워 taint가 걷혀야 풀린다.

[1편]({% post_url 2025-11-05-Kubernetes-Scheduling-01 %})과 [2편]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %})에서 다룬 스케줄러의 개념, 프로세스와 함께 이 글의 스케줄링 제어 설정을 이해하면, 파드가 왜 특정 노드에 배치되었는지(또는 배치되지 않았는지)를 체계적으로 파악할 수 있다. [4편]({% post_url 2025-11-05-Kubernetes-Scheduling-04 %})에서는 스케줄러 설정과 최적화(NodeResourcesFit 전략, GPU 단편화, 멀티 프로필 등)를 다룬다.

<br>

# 참고 링크

- [Assigning Pods to Nodes - Kubernetes 공식 문서](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/)
- [Pod Scheduling Readiness - Kubernetes 공식 문서](https://kubernetes.io/docs/concepts/scheduling-eviction/pod-scheduling-readiness/)
- [Pod Topology Spread Constraints - Kubernetes 공식 문서](https://kubernetes.io/docs/concepts/scheduling-eviction/topology-spread-constraints/)
- [Taints and Tolerations - Kubernetes 공식 문서](https://kubernetes.io/docs/concepts/scheduling-eviction/taint-and-toleration/)
- [Well-Known Labels, Annotations and Taints - Kubernetes 공식 문서](https://kubernetes.io/docs/reference/labels-annotations-taints/)
- [Safely Drain a Node - Kubernetes 공식 문서](https://kubernetes.io/docs/tasks/administer-cluster/safely-drain-node/)

<br>
