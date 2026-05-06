---
title:  "[Kubernetes] 쿠버네티스 스케줄링 - 5. Extension Point 심화와 PodGroup 스케줄링"
excerpt: "Extension Point의 결정권 분류, PreScore 역할, 기본 플러그인 심화, PodGroup 스케줄링, 멀티 스케줄러 아키텍처를 알아보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - Scheduler
  - Scheduling
  - Scheduling Framework
  - Plugin
  - PodGroup
  - Volcano
  - Kueue
---

<br>

# TL;DR

- Extension Point는 결정권에 따라 세 가지로 분류된다: **gate**(PreFilter — Pod reject, Filter — 노드 탈락), **informational**(PreScore — 데이터 준비만), **ranking**(Score — 점수만 매김, 탈락시키지 않음).
- PreScore는 스케줄링 사이클당 1번 호출되어 비싼 계산을 `CycleState`에 캐시하고, Score는 (노드 수 x 플러그인 수)번 호출되어 캐시된 데이터로 점수를 산출한다. PreScore는 결정권이 없는 informational 단계다.
- 하나의 플러그인이 여러 extension point에 걸쳐 동작하며, 각 단계에서의 역할이 다르다. `NodeResourcesFit`은 PreFilter(리소스 타입 파악) → Filter(충분 여부) → PreScore(전략 가중치 계산) → Score(전략별 점수) → placementScore(PodGroup용)로 5개 extension point에 관여한다.
- v1.35/1.36에서 PodGroup-level extension point(`placementGenerate`, `placementScore`)가 도입되었다. `workloadRef`가 있는 Pod은 PodGroup 스케줄링 사이클로 분기하여, 그룹 전체에 대해 atomic 결정(전부 bind 또는 전부 반환)을 수행한다.
- 별도 스케줄러 바이너리가 필요한 경우와 Profile만으로 충분한 경우를 구분해야 한다. 기본 플러그인 조합 변경은 Profile로, 기본 플러그인에 없는 로직(gang scheduling, fair-share queue 등)은 별도 바이너리(Volcano)나 별도 컨트롤러(Kueue)가 필요하다.

<br>

# 들어가며

[이전 글]({% post_url 2025-11-05-Kubernetes-Scheduling-04 %})에서 `KubeSchedulerConfiguration`의 설정 계층 구조, 플러그인 설정 패턴, 스코어링 전략, 멀티 프로필을 다뤘다. 이번 글에서는 스케줄링 프레임워크의 **내부 동작**을 자세히 다룬다.

1. **Extension Point 결정권 분류**: [2편]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %})에서 extension point를 "순서"와 "동작 규칙"으로 설명했다면, 여기서는 "결정권"이라는 관점으로 재분류한다.
2. **PreScore 역할 심화**: informational 단계인 PreScore가 구체적으로 어떤 일을 하는지, 대표 플러그인의 동작 예시를 통해 살펴본다.
3. **기본 플러그인 심화 해부**: 주요 플러그인이 여러 extension point에서 각각 무엇을 하는지 상세히 분석한다.
4. **PodGroup-level Extension Points**: v1.35/1.36에서 도입된 PodGroup 스케줄링 사이클과 `placementGenerate`, `placementScore` extension point를 다룬다.
5. **멀티 스케줄러 심화**: Profile만으로 되는 경우와 별도 바이너리가 필요한 경우의 구분, Volcano와 Kueue의 아키텍처 비교를 다룬다.

<br>

# Extension Point 결정권 분류

[2편]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %})에서 각 extension point의 역할과 복수 플러그인 동작 규칙을 정리했다. 여기서는 "결정권(decision power)"이라는 관점으로 extension point를 재분류한다. 이 분류를 이해하면 스케줄링 실패 원인을 좁힐 때 "어느 단계에서 탈락/거부가 가능한가"를 즉시 판단할 수 있다.

