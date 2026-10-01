---
title:  "[Kubernetes] 쿠버네티스 스케줄링 - 5. Extension Point 심화와 PodGroup 스케줄링"
excerpt: "Extension Point의 결정권 분류, PreScore 역할, 기본 플러그인 심화, 스케줄링 실패 진단, PodGroup 스케줄링, 멀티 스케줄러 아키텍처를 알아보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - MLOps
  - Kubernetes
  - Scheduler
  - Scheduling
  - Scheduling Framework
  - Plugin
  - PodGroup
  - Volcano
  - Kueue
last_modified_at: 2026-10-01
---

<br>

# TL;DR

- Extension Point는 결정권에 따라 세 가지로 분류된다: **gate**(PreFilter — Pod reject 및 후보 노드 축소, Filter — 노드 탈락), **informational**(PreScore — 데이터 준비만), **ranking**(Score — 점수만 매김, 탈락시키지 않음).
- PreScore는 스케줄링 사이클당 1번 호출되어 비싼 계산을 `CycleState`에 캐시하고, Score는 (노드 수 x 플러그인 수)번 호출되어 캐시된 데이터로 점수를 산출한다. PreScore는 결정권이 없는 informational 단계다.
- 하나의 플러그인이 여러 extension point에 걸쳐 동작하며, 각 단계에서의 역할이 다르다. v1.32 기준 `NodeResourcesFit`은 PreFilter → Filter → PreScore → Score 네 곳, `VolumeBinding`은 여섯 곳에 관여한다.
- 파드가 Pending에 빠졌을 때는 Events의 `FailedScheduling` 메시지로 어느 플러그인에서 탈락했는지 좁히고, `scheduler_pending_pods` 메트릭의 `queue` 라벨로 어느 큐에 있는지 확인한다.
- v1.35에서 gang scheduling이 alpha로 도입되었고(KEP-4671), v1.36에서 PodGroup 단위 스케줄링 사이클과 `placementGenerate`/`placementScore` extension point가 추가되었다(KEP-5732). 두 기능 모두 alpha이고 feature gate가 필요하다.
- 별도 스케줄러 바이너리가 필요한 경우와 Profile만으로 충분한 경우를 구분해야 한다. 기본 플러그인 조합 변경은 Profile로, 기본 플러그인에 없는 로직(fair-share queue 등)은 별도 바이너리(Volcano)나 별도 컨트롤러(Kueue)가 필요하다.

<br>

# 들어가며

[4편]({% post_url 2025-11-05-Kubernetes-Scheduling-04 %})에서 `KubeSchedulerConfiguration`의 설정 계층 구조, 플러그인 설정 패턴, 스코어링 전략, 멀티 프로필을 다뤘다. 이번 글은 1~4편에서 한 줄로 지나간 내부 동작을 되짚어 심화하고, 시리즈 전체를 진단 절차로 묶는다.

