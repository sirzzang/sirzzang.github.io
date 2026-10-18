---
title:  "[Kubernetes] 쿠버네티스 스케줄링 - 6. Extension Point 심화와 스케줄링 실패 진단"
excerpt: "Extension Point의 결정권 분류, PreScore 역할, 기본 플러그인 심화, 스케줄링 실패 진단과 수동 배치의 제약을 알아보자."
permalink: /kubernetes/Kubernetes-Scheduling-06/
categories:
  - k8s-scheduling
  - mlops-resource
  - k8s-operations
  - concept
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - Scheduler
  - Scheduling
  - Scheduling Framework
  - Plugin
  - Troubleshooting
last_modified_at: 2026-10-15
---

<br>

# TL;DR

- extension point는 결정권에 따라 나뉜다: **gate**(PreFilter — 파드 reject 및 후보 노드 축소, Filter — 노드 탈락, Reserve·Permit — 예약 실패·승인 거부), **recovery**(PostFilter — 실패 경로에서 공간 확보), **informational**(PreScore — 데이터 준비만), **ranking**(Score — 점수만 매김, 탈락시키지 않음).
- PreScore는 스케줄링 사이클당 1번 호출되어 비싼 계산을 `CycleState`에 캐시하고, Score는 (노드 수 × 플러그인 수)번 호출되어 캐시된 데이터로 점수를 산출한다. PreScore는 결정권이 없는 informational 단계다.
- 하나의 플러그인이 여러 extension point에 걸쳐 동작하며, 각 단계에서의 역할이 다르다. v1.32 기준 `NodeResourcesFit`은 PreFilter → Filter → PreScore → Score 네 곳, `VolumeBinding`은 여섯 곳에 관여한다.
- 파드가 Pending에 빠졌을 때는 Events의 `FailedScheduling` 메시지로 어느 플러그인에서 탈락했는지 좁히고, `scheduler_pending_pods` 메트릭의 `queue` 라벨로 어느 큐에 있는지 확인한다.
- 스케줄러를 우회한 수동 배치는 kubelet이 리소스·노드 선택 조건·`NoExecute` taint만 다시 검사한다. cordon, `NoSchedule` taint, 파드 간 배치 규칙은 아무도 막지 않으며, 이미 배치된 파드를 옮기는 방법은 삭제 후 재생성뿐이다.

<br>

# 들어가며

[5편]({% post_url 2025-11-05-Kubernetes-Scheduling-05 %})에서 파드 단위 스케줄링의 한계와 gang scheduling을 다뤘다. 이번 글은 1·2·4편에서 한 줄로 지나간 `kube-scheduler` 내부 동작을 되짚어 심화하고, 시리즈 전체를 진단 절차로 묶는다.

1. **Extension Point 결정권 분류**: [2편의 동작 규칙 요약]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %}#extension-point별-동작-규칙-요약)을 "결정권"이라는 관점으로 재분류한다
2. **PreScore 역할**: [2편의 PreScore]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %}#prescore) 한 줄 설명을 호출 횟수와 캐시 관점으로 푼다
3. **기본 플러그인 해부**: [2편의 플러그인 매핑 표]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %}#기본-플러그인과-extension-point-매핑)와 [4편의 스코어링 전략]({% post_url 2025-11-05-Kubernetes-Scheduling-04 %}#noderesourcesfit-스코어링-전략)을 extension point별로 분해한다
4. **스케줄링 실패 진단과 수동 배치의 제약**: [1편]({% post_url 2025-11-05-Kubernetes-Scheduling-01 %}) 정리에서 6편으로 넘긴 큐 판별 절차를 실제 명령과 출력으로 채우고, 스케줄러를 우회한 파드가 무엇에 막히는지 정리한다

기준 버전은 시리즈 기준인 v1.32다. 그 이후의 변화는 등장 지점에 버전을 따로 표기한다.

<br>

# Scheduling Framework 내부 심화

## Extension Point 결정권 분류

[2편]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %}#extension-point별-동작-규칙-요약)에서 각 extension point의 역할과 복수 플러그인 동작 규칙을 정리했다. 여기서는 "결정권(decision power)"이라는 관점으로 재분류한다. 이 분류를 이해하면 스케줄링 실패 원인을 좁힐 때 "어느 단계에서 탈락/거부가 가능한가"를 즉시 판단할 수 있다.

| Extension Point | 노드를 줄일 수 있나? | 파드 reject 가능? | 성격 |
| --- | --- | --- | --- |
| **PreFilter** | O (후보 집합 축소) | O | **gate** — 파드 자체가 스케줄링 불가 판정, 또는 후보 노드 제한 |
| **Filter** | O (노드 탈락) | (간접적으로) | **gate** — 노드 탈락 |
| **PostFilter** | X | X (선점 시도) | **recovery** — 실패 경로에서 공간 확보 |
| **PreScore** | X | X (에러 시에만 중단) | **informational** — 데이터 준비만 |
| **Score** | X | X | **ranking** — 점수만 매김 |
| **Reserve** | X | O (실패 시 Unreserve) | **gate** — 리소스 예약 실패 시 중단 |
| **Permit** | X | O (deny 가능) | **gate** — 바인딩 승인/거부 |