| Extension Point | 노드를 탈락시킬 수 있나? | Pod reject 가능? | 성격 |
| --- | --- | --- | --- |
| **PreFilter** | X | O (에러 시 사이클 중단) | **gate** — Pod 자체가 스케줄링 불가 판정 |
| **Filter** | O | (간접적으로) | **gate** — 노드 탈락 |
| **PostFilter** | X | X (선점 시도) | **recovery** — 실패 경로에서 공간 확보 |
| **PreScore** | X | X (에러 시에만 중단) | **informational** — 데이터 준비만 |
| **Score** | X | X | **ranking** — 점수만 매김 |
| **Reserve** | X | O (실패 시 Unreserve) | **gate** — 리소스 예약 실패 시 중단 |
| **Permit** | X | O (deny 가능) | **gate** — 바인딩 승인/거부 |

핵심 구분은 다음과 같다.

- **Gate 성격** (PreFilter, Filter, Reserve, Permit): 스케줄링 결과에 직접 영향을 준다. Pod을 reject하거나 노드를 탈락시킬 수 있다.
- **Informational 성격** (PreScore): 결정권이 없다. 정상 동작에서 항상 성공해야 하며, Score에게 정보를 제공할 뿐이다. 에러를 반환하면 사이클이 중단되지만, 이는 "의미론적 결정"이 아니라 **내부 오류** 취급이다.
- **Ranking 성격** (Score): 노드를 탈락시키지도, Pod을 reject하지도 않는다. 순위만 매긴다.

<br>

# PreScore 역할 심화

[2편]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %})에서 PreScore를 "Score 플러그인이 사용할 공유 상태를 생성하는 사전 처리 단계"라고 한 줄로 설명했다. 여기서는 왜 PreScore가 별도 단계로 존재하는지, 구체적으로 어떤 계산을 하는지를 상세히 살펴본다.

## PreScore가 존재하는 이유

| 특성 | PreScore | Score |
| --- | --- | --- |
| **호출 횟수** | 스케줄링 사이클당 **1번** | 스케줄링 사이클당 **노드 수 x 플러그인 수** |
| **역할** | 비싼 계산을 1번 하고 `CycleState`에 캐시 | 캐시된 데이터로 노드별 점수 산출 |
| **결정권** | 없음 | 없음 (ranking만) |

Score는 적합 노드가 1,000개이고 Score 플러그인이 5개라면 5,000번 호출된다. Pod 분포 계산이나 리소스 타입 파악 같은 비싼 연산을 Score 안에서 하면 매번 반복된다. PreScore에서 1번만 계산하고 `CycleState`에 저장하면 O(N) → O(1)로 줄어든다.

## PreFilter와의 비교

PreFilter도 "사전 처리" 성격이 있어 혼동될 수 있다. 핵심 차이는 **결정권**이다.

- **PreFilter**: "이 Pod은 아예 스케줄링할 수 없다"를 판단할 수 있다 (예: PVC가 존재하지 않으면 reject)
- **PreScore**: 그런 판단이 없다. Filter를 통과한 feasible 노드들에 대해 **점수 매기는 준비만** 한다

## 대표 플러그인의 PreScore 동작

### InterPodAffinity

가장 대표적인 PreScore 활용 사례다.

```yaml
# Pod spec에 아래가 설정된 경우:
podAffinity:
  preferredDuringSchedulingIgnoredDuringExecution:
  - weight: 100
    podAffinityTerm:
      topologyKey: "topology.kubernetes.io/zone"
      labelSelector:
        matchLabels:
          app: web
```

- **PreScore에서 하는 일**: 클러스터의 모든 기존 Pod을 순회하면서 `app: web` 라벨을 가진 Pod이 어떤 노드/zone에 분포해 있는지 미리 계산. 이 결과를 `CycleState`에 저장
- **Score에서 하는 일**: PreScore가 저장해 둔 분포 데이터를 꺼내서, 각 노드에 "web Pod이 많은 zone일수록 높은 점수" 부여