1. **Extension Point 결정권 분류**: [2편의 동작 규칙 요약]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %}#extension-point별-동작-규칙-요약)을 "결정권"이라는 관점으로 재분류한다
2. **PreScore 역할**: [2편의 PreScore]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %}#prescore) 한 줄 설명을 호출 횟수와 캐시 관점으로 푼다
3. **기본 플러그인 해부**: [2편의 플러그인 매핑 표]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %}#기본-플러그인과-extension-point-매핑)와 [4편의 스코어링 전략]({% post_url 2025-11-05-Kubernetes-Scheduling-04 %}#noderesourcesfit-스코어링-전략)을 extension point별로 분해한다
4. **스케줄링 실패 진단**: [1편]({% post_url 2025-11-05-Kubernetes-Scheduling-01 %})이 "파드가 어느 큐에 있는지 확인한다"고 한 것을 실제 명령과 출력으로 채운다
5. **PodGroup-level Extension Points**: [4편의 GPU 단편화]({% post_url 2025-11-05-Kubernetes-Scheduling-04 %}#리소스-단편화-문제)가 개별 파드 문제라면, 여기서는 파드 그룹 단위의 문제를 다룬다
6. **멀티 스케줄러 심화**: [1편의 다중 스케줄러]({% post_url 2025-11-05-Kubernetes-Scheduling-01 %}#커스텀-스케줄러와-다중-스케줄러)와 [3편의 Scheduling Gate]({% post_url 2025-11-05-Kubernetes-Scheduling-03 %}#scheduling-gate)가 Volcano·Kueue에서 어떻게 조합되는지 본다

기준 버전은 앞 편들과 같은 v1.32이며, PodGroup 관련 절만 v1.35/v1.36 기준이다. 해당 절에서 따로 표기한다.

<br>

# 프레임워크 내부 심화

## Extension Point 결정권 분류

[2편]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %}#extension-point별-동작-규칙-요약)에서 각 extension point의 역할과 복수 플러그인 동작 규칙을 정리했다. 여기서는 "결정권(decision power)"이라는 관점으로 재분류한다. 이 분류를 이해하면 스케줄링 실패 원인을 좁힐 때 "어느 단계에서 탈락/거부가 가능한가"를 즉시 판단할 수 있다.

| Extension Point | 노드를 줄일 수 있나? | Pod reject 가능? | 성격 |
| --- | --- | --- | --- |
| **PreFilter** | O (후보 집합 축소) | O | **gate** — Pod 자체가 스케줄링 불가 판정, 또는 후보 노드 제한 |
| **Filter** | O (노드 탈락) | (간접적으로) | **gate** — 노드 탈락 |
| **PostFilter** | X | X (선점 시도) | **recovery** — 실패 경로에서 공간 확보 |
| **PreScore** | X | X (에러 시에만 중단) | **informational** — 데이터 준비만 |
| **Score** | X | X | **ranking** — 점수만 매김 |
| **Reserve** | X | O (실패 시 Unreserve) | **gate** — 리소스 예약 실패 시 중단 |
| **Permit** | X | O (deny 가능) | **gate** — 바인딩 승인/거부 |

핵심 구분은 다음과 같다.

- **Gate 성격** (PreFilter, Filter, Reserve, Permit): 스케줄링 결과에 직접 영향을 준다. Pod을 reject하거나 노드를 탈락시킬 수 있다.
- **Informational 성격** (PreScore): 결정권이 없다. 정상 동작에서 항상 성공해야 하며, Score에게 정보를 제공할 뿐이다. 에러를 반환하면 사이클이 중단되지만, 이는 "의미론적 결정"이 아니라 **내부 오류** 취급이다.
- **Ranking 성격** (Score): 노드를 탈락시키지도, Pod을 reject하지도 않는다. 순위만 매긴다.

PreFilter가 노드를 줄일 수 있다는 점을 짚어 둘 필요가 있다. PreFilter는 `PreFilterResult`를 반환해 **Filter가 평가할 후보 노드 집합 자체를 제한**할 수 있다. `NodeAffinity`는 `matchFields`로 노드 이름이 확정된 경우 그 노드만 반환하고, `NodeName`도 같은 방식이다. Filter처럼 노드를 하나씩 탈락시키는 것이 아니라 애초에 평가 대상을 좁히는 것이므로, 대규모 클러스터에서 비용 차이가 크다. [1편의 DaemonSet 스케줄러 위임]({% post_url 2025-11-05-Kubernetes-Scheduling-01 %}#사례-daemonset의-수동--스케줄러-위임-전환)이 이 경로를 탄다.

<br>

## PreScore 역할

[2편]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %}#prescore)에서 PreScore를 "Score 플러그인이 사용할 공유 상태를 생성하는 사전 처리 단계"라고 한 줄로 설명했다. 여기서는 왜 PreScore가 별도 단계로 존재하는지, 구체적으로 어떤 계산을 하는지를 상세히 살펴본다.

### PreScore가 존재하는 이유

| 특성 | PreScore | Score |
| --- | --- | --- |
| **호출 횟수** | 스케줄링 사이클당 **1번** | 스케줄링 사이클당 **노드 수 x 플러그인 수** |
| **역할** | 비싼 계산을 1번 하고 `CycleState`에 캐시 | 캐시된 데이터로 노드별 점수 산출 |
| **결정권** | 없음 | 없음 (ranking만) |

Score는 적합 노드가 1,000개이고 Score 플러그인이 5개라면 5,000번 호출된다. Pod 분포 계산이나 리소스 타입 파악 같은 비싼 연산을 Score 안에서 하면 매번 반복된다. PreScore에서 1번만 계산하고 `CycleState`에 저장하면 O(N) → O(1)로 줄어든다.

### PreFilter와의 비교

PreFilter도 "사전 처리" 성격이 있어 혼동될 수 있다. 핵심 차이는 **결정권**이다.

- **PreFilter**: "이 Pod은 아예 스케줄링할 수 없다"를 판단할 수 있고, 후보 노드 집합도 좁힐 수 있다 (예: PVC가 존재하지 않으면 reject)
- **PreScore**: 그런 판단이 없다. Filter를 통과한 feasible 노드들에 대해 **점수 매기는 준비만** 한다

### 대표 플러그인의 PreScore 동작

#### InterPodAffinity의 PreScore

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

분리한 이유는 명확하다. Score가 노드 1,000개에 대해 호출되는데, 매번 "전체 Pod 순회 → 분포 계산"을 반복하면 비효율적이다. PreScore에서 1번만 계산하면 된다. [3편에서 다룬 Pod Affinity의 계산 비용]({% post_url 2025-11-05-Kubernetes-Scheduling-03 %}#스케줄링-비용)이 큰 이유도 이 순회 때문이다.

#### NodeResourcesFit의 PreScore

- **PreScore에서 하는 일**: Pod이 요청하는 리소스 타입(CPU, Memory, GPU 등)을 파악하고, scoring 전략(LeastAllocated / MostAllocated / RequestedToCapacityRatio)에 맞는 가중치를 미리 계산해서 `CycleState`에 저장
- **Score에서 하는 일**: 노드별로 저장된 가중치를 꺼내서 점수 계산

#### TaintToleration의 PreScore

- **PreScore에서 하는 일**: Pod의 tolerations 목록을 미리 파싱/정리
- **Score에서 하는 일**: 각 노드의 taint와 비교해서 "toleration이 필요한 taint가 적을수록 높은 점수" 부여 (PreferNoSchedule taint 기반 soft preference)

<br>

## 기본 플러그인 해부

[2편]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %}#기본-플러그인과-extension-point-매핑)에서 기본 플러그인 목록과 extension point 매핑 표를 정리했다. 여기서는 주요 플러그인이 **각 extension point에서 구체적으로 무엇을 하는지** 분석한다.

### NodeResourcesFit

가장 많은 extension point에 관여하는 핵심 플러그인 중 하나다. v1.32 기준 네 곳에 등록된다.

| Extension Point | 역할 |
| --- | --- |
| **PreFilter** | Pod이 요청하는 리소스 타입 목록을 파악하여 `CycleState`에 저장. 이후 Filter에서 불필요한 리소스 체크를 건너뛰는 최적화에 사용 |
| **Filter** | 노드의 allocatable 리소스에서 이미 할당된 양을 빼고, Pod의 requests를 수용할 수 있는지 체크. 불가능하면 노드 탈락 |
| **PreScore** | scoring 전략(LeastAllocated/MostAllocated/RequestedToCapacityRatio)에 맞는 리소스별 가중치를 미리 계산 |
| **Score** | 전략에 따라 노드별 점수 산출. LeastAllocated는 여유 많은 노드, MostAllocated는 사용률 높은 노드에 높은 점수 |

Score 전략별 점수 공식과 계산 예시는 [4편 - NodeResourcesFit 스코어링 전략]({% post_url 2025-11-05-Kubernetes-Scheduling-04 %}#noderesourcesfit-스코어링-전략)에 있다.

v1.36 기준으로는 `placementScore` extension point에도 관여한다. PodGroup 스케줄링 시 placement 전체의 resource utilization을 계산하는 역할이며, [아래 PodGroup 절](#noderesourcesfit의-podgroup-모드)에서 다룬다.

### VolumeBinding

v1.32 기준 여섯 개 extension point를 관통하는 플러그인이다. PVC/PV 라이프사이클 전체를 스케줄링 과정에서 관리한다.

| Extension Point | 역할 |
| --- | --- |
| **PreFilter** | Pod이 참조하는 PVC 목록을 수집하고, 각 PVC의 바인딩 상태(bound/unbound)를 확인. PVC가 존재하지 않으면 Pod reject |
| **Filter** | 해당 노드에서 PV를 마운트할 수 있는지 확인. zone 제약, access mode, 노드 affinity 등을 체크 |
| **PreScore** | Score에서 쓸 상태를 준비. scorer가 비활성이면 여기서 `Skip`을 반환해 Score를 건너뛴다 |
| **Score** | 볼륨 용량 기반 스코어링. **feature gate가 꺼져 있으면 동작하지 않는다**(아래 참고) |
| **Reserve** | 선택된 노드에 대해 PV-PVC 바인딩을 예약. 다른 Pod이 같은 PV를 가져가지 못하도록 함 |
| **PreBind** | 실제로 PV를 프로비저닝하고 PVC에 바인딩. 네트워크 볼륨 생성 등 시간이 걸리는 작업 |

> **볼륨 용량 스코어링의 feature gate**: v1.32에서는 `VolumeCapacityPriority`(alpha, 기본 비활성화, v1.21 도입)가 이 scorer를 켠다. v1.33에서 `StorageCapacityScoring`(KEP-4049, alpha)으로 대체되었고 `VolumeCapacityPriority`는 deprecated되었다. 두 게이트는 **선호 방향이 다르다.** 구 `VolumeCapacityPriority`는 정적 PV 바인딩에서 요청 크기에 가장 잘 맞는(가장 작은) PV가 있는 노드를 선호했고, `StorageCapacityScoring`은 동적 프로비저닝에서 **여유 용량이 가장 많은** 노드를 선호하는 것이 기본이다(`shape` 설정으로 반대 방향도 가능하다).

### 기본 활성화 vs 기본 비활성화

v1.32 기준 [2편의 매핑 표]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %}#기본-플러그인과-extension-point-매핑)에 나온 18개 플러그인은 모두 기본 활성화되어 있다. 여기에 더해, feature gate로 켜지는 플러그인이 있다.

| 구분 | 플러그인 | 조건 |
| --- | --- | --- |
| **기본 활성화** | NodeResourcesFit, TaintToleration, NodeAffinity, InterPodAffinity, PodTopologySpread, VolumeBinding 등 18개 | 범용적으로 필요 |
| **feature gate 조건부** | DynamicResources | `DynamicResourceAllocation` 게이트 활성 시 추가 등록 |

클라우드 벤더 전용 볼륨 제한 플러그인(`EBSLimits`, `GCEPDLimits`, `AzureDiskLimits`, `CinderLimits`)은 과거에 기본 비활성화 플러그인으로 존재했으나, **v1.32에서 네 개 모두 제거**되었다. in-tree 볼륨 플러그인이 CSI로 마이그레이션되면서 역할을 잃었기 때문이다.

| 플러그인 | 대상 | 현재 상태 |
| --- | --- | --- |
| `NodeVolumeLimits` | CSI 전체 | **유지** — CSI 드라이버가 보고하는 노드당 볼륨 부착 한도를 확인한다 |
| `EBSLimits` | AWS | v1.32에서 제거 |
| `GCEPDLimits` | GCP | v1.32에서 제거 |
| `AzureDiskLimits` | Azure | v1.32에서 제거 |
| `CinderLimits` | OpenStack | v1.32에서 제거 |

v1.31 이하에서 이 이름들을 `KubeSchedulerConfiguration`에 명시적으로 활성화해 둔 클러스터는, v1.32로 업그레이드할 때 해당 설정을 제거해야 한다. 존재하지 않는 플러그인 이름이 남아 있으면 스케줄러가 기동에 실패한다([4편 - 설정 적용과 롤백]({% post_url 2025-11-05-Kubernetes-Scheduling-04 %}#설정-적용과-롤백)).

<br>

# 스케줄링 실패 진단

[1편]({% post_url 2025-11-05-Kubernetes-Scheduling-01 %})은 "파드가 Pending에 빠졌을 때 `spec.nodeName`이 비어 있는지 확인하고, 스케줄링 문제라면 어느 큐에 있는지를 좁혀 나간다"로 끝났다. 여기서는 그 절차를 실제 명령과 출력으로 채운다.

진단 순서는 다음과 같다.

```
1. 스케줄링 문제인가?        → spec.nodeName이 비어 있는지 확인
2. 어느 단계에서 탈락했나?    → Events의 FailedScheduling 메시지
3. 어느 큐에 있나?            → 파드 상태 신호 + 스케줄러 메트릭
4. 무엇을 바꿔야 하나?        → 탈락 플러그인에 대응하는 설정
```

첫 단계는 한 줄로 끝난다.

```shell
# 비어 있으면 스케줄링 대상, 값이 있으면 스케줄링은 이미 끝난 것
~$ kubectl get pod <pod> -o jsonpath='{.spec.nodeName}'
```

값이 있으면 스케줄링 문제가 아니다. 이미지 pull, init container, 볼륨 마운트 등을 봐야 한다.

<br>

## Events 메시지 읽기

`spec.nodeName`이 비어 있으면 Events를 본다.

```shell
~$ kubectl describe pod ml-training-7d4b8c-xk2p9
```

```
# 실행 결과 (Events 섹션만 발췌)
Events:
  Type     Reason            Age                From               Message
  ----     ------            ----               ----               -------
  Warning  FailedScheduling  3m21s              default-scheduler  0/10 nodes are available: 1 Insufficient nvidia.com/gpu, 3 node(s) had untolerated taint {nvidia.com/gpu: present}, 6 node(s) didn't match Pod's node affinity/selector. preemption: 0/10 nodes are available: 10 Preemption is not helpful for scheduling.
  Warning  FailedScheduling  18s (x4 over 2m9s)  default-scheduler  0/10 nodes are available: 1 Insufficient nvidia.com/gpu, 3 node(s) had untolerated taint {nvidia.com/gpu: present}, 6 node(s) didn't match Pod's node affinity/selector.
```

[1편에서 본 것처럼]({% post_url 2025-11-05-Kubernetes-Scheduling-01 %}#판단-기준-specnodename) `0/10`은 적합 노드 수 / 평가 노드 수이고, 그 뒤가 사유별 노드 수다. 위 출력은 노드 10개가 세 가지 이유로 전부 탈락했다는 뜻이다.

각 메시지 조각은 특정 Filter 플러그인이 반환한 것이다. 대응 관계를 정리하면 다음과 같다.

| 메시지 조각 | 플러그인 | 관련 설정 |
| --- | --- | --- |
| `Insufficient <resource>` | NodeResourcesFit | 파드의 `requests` 또는 [노드 용량]({% post_url 2025-11-05-Kubernetes-Scheduling-04 %}#현재-상태-확인하기) |
| `node(s) didn't match Pod's node affinity/selector` | NodeAffinity | [nodeSelector / Node Affinity]({% post_url 2025-11-05-Kubernetes-Scheduling-03 %}#node-affinity) |
| `node(s) had untolerated taint {k: v}` | TaintToleration | [Taints / Tolerations]({% post_url 2025-11-05-Kubernetes-Scheduling-03 %}#taints-and-tolerations) |
| `node(s) were unschedulable` | NodeUnschedulable | [cordon]({% post_url 2025-11-05-Kubernetes-Scheduling-03 %}#cordon의-기술적-의미) |
| `node(s) had untolerated taint {node.kubernetes.io/disk-pressure}` | TaintToleration | [노드 압박]({% post_url 2025-11-05-Kubernetes-Scheduling-03 %}#노드-압박과-스케줄링). 설정이 아니라 노드 상태 문제다 |
| `node(s) didn't match pod anti-affinity rules` | InterPodAffinity | [Pod Anti-Affinity]({% post_url 2025-11-05-Kubernetes-Scheduling-03 %}#pod-affinity--anti-affinity) |
| `node(s) didn't match pod topology spread constraints` | PodTopologySpread | [Topology Spread]({% post_url 2025-11-05-Kubernetes-Scheduling-03 %}#topology-spread-constraints) |
| `node(s) didn't have free ports for the requested pod ports` | NodePorts | 파드의 `hostPort` |
| `node(s) had volume node affinity conflict` | VolumeBinding | PV의 zone/노드 제약 |
| `node(s) exceed max volume count` | NodeVolumeLimits | CSI 드라이버의 노드당 볼륨 한도 |

위 예시를 이 표로 읽으면 처방이 나온다. GPU 노드 3대는 taint를 tolerate하지 못해서, 일반 노드 6대는 nodeSelector가 맞지 않아서 탈락했다. 즉 **파드에 toleration이 없다.** GPU 노드에 배치하려면 [3편에서 본 조합]({% post_url 2025-11-05-Kubernetes-Scheduling-03 %}#toleration)대로 nodeSelector와 toleration을 함께 넣어야 한다.

메시지 뒤에 붙는 `preemption: ... Preemption is not helpful for scheduling`은 PostFilter가 선점을 시도했지만 공간을 만들 수 없었다는 뜻이다. 선점으로 해결될 문제가 아니라는 신호다 — taint나 affinity 불일치는 낮은 우선순위 파드를 죽여도 해결되지 않기 때문이다.

파드가 많을 때는 실패 이벤트만 모아 볼 수 있다.

```shell
~$ kubectl get events -A --field-selector reason=FailedScheduling --sort-by=.lastTimestamp
```

<br>

## 축출된 파드와 스케줄링 실패 구분

진단 1단계(`spec.nodeName`이 비었는지)에서 걸러지지만, 헷갈리기 쉬운 경우가 하나 있다. **축출된 파드**다.

축출은 파드가 배치된 **뒤에** 일어나므로, 축출된 파드에는 `spec.nodeName`이 남아 있고 `PodScheduled` 조건도 `True`로 남아 있다. 1단계 판별에서 "스케줄링 문제가 아니다"로 나오는 것이 맞다. 그 파드는 이미 끝난 파드이고, 실제로 봐야 할 것은 **컨트롤러가 그 자리에 다시 만든 새 파드**다.

아래는 노드의 디스크가 차서 축출된 파드의 실제 출력이다.

```shell
~$ kubectl describe pod -n label-studio label-studio-ls-app-<hash>-mh74p
```

```
# 실행 결과 (발췌, 식별자는 익명화)
Node:             node-01/10.0.1.10
Priority:         0
Status:           Failed
Reason:           Evicted
Message:          The node was low on resource: ephemeral-storage.
                  Threshold quantity: 12439225938, available: 34765552Ki.
                  Container app was using 670040, request is 0, has larger consumption of ephemeral-storage.
Conditions:
  Type               Status
  DisruptionTarget   True
  PodScheduled       True
QoS Class:           BestEffort
Tolerations:         node.kubernetes.io/not-ready:NoExecute op=Exists for 300s
                     node.kubernetes.io/unreachable:NoExecute op=Exists for 300s
```

이 출력 하나에 스케줄링 판단에 쓰이는 정보가 여러 개 들어 있다.

| 필드 | 읽는 방법 |
| --- | --- |
| `Reason: Evicted` + `Node`가 채워져 있음 | 스케줄링은 성공했고, 그 뒤에 축출된 것이다. 스케줄링 실패와 혼동하면 안 된다 |
| `QoS Class: BestEffort` (`request is 0`) | 리소스 요청을 선언하지 않았다. kubelet의 노드 압박 축출은 BestEffort를 먼저 고른다 |
| `Priority: 0` | PriorityClass가 없다. 다른 파드도 모두 0이면 [선점]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %}#선점)으로 공간을 만들 수 없다 |
| `PodScheduled: True` | [1편]({% post_url 2025-11-05-Kubernetes-Scheduling-01 %}#statusconditions-podscheduled)에서 본 대로 결과 기록이다. 현재 실행 가능 여부를 뜻하지 않는다 |
| `Tolerations`의 `300s` | 직접 설정한 값이 아니라 API Server가 자동 주입한 기본값이다([3편]({% post_url 2025-11-05-Kubernetes-Scheduling-03 %}#noexecute와-tolerationseconds)) |

이 사례에서 실제 문제는 재생성된 파드들이었다. 노드에 `disk-pressure` taint가 붙어 Filter에서 탈락하고, 우선순위가 전부 같아 선점도 불가능해 Pending이 누적됐다. 전체 경위는 [MinIO existingClaim 트러블슈팅]({% post_url 2026-02-24-Dev-Minio-Custom-PVC-Troubleshooting %}#왜-재스케줄링이-안-됐나-추론)에 있다.

<br>

## 파드가 어느 큐에 있는지 판별

큐 이름은 파드 오브젝트에 직접 노출되지 않는다. 파드 쪽 신호로는 아래와 같이 **추정**할 수 있다.

| 관찰되는 신호 | 추정 큐 | 근거 |
| --- | --- | --- |
| `status.phase: Pending`, `PodScheduled` 조건이 `reason: SchedulingGated` | 큐 진입 전 (PreEnqueue에서 차단) | [Scheduling Gate]({% post_url 2025-11-05-Kubernetes-Scheduling-03 %}#scheduling-gate)가 남아 있다 |
| `status.nominatedNodeName`에 값이 있음 | 선점 성공 후 대기 | [선점]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %}#선점)이 이뤄졌고 victim 종료를 기다리는 중 |
| `FailedScheduling` 이벤트가 수초 간격으로 반복 | Backoff Queue 경유 | 백오프 타이머(1~10초)에 맞춰 재시도되고 있다 |
| `FailedScheduling` 이벤트가 한 번 찍히고 오래 조용함 | Unschedulable Queue | 클러스터 이벤트를 기다리는 중 |

이것은 어디까지나 추정이다. 확정하려면 스케줄러 메트릭을 봐야 한다.

```shell
# 큐별 pending 파드 수 (스케줄러의 metrics 엔드포인트)
~$ kubectl get --raw /metrics | grep '^scheduler_pending_pods'
```

```
# 실행 결과
scheduler_pending_pods{queue="active"} 0
scheduler_pending_pods{queue="backoff"} 0
scheduler_pending_pods{queue="gated"} 2
scheduler_pending_pods{queue="unschedulable"} 1
```

`scheduler_pending_pods`의 `queue` 라벨 네 값이 [1편의 큐 모델]({% post_url 2025-11-05-Kubernetes-Scheduling-01 %}#스케줄러-큐)과 그대로 대응한다.

| 라벨 값 | 의미 |
| --- | --- |
| `active` | Active Queue에 있는 파드 수 |
| `backoff` | Backoff Queue에 있는 파드 수 |
| `unschedulable` | 스케줄링을 시도했다가 실패해 Unschedulable Queue에 있는 파드 수 |
| `gated` | 게이트 때문에 스케줄링을 **시도조차 하지 않은** 파드 수 |

`gated`가 별도 라벨로 분리되어 있다는 점이 유용하다. Scheduling Gate로 막힌 파드와 스케줄링에 실패한 파드를 수치로 구분할 수 있다.

주의할 점은, 이 메트릭이 **클러스터 전체의 집계값**이라는 것이다. 특정 파드가 어느 큐에 있는지 직접 알려주지는 않는다. 위 표의 파드 쪽 신호와 함께 봐야 한다.

<br>

## 스케줄러 로그와 메트릭

사유별 노드 수만으로 부족하면 스케줄러 로그를 본다.

```shell
~$ kubectl logs -n kube-system kube-scheduler-<control-plane-node> --tail=50
```

기본 로그 레벨에서는 스케줄링 성공/실패 요약만 나온다. 플러그인별 판정까지 보려면 `--v` 값을 올려야 하는데, 이는 [스케줄러 설정 변경]({% post_url 2025-11-05-Kubernetes-Scheduling-04 %}#설정-적용과-롤백)에 해당하므로 운영 클러스터에서는 신중하게 접근해야 한다. 로그량이 크게 늘어난다.

시계열로 볼 때 유용한 메트릭도 있다.

| 메트릭 | 용도 |
| --- | --- |
| `scheduler_pending_pods{queue}` | 큐별 적체 추이. `unschedulable`이 계속 쌓이면 구조적 문제다 |
| `scheduler_schedule_attempts_total{result}` | `result`가 `scheduled` / `unschedulable` / `error`로 나뉜다. `error` 증가는 내부 오류 신호다 |
| `scheduler_pod_scheduling_attempts` | 파드 하나가 배치되기까지의 시도 횟수 분포 |
| `scheduler_queue_incoming_pods_total{queue,event}` | 어떤 이벤트로 어느 큐에 파드가 들어왔는지. [QueueingHint]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %}#enqueueextension과-queueinghint) 동작을 관찰할 수 있다 |

<br>

# PodGroup-level Extension Points

이 절은 **v1.35와 v1.36 기준**이다. 앞 절들의 기준 버전(v1.32)보다 뒤이고, 두 기능 모두 alpha 단계라 feature gate를 켜야 동작한다.

## 배경: Pod 단위에서 Workload 단위로

기존 스케줄링 프레임워크의 extension point는 모두 **Pod 단위**로 동작한다. 한 번에 하나의 Pod을 평가하고, 하나의 노드를 선택하고, 하나의 바인딩을 수행한다.

그러나 ML 학습 워크로드처럼 여러 Pod이 **동시에** 자원을 확보해야 하는 경우(gang scheduling), Pod 단위 스케줄링으로는 한계가 있다. 예를 들어 8-GPU Pod 4개가 동시에 확보되어야 학습을 시작할 수 있는데, Pod을 하나씩 스케줄링하면 일부만 배치되고 나머지는 자원 부족으로 Pending에 빠지는 교착 상태가 발생한다.

이는 [4편 - 리소스 단편화 문제]({% post_url 2025-11-05-Kubernetes-Scheduling-04 %}#리소스-단편화-문제)의 단편화가 파드 그룹 단위로 확대된 형태다. 4편의 bin packing 전략은 파드 하나가 필요한 GPU를 한 노드에서 확보하게 만들지만, "4개 파드가 동시에 확보되어야 한다"는 요구는 표현할 수 없다.

## 2계층 Extension Point 체계

v1.36 기준으로 스케줄링 프레임워크의 extension point는 2계층으로 구성된다.

1. **Pod-level extension points** (기존): QueueSort → PreFilter → Filter → Score → ... → Bind
2. **PodGroup-level extension points** (v1.36 추가): PlacementGenerate → (Pod-level 재활용) → PlacementScore

PodGroup-level이 Pod-level을 **대체하는 게 아니라 감싸는(wrapping) 구조**다. PodGroup 사이클 내부에서 기존 Pod-level Filter/Score를 그대로 재활용한다.

| Extension Point | 등장 시점 | 상태 | 역할 |
| --- | --- | --- | --- |
| `queueSort`, `filter`, `score`, `bind` 등 | K8s 초기~1.19+ | stable | Pod 단위 스케줄링 |
| `placementGenerate` | **v1.36** | **alpha** | PodGroup이 배치될 수 있는 노드 집합(placement) 후보를 생성 |
| `placementScore` | **v1.36** | **alpha** | placement 후보들에 점수를 매겨 최적 배치를 선택 |

두 extension point는 `KubeSchedulerConfiguration` v1의 `PlacementGenerate` / `PlacementScore` PluginSet으로 노출된다. 출처 KEP은 gang scheduling(KEP-4671)이 아니라 **KEP-5732 "Topology-aware workload scheduling"**이며, feature gate는 `TopologyAwareWorkloadScheduling`이다.

## 동작 흐름

Pod 단위 스케줄링이 사라지는 것은 아니다. Pod이 PodGroup에 속할 때만 PodGroup 스케줄링 사이클로 분기한다.

```
스케줄러가 큐에서 Pod을 꺼냄 (pop)
    │
    ├─ 그룹 소속 아님 → 기존 Pod 스케줄링 사이클 (그대로)
    │   PreFilter → Filter → Score → Reserve → Permit → Bind
    │
    └─ 그룹 소속 → PodGroup 스케줄링 사이클로 전환
        │
        ├─ 같은 PodGroup에 속한 다른 Pod들을 큐에서 모두 가져옴
        ├─ 클러스터 상태 스냅샷 1회 찍음 (그룹 전체에 일관된 상태)
        ├─ 그룹 전체에 대해 placement 탐색
        │   └─ PlacementGenerate → Pod-level Filter/Score → PlacementScore
        └─ 결과에 따라 atomic 결정
            ├─ 성공 (minCount 충족) → 전부 bind
            └─ 실패 → 전부 큐로 반환 (아무것도 bind 안 함)
```

여기서 `minCount`는 **그룹이 시작되기 위해 최소한 배치되어야 하는 Pod 수**다. Workload 오브젝트에 지정하며, 이 수를 채우지 못하면 아무것도 바인딩하지 않고 전부 큐로 돌려보낸다. 일부만 떠서 자원을 점유한 채 나머지를 기다리는 교착을 원천적으로 막는 것이 atomic 결정의 목적이다.

Pod이 어느 그룹에 속하는지를 가리키는 필드는 버전에 따라 다르다. v1.35에서는 `spec.workloadRef`였고, **v1.36에서 `spec.schedulingGroup`으로 교체**되었다.

트리거는 여전히 개별 Pod을 큐에서 꺼내는 것이다. 다만 그 Pod이 그룹 소속이면 이후에 타게 되는 사이클 자체가 달라진다.

## v1.35 vs v1.36 구현 차이

| 버전 | 방식 |
| --- | --- |
| **v1.35** (gang scheduling alpha, KEP-4671) | Pod을 **하나씩** 스케줄링하되, `PreEnqueue`와 `Permit`에 배리어를 두어 그룹 전체가 모일 때까지 진행을 막는다. 기존 Pod 단위 파이프라인을 그대로 재활용하는 방식 |
| **v1.36** (PodGroup scheduling cycle, KEP-5732) | **별도의 사이클**로 그룹 전체를 한 번에 평가한다. 스냅샷 1회, atomic 결정, `placementGenerate`/`placementScore` 도입 |

v1.35는 기존 파이프라인 위에 배리어를 얹어 그룹 동작을 구현한 것이고, v1.36에서 그룹 자체를 스케줄링 단위로 다루는 사이클이 생겼다. KEP-4671은 gang scheduling을 v1.37에 beta로 올리는 것을 목표로 하고 있으며, workload 단위 스케줄링 사이클의 beta 목표도 v1.37로 이동했다.

## NodeResourcesFit의 PodGroup 모드

`NodeResourcesFit`은 PodGroup 스케줄링 시 `placementScore` extension point에서도 동작하며, resource utilization을 **placement 전체 단위**로 계산한다. 이때 `MostAllocated` 방향으로 고정된다.

PodGroup은 여러 Pod을 하나의 placement(노드 집합)에 모아서 배치하는데, placement 내 노드의 사용률을 최대한 높여야 placement가 차지하는 노드 수가 줄고, 남는 노드를 다른 워크로드가 쓸 수 있기 때문이다. `LeastAllocated`(분산 배치)는 개별 Pod에는 적합하지만, 그룹 단위 배치에서는 [자원 단편화]({% post_url 2025-11-05-Kubernetes-Scheduling-04 %}#단편화란)를 일으킨다.

## Feature Gate 상태와 활성화

PodGroup 관련 기능은 모두 alpha 상태로, 사용하려면 feature gate를 수동으로 활성화해야 한다.

| Feature Gate | 도입 | 상태 | 역할 |
| --- | --- | --- | --- |
| `GangScheduling` | v1.35 | alpha | gang scheduling 플러그인 활성화 |
| `GenericWorkload` | v1.35 | alpha | Workload API 활성화 |
| `TopologyAwareWorkloadScheduling` | v1.36 | alpha | `placementGenerate` / `placementScore` extension point 활성화 |

GA가 되더라도 "모든 Pod이 PodGroup으로 스케줄링된다"는 것이 아니다. 그룹에 속하지 않은 Pod은 기존 Pod 단위 사이클을 그대로 탄다.

<br>

# 멀티 스케줄러 심화

[1편]({% post_url 2025-11-05-Kubernetes-Scheduling-01 %}#커스텀-스케줄러와-다중-스케줄러)에서 다중 스케줄러 운영의 기본 개념과 `schedulerName` 기반 라우팅을 다뤘다. 여기서는 내부 동작 관점에서 자세히 다룬다.

## Profile만으로 되는 경우 vs 별도 바이너리가 필요한 경우

```
"다른 plugin 조합을 쓰고 싶다"
  → Profile만 추가하면 됨 (바이너리 동일)

"기본 플러그인에 없는 로직이 필요하다"
  → 새 플러그인 코드 작성 + 바이너리에 컴파일 필요
  → Volcano: 별도 스케줄러 바이너리
  → Kueue: 스케줄러를 수정하지 않고, 별도 컨트롤러가 큐 진입 시점을 제어
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

같은 구성을 `pluginConfig`까지 포함해 쓴 예시는 [4편 - 워크로드 성격에 따른 프로필 분리]({% post_url 2025-11-05-Kubernetes-Scheduling-04 %}#워크로드-성격에-따른-프로필-분리)에 있다.

기본 플러그인으로 불가능한 기능은 다음과 같다.

| 기능 | kube-scheduler 기본 플러그인으로 가능? |
| --- | --- |
| Gang scheduling (Pod 그룹이 동시에 자원 확보되어야 스케줄링) | v1.35 alpha부터 네이티브 지원 시작 ([위 절](#podgroup-level-extension-points)) |
| Fair-share queue (팀별 자원 할당량 관리) | X |
| [Job-level preemption]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %}#선점의-한계) (개별 Pod이 아닌 Job 단위 preemption) | X |
| Borrowing/Lending (큐 간 자원 대여) | X |

이런 로직은 새로운 플러그인 코드를 Go로 작성해야 하고, 플러그인은 바이너리에 컴파일되어야 하므로 별도 빌드/배포가 필요하다. [2편의 PostFilter 절]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %}#postfilter)에서 본 out-of-tree 플러그인들도 같은 이유로 별도 바이너리가 필요하다.

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
│       └── Job은 suspend, Pod은 Scheduling Gate로 제어      │
│                                                          │
│  → kube-scheduler 바이너리를 수정하지 않음                   │
│  → 대신 Kueue가 "스케줄링 전 단계"를 제어                    │
└─────────────────────────────────────────────────────────┘
```

|  | Volcano | Kueue |
| --- | --- | --- |
| **kube-scheduler 변경** | 대체 또는 병행 (별도 스케줄러 바이너리) | 수정하지 않음 (기본 kube-scheduler 그대로) |
| **어떻게 동작** | 자체 스케줄링 로직 전체 구현 | admission 단계에서 "언제 스케줄링 큐에 넣을지" 제어 |
| **추가 바이너리** | volcano-scheduler + volcano-controller | kueue-controller만 |
| **Profile 사용** | 자체 profile 개념 | kube-scheduler의 기본 profile 활용 |
| **race condition** | 별도 프로세스라 자원 뷰 충돌 가능 | kube-scheduler가 유일한 스케줄러이므로 충돌 없음 |

Kueue가 파드를 붙잡아 두는 수단은 워크로드 종류에 따라 다르다.

| 워크로드 | 제어 수단 |
| --- | --- |
| batch/v1 Job 등 suspend를 지원하는 리소스 | webhook으로 `.spec.suspend`를 `true`로 두고, 자원이 확보되면 `false`로 바꾼다 |
| plain Pod (Pod 계열 integration) | [3편에서 다룬 Scheduling Gate]({% post_url 2025-11-05-Kubernetes-Scheduling-03 %}#scheduling-gate)(`kueue.x-k8s.io/admission`)를 주입하고, 자원이 확보되면 제거한다 |

어느 쪽이든 공통점은 **스케줄러 앞단에서 진입 시점만 제어한다**는 것이다. 큐 정책(fair-share, borrowing/lending 등)에 따라 언제 풀어 줄지를 Kueue가 판단하고, 실제 노드 선택은 기본 kube-scheduler가 한다. 스케줄러가 하나뿐이므로 자원 뷰 충돌이 설계 단계에서 발생하지 않는다.

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

만약 두 스케줄러가 같은 `schedulerName`을 가지면, 둘 다 같은 Pod을 스케줄링하려고 시도한다. API server의 optimistic concurrency로 하나만 성공하고 나머지는 실패한 뒤 retry한다. 먼저 쓴 쪽이 이기고 늦은 쪽은 `resourceVersion` 충돌로 거부되는 방식이다. 동작은 하지만 비효율적이고 결과를 예측하기 어렵다.

Volcano는 이를 의도적으로 피한다. 기본 `schedulerName`으로 `volcano`를 사용하고, VolcanoJob controller가 Pod을 생성할 때 `spec.schedulerName: volcano`를 자동으로 설정한다.

## default-scheduler 부재 시나리오

`default-scheduler`라는 이름의 profile이 클러스터에 없으면 어떻게 되나?

`spec.schedulerName`을 지정하지 않은 Pod은 kube-apiserver가 자동으로 `default-scheduler`로 설정한다([1편 - schedulerName 지정]({% post_url 2025-11-05-Kubernetes-Scheduling-01 %}#schedulername-지정)). 이 이름을 처리할 스케줄러가 없으면, 해당 Pod은 아무도 pick up하지 않으므로 **영구 Pending** 상태가 된다.

| 시나리오 | 결과 |
| --- | --- |
| kube-scheduler를 끄고 volcano만 운영 + **모든** Pod에 `schedulerName: volcano` 명시 | 문제 없음 |
| kube-scheduler를 끄고 volcano만 운영 + **일부** Pod이 schedulerName 미지정 | 해당 Pod 영구 Pending |
| kube-scheduler를 끄고 volcano만 운영 + **시스템 Pod** (coredns 등) | 시스템 Pod도 Pending → 클러스터 기능 장애 |

마지막 케이스는 영향 범위가 클러스터 전체로 넓어진다. `coredns`, `kube-proxy` 같은 시스템 컴포넌트도 기본적으로 `schedulerName`을 생략하기 때문에 `default-scheduler`를 기대한다. 이것이 실무에서 기본 kube-scheduler를 완전히 끄는 구성이 드문 이유이며, 대부분 병행 운영하는 이유다.

## 자원 뷰 충돌

[1편]({% post_url 2025-11-05-Kubernetes-Scheduling-01 %}#파드와-스케줄러의-매칭-경쟁은-없다)에서 다중 스케줄러 간 리소스 경쟁 문제를 언급했다. 구체적인 메커니즘은 다음과 같다.

| 비교 | Profile 여러 개 (하나의 스케줄러 안) | 스케줄러 여러 개 |
| --- | --- | --- |
| **프로세스** | 1개 | 2개 이상 |
| **Configuration** | 1개 | 각각 1개씩 |
| **바이너리** | 동일 (kube-scheduler) | 다를 수 있음 |
| **플러그인** | 같은 바이너리에 컴파일된 것만 사용 | 각 바이너리가 다른 플러그인 세트 가능 |
| **자원 뷰** | 하나의 프로세스라 일관된 상태 | 각자 독립적으로 API server를 watch → **race condition 가능** |

스케줄러가 2개면 같은 노드에 동시에 Pod을 배치하려다 충돌이 날 수 있다. 예: 둘 다 "이 노드에 GPU 4개 남아있네" → 동시에 bind → 실제로는 4개밖에 없는데 8개 배치 시도. K8s는 이를 optimistic concurrency(API server에서 bind 시 충돌 감지 → 실패한 쪽이 retry)로 처리하지만, 완벽하지는 않다.

## 실무 권장

- **가능하면 하나의 스케줄러 + 여러 Profile**로 두는 편이 적절하다. 하나의 프로세스 안에서 일관된 자원 뷰를 가지므로 race condition이 없다.
- **기본 플러그인에 없는 로직이 필요할 때만** 별도 스케줄러를 추가한다 (Volcano 등).
- Kueue는 아예 스케줄러를 추가하지 않고, 기본 스케줄러 앞에서 진입 시점만 제어하여 race condition 문제를 설계 단계에서 회피한다.

<br>

# 정리

이 글에서 다룬 핵심 내용을 정리한다.

1. **Extension Point는 결정권에 따라 gate/informational/ranking으로 분류된다.** PreFilter와 Filter는 gate(reject/탈락 가능), PreScore는 informational(데이터 준비만), Score는 ranking(점수만 매김)이다. PreFilter는 노드를 탈락시키는 것이 아니라 후보 집합 자체를 좁힐 수 있다는 점에서 Filter와 다르다.
2. **PreScore는 비용이 큰 계산을 1번만 수행하여 Score에 공유하는 캐시 레이어다.** Score가 (노드 수 x 플러그인 수)번 호출되므로, PreScore에서 미리 계산하면 O(N) → O(1)로 줄어든다. PreFilter와 달리 결정권은 없다.
3. **주요 플러그인은 여러 extension point에 걸쳐 동작하며, 각 단계에서의 역할이 다르다.** v1.32 기준 `NodeResourcesFit`은 4개, `VolumeBinding`은 6개 extension point에 관여한다. 클라우드 벤더 전용 볼륨 제한 플러그인 4개는 v1.32에서 제거되었다.
4. **진단은 Events → 메트릭 순서로 좁힌다.** `FailedScheduling` 메시지의 사유 조각이 어느 Filter 플러그인에서 나온 것인지 대응시키면 처방이 나오고, `scheduler_pending_pods`의 `queue` 라벨(`active`/`backoff`/`unschedulable`/`gated`)로 큐 적체를 확인한다.
5. **v1.35에서 gang scheduling이, v1.36에서 PodGroup 단위 스케줄링 사이클이 도입되었다.** 그룹에 속한 Pod은 별도 사이클로 분기하여 `minCount` 충족 여부에 따라 전부 bind 또는 전부 반환하는 atomic 결정을 받는다. 모두 alpha이고 feature gate가 필요하다.
6. **Profile만으로 되는 경우와 별도 바이너리가 필요한 경우를 구분해야 한다.** 기본 플러그인 조합 변경은 Profile로 충분하고, fair-share queue 같은 기본 플러그인에 없는 로직은 별도 바이너리(Volcano)나 컨트롤러(Kueue)가 필요하다. 실무에서는 가능하면 단일 스케줄러 + 여러 Profile을 권장하며, Kueue는 suspend와 Scheduling Gate로 race condition을 원천 회피하는 설계다.

스케줄링 시리즈 전체를 종합하면:

| 편 | 핵심 |
| --- | --- |
| [1편]({% post_url 2025-11-05-Kubernetes-Scheduling-01 %}) | 스케줄링 개념, 스케줄러, 판단 기준, 수동 스케줄링, DaemonSet, 큐 |
| [2편]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %}) | 스케줄링 프레임워크, Extension Point, 플러그인, 선점 |
| [3편]({% post_url 2025-11-05-Kubernetes-Scheduling-03 %}) | Scheduling Gate, nodeSelector, Affinity, Topology Spread, Taint/Toleration, cordon |
| [4편]({% post_url 2025-11-05-Kubernetes-Scheduling-04 %}) | 설정 계층 구조, 설정 적용과 롤백, NodeResourcesFit 전략, GPU 단편화, 멀티 프로필 |
| 5편 (이 글) | Extension Point 심화, PreScore 역할, 실패 진단, PodGroup 스케줄링, 멀티 스케줄러 아키텍처 |

<br>

# 참고 링크

- [Scheduling Framework - Kubernetes 공식 문서](https://kubernetes.io/docs/concepts/scheduling-eviction/scheduling-framework/)
- [Scheduler Configuration - Kubernetes 공식 문서](https://kubernetes.io/docs/reference/scheduling/config/)
- [Scheduler Metrics - Kubernetes 공식 문서](https://kubernetes.io/docs/reference/instrumentation/metrics/)
- [KEP-4671: Gang Scheduling](https://github.com/kubernetes/enhancements/tree/master/keps/sig-scheduling/4671-gang-scheduling)
- [KEP-5732: Topology-aware workload scheduling](https://github.com/kubernetes/enhancements/tree/master/keps/sig-scheduling/5732-topology-aware-workload-scheduling)
- [KEP-4049: Storage Capacity Scoring of Nodes for Dynamic Provisioning](https://github.com/kubernetes/enhancements/tree/master/keps/sig-storage/4049-storage-capacity-scoring-of-nodes-for-dynamic-provisioning)
- [Volcano - High Performance Batch System](https://volcano.sh/)
- [Kueue - Job Queueing](https://kueue.sigs.k8s.io/)
- [Kueue - Run Plain Pods](https://kueue.sigs.k8s.io/docs/tasks/run/plain_pods/)

<br>