핵심 구분은 다음과 같다.

- **Gate 성격** (PreFilter, Filter, Reserve, Permit): 스케줄링 결과에 직접 영향을 준다. 파드를 reject하거나 노드를 탈락시킬 수 있다.
- **Informational 성격** (PreScore): 결정권이 없다. 정상 동작에서 항상 성공해야 하며, Score에게 정보를 제공할 뿐이다. 에러를 반환하면 사이클이 중단되지만, 이는 "의미론적 결정"이 아니라 **내부 오류** 취급이다.
- **Ranking 성격** (Score): 노드를 탈락시키지도, 파드를 reject하지도 않는다. 순위만 매긴다.

PreFilter는 노드를 줄일 수도 있다. `PreFilterResult`를 반환해 **Filter가 평가할 후보 노드 집합 자체를 제한**하는 방식이며, v1.32 기준 `NodeAffinity`가 여기 해당한다 — `matchFields`로 노드 이름이 확정되면 그 노드만 반환한다. Filter처럼 노드를 하나씩 탈락시키는 것이 아니라 애초에 평가 대상을 좁히는 것이므로, 대규모 클러스터에서 비용 차이가 크다. [1편의 DaemonSet 스케줄러 위임]({% post_url 2025-11-05-Kubernetes-Scheduling-01 %}#사례-daemonset의-수동--스케줄러-위임-전환)이 이 경로를 탄다.

<br>

## PreScore 역할

[2편]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %}#prescore)에서 PreScore를 "Score 플러그인이 사용할 공유 상태를 생성하는 사전 처리 단계"라고 한 줄로 설명했다. 여기서는 왜 PreScore가 별도 단계로 존재하는지, 구체적으로 어떤 계산을 하는지를 상세히 살펴본다.

### PreScore가 존재하는 이유

| 특성 | PreScore | Score |
| --- | --- | --- |
| **호출 횟수** | 스케줄링 사이클당 **1번** | 스케줄링 사이클당 **노드 수 × 플러그인 수** |
| **역할** | 비싼 계산을 1번 하고 `CycleState`에 캐시 | 캐시된 데이터로 노드별 점수 산출 |
| **결정권** | 없음 | 없음 (ranking만) |

Score는 적합 노드가 1,000개이고 Score 플러그인이 5개라면 5,000번 호출된다. 파드 분포 계산이나 리소스 타입 파악 같은 비싼 연산을 Score 안에서 하면 매번 반복된다. PreScore에서 1번만 계산하고 `CycleState`에 저장하면 O(N) → O(1)로 줄어든다.

### PreFilter와의 비교

PreFilter도 "사전 처리" 성격이 있어 혼동될 수 있다. 핵심 차이는 **결정권**이다.

- **PreFilter**: "이 파드는 아예 스케줄링할 수 없다"를 판단할 수 있고, 후보 노드 집합도 좁힐 수 있다 (예: PVC가 존재하지 않으면 reject)
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

- **PreScore에서 하는 일**: 클러스터의 모든 기존 파드를 순회하면서 `app: web` 라벨을 가진 Pod이 어떤 노드/zone에 분포해 있는지 미리 계산. 이 결과를 `CycleState`에 저장
- **Score에서 하는 일**: PreScore가 저장해 둔 분포 데이터를 꺼내서, 각 노드에 "web 파드가 많은 zone일수록 높은 점수" 부여

분리한 이유는 명확하다. Score가 노드 1,000개에 대해 호출되는데, 매번 "전체 파드 순회 → 분포 계산"을 반복하면 비효율적이다. PreScore에서 1번만 계산하면 된다. [3편에서 다룬 Pod Affinity의 계산 비용]({% post_url 2025-11-05-Kubernetes-Scheduling-03 %}#스케줄링-비용)이 큰 이유도 이 순회 때문이다.

#### NodeResourcesFit의 PreScore

- **PreScore에서 하는 일**: `scoringStrategy.resources`에 적힌 리소스별로 파드가 요청하는 양을 계산해 `CycleState`에 저장한다. 리소스별 가중치는 설정값을 그대로 쓴다
- **Score에서 하는 일**: 노드별로 저장된 가중치를 꺼내서 점수 계산

#### TaintToleration의 PreScore

- **PreScore에서 하는 일**: 파드의 tolerations 목록을 미리 파싱/정리
- **Score에서 하는 일**: 각 노드에서 파드가 tolerate하지 못하는 `PreferNoSchedule` taint의 수를 세어, 적을수록 높은 점수를 준다(soft preference). tolerate한 taint나 `NoSchedule`·`NoExecute` taint는 점수에 영향이 없다

<br>

## 기본 플러그인 해부

[2편]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %}#기본-플러그인과-extension-point-매핑)에서 기본 플러그인 목록과 extension point 매핑 표를 정리했다. 여기서는 주요 플러그인이 **각 extension point에서 구체적으로 무엇을 하는지** 분석한다.