분리한 이유는 명확하다. Score가 노드 1,000개에 대해 호출되는데, 매번 "전체 Pod 순회 → 분포 계산"을 반복하면 비효율적이다. PreScore에서 1번만 계산하면 된다.

### NodeResourcesFit

- **PreScore에서 하는 일**: Pod이 요청하는 리소스 타입(CPU, Memory, GPU 등)을 파악하고, scoring 전략(LeastAllocated / MostAllocated / RequestedToCapacityRatio)에 맞는 가중치를 미리 계산해서 `CycleState`에 저장
- **Score에서 하는 일**: 노드별로 저장된 가중치를 꺼내서 점수 계산

### TaintToleration

- **PreScore에서 하는 일**: Pod의 tolerations 목록을 미리 파싱/정리
- **Score에서 하는 일**: 각 노드의 taint와 비교해서 "toleration이 필요한 taint가 적을수록 높은 점수" 부여 (PreferNoSchedule taint 기반 soft preference)

<br>

# 기본 플러그인 심화 해부

[2편]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %})에서 기본 플러그인 목록과 extension point 매핑 표를 정리했다. 여기서는 주요 플러그인이 **각 extension point에서 구체적으로 무엇을 하는지** 분석한다.

## NodeResourcesFit

가장 많은 extension point에 관여하는 핵심 플러그인이다.

| Extension Point | 역할 |
| --- | --- |
| **PreFilter** | Pod이 요청하는 리소스 타입 목록을 파악하여 `CycleState`에 저장. 이후 Filter에서 불필요한 리소스 체크를 건너뛰는 최적화에 사용 |
| **Filter** | 노드의 allocatable 리소스에서 이미 할당된 양을 빼고, Pod의 requests를 수용할 수 있는지 체크. 불가능하면 노드 탈락 |
| **PreScore** | scoring 전략(LeastAllocated/MostAllocated/RequestedToCapacityRatio)에 맞는 리소스별 가중치를 미리 계산 |
| **Score** | 전략에 따라 노드별 점수 산출. LeastAllocated는 여유 많은 노드, MostAllocated는 사용률 높은 노드에 높은 점수 |
| **placementScore** | PodGroup 스케줄링 시 placement 전체의 resource utilization을 계산. MostAllocated 방향으로 동작 |

Score 전략에 따른 점수 계산:

- **LeastAllocated**: `(allocatable - requested) / allocatable * MaxScore` — 여유가 많을수록 높은 점수
- **MostAllocated**: `requested / allocatable * MaxScore` — 사용률이 높을수록 높은 점수
- **RequestedToCapacityRatio**: shape 파라미터로 정의한 사용률-점수 곡선에 따라 계산

## VolumeBinding

5개 extension point를 관통하는 플러그인이다. PVC/PV 라이프사이클 전체를 스케줄링 과정에서 관리한다.

| Extension Point | 역할 |
| --- | --- |
| **PreFilter** | Pod이 참조하는 PVC 목록을 수집하고, 각 PVC의 바인딩 상태(bound/unbound)를 확인. PVC가 존재하지 않으면 Pod reject |
| **Filter** | 해당 노드에서 PV를 마운트할 수 있는지 확인. zone 제약, access mode, 노드 affinity 등을 체크 |
| **Reserve** | 선택된 노드에 대해 PV-PVC 바인딩을 예약. 다른 Pod이 같은 PV를 가져가지 못하도록 함 |
| **PreBind** | 실제로 PV를 프로비저닝하고 PVC에 바인딩. 네트워크 볼륨 생성 등 시간이 걸리는 작업 |
| **Score** | `StorageCapacityScoring` feature 활성 시, 요청된 볼륨 크기에 가장 적합한(가장 작은) PV가 있는 노드 선호 |

## 기본 활성화 vs 기본 비활성화

대부분의 플러그인은 기본 활성화되어 있지만, 일부는 수동으로 활성화해야 한다.

| 구분 | 플러그인 | 이유 |
| --- | --- | --- |
| **기본 활성화** | NodeResourcesFit, TaintToleration, NodeAffinity, InterPodAffinity, PodTopologySpread, VolumeBinding 등 | 범용적으로 필요 |
| **기본 비활성화** | CinderLimits | OpenStack 전용. 사용하는 환경에서만 활성화 |

클라우드 전용 볼륨 제한 플러그인(`EBSLimits`, `GCEPDLimits`, `AzureDiskLimits`)은 기본 활성화되어 있으나, 해당 클라우드 CSI 드라이버가 없는 환경에서는 실질적으로 동작하지 않는다(체크할 대상이 없으므로 항상 통과).

| 플러그인 | 대상 | 체크 항목 |
| --- | --- | --- |
| `EBSLimits` | AWS | 노드당 EBS 볼륨 부착 개수 제한 |
| `GCEPDLimits` | GCP | 노드당 Persistent Disk 부착 개수 제한 |
| `AzureDiskLimits` | Azure | 노드당 Azure Disk 부착 개수 제한 |
| `CinderLimits` | OpenStack | 노드당 Cinder 볼륨 부착 개수 제한 (**기본 비활성화**) |

<br>

# PodGroup-level Extension Points

## 배경: Pod 단위에서 Workload 단위로

기존 스케줄링 프레임워크의 extension point(QueueSort → PreFilter → Filter → Score → ... → Bind)는 모두 **Pod 단위**로 동작한다. 한 번에 하나의 Pod을 평가하고, 하나의 노드를 선택하고, 하나의 바인딩을 수행한다.

그러나 ML 학습 워크로드처럼 여러 Pod이 **동시에** 자원을 확보해야 하는 경우(gang scheduling), Pod 단위 스케줄링으로는 한계가 있다. 예를 들어 8-GPU Pod 4개가 동시에 확보되어야 학습을 시작할 수 있는데, Pod을 하나씩 스케줄링하면 일부만 배치되고 나머지는 자원 부족으로 Pending에 빠지는 교착 상태가 발생한다.

v1.35에서 이 문제를 해결하기 위한 PodGroup 스케줄링이 도입되었고, v1.36에서 별도의 스케줄링 사이클로 개선되었다.

## 2계층 Extension Point 체계

v1.36 기준으로 스케줄링 프레임워크의 extension point는 2계층으로 구성된다.

1. **Pod-level extension points** (기존): QueueSort → PreFilter → Filter → Score → ... → Bind
2. **PodGroup-level extension points** (v1.35/1.36 추가): PlacementGenerate → (Pod-level 재활용) → PlacementScore

PodGroup-level이 Pod-level을 **대체하는 게 아니라 감싸는(wrapping) 구조**다. PodGroup 사이클 내부에서 기존 Pod-level Filter/Score를 그대로 재활용한다.

| Extension Point | 등장 시점 | 상태 | 역할 |
| --- | --- | --- | --- |
| `queueSort`, `filter`, `score`, `bind` 등 | K8s 초기~1.19+ | stable | Pod 단위 스케줄링 |
| `placementGenerate` | **v1.36** | **alpha** | PodGroup이 배치될 수 있는 노드 집합(placement) 후보를 생성 |
| `placementScore` | **v1.36** | **alpha** | placement 후보들에 점수를 매겨 최적 배치를 선택 |

## 동작 흐름

Pod 단위 스케줄링이 사라지는 것은 아니다. Pod에 `workloadRef`가 있을 때만 PodGroup 스케줄링 사이클로 분기한다.