### NodeResourcesFit

가장 많은 extension point에 관여하는 핵심 플러그인 중 하나다. v1.32 기준 네 곳에 등록된다.

| Extension Point | 역할 |
| --- | --- |
| **PreFilter** | 파드가 요청하는 리소스 타입 목록을 파악하여 `CycleState`에 저장. 이후 Filter에서 불필요한 리소스 체크를 건너뛰는 최적화에 사용 |
| **Filter** | 노드의 allocatable 리소스에서 이미 할당된 양을 빼고, 파드의 requests를 수용할 수 있는지 체크. 불가능하면 노드 탈락 |
| **PreScore** | `scoringStrategy.resources`에 적힌 리소스별로 파드의 요청량을 계산해 저장(가중치는 설정값을 그대로 씀) |
| **Score** | 전략에 따라 노드별 점수 산출. LeastAllocated는 여유 많은 노드, MostAllocated는 사용률 높은 노드에 높은 점수 |

Score 전략별 점수 공식과 계산 예시는 [4편 - NodeResourcesFit 스코어링 전략]({% post_url 2025-11-05-Kubernetes-Scheduling-04 %}#noderesourcesfit-스코어링-전략)에 있다.

v1.36 기준으로는 `placementScore` extension point에도 관여한다. PodGroup 스케줄링 시 placement 전체의 resource utilization을 계산하는 역할이며, [5편 - NodeResourcesFit의 PodGroup 모드]({% post_url 2025-11-05-Kubernetes-Scheduling-05 %}#noderesourcesfit의-podgroup-모드)에서 다룬다.

### VolumeBinding

v1.32 기준 여섯 개 extension point를 관통하는 플러그인이다. PVC/PV 라이프사이클 전체를 스케줄링 과정에서 관리한다.

| Extension Point | 역할 |
| --- | --- |
| **PreFilter** | 파드가 참조하는 PVC 목록을 수집하고, 각 PVC의 바인딩 상태(bound/unbound)를 확인. PVC가 존재하지 않으면 파드 reject |
| **Filter** | 해당 노드에서 PV를 마운트할 수 있는지 확인. zone 제약, access mode, 노드 affinity 등을 체크 |
| **PreScore** | Score에서 쓸 상태를 준비. scorer가 비활성이면 여기서 `Skip`을 반환해 Score를 건너뛴다 |
| **Score** | 볼륨 용량 기반 스코어링. **feature gate가 꺼져 있으면 동작하지 않는다**(아래 참고) |
| **Reserve** | 선택된 노드에 대해 PV-PVC 바인딩을 예약. 다른 파드가 같은 PV를 가져가지 못하도록 함 |
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
1. 스케줄링 문제인가?            → spec.nodeName이 비어 있는지 확인
2. 어느 단계에서 탈락했고          → Events의 FailedScheduling 메시지에서
   무엇을 바꿔야 하나?              탈락 플러그인을 찾고 대응 설정으로 연결
3. 축출된 파드와 혼동하고 있지 않나? → describe pod의 Reason / Node 확인
4. 어느 큐에 있나?                → 파드 상태 신호 + 스케줄러 메트릭
5. 더 파고들어야 하나?             → 스케줄러 로그와 메트릭
6. 스케줄러를 우회한 파드인가?      → 수동 배치의 제약 확인
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
  Warning  FailedScheduling  3m21s              default-scheduler  0/10 nodes are available: 1 Insufficient nvidia.com/gpu, 3 node(s) had untolerated taint {nvidia.com/gpu: present}, 6 node(s) didn't match Pod's node affinity/selector. preemption: 0/10 nodes are available: 1 No preemption victims found for incoming pod, 9 Preemption is not helpful for scheduling.
  Warning  FailedScheduling  18s (x4 over 2m9s)  default-scheduler  0/10 nodes are available: 1 Insufficient nvidia.com/gpu, 3 node(s) had untolerated taint {nvidia.com/gpu: present}, 6 node(s) didn't match Pod's node affinity/selector. preemption: 0/10 nodes are available: 1 No preemption victims found for incoming pod, 9 Preemption is not helpful for scheduling.
```

[1편에서 본 것처럼]({% post_url 2025-11-05-Kubernetes-Scheduling-01 %}#판단-기준-specnodename) `0/10`의 앞 0은 고정값이고(이 메시지는 적합 노드가 하나도 없을 때만 만들어진다) 뒤 10은 스케줄러가 보는 전체 노드 수이며, 그 뒤가 사유별 노드 수다. 위 출력은 노드 10개가 세 가지 이유로 전부 탈락했다는 뜻이다.

각 메시지 조각은 특정 Filter 플러그인이 반환한 것이다. 노드마다 Filter 플러그인은 설정 순서대로 실행되고 처음 실패한 플러그인에서 멈추므로, 집계에는 노드당 **첫 탈락 사유 하나**만 나온다(v1.32 기본 순서는 NodeUnschedulable → NodeName → TaintToleration → NodeAffinity → NodePorts → NodeResourcesFit → 볼륨 계열 → PodTopologySpread → InterPodAffinity). 대응 관계를 정리하면 다음과 같다.

| 메시지 조각 | 플러그인 | 관련 설정 |
| --- | --- | --- |
| `Insufficient <resource>` | NodeResourcesFit | 파드의 `requests` 또는 [노드 용량]({% post_url 2025-11-05-Kubernetes-Scheduling-04 %}#현재-상태-확인하기) |
| `node(s) didn't match Pod's node affinity/selector` | NodeAffinity | [nodeSelector / Node Affinity]({% post_url 2025-11-05-Kubernetes-Scheduling-03 %}#node-affinity) |
| `node(s) had untolerated taint {k: v}` | TaintToleration | [Taints / Tolerations]({% post_url 2025-11-05-Kubernetes-Scheduling-03 %}#taints-and-tolerations) |
| `node(s) were unschedulable` | NodeUnschedulable | [cordon]({% post_url 2025-11-05-Kubernetes-Scheduling-03 %}#cordon의-기술적-의미) |
| `node(s) had untolerated taint {node.kubernetes.io/disk-pressure}` | TaintToleration | [노드 압박]({% post_url 2025-11-05-Kubernetes-Scheduling-03 %}#노드-압박과-스케줄링). 설정이 아니라 노드 상태 문제다 |
| `node(s) didn't match pod anti-affinity rules` | InterPodAffinity | [Pod Anti-Affinity]({% post_url 2025-11-05-Kubernetes-Scheduling-03 %}#pod-affinity--anti-affinity) |
| `node(s) didn't match pod affinity rules` | InterPodAffinity | 파드의 required podAffinity |
| `node(s) didn't satisfy existing pods anti-affinity rules` | InterPodAffinity | 이미 배치된 파드의 required anti-affinity |
| `node(s) didn't match pod topology spread constraints` | PodTopologySpread | [Topology Spread]({% post_url 2025-11-05-Kubernetes-Scheduling-03 %}#topology-spread-constraints) |
| `node(s) didn't have free ports for the requested pod ports` | NodePorts | 파드의 `hostPort` |
| `node(s) had volume node affinity conflict` | VolumeBinding | PV의 zone/노드 제약 |
| `node(s) exceed max volume count` | NodeVolumeLimits | CSI 드라이버의 노드당 볼륨 한도 |

위 예시를 이 표로 읽으면 처방이 나온다. GPU 노드 3대는 taint를 tolerate하지 못해서, 일반 노드 6대는 nodeSelector가 맞지 않아서 탈락했다. 즉 **파드에 toleration이 없다.** GPU 노드에 배치하려면 [3편에서 본 조합]({% post_url 2025-11-05-Kubernetes-Scheduling-03 %}#toleration)대로 nodeSelector와 toleration을 함께 넣어야 한다. 다만 이것은 taint 단계에서 멈춘 결과라, toleration을 넣은 뒤 GPU 노드가 다음 Filter(예: 자원 부족)에서 다시 탈락할 수 있다.

메시지 뒤의 `preemption:` 부분은 PostFilter(DefaultPreemption)의 결과다. `Preemption is not helpful for scheduling`은 그 노드의 탈락 사유가 선점으로 풀리지 않는 종류(taint·affinity 불일치 등)라 선점 후보에서 아예 빠졌다는 뜻이다. 낮은 우선순위 파드를 죽여도 taint나 affinity 불일치는 해결되지 않기 때문이다. `No preemption victims found for incoming pod`는 자원 부족처럼 선점으로 풀릴 수 있는 노드에서 선점을 시뮬레이션했지만, 내보낼 낮은 우선순위 파드가 없었다는 뜻이다.

파드가 많을 때는 실패 이벤트만 모아 볼 수 있다.

```shell
~$ kubectl get events -A --field-selector reason=FailedScheduling --sort-by=.lastTimestamp
```

<br>

## 축출된 파드와 스케줄링 실패 구분

진단 1단계(`spec.nodeName`이 비었는지)에서 걸러지지만, 헷갈리기 쉬운 경우가 하나 있다. **축출된 파드**다.

축출은 파드가 배치된 **뒤에** 일어나므로, 축출된 파드에는 `spec.nodeName`이 남아 있고 `PodScheduled` 조건도 `True`로 남아 있다. 1단계 판별에서 "스케줄링 문제가 아니다"로 나오는 것이 맞다. 그 파드는 이미 끝난 파드가고, 실제로 봐야 할 것은 **컨트롤러가 그 자리에 다시 만든 새 파드**다.

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
| `QoS Class: BestEffort` (`request is 0`) | 리소스 요청을 선언하지 않았다. kubelet은 축출 대상을 고를 때 ① requests 초과 여부 ② Pod Priority ③ requests 대비 사용량을 보는데, requests가 0이면 항상 ①에 걸린다 |
| `Priority: 0` | PriorityClass가 없다. 다른 파드도 모두 0이면 [선점]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %}#선점)으로 공간을 만들 수 없다 |
| `PodScheduled: True` | [1편]({% post_url 2025-11-05-Kubernetes-Scheduling-01 %}#statusconditions-podscheduled)에서 본 대로 결과 기록이다. 현재 실행 가능 여부를 뜻하지 않는다 |
| `Tolerations`의 `300s` | 직접 설정한 값이 아니라 API Server가 자동 주입한 기본값이다([3편]({% post_url 2025-11-05-Kubernetes-Scheduling-03 %}#noexecute와-tolerationseconds)) |

이 사례에서 실제 문제는 재생성된 파드들이었다. 노드에 `disk-pressure` taint가 붙어 Filter에서 탈락하고, 우선순위가 전부 같아 선점도 불가능해 Pending이 누적됐다. 전체 경위는 [MinIO existingClaim 트러블슈팅]({% post_url 2026-02-24-Dev-Minio-Custom-PVC-Troubleshooting %}#왜-재스케줄링이-안-됐나-추론)에 있다.

<br>

## 파드가 어느 큐에 있는지 판별

큐 이름은 파드 오브젝트에 직접 노출되지 않는다. 파드 쪽 신호로는 아래와 같이 **추정**할 수 있다.

| 관찰되는 신호 | 추정 큐 | 근거 |
| --- | --- | --- |
| `status.phase: Pending`, `PodScheduled` 조건이 `reason: SchedulingGated` | Unschedulable Queue (PreEnqueue에서 차단되어 Active Queue에 진입한 적 없음) | [Scheduling Gate]({% post_url 2025-11-05-Kubernetes-Scheduling-03 %}#scheduling-gate)가 남아 있다 |
| `status.nominatedNodeName`에 값이 있음 | 선점 성공 후 대기 | [선점]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %}#선점)이 이뤄졌고 victim 종료를 기다리는 중 |
| `FailedScheduling` 이벤트가 수초 간격으로 반복 | Backoff Queue 경유 | 백오프 타이머(1~10초)에 맞춰 재시도되고 있다 |
| `FailedScheduling` 이벤트가 한 번 찍히고 오래 조용함 | Unschedulable Queue | 클러스터 이벤트를 기다리는 중 |

이것은 어디까지나 추정이다. 확정하려면 스케줄러 메트릭을 봐야 한다.

```shell
# 큐별 pending 파드 수. kube-scheduler의 보안 포트(기본 10259)를 컨트롤 플레인 노드에서 직접 조회한다
# (kubeadm은 bind-address를 127.0.0.1로 띄운다. $TOKEN의 주체에는 nonResourceURL /metrics에 대한 get 권한이 필요하다)
~$ curl -sk -H "Authorization: Bearer $TOKEN" https://127.0.0.1:10259/metrics | grep '^scheduler_pending_pods'
```

```
# 출력 형식 예시
scheduler_pending_pods{queue="active"} 0
scheduler_pending_pods{queue="backoff"} 0
scheduler_pending_pods{queue="gated"} 2
scheduler_pending_pods{queue="unschedulable"} 1
```

`scheduler_pending_pods`의 `queue` 라벨 네 값이 [2편의 큐 모델]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %}#스케줄러-큐)과 그대로 대응한다.

| 라벨 값 | 의미 |
| --- | --- |
| `active` | Active Queue에 있는 파드 수 |
| `backoff` | Backoff Queue에 있는 파드 수 |
| `unschedulable` | 스케줄링을 시도했다가 실패해 Unschedulable Queue에 있는 파드 수 |
| `gated` | 게이트 때문에 스케줄링을 **시도조차 하지 않은** 파드 수 |

`gated`가 별도 라벨로 분리되어 있다는 점이 유용하다. Scheduling Gate로 막힌 파드와 스케줄링에 실패한 파드를 수치로 구분할 수 있다.

`kubectl get --raw /metrics`는 kube-apiserver의 메트릭을 읽으므로 `scheduler_*` 메트릭이 나오지 않는다. 관리형 컨트롤 플레인은 제공자가 노출하는 경로를 쓴다(예: EKS는 `kubectl get --raw /apis/metrics.eks.amazonaws.com/v1/ksh/container/metrics`).

주의할 점은, 이 메트릭이 **클러스터 전체의 집계값**이라는 것이다. 특정 파드가 어느 큐에 있는지 직접 알려주지는 않는다. 위 표의 파드 쪽 신호와 함께 봐야 한다.

<br>

## 스케줄러 로그와 메트릭

사유별 노드 수만으로 부족하면 스케줄러 로그를 본다.

```shell
~$ kubectl logs -n kube-system kube-scheduler-<control-plane-node> --tail=50
```

기본 로그 레벨에서는 스케줄링 성공/실패 요약만 나온다. 플러그인별 판정까지 보려면 `--v` 값을 올려야 한다. `--profiling`이 켜져 있으면(기본값) 보안 포트에 `PUT /debug/flags/v`(본문에 숫자)를 보내 재시작 없이 바꿀 수 있고, 그렇지 않으면 [스케줄러 설정 변경]({% post_url 2025-11-05-Kubernetes-Scheduling-04 %}#설정-적용과-롤백)에 해당한다. 어느 쪽이든 로그량이 크게 늘어나므로 운영 클러스터에서는 신중하게 접근하고, 진단 뒤 원래 값으로 되돌린다.

시계열로 볼 때 유용한 메트릭도 있다.

| 메트릭 | 용도 |
| --- | --- |
| `scheduler_pending_pods{queue}` | 큐별 적체 추이. `unschedulable`이 계속 쌓이면 구조적 문제다 |
| `scheduler_schedule_attempts_total{result}` | `result`가 `scheduled` / `unschedulable` / `error`로 나뉜다. `error` 증가는 내부 오류 신호다 |
| `scheduler_pod_scheduling_attempts` | 파드 하나가 배치되기까지의 시도 횟수 분포 |
| `scheduler_queue_incoming_pods_total{queue,event}` | 어떤 이벤트로 어느 큐에 파드가 들어왔는지. [QueueingHint]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %}#enqueueextension과-queueinghint) 동작을 관찰할 수 있다 |

<br>

## 수동 배치의 제약

[1편 - 수동 스케줄링]({% post_url 2025-11-05-Kubernetes-Scheduling-01 %}#수동-스케줄링)에서 `spec.nodeName` 직접 지정과 Binding 오브젝트 두 방법을 다뤘다. 여기서는 그 두 방법이 **무엇을 건너뛰고 무엇에 막히는지**를 정리한다. 진단 과정에서 "스케줄러를 우회했는데 왜 이렇게 동작하나"를 확인할 때 쓰는 내용이다.

### kubelet이 다시 검사하는 것과 하지 않는 것

스케줄러의 Filter를 건너뛴다고 해서 아무 검증도 없는 것은 아니다. kubelet은 자신의 노드에 배정된 파드를 실행하기 전에 admission 검사를 수행하며, 여기서 Filter 플러그인 일부와 같은 판정을 다시 한다. 다만 **다시 하는 항목과 하지 않는 항목이 명확히 갈린다**.

| 검사 항목 | 스케줄러 Filter | kubelet admission | 수동 배치 시 결과 |
| --- | --- | --- | --- |
| 리소스 충분 여부 (`NodeResourcesFit`) | O | **O** | 부족하면 파드가 `OutOfcpu` / `OutOfmemory` 등으로 실행 거부 |
| `nodeSelector` / Node Affinity `required` | O | **O** | 불일치하면 실행 거부 |
| 노드명 일치 (`NodeName`) | O | **O** | — |
| `hostPort` 충돌 (`NodePorts`) | O | **O** | 충돌하면 실행 거부 |
| `NoExecute` taint | O | **O** (Static Pod은 제외) | tolerate하지 않으면 실행 거부 |
| **cordon (`NodeUnschedulable`)** | O | **X** | **그대로 실행된다** |
| **`NoSchedule` / `PreferNoSchedule` taint** | O | **X** | **그대로 실행된다** |
| Pod Affinity / Anti-Affinity (`InterPodAffinity`) | O | **X** | 배치 규칙을 위반한 채로 실행된다 |
| 토폴로지 분산 (`PodTopologySpread`) | O | **X** | 분산 제약을 위반한 채로 실행된다 |
| 볼륨 제약 (`VolumeBinding`, `VolumeZone` 등) | O | **X** | 마운트 단계에서 실패한다 |

정리하면, **리소스와 노드 선택 조건은 kubelet이 막아 주지만, 배치 정책에 해당하는 것(cordon, `NoSchedule` taint, 파드 간 관계, 토폴로지 분산)은 아무도 막지 않는다.** taint/toleration의 effect별 의미는 [3편 - Taints and Tolerations]({% post_url 2025-11-05-Kubernetes-Scheduling-03 %}#taints-and-tolerations)에서 다룬다.

<br>

### cordon된 노드에 nodeName을 지정하면

위 표에서 cordon이 kubelet 검사 대상이 아닌 것이 실무에서 자주 마주치는 결과로 이어진다. `kubectl cordon`은 노드에 `spec.unschedulable: true`를 설정하고, 이것이 **두 경로로** 스케줄링을 막는다 — `NodeUnschedulable` 플러그인이 그 필드를 직접 확인하는 경로와, node lifecycle controller가 붙인 `node.kubernetes.io/unschedulable:NoSchedule` taint를 `TaintToleration`이 평가하는 경로다(자세한 구조는 [3편 - cordon의 기술적 의미]({% post_url 2025-11-05-Kubernetes-Scheduling-03 %}#cordon의-기술적-의미)).

중요한 것은 **둘 다 Filter 단계**라는 점이다. 따라서 `spec.nodeName`을 직접 지정해 스케줄러를 우회하면 두 검사 모두 실행되지 않는다. 그리고 cordon이 부착하는 taint의 effect는 `NoSchedule`인데 kubelet은 `NoExecute`만 확인하므로, kubelet admission도 이 파드를 통과시킨다. 결과적으로 **cordon된 노드에도 파드가 정상적으로 뜬다.**

이 동작은 버그가 아니라 설계된 경로이고, 실제로 활용할 여지도 있다. GPU 이상으로 cordon해 둔 노드에 인프라 조치가 끝난 뒤, 해당 노드에서만 짧은 검증 작업(예: CUDA `vectorAdd` 같은 probe Job)을 돌려 정상 여부를 확인하고 싶을 때가 그렇다. cordon을 풀면 그 즉시 일반 워크로드가 들어올 수 있으므로, cordon을 유지한 채 `spec.nodeName`으로 probe만 밀어 넣는 방식을 쓸 수 있다.

다만 이것은 **cordon의 의도를 의도적으로 우회하는 것**이므로, 검증 목적의 단발성 파드에 한정하는 편이 적절하다. 일반 워크로드를 이렇게 배치하면 cordon으로 노드를 비우려는 작업(드레인, 교체, 커널 업그레이드)과 충돌한다.

반대로 스케줄러를 정상적으로 거친 파드는 cordon된 노드에 배치되지 않고 [Unschedulable Queue]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %}#스케줄러-큐)에서 대기한다. cordon을 해제하는 노드 변경 이벤트가 있어야 다시 Active Queue로 돌아온다.

<br>

### Binding이 거부되는 조건

API Server의 Binding 핸들러는 다음 세 가지 경우에 요청을 거부한다.

| 조건 | 에러 |
| --- | --- |
| `spec.nodeName`이 이미 설정되어 있음 | `pod <name> is already assigned to node "<node>"` (409 Conflict) |
| 파드가 삭제 중임(`deletionTimestamp`가 있음) | `pod <name> is being deleted, cannot be assigned to a host` |
| `spec.schedulingGates`가 비어 있지 않음 | `pod <name> has non-empty .spec.schedulingGates` |

세 번째 조건이 의외일 수 있다. [Scheduling Gate]({% post_url 2025-11-05-Kubernetes-Scheduling-03 %}#scheduling-gate)로 스케줄링을 보류시킨 뒤 그 사이에 Binding을 만드는 방식은 **동작하지 않는다.** 게이트가 남아 있으면 Binding 자체가 거부된다.

그렇다면 정상적으로 생성된 파드를 Binding으로 수동 배치하려면, 스케줄러가 먼저 바인딩해 버리기 전에 요청을 넣어야 하는 것인가. 스케줄러는 파드가 등록된 직후에 바인딩하므로 그 경쟁에서 이기는 것은 현실적이지 않다. 대신 **경쟁 자체를 없애는 경로가 있다.** [`spec.schedulerName`]({% post_url 2025-11-05-Kubernetes-Scheduling-01 %}#schedulername-지정)에 `default-scheduler`가 아닌 이름을 넣으면 기본 스케줄러가 그 파드를 스케줄링 큐에 넣지 않으므로, 파드는 Pending으로 남아 있고 그동안 Binding을 생성할 수 있다. 스케줄러를 직접 구현할 때 도는 루프가 정확히 이 구조다 — 자기 이름이 붙고 `spec.nodeName`이 비어 있는 파드를 Watch하다가, 노드를 골라 Binding을 POST한다.

<br>

### 이미 스케줄링된 파드는 옮길 수 없다

[Binding이 1회성]({% post_url 2025-11-05-Kubernetes-Scheduling-01 %}#이미-생성된-파드에-대한-수동-스케줄링-binding-오브젝트)이라는 것은, **스케줄링이 완료된 파드의 배치를 바꿀 수 없다**는 뜻이기도 하다. `spec.nodeName`은 API Server가 업데이트를 거부하는 필드이고, 파드 생성 후 변경할 수 있는 `spec` 필드는 아래로 한정된다.

```
spec.containers[*].image
spec.initContainers[*].image
spec.activeDeadlineSeconds
spec.tolerations                       # 추가만 가능
spec.terminationGracePeriodSeconds     # 음수였던 경우 1로만
spec.schedulingGates                   # 삭제만 가능
spec.nodeSelector                      # 게이트가 있는 동안 추가만 가능
spec.affinity.nodeAffinity             # 게이트가 있는 동안만
```

쿠버네티스에는 실행 중인 파드를 다른 노드로 옮기는 마이그레이션 기능이 없다. 따라서 이미 배치된 파드를 다른 노드에 두려면 **삭제하고 다시 만드는 것이 유일한 경로**다. 리소스 컨트롤러(Deployment, DaemonSet 등)가 관리하는 파드라면 파드를 삭제하면 컨트롤러가 새 파드를 만들고, 그 새 파드가 스케줄링을 처음부터 다시 받는다.

선점도 이 원칙의 예외가 아니다. 선점은 victim의 `nodeName`을 고쳐 다른 곳으로 옮기는 것이 아니라 **victim을 삭제**하고, victim의 컨트롤러가 새 파드를 만들고, 그 파드가 다시 스케줄링을 받는 구조다. 축출(Eviction)이나 Descheduler도 같다 — 전부 "삭제 후 재생성"이며, 재배치는 컨트롤러와 스케줄러가 처음부터 다시 수행한다. 선점의 내부 동작은 [2편 - 선점]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %}#선점)에서 다룬다.

<br>

# 정리

이 글에서 다룬 핵심 내용을 정리한다.

1. **extension point는 결정권에 따라 gate/recovery/informational/ranking으로 분류된다.** PreFilter·Filter·Reserve·Permit은 gate(reject/탈락 가능), PostFilter는 recovery(실패 경로에서 공간 확보), PreScore는 informational(데이터 준비만), Score는 ranking(점수만 매김)이다. PreFilter는 노드를 탈락시키는 것이 아니라 후보 집합 자체를 좁힐 수 있다는 점에서 Filter와 다르다.
2. **PreScore는 비용이 큰 계산을 1번만 수행하여 Score에 공유하는 캐시 레이어다.** Score가 (노드 수 × 플러그인 수)번 호출되므로, PreScore에서 미리 계산하면 O(N) → O(1)로 줄어든다. PreFilter와 달리 결정권은 없다.
3. **주요 플러그인은 여러 extension point에 걸쳐 동작하며, 각 단계에서의 역할이 다르다.** v1.32 기준 `NodeResourcesFit`은 4개, `VolumeBinding`은 6개 extension point에 관여한다. 클라우드 벤더 전용 볼륨 제한 플러그인 4개는 v1.32에서 제거되었다.
4. **진단은 Events → 메트릭 순서로 좁힌다.** `FailedScheduling` 메시지의 사유 조각이 어느 Filter 플러그인에서 나온 것인지 대응시키면 처방이 나오고, `scheduler_pending_pods`의 `queue` 라벨(`active`/`backoff`/`unschedulable`/`gated`)로 큐 적체를 확인한다.
5. **스케줄러를 우회한 파드는 배치 정책 검사를 받지 않는다.** kubelet admission은 리소스·노드 선택 조건·`NoExecute` taint만 다시 본다. Binding은 이미 노드가 있거나, 삭제 중이거나, 게이트가 남은 파드에 대해서만 거부되고, 이미 배치된 파드를 옮기는 방법은 삭제 후 재생성뿐이다.

시리즈 전체의 편별 구성은 [0편 - 시리즈 구성]({% post_url 2025-11-05-Kubernetes-Scheduling-00 %}#시리즈-구성)에 있다.

<br>

# 참고 링크

- [Scheduling Framework - Kubernetes 공식 문서](https://kubernetes.io/docs/concepts/scheduling-eviction/scheduling-framework/)
- [Scheduler Configuration - Kubernetes 공식 문서](https://kubernetes.io/docs/reference/scheduling/config/)
- [Scheduler Metrics - Kubernetes 공식 문서](https://kubernetes.io/docs/reference/instrumentation/metrics/)
- [KEP-4049: Storage Capacity Scoring of Nodes for Dynamic Provisioning](https://github.com/kubernetes/enhancements/tree/master/keps/sig-storage/4049-storage-capacity-scoring-of-nodes-for-dynamic-provisioning)

<br>