```
스케줄러가 큐에서 Pod을 꺼냄 (pop)
    │
    ├─ workloadRef 없음 → 기존 Pod 스케줄링 사이클 (그대로)
    │   PreFilter → Filter → Score → Reserve → Permit → Bind
    │
    └─ workloadRef 있음 → PodGroup 스케줄링 사이클로 전환
        │
        ├─ 같은 PodGroup에 속한 다른 Pod들을 큐에서 모두 가져옴
        ├─ 클러스터 상태 스냅샷 1회 찍음 (그룹 전체에 일관된 상태)
        ├─ 그룹 전체에 대해 placement 탐색
        │   └─ PlacementGenerate → Pod-level Filter/Score → PlacementScore
        └─ 결과에 따라 atomic 결정
            ├─ 성공 (minCount 충족) → 전부 bind
            └─ 실패 → 전부 큐로 반환 (아무것도 bind 안 함)
```

트리거는 여전히 개별 Pod을 큐에서 꺼내는 것이다. 다만 그 Pod이 PodGroup 소속이면 이후에 타게 되는 사이클 자체가 달라진다.

## v1.35 vs v1.36 구현 차이

| 버전 | 방식 |
| --- | --- |
| **v1.35** (gang scheduling 첫 구현) | Pod을 **하나씩** 스케줄링하되, Permit gate에서 **hold** → 그룹 전체가 모이면 한꺼번에 release. 기존 사이클을 재활용하는 방식 |
| **v1.36** (PodGroup scheduling cycle) | **아예 별도의 사이클**로 그룹 전체를 한 번에 평가. 스냅샷 1회, atomic 결정. PlacementGenerate/Score 도입 |

v1.35는 "기존 파이프라인 위에 Permit 플러그인으로 gang을 흉내 낸 것"이고, v1.36부터가 "진짜 그룹 단위 스케줄링 사이클"이다.

## NodeResourcesFit의 PodGroup 모드

`NodeResourcesFit`은 PodGroup 스케줄링 시 `placementScore` extension point에서 동작하며, resource utilization을 **placement 전체 단위**로 계산한다. 이때 기본적으로 **MostAllocated 방향**으로 동작한다.

PodGroup은 여러 Pod을 하나의 placement(노드 집합)에 모아서 배치하는데, 노드들을 빈틈없이 꽉 채워야 placement 내 노드 수를 최소화하고, 나머지 클러스터 자원을 다른 워크로드에 남겨줄 수 있기 때문이다. LeastAllocated(분산 배치)는 개별 Pod에는 적합하지만, 그룹 단위 배치에서는 자원 파편화를 일으킨다.

## Feature Gate 상태와 활성화

PodGroup 스케줄링은 현재 alpha 상태로, 사용하려면 feature gate를 수동으로 활성화해야 한다.

| 상태 | 의미 |
| --- | --- |
| **alpha** (현재, v1.36) | feature gate 수동 활성화 필요. Workload API도 명시적으로 켜야 함 |
| **beta** (추후) | 기본 활성화. 하지만 `workloadRef` 없는 Pod은 기존 사이클 그대로 |
| **GA** (추후) | feature gate 제거, 항상 활성화. 여전히 `workloadRef` 없으면 기존 사이클 |

GA가 되더라도 "모든 Pod이 PodGroup으로 스케줄링된다"는 것이 아니다. `workloadRef`가 없는 Pod은 기존 사이클을 그대로 탄다.

<br>

# 멀티 스케줄러 심화

[1편]({% post_url 2025-11-05-Kubernetes-Scheduling-01 %})에서 다중 스케줄러 운영의 기본 개념과 `schedulerName` 기반 라우팅을 다뤘다. 여기서는 내부 동작 관점에서 자세히 다룬다.

## Profile만으로 되는 경우 vs 별도 바이너리가 필요한 경우

```
"다른 plugin 조합을 쓰고 싶다"
  → Profile만 추가하면 됨 (바이너리 동일)

"기본 플러그인에 없는 로직이 필요하다"
  → 새 플러그인 코드 작성 + 바이너리에 컴파일 필요
  → Volcano: 별도 스케줄러 바이너리
  → Kueue: 스케줄러는 안 건드리고, 별도 컨트롤러로 "입구"를 제어
```

Profile만으로 가능한 경우는 kube-scheduler 바이너리에 **이미 컴파일되어 있는 플러그인들**의 조합만 바꾸는 것이다.

```yaml
# Profile로 충분한 예: 기본 플러그인의 weight만 변경
profiles:
  - schedulerName: gpu-scheduler
    plugins:
      score:
        enabled:
          - name: NodeResourcesFit
            weight: 5    # GPU 노드는 bin-packing 강하게
```

기본 플러그인으로 불가능한 기능:

| 기능 | kube-scheduler 기본 플러그인으로 가능? |
| --- | --- |
| Gang scheduling (Pod 그룹이 동시에 자원 확보되어야 스케줄링) | X (v1.36 alpha에서 네이티브 지원 시작) |
| Fair-share queue (팀별 자원 할당량 관리) | X |
| Job-level preemption (개별 Pod이 아닌 Job 단위 preemption) | X |
| Borrowing/Lending (큐 간 자원 대여) | X |

이런 로직은 새로운 플러그인 코드를 Go로 작성해야 하고, 플러그인은 바이너리에 컴파일되어야 하므로 별도 빌드/배포가 필요하다.

## Volcano vs Kueue: 접근 방식의 차이

```
┌─────────────────────────────────────────────────────────┐
│ Volcano                                                  │
│                                                          │
│  kube-scheduler (기본)  +  volcano-scheduler (별도 바이너리) │
│       ↑ 일반 Pod            ↑ Volcano Job의 Pod           │
│                                                          │
│  → 완전히 별도의 스케줄러 바이너리를 추가 배포                  │
│  → kube-scheduler를 대체하거나 병행 운영                     │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ Kueue                                                    │
│                                                          │
│  kube-scheduler (기본, 그대로 사용)                         │
│       ↑                                                  │
│  Kueue controller (별도 프로세스)                           │
│       └── "이 Pod을 언제 스케줄링 대상으로 풀어줄지" 관리       │
│       └── SchedulingGate를 걸고 해제하는 방식               │
│                                                          │
│  → kube-scheduler 바이너리는 안 건드림                      │
│  → 대신 Kueue가 "스케줄링 전 단계"를 제어                    │
└─────────────────────────────────────────────────────────┘
```

|  | Volcano | Kueue |
| --- | --- | --- |
| **kube-scheduler 변경** | 대체 또는 병행 (별도 스케줄러 바이너리) | 안 건드림 (기본 kube-scheduler 그대로) |
| **어떻게 동작** | 자체 스케줄링 로직 전체 구현 | SchedulingGate + Admission으로 "언제 스케줄링 큐에 넣을지" 제어 |
| **추가 바이너리** | volcano-scheduler + volcano-controller | kueue-controller만 |
| **Profile 사용** | 자체 profile 개념 | kube-scheduler의 기본 profile 활용 |
| **race condition** | 별도 프로세스라 자원 뷰 충돌 가능 | kube-scheduler가 유일한 스케줄러이므로 충돌 없음 |

Kueue는 [3편]({% post_url 2025-11-05-Kubernetes-Scheduling-03 %})에서 다룬 Scheduling Gate를 핵심 메커니즘으로 활용한다. Pod에 SchedulingGate를 걸어 스케줄러 큐에 진입하지 못하게 한 뒤, 큐 정책(fair-share, borrowing/lending 등)에 따라 gate를 해제하여 "언제 스케줄링 대상이 되는지"를 제어한다. 이 방식은 race condition 문제를 설계 단계에서 회피한다.

## schedulerName 고유성 메커니즘

하나의 스케줄러 **내부**에서 profile 간 `schedulerName` 중복은 스케줄러 시작 시 validation error로 **강제 거부**된다.

그러나 **서로 다른 스케줄러 프로세스 간**에는 이름 중복을 검증하는 중앙 메커니즘이 없다. 각 스케줄러가 독립적으로 API server를 watch하기 때문이다.

```
클러스터 전역의 schedulerName 공간:
├── "default-scheduler"  ← kube-scheduler가 소유
├── "volcano"            ← volcano-scheduler가 소유
├── "gpu-scheduler"      ← kube-scheduler의 두 번째 profile
└── ...

규칙: 서로 다른 스케줄러 프로세스 간에 이름이 겹치지 않도록
      운영자가 관리해야 함 (K8s가 enforce하지 않음)
```

만약 두 스케줄러가 같은 `schedulerName`을 가지면, 둘 다 같은 Pod을 스케줄링하려고 시도한다. API server의 optimistic concurrency(bind 시 resourceVersion 충돌 감지)로 하나만 성공하고 나머지는 실패 → retry하지만, 비효율적이고 예측 불가능하다.

Volcano는 이를 의도적으로 피한다. 기본 `schedulerName`으로 `volcano`를 사용하고, VolcanoJob controller가 Pod을 생성할 때 `spec.schedulerName: volcano`를 자동으로 설정한다.

## default-scheduler 부재 시나리오

`default-scheduler`라는 이름의 profile이 클러스터에 없으면 어떻게 되나?

`spec.schedulerName`을 지정하지 않은 Pod은 kube-apiserver가 자동으로 `default-scheduler`로 설정한다. 이 이름을 처리할 스케줄러가 없으면, 해당 Pod은 아무도 pick up하지 않으므로 **영구 Pending** 상태가 된다.

| 시나리오 | 결과 |
| --- | --- |
| kube-scheduler를 끄고 volcano만 운영 + **모든** Pod에 `schedulerName: volcano` 명시 | 문제 없음 |
| kube-scheduler를 끄고 volcano만 운영 + **일부** Pod이 schedulerName 미지정 | 해당 Pod 영구 Pending |
| kube-scheduler를 끄고 volcano만 운영 + **시스템 Pod** (coredns 등) | 시스템 Pod도 Pending → 클러스터 기능 장애 |

마지막 케이스가 특히 위험하다. `coredns`, `kube-proxy` 같은 시스템 컴포넌트도 기본적으로 `schedulerName`을 생략하기 때문에 `default-scheduler`를 기대한다. 이것이 실무에서 기본 kube-scheduler를 완전히 끄는 것이 매우 드문 구성인 이유이며, 대부분 병행 운영하는 이유다.

## 자원 뷰 충돌

[1편]({% post_url 2025-11-05-Kubernetes-Scheduling-01 %})에서 다중 스케줄러 간 리소스 경쟁 문제를 언급했다. 구체적인 메커니즘은 다음과 같다.

| 비교 | Profile 여러 개 (하나의 스케줄러 안) | 스케줄러 여러 개 |
| --- | --- | --- |
| **프로세스** | 1개 | 2개 이상 |
| **Configuration** | 1개 | 각각 1개씩 |
| **바이너리** | 동일 (kube-scheduler) | 다를 수 있음 |
| **플러그인** | 같은 바이너리에 컴파일된 것만 사용 | 각 바이너리가 다른 플러그인 세트 가능 |
| **자원 뷰** | 하나의 프로세스라 일관된 상태 | 각자 독립적으로 API server를 watch → **race condition 가능** |

스케줄러가 2개면 같은 노드에 동시에 Pod을 배치하려다 충돌이 날 수 있다. 예: 둘 다 "이 노드에 GPU 4개 남아있네" → 동시에 bind → 실제로는 4개밖에 없는데 8개 배치 시도. K8s는 이를 optimistic concurrency(API server에서 bind 시 충돌 감지 → 실패한 쪽이 retry)로 처리하지만, 완벽하지는 않다.

## 실무 권장

- **가능하면 하나의 스케줄러 + 여러 Profile**이 깔끔하다. 하나의 프로세스 안에서 일관된 자원 뷰를 가지므로 race condition이 없다.
- **기본 플러그인에 없는 로직이 필요할 때만** 별도 스케줄러를 추가한다 (Volcano 등).
- Kueue는 아예 스케줄러를 추가하지 않고, 기본 스케줄러 앞에서 SchedulingGate만 걸어서 race condition 문제를 설계 단계에서 회피한다.

<br>

# 정리

이 글에서 다룬 핵심 내용을 정리한다.

1. **Extension Point는 결정권에 따라 gate/informational/ranking으로 분류된다.** PreFilter와 Filter는 gate(reject/탈락 가능), PreScore는 informational(데이터 준비만), Score는 ranking(점수만 매김)이다. 스케줄링 실패 원인을 좁힐 때 "어느 단계에서 탈락이 가능한가"를 판단하는 기준이 된다.
2. **PreScore는 비용이 큰 계산을 1번만 수행하여 Score에 공유하는 캐시 레이어다.** Score가 (노드 수 x 플러그인 수)번 호출되므로, PreScore에서 미리 계산하면 O(N) → O(1)로 줄어든다. PreFilter와 달리 결정권은 없다.
3. **주요 플러그인은 여러 extension point에 걸쳐 동작하며, 각 단계에서의 역할이 다르다.** `NodeResourcesFit`은 5개 extension point, `VolumeBinding`도 5개 extension point에 관여한다. 각 단계에서 무엇을 하는지 이해하면 스케줄링 동작을 정확히 예측할 수 있다.
4. **v1.35/1.36에서 PodGroup-level extension point가 도입되었다.** `workloadRef`가 있는 Pod은 별도의 PodGroup 스케줄링 사이클로 분기하여, 그룹 전체에 대해 atomic 결정을 수행한다. v1.35는 Permit gate 방식, v1.36는 별도 사이클(`placementGenerate`/`placementScore`) 방식이다.
5. **Profile만으로 되는 경우와 별도 바이너리가 필요한 경우를 구분해야 한다.** 기본 플러그인 조합 변경은 Profile로 충분하고, gang scheduling이나 fair-share queue 같은 기본 플러그인에 없는 로직은 별도 바이너리(Volcano)나 컨트롤러(Kueue)가 필요하다. 실무에서는 가능하면 단일 스케줄러 + 여러 Profile을 권장하며, Kueue는 SchedulingGate로 race condition을 원천 회피하는 설계다.

스케줄링 시리즈 전체를 종합하면:

| 편 | 핵심 |
| --- | --- |
| [1편]({% post_url 2025-11-05-Kubernetes-Scheduling-01 %}) | 스케줄링 개념, 스케줄러, 판단 기준, 수동 스케줄링, DaemonSet, 큐 |
| [2편]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %}) | 스케줄링 프레임워크, Extension Point, 플러그인, 선점 |
| [3편]({% post_url 2025-11-05-Kubernetes-Scheduling-03 %}) | Scheduling Gate, nodeSelector, Affinity, Topology Spread, Taint/Toleration |
| [4편]({% post_url 2025-11-05-Kubernetes-Scheduling-04 %}) | 설정 계층 구조, 플러그인 설정 패턴, NodeResourcesFit 전략, GPU 단편화, 멀티 프로필 |
| 5편 (이 글) | Extension Point 심화, PreScore 역할, PodGroup 스케줄링, 멀티 스케줄러 아키텍처 |

<br>

# 참고 링크

- [Scheduling Framework - Kubernetes 공식 문서](https://kubernetes.io/docs/concepts/scheduling-eviction/scheduling-framework/)
- [Scheduler Configuration - Kubernetes 공식 문서](https://kubernetes.io/docs/reference/scheduling/config/)
- [KEP-4639: OG Scheduling For Elastic Quota (PodGroup)](https://github.com/kubernetes/enhancements/tree/master/keps/sig-scheduling/4639-og-scheduling-for-elastic-quota)
- [Kubernetes Blog - scalable-scheduling-by-gang (v1.35)](https://kubernetes.io/blog/2025/04/18/scalable-scheduling-by-gang/)
- [Volcano - High Performance Batch System](https://volcano.sh/)
- [Kueue - Job Queueing](https://kueue.sigs.k8s.io/)
