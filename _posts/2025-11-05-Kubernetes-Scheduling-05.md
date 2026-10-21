---
title:  "[Kubernetes] 쿠버네티스 스케줄링 - 5. 파드 단위 스케줄링의 한계와 Gang Scheduling"
excerpt: "파드를 하나씩 배치하는 kube-scheduler가 분산 학습 같은 그룹 워크로드에서 겪는 한계와, 이를 푸는 Coscheduling, 네이티브 Workload API, Volcano, Kueue의 접근 방식을 알아보자."
permalink: /kubernetes/Kubernetes-Scheduling-05/
categories:
  - mlops-resource
  - k8s-scheduling
  - concept
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - MLOps
  - Kubernetes
  - Scheduling
  - Gang Scheduling
  - PodGroup
  - Coscheduling
  - Volcano
  - Kueue
last_modified_at: 2026-10-21
---

<br>

# TL;DR

- `kube-scheduler`는 큐잉, 배치, 선점을 모두 파드 단위로 한다. 그래서 분산 학습처럼 여러 파드가 함께 떠야 하는 워크로드에서 일부 파드만 배치되어 GPU를 잡은 채 나머지를 기다리는 **부분 배정**이 생기고, 잡 단위의 대기·쿼터·선점도 표현할 수 없다.
- gang scheduling(파드 그룹을 전부 배치하거나 하나도 배치하지 않는 것)을 구현하는 지점은 세 곳이다. 스케줄러 앞단의 admission(Kueue, Volcano enqueue), 그룹 전체를 가상 배치하는 스케줄링 사이클(Volcano allocate, 네이티브 Workload Scheduling Cycle), 파드 단위 사이클의 확정 지점 제어(Coscheduling의 Permit)다. ①은 들여보낼 시점을 정해 ②·③을 보완하고, ②와 ③은 같은 문제(전부 아니면 전무)를 다른 방식으로 푼다.
- **Coscheduling**은 out-of-tree 플러그인으로, 이를 넣은 커스텀 빌드 kube-scheduler에서 동작한다. Permit에서 그룹이 `minMember`만큼 모일 때까지 바인딩을 미룬다. 기다리는 동안 스케줄러 캐시 안에서 자원을 잡아 두므로, 그룹끼리 경쟁하면 잡았다 반납하는 일이 반복될 수 있다. PodGroup에 `minResources`를 적으면 PreFilter의 클러스터 합계 검사로 이 경합을 줄일 수 있다.
- **네이티브 gang scheduling**은 v1.35 alpha(파드 단위 사이클 위의 PreEnqueue·Permit 배리어)로 시작해, v1.36에서 그룹 전체를 한 번에 평가하는 Workload Scheduling Cycle이 추가되었다. v1.37에서 관련 게이트가 `GenericWorkload`로 합쳐져 beta가 되었지만 기본은 비활성이다.
- **Volcano**는 Scheduling Framework를 쓰지 않는 별도 구현 스케줄러로, 주기적 세션 안에서 잡 전체를 가상 배치한 뒤 commit 또는 discard한다. **Kueue**는 스케줄러가 아니라 잡을 들여보낼 시점을 정하는 워크로드 admission 컨트롤러로, 쿼터·대여·워크로드 단위 선점을 맡고 노드 배치는 뒤의 스케줄러에 맡긴다.
- 두 번째 스케줄러가 기본 스케줄러와 같은 노드를 쓰면 서로의 예약을 몰라 충돌이 생길 수 있다. kube-scheduler 계열에서 gang scheduling을 쓸 때(Coscheduling을 넣은 커스텀 빌드 kube-scheduler, 네이티브 gang scheduling) bin packing은 그룹 파드의 `schedulerName`에 대응하는 프로필에 설정해야 한다. Volcano는 ConfigMap `tiers`의 binpack 플러그인으로 설정한다. pod affinity는 프로필이 아니라 파드 스펙(워크로드 템플릿)에 적는다.

<br>

# 들어가며

[1편]({% post_url 2025-11-05-Kubernetes-Scheduling-01 %})부터 [4편]({% post_url 2025-11-05-Kubernetes-Scheduling-04 %})까지는 파드 하나가 노드 하나에 배치되는 과정을 다뤘다. 분산 학습 잡은 사정이 다르다. 워커 파드가 모두 떠야 학습이 시작되는데, `kube-scheduler`는 그중 일부만 먼저 배치할 수 있다. 실제로 분산 학습 잡의 워커 일부만 GPU를 배정받고 나머지는 Pending에 머무는 상황이 생기면, 배정받은 워커는 GPU를 잡은 채 연산 없이 기다리고, 그 GPU는 다른 잡도 쓰지 못한다.

이 문제를 풀기 위해 쿠버네티스 생태계에는 여러 도구가 있다. 그런데 도구마다 문제를 푸는 위치가 달라서, 이름만 보고 나란히 비교하면 혼동이 생긴다. 그래서 문제를 먼저 정의하고, 어느 지점에서 풀 수 있는지를 나눈 뒤 도구를 그 지점에 대응시킨다.

1. **파드 단위 스케줄링의 한계**: 부분 배정이 생기는 구조와, 큐·쿼터·선점에서 함께 드러나는 한계
2. **해결 방식의 레이어**: admission, 그룹 단위 스케줄링 사이클, 확정 지점 제어, 배치 정책
3. **스케줄링 레이어의 gang 구현**: Coscheduling, 네이티브 Workload API, Volcano
4. **admission 레이어**: Kueue
5. **도입 시 고려 사항**: 워크로드 컨트롤러 연동, 스케줄러 구성별 충돌, bin packing과 affinity의 위치

버전이 섞이는 글이다. 쿠버네티스 기본 서술은 시리즈 기준인 v1.32이고, [네이티브 Workload API](#네이티브-workload-api) 절은 v1.35~v1.37 기준이다. 외부 프로젝트(scheduler-plugins, Volcano, Kueue, KubeRay)는 2026년 10월 시점의 문서와 소스 기준이다. 각 도구의 동작 방식과 서로의 관계까지가 이 글의 범위이고, 실제 클러스터에 도입해 효과를 측정한 결과는 다루지 않는다. 도입 방향에 대한 서술은 조사 결과로, 검증한 범위 밖이다. 노드 오토스케일러(Cluster Autoscaler, Karpenter)와 gang의 상호작용도 다루지 않는다. 그룹을 모르는 오토스케일러는 노드를 일부만 늘릴 수 있고, Kueue는 이를 위해 ProvisioningRequest admission check를 따로 둔다.

<br>

# 파드 단위 스케줄링의 한계

## 배경: 파드 단위에서 그룹 단위로

기존 Scheduling Framework의 extension point는 모두 **파드 단위**로 동작한다. 한 번에 하나의 파드를 평가하고, 하나의 노드를 선택하고, 하나의 바인딩을 수행한다([1편 - Scheduling Framework]({% post_url 2025-11-05-Kubernetes-Scheduling-01 %}#scheduling-framework)).

그러나 ML 학습 워크로드처럼 여러 파드가 **동시에** 자원을 확보해야 하는 경우(gang scheduling), 파드 단위 스케줄링으로는 한계가 있다. 예를 들어 8-GPU 파드 4개가 동시에 확보되어야 학습을 시작할 수 있는데, 파드를 하나씩 스케줄링하면 일부만 배치되고 나머지는 자원 부족으로 Pending에 빠지는 [부분 배정](#부분-배정)이 생기고, 잡끼리 경쟁하면 교착 상태로 이어진다.

이는 [4편 - 리소스 단편화 문제]({% post_url 2025-11-05-Kubernetes-Scheduling-04 %}#리소스-단편화-문제)의 단편화가 파드 그룹 단위로 확대된 형태다. 4편의 bin packing 전략은 파드 하나가 필요한 GPU를 한 노드에서 확보하게 만들지만, "4개 파드가 동시에 확보되어야 한다"는 요구는 표현할 수 없다.

<br>

## 부분 배정

부분 배정은 하나의 잡에 속한 파드 중 일부만 노드에 배치되고 나머지는 배치되지 못한 상태다. 배치된 파드는 자원을 잡고 있지만, 잡 전체가 모이지 않았으므로 일을 하지 못한다.

두 잡이 경쟁하면 더 나빠진다. GPU 8장이 남은 클러스터에 각각 8장이 필요한 잡 A와 B가 동시에 들어왔다고 하자. 파드 단위 스케줄링에서는 두 잡의 파드가 큐에서 섞여 처리되므로, A가 4장, B가 4장을 먼저 잡을 수 있다. 둘 다 나머지 4장을 기다리지만 남은 GPU는 없다. 어느 쪽도 시작하지 못하고, 어느 쪽도 자원을 내놓지 않는다.

`kube-scheduler`에는 이 상황을 감지하고 풀어 줄 장치가 없다. 배치된 파드는 이미 바인딩되어 노드에서 실행 중이고, 스케줄러는 그 파드가 어떤 잡의 일부인지 모른다.

<br>

## 큐, 쿼터, 선점의 한계

부분 배정의 원인은 `kube-scheduler`가 잡이라는 단위를 모른다는 것이다. 같은 원인이 큐, 쿼터, 선점에서도 한계로 드러난다.

| 영역 | v1.32 `kube-scheduler`의 동작 | 생기는 문제 |
| --- | --- | --- |
| 큐 | 파드 단위로 쌓이고, 기본 정렬 기준(`PrioritySort`)은 우선순위와 큐 진입 시각이다 ([2편 - 스케줄러 큐]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %}#스케줄러-큐)) | 서로 다른 잡의 파드가 섞여 처리되어 부분 배정이 생긴다. "잡이 용량을 기다리는 상태"를 표현할 수 없고, 팀·잡 사이의 공정한 순서도 표현할 수 없다 |
| 쿼터 | ResourceQuota가 네임스페이스 상한을 API Server의 파드 생성 시점에 검사한다 | 상한을 넘으면 대기 없이 파드 생성을 거부한다. 파드 단위로 차감되므로 잡의 일부만 쿼터 안에 드는 상황을 막지 못한다. 클러스터의 실제 여유 용량이나 사용 이력은 모른다 |
| 선점 | 파드 단위·노드 단위로 victim을 고른다 ([2편 - 선점의 한계]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %}#선점의-한계)) | gang의 일부만 축출해 남은 파드를 쓸모없게 만들거나, 어차피 완성하지 못할 gang을 위해 선점할 수 있다. gang 하나를 띄우려고 필요한 만큼을 한꺼번에 비우는 판단도 하지 못한다 |

이 표의 세 영역은 [0편 - 스케줄러의 공통 질문]({% post_url 2025-11-05-Kubernetes-Scheduling-00 %}#스케줄러의-공통-질문)의 "누구부터 하나", "들여보내도 되나", "누구를 내보내나"에 해당한다. HPC 배치 스케줄러는 처음부터 잡을 단위로 이 질문들에 답하지만, `kube-scheduler`는 파드를 단위로 답한다.

<br>

# 해결 방식의 레이어

## 세 가지 질문

그룹 워크로드의 스케줄링 문제는 세 가지 질문으로 나뉘고, 질문마다 다루는 레이어가 다르다. 결론부터 말하면 세 질문은 서로 대체 관계가 아니고, 그중 "다 같이 놓을 수 있나"는 ②와 ③ 두 방식으로 풀 수 있다.

| 질문 | 레이어 | 다루는 것 |
| --- | --- | --- |
| 들여보내도 되나 | ① admission (스케줄러 앞단) | 잡 단위 큐잉, 쿼터, 대여(borrowing), 공정 분배(fair share) |
| 다 같이 놓을 수 있나 | ② 그룹 단위 스케줄링 사이클, ③ 파드 단위 사이클의 확정 지점 제어 | gang(전부 아니면 전무) |
| 어디에 놓을까 | 배치 정책(Score) | bin packing, affinity, topology |

②와 ③은 같은 질문을 다른 방식으로 푼다.

| 레이어 | 접근 방식 | 예 |
| --- | --- | --- |
| ① admission | 잡 전체가 쿼터와 용량에 들어갈 때만 파드를 스케줄러로 보낸다 | Kueue, Volcano의 enqueue action |
| ② 그룹 단위 사이클 | 그룹 전체를 가상으로 배치해 보고, 확정하거나 되돌린다 | Volcano의 allocate action, 네이티브 Workload Scheduling Cycle(v1.36+) |
| ③ 파드 단위 사이클 + 확정 지점 제어 | 노드 선택은 파드별로 하고, 확정(바인딩)만 그룹이 모일 때까지 미룬다 | Coscheduling, 네이티브 gang scheduling(v1.35) |

③은 기존 파드 단위 사이클을 그대로 쓰므로 구현이 간단하지만, 그룹 전체가 노드 단위로 들어갈 수 있는지는 미리 보지 못한다(Coscheduling의 `minResources` 검사는 클러스터 합계 비교다). ②는 그룹을 한 번에 평가하므로 이 문제가 없지만, 스케줄링 사이클 자체를 바꿔야 한다. ①은 스케줄러에 들어가기 전에 걸러 주므로 ②·③의 경합을 줄이지만, 바인딩은 하지 않는다(Kueue의 Topology Aware Scheduling은 배치할 토폴로지 도메인까지 정한다).

<br>

## 문제별 도구

| 문제 | 레이어 | 도구 |
| --- | --- | --- |
| 부분 배정 | ②·③ (①로 보완) | Coscheduling, 네이티브 gang scheduling, Volcano |
| 잡 단위 큐잉·공정성 | ① | Kueue, Volcano Queue |
| 쿼터·대여 | ① | Kueue의 ClusterQueue·cohort, Volcano Queue의 capability·reclaim |
| gang을 인지하는 선점 | ①·② | Kueue(워크로드 단위 선점), Volcano(v1.15+ `gangPreempt`·`gangReclaim`, alpha), 네이티브 워크로드 단위 선점(v1.36+) |
| GPU 단편화·워커 분산 | 배치 정책 | `NodeResourcesFit`의 MostAllocated 등([4편]({% post_url 2025-11-05-Kubernetes-Scheduling-04 %}#noderesourcesfit-스코어링-전략)), Kueue TAS(admission 시 토폴로지 도메인 배정), Volcano binpack |

도구를 [0편 - 스케줄링 동작 변경 층위]({% post_url 2025-11-05-Kubernetes-Scheduling-00 %}#스케줄링-동작-변경-층위)로 나누면 다음과 같다. Coscheduling은 커스텀 빌드 kube-scheduler(층위 2), 네이티브 gang scheduling은 기본 바이너리 그대로 feature gate를 켜는 방식(층위 1에 가깝다), Volcano는 별도 구현 스케줄러(층위 3), Kueue는 스케줄러 앞단의 워크로드 admission(층위 4)이다.

<br>

# 스케줄링 레이어의 gang 구현

세 구현의 차이는 그룹 단위 판단을 어디에 두느냐다. Coscheduling은 파드 단위 사이클을 그대로 두고 확정 지점(Permit)에서만 그룹을 기다린다. 네이티브 gang scheduling은 같은 방식으로 시작해 그룹 단위 사이클로 옮겨 가는 중이다. Volcano는 처음부터 잡 단위 세션으로 설계되었다.

## Coscheduling

### Coscheduling의 위치

Coscheduling은 [kubernetes-sigs/scheduler-plugins](https://github.com/kubernetes-sigs/scheduler-plugins)에 있는 out-of-tree 플러그인이다. 기본 `kube-scheduler` 바이너리에는 없으므로, 플러그인을 넣은 커스텀 빌드 kube-scheduler를 띄우고 대상 파드가 그 스케줄러를 쓰게 해야 한다([1편 - 커스텀 빌드 kube-scheduler 배포 방식]({% post_url 2025-11-05-Kubernetes-Scheduling-01 %}#커스텀-빌드-kube-scheduler-배포-방식)). 커스텀 빌드 kube-scheduler도 내부 구조는 Scheduling Framework 그대로이므로, 프로필 문법과 extension point는 `kube-scheduler`와 같다([1편 - 커스텀 빌드 kube-scheduler와 kube-scheduler의 관계]({% post_url 2025-11-05-Kubernetes-Scheduling-01 %}#커스텀-빌드-kube-scheduler와-kube-scheduler의-관계)).

### 동작

그룹은 PodGroup CRD(`scheduling.x-k8s.io/v1alpha1`)로 선언하고, 파드는 `scheduling.x-k8s.io/pod-group` 라벨에 PodGroup 이름을 적어 그룹에 속한다.

```yaml
# 최소 4개 파드가 모여야 시작하는 그룹. 60초 안에 모이지 않으면 잡아 둔 자원을 반납한다
apiVersion: scheduling.x-k8s.io/v1alpha1
kind: PodGroup
metadata:
  name: train-job
spec:
  minMember: 4                 # 한꺼번에 확정할 최소 파드 수
  minResources:                # 그룹이 시작하는 데 필요한 최소 자원. PreFilter가 클러스터 남은 자원 합계와 비교한다
    nvidia.com/gpu: 32
  scheduleTimeoutSeconds: 60   # Permit에서 기다리는 최대 시간
---
apiVersion: v1
kind: Pod
metadata:
  name: train-job-worker-0
  labels:
    scheduling.x-k8s.io/pod-group: train-job   # 이 라벨로 그룹에 속한다
spec:
  schedulerName: scheduler-plugins-scheduler   # Coscheduling을 넣은 커스텀 빌드 kube-scheduler의 프로필 이름
  containers:
  - name: trainer
    image: trainer:latest
```

노드 선택(Filter·Score)은 여전히 파드 하나씩 진행하고, 고른 노드를 바로 확정하지 않고 Permit에서 기다리게 한다. 그룹의 파드가 `minMember`만큼 모이면 한꺼번에 승인해 바인딩하고, 타임아웃이 되면 전부 반납한다.

| extension point | 하는 일 |
| --- | --- |
| QueueSort | 같은 PodGroup의 파드가 큐에서 연달아 처리되도록 정렬한다 |
| PreFilter | 그룹에 속한 파드 수가 `minMember`보다 적거나, 스케줄링 게이트가 남은 형제 파드가 있거나, `minResources`가 클러스터 전체 남은 자원(합계)을 넘으면 거절한다. `podGroupBackoffSeconds`(기본 0)를 주면 직전에 실패한 그룹도 그 시간 동안 거절한다 |
| PostFilter | 그룹의 파드 하나가 Filter에서 실패하면, 같은 그룹에서 Permit 대기 중인 파드를 즉시 거절해 자원을 반납시킨다(남은 인원 비율이 `podGroupRejectPercentage`, 기본 10% 이하면 기다린다) |
| Reserve·Unreserve | 타임아웃이나 실패 시 그룹 전체의 예약을 해제한다 |
| **Permit** | **`minMember`만큼 모일 때까지 대기시켰다가 한꺼번에 승인한다**(대기 상한은 PodGroup의 `scheduleTimeoutSeconds`, 없으면 플러그인 인자 `permitWaitingTimeSeconds`, 기본 60초) |

핵심인 "한꺼번에 확정"은 Permit에서 일어나고, 나머지 extension point는 그룹 단위 정렬, 사전 거절, 일괄 반납을 보조한다. Coscheduling은 PreEnqueue를 구현하지 않는다. 그룹 인원이 모자라는 파드는 큐에 들어온 뒤 PreFilter에서 거절된다. QueueSort를 바꾸므로, 같은 스케줄러 프로세스 안의 모든 프로필이 Coscheduling의 QueueSort를 쓰게 된다([4편 - 다중 프로필의 제약]({% post_url 2025-11-05-Kubernetes-Scheduling-04 %}#다중-프로필의-제약)).

### 한계

Permit에서 기다리는 파드는 아직 바인딩 전이지만, 스케줄러 캐시 안에서는 자원을 이미 쓴 것(assumed)으로 처리된다. 노드에 바인딩된 채 GPU를 놀리는 문제는 막지만, **스케줄러 안에서 자원을 잡아 두는 문제는 남는다.** PodGroup에 `minResources`가 없으면, 여러 그룹이 동시에 들어와 경쟁할 때 [앞의 부분 배정 예시](#부분-배정)와 비슷한 흐름이 스케줄러 안에서 생길 수 있다.

1. 잡 A가 GPU 4장, 잡 B가 GPU 4장을 먼저 잡고 Permit에서 기다린다
2. A의 다음 파드가 Filter에서 실패하면, PostFilter가 A의 대기 파드를 즉시 거절해 자원을 반납시킨다. 남은 인원이 `minMember`의 `podGroupRejectPercentage`(기본 10%) 이하면 반납하지 않고 기다린다
3. 반납된 자원을 B가 가져가 완성하거나, 같은 경합이 반복된다

`scheduleTimeoutSeconds`는 형제 파드가 Filter까지 오지 못한 채 대기가 길어질 때의 상한이다. 그래서 실제 흐름은 타임아웃까지 서로 붙잡고 있는 교착보다는, 잡았다 반납하고 다시 경합하는 반복에 가깝다.

`minResources`를 적으면 PreFilter가 그룹의 최소 자원을 클러스터 전체의 남은 자원 합계와 비교해(다른 그룹이 assumed로 잡아 둔 자원도 사용 중으로 친다), 들어갈 수 없는 그룹을 자원을 잡기 전에 거절한다. KubeRay의 scheduler-plugins 연동은 PodGroup을 만들 때 `minResources`를 채운다. 다만 이 검사는 노드별 단편화나 affinity·taint를 보지 않는 합계 비교라서, 그룹이 실제로 배치될 수 있는지까지 보장하지는 않는다.

QueueSort로 같은 그룹의 파드를 연달아 처리하고, `minResources` 사전 검사와 PostFilter의 일괄 반납으로 완화할 수는 있지만 완전히 없애지는 못한다. 그룹 전체가 노드 단위로 들어갈 수 있는지 미리 보지 못하는 파드 단위 사이클의 한계를 그대로 물려받기 때문이다.

그 밖의 한계는 다음과 같다.

- **기본 스케줄러를 교체하지 않으면 두 번째 스케줄러로 띄워야 한다.** 기본 스케줄러와 같은 노드를 쓰면 자원 뷰 충돌이 생기고, Permit 대기 시간만큼 충돌 가능 구간이 길어진다([1편 - 자원 뷰 충돌]({% post_url 2025-11-05-Kubernetes-Scheduling-01 %}#자원-뷰-충돌), [아래 스케줄러 구성별 충돌](#스케줄러-구성별-충돌))
- **큐잉, 쿼터, 선점 개념이 없다.** 이 부분은 admission 레이어([Kueue](#admission-레이어-kueue))나 Volcano가 맡는다

<br>

## 네이티브 Workload API

이 절은 **v1.35~v1.37 기준**이다. 시리즈 기준 버전(v1.32)보다 뒤이고, v1.37에서도 기능이 기본 비활성이라 feature gate를 켜야 동작한다.

쿠버네티스 업스트림은 Workload API(KEP-4671)로 기본 `kube-scheduler`가 그룹 단위로 스케줄링하도록 만들고 있다. 기본 스케줄러 안에서 동작하므로 두 번째 스케줄러가 필요 없고, 스케줄러 캐시가 하나라 스케줄러 간 충돌도 없다. 큐잉, 쿼터, 대여는 제공하지 않는다. 이것이 필요하면 admission 레이어를 앞에 두는 구성을 생각할 수 있지만, Kueue와 네이티브 gang scheduling의 조합은 Kueue 문서에서 확인하지 못했다(검증 범위 밖). 또 feature gate와 `--runtime-config`를 직접 줄 수 없는 관리형 컨트롤 플레인에서는 이 경로를 쓸 수 없다.

### 2계층 Extension Point 체계

v1.36 기준으로 Scheduling Framework의 extension point는 2계층으로 구성된다.

1. **Pod-level extension points** (기존): QueueSort → PreFilter → Filter → Score → ... → Bind
2. **PodGroup-level extension points** (v1.36 추가): PlacementGenerate → (Pod-level 재활용) → PlacementScore

PodGroup-level이 Pod-level을 **대체하는 게 아니라 감싸는(wrapping) 구조**다. PodGroup 사이클 내부에서 기존 Pod-level Filter/Score를 그대로 재활용한다.

| Extension Point | 등장 시점 | 상태 | 역할 |
| --- | --- | --- | --- |
| `queueSort`, `filter`, `score`, `bind` 등 | K8s 초기~1.19+ | stable | 파드 단위 스케줄링 |
| `placementGenerate` | **v1.36** | **alpha** | PodGroup이 배치될 수 있는 노드 집합(placement) 후보를 생성 |
| `placementScore` | **v1.36** | **alpha** | placement 후보들에 점수를 매겨 최적 배치를 선택 |
| `podGroupPostFilter` | **v1.37** | **beta(기본 비활성)** | PodGroup 스케줄링 사이클이 실패했을 때만 실행되어 그룹 전체가 들어갈 자리를 만든다(기본은 워크로드 단위 선점). 성공해도 바로 바인딩하지 않고, 그룹을 큐로 돌려 다음 사이클에서 다시 평가한다. 파드 단위의 [PostFilter]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %}#postfilter)에 대응한다 |

`placementGenerate`·`placementScore`는 `KubeSchedulerConfiguration` v1의 `PlacementGenerate` / `PlacementScore` PluginSet으로 노출된다. 출처 KEP은 gang scheduling(KEP-4671)이 아니라 **KEP-5732 "Topology-aware workload scheduling"**이며, feature gate는 `TopologyAwareWorkloadScheduling`이다. KEP-5732는 아래 [동작 흐름](#동작-흐름)의 그룹 단위 사이클(KEP-4671) 위에, 토폴로지를 고려해 placement를 고르는 알고리즘을 얹는다.

### 동작 흐름

파드 단위 스케줄링이 사라지는 것은 아니다. 파드가 PodGroup에 속할 때만 PodGroup 스케줄링 사이클로 분기한다. 이 사이클은 v1.36에 추가되었고, KEP-4671은 Workload Scheduling Cycle, 공식 문서는 PodGroup scheduling cycle이라고 부른다.

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
        │      (TopologyAwareWorkloadScheduling 게이트를 켰을 때)
        └─ 결과에 따라 atomic 결정
            ├─ 성공 (minCount 이상 배치 가능) → 들어가는 파드를 bind
            │   (minCount를 넘어 남은 파드는 큐로 반환)
            └─ 실패 → 전부 큐로 반환 (아무것도 bind 안 함)
```

여기서 `minCount`는 **그룹이 시작되기 위해 최소한 배치되어야 하는 파드 수**다. v1.35에서는 Workload 오브젝트에 지정했고, v1.36부터는 PodGroup의 `spec.schedulingPolicy.gang.minCount`에 지정한다(Workload의 `spec.podGroupTemplates[].schedulingPolicy.gang.minCount`로 템플릿을 둘 수도 있다). 이 수를 채우지 못하면 아무것도 바인딩하지 않고 전부 큐로 돌려보낸다. 규칙은 "minCount 이상이거나, 하나도 아니거나"다. 일부만 떠서 자원을 점유한 채 나머지를 기다리는 교착을 원천적으로 막는 것이 atomic 결정의 목적이다.

`minCount` 강제는 `GangScheduling` 플러그인이 맡는다. v1.36에서는 이 플러그인이 `GenericWorkload`와 별개인 `GangScheduling` 게이트로 켜지므로, `GenericWorkload`만 켜면 그룹 사이클은 돌지만 `minCount`는 강제되지 않는다. v1.37에서는 `GangScheduling` 게이트가 `GenericWorkload`로 합쳐졌다.

파드가 어느 그룹에 속하는지를 가리키는 필드는 버전에 따라 다르다. v1.35에서는 `spec.workloadRef`였고, **v1.36에서 `spec.schedulingGroup`으로 교체**되었다. `spec.schedulingGroup.podGroupName`이 PodGroup 오브젝트를 가리키며, 파드 생성 후에는 바꿀 수 없다. 같은 v1.36에서 PodGroup이 Workload에서 별도 오브젝트로 분리되었다(KEP-5832).

트리거는 여전히 개별 파드를 큐에서 꺼내는 것이다. 다만 그 파드가 그룹 소속이면 이후에 타게 되는 사이클 자체가 달라진다.

### 버전별 구현 차이

| 버전 | 방식 |
| --- | --- |
| **v1.35** (gang scheduling alpha, KEP-4671) | 파드를 **하나씩** 스케줄링하되, `PreEnqueue`와 `Permit`에 배리어를 두어 그룹 전체가 모일 때까지 진행을 막는다. 기존 파드 단위 파이프라인을 그대로 재활용하는 방식. API는 `scheduling.k8s.io/v1alpha1` Workload |
| **v1.36** (Workload Scheduling Cycle, KEP-4671 / placement, KEP-5732) | **별도의 사이클**로 그룹 전체를 한 번에 평가한다. 스냅샷 1회, atomic 결정. `minCount` 강제에는 `GangScheduling` 게이트가 따로 필요하다. KEP-5732가 `placementGenerate`/`placementScore`를 도입했다. API는 `v1alpha2` Workload + PodGroup |
| **v1.37** (beta, 기본 비활성) | `GangScheduling`·`WorkloadAwarePreemption` 게이트가 `GenericWorkload`로 합쳐졌고, `GenericWorkload`가 beta가 되었다. Workload·PodGroup API는 `v1beta1`. `podGroupPostFilter` extension point가 추가되었다. KEP-5732는 여전히 alpha |

v1.35는 기존 파이프라인 위에 배리어를 얹어 그룹 동작을 구현한 것으로, 레이어로 보면 Coscheduling과 같은 ③이다. v1.36에서 그룹 자체를 스케줄링 단위로 다루는 사이클이 생기면서 ②로 옮겨 갔다. KEP-5732는 beta를 v1.38로 계획하고 있다.

### 워크로드 단위 선점

KEP-5710(Workload-aware preemption)은 파드 단위 선점의 한계([2편 - 선점의 한계]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %}#선점의-한계))를 워크로드 단위로 푸는 작업이다. v1.36에서 `WorkloadAwarePreemption` 게이트로 alpha가 되었고, v1.37에서 `GenericWorkload`로 합쳐졌다(beta, 기본 비활성). v1.37에는 PodGroup의 선점 정책을 다루는 `PodGroupPreemptionPolicy` 게이트(alpha)도 추가되었다.

### NodeResourcesFit의 PodGroup 모드

`NodeResourcesFit`은 PodGroup 스케줄링 시 `placementScore` extension point에서도 동작하며, resource utilization을 **placement 전체 단위**로 계산한다. 이때 `MostAllocated` 방향으로 고정된다. 소스에서 placement용 scorer의 전략 타입이 `MostAllocated`로 하드코딩되어 있고, 사용자가 `scoringStrategy`에 적은 값 중 리소스별 가중치(`resources`)만 가져온다. 이 scorer는 `TopologyAwareWorkloadScheduling` 게이트를 켰을 때만 만들어진다.

PodGroup은 여러 파드를 하나의 placement(노드 집합)에 모아서 배치하는데, placement 내 노드의 사용률을 최대한 높여야 placement가 차지하는 노드 수가 줄고, 남는 노드를 다른 워크로드가 쓸 수 있기 때문이다. `LeastAllocated`(분산 배치)는 개별 파드에는 적합하지만, 그룹 단위 배치에서는 [자원 단편화]({% post_url 2025-11-05-Kubernetes-Scheduling-04 %}#단편화란)를 일으킨다.

### Feature Gate 상태와 활성화

PodGroup 관련 기능은 v1.36까지 모두 alpha였고, v1.37에서도 beta이지만 기본 비활성이라 feature gate를 수동으로 활성화해야 한다.

| Feature Gate | 도입 | v1.37 상태 | 역할 |
| --- | --- | --- | --- |
| `GangScheduling` | v1.35 | `GenericWorkload`로 합쳐짐 | gang scheduling 플러그인 활성화. v1.36까지는 `GenericWorkload`와 별도로 켜야 `minCount`가 강제된다 |
| `GenericWorkload` | v1.35 | beta, 기본 비활성 | Workload API와 그룹 단위 스케줄링 활성화 |
| `TopologyAwareWorkloadScheduling` | v1.36 | alpha | `placementGenerate` / `placementScore` extension point 활성화 |
| `WorkloadAwarePreemption` | v1.36 | `GenericWorkload`로 합쳐짐 | 워크로드 단위 선점 |
| `PodGroupPreemptionPolicy` | v1.37 | alpha | PodGroup의 선점 정책 |

v1.37에서 켜려면 두 가지가 필요하다. Workload·PodGroup이 속한 `scheduling.k8s.io/v1beta1`은 새 beta API라 기본 비활성이므로 kube-apiserver에 `--runtime-config=scheduling.k8s.io/v1beta1=true`를 주어야 하고, `GenericWorkload` 게이트는 kube-apiserver, kube-controller-manager, kube-scheduler에 함께 켜야 한다.

GA가 되더라도 "모든 파드가 PodGroup으로 스케줄링된다"는 것이 아니다. 그룹에 속하지 않은 파드는 기존 파드 단위 사이클을 그대로 탄다.

Coscheduling에서 네이티브 기능으로 옮겨 가면 그룹을 선언하는 API가 바뀐다. Coscheduling의 PodGroup(`scheduling.x-k8s.io`)과 네이티브 Workload·PodGroup(`scheduling.k8s.io`)은 다른 API이므로, 잡을 제출하는 템플릿이나 이를 만들어 주는 워크로드 컨트롤러가 함께 바뀌어야 한다([아래 워크로드 컨트롤러 연동](#워크로드-컨트롤러-연동)).

<br>

## Volcano

### Volcano의 위치

Volcano는 `kube-scheduler`와 별개의 스케줄러(`volcano-scheduler`)로, kube-batch 프로젝트에서 출발했다. 쿠버네티스 위에서 `schedulerName: volcano`로 파드를 골라 Binding API로 노드를 지정한다는 공통 규칙은 같지만([0편 - 스케줄러 공통 규칙]({% post_url 2025-11-05-Kubernetes-Scheduling-00 %}#스케줄러-공통-규칙)), 내부는 Scheduling Framework가 아니라 자체 확장 구조로 동작한다. 즉 Volcano는 별도 구현 스케줄러다. 쿠버네티스와 주고받는 규칙은 같고, 내부 구조는 다르다.

### 구성 요소

| 요소 | 역할 |
| --- | --- |
| action | 세션 안에서 실행할 단계(enqueue, allocate, preempt, reclaim, backfill 등). 설정으로 순서를 정한다. 기본 설정은 `enqueue, allocate, backfill`. Volcano의 backfill action은 [0편]({% post_url 2025-11-05-Kubernetes-Scheduling-00 %}#slurm-혼합-방식)에서 정의한 HPC backfill과 다른 단계로, Volcano 문서는 자원 요청이 없는(BestEffort) 파드를 배치하는 단계로 설명한다 |
| plugin | gang, priority, drf, proportion, predicates, nodeorder, binpack 등. 각 plugin은 세션에 콜백 함수(JobOrderFn, JobReadyFn, PredicateFn, NodeOrderFn 등)를 등록하고, action이 그 콜백을 호출한다 |
| 설정 | `volcano-scheduler` ConfigMap의 `actions`와 `tiers`. 프로필 개념은 없고, 정책은 Queue로 나눈다 |

### 동작 흐름

Volcano는 주기(기본 1초)마다 클러스터 스냅샷으로 세션을 열고(OpenSession), action을 순서대로 실행한 뒤 세션을 닫는다(CloseSession).

- **enqueue**: Queue의 용량이 부족한 PodGroup은 스케줄링 대상(Inqueue 상태)으로 넘기지 않는다. admission 레이어(①)에 해당한다
- **allocate**: Queue → 잡 → 태스크(파드) 순으로 고르고, 노드 필터·점수를 계산해 잡에 속한 태스크들을 **가상으로 배치해 본다**. 그룹의 최소 인원(PodGroup의 `minMember`, Volcano Job에서는 `minAvailable`)을 채우면 확정(commit)하고, 채우지 못하면 바인딩 전에 취소(discard)한다. 그룹 단위 사이클(②)에 해당한다

`kube-scheduler`는 파드가 흐름의 단위이고, Volcano는 세션과 잡이 흐름의 단위다. 그래서 "잡 전체를 가상 배치한 뒤 확정하거나 되돌리는" 동작이 구조적으로 가능하다. [앞의 Coscheduling 교착 예시](#한계)에서 잡 A와 B가 각자 4장씩 잡는 일이, allocate가 잡 하나의 배치를 끝까지 계산한 뒤 확정하는 구조에서는 생기지 않는다.

### Queue

Volcano의 Queue는 사용자가 만드는 CRD로, 정책과 자원 분배의 단위다.

| 속성 | 뜻 |
| --- | --- |
| `capability` | 큐가 쓸 수 있는 자원 상한 |
| `weight` | 큐 간 자원 분배 비율(proportion 플러그인) |
| `reclaimable` | 빌려준 자원을 다른 큐가 회수해 갈 수 있는지 여부. reclaim action과 연결된다 |

Volcano는 gang, 잡 단위 큐잉, 쿼터(capability), 대여·회수(reclaim)를 자체로 제공한다. 선점·회수 action은 기본 설정(`enqueue, allocate, backfill`)에 없어 추가해야 하고, 기존 `preempt`·`reclaim`은 victim을 태스크 단위로 고른다. 잡 단위로 victim을 고르는 `gangPreempt`·`gangReclaim`은 v1.15.0에서 alpha로 추가된 별도 action이다. 대신 `volcano-scheduler`, 컨트롤러, admission webhook 등 운영할 컴포넌트가 늘고, 파드마다 Volcano PodGroup이 있어야 한다. 학습 잡 오퍼레이터(KubeRay, Training Operator, MPI Operator, Kubeflow Trainer)는 Volcano 연동을 켜면 PodGroup을 만들어 주므로, 파드를 직접 만드는 워크로드만 Volcano Job이나 PodGroup 기준으로 바꾸면 된다. 기본 스케줄러와 같은 노드를 쓰면 자원 뷰 충돌도 생길 수 있다([아래 스케줄러 구성별 충돌](#스케줄러-구성별-충돌)).

<br>

# admission 레이어: Kueue

## Kueue의 위치와 구성

Kueue는 파드를 스케줄러에 넘기기 전에 잡을 들여보낼지 정하는 워크로드 admission 컨트롤러다. 이름에 admission이 들어가지만 API Server의 admission controller(웹훅·플러그인)와는 다른 것이다. 잡을 대기 상태로 두었다가 쿼터와 용량이 허락할 때 풀어 주고, 실제 노드 배치는 뒤에 있는 스케줄러가 한다. 기본 동작에서는 노드를 고르지 않고, 바인딩도 하지 않으므로 스케줄러가 아니다. 다만 Topology Aware Scheduling(TAS, v0.14부터 beta, 기본 활성)을 쓰면 Kueue가 노드·토폴로지 도메인별 남은 용량을 직접 계산해 그룹 전체가 들어갈 때만 admission하고, 토폴로지의 최하위 레벨이 노드이면 파드별 노드를 정해 nodeSelector로 넣는다. 이때도 바인딩은 `kube-scheduler`가 한다.

| 구성 요소 | 역할 |
| --- | --- |
| ClusterQueue | 자원 쿼터와 정책을 정의하는 클러스터 단위 큐 |
| LocalQueue | 네임스페이스 안에서 잡이 제출되는 진입점. ClusterQueue를 가리킨다 |
| ResourceFlavor | GPU 기종 등 자원 종류의 구분 |
| Cohort | ClusterQueue를 묶는 단위. 같은 cohort 안에서 남는 쿼터를 빌려 주고 빌려 쓴다 |

## 지원 기능

- **잡 단위 큐잉**: 잡 전체가 쿼터에 들어갈 때만 admission한다
- **대여(borrowing/lending)**: 같은 cohort에 묶인 ClusterQueue끼리 남는 쿼터를 빌려 쓰고, 원래 주인이 필요해지면 회수한다
- **선점**: 워크로드 단위로 선점하므로 gang 일부만 쫓아내지 않는다. 큐 안의 우선순위와 cohort 회수 기준으로 동작한다
- **공정 분배(fair sharing)**: cohort 안에서 큐 간 자원을 공정하게 나눈다
- **waitForPodsReady**: admission 뒤 잡의 파드가 모두 Ready가 되는지 지켜보고, `timeout` 안에 되지 않으면 잡을 내리고 백오프를 두어 다시 큐에 넣는다. Kueue 문서는 이 기능을 부분 배정을 막는 장치가 아니라, 부분 배정된 잡이 자원을 무한정 붙잡지 않게 하는 휴리스틱으로 설명한다. 두 잡이 반씩 배치되어 서로 막는 상황을 막는 것은 `blockAdmission: true`로, 앞서 admission된 워크로드의 파드가 모두 Ready가 될 때까지 모든 ClusterQueue의 다음 admission을 멈춘다(기본 false. 그만큼 admission이 직렬화된다). 실행 중 파드를 잃은 잡도 `recoveryTimeout`이 지나면 잡 전체가 축출된다

Kueue는 바인딩을 하지 않으므로 뒤에 붙는 스케줄러가 필요하다. Kueue 문서는 `kube-scheduler`를 전제로 all-or-nothing을 쿼터 일괄 예약, TAS, ProvisioningRequest, waitForPodsReady의 조합으로 설명한다. Coscheduling이나 네이티브 gang scheduling과 함께 쓰는 구성은 Kueue 문서에서 확인하지 못했고, 이 글의 검증 범위 밖이다. 세부 필드와 기본값은 버전 문서로 확인이 필요하다.

## 쿼터와 실제 용량의 불일치

Kueue가 관리하지 않는 워크로드가 같은 노드를 쓰면, Kueue는 쿼터상 들어갈 수 있다고 보고 잡을 들여보내는데 실제로는 자리가 없어 파드가 Pending에 머물 수 있다. 바인딩 충돌이 아니라 **쿼터와 실제 용량이 어긋나는 문제**다. Kueue의 쿼터는 실제 노드 용량이 아니라 ClusterQueue에 적은 값이기 때문이다. [아래 스케줄러 구성별 충돌](#스케줄러-구성별-충돌)의 자원 뷰 충돌과는 다른 문제다. Kueue 문서는 이 불일치의 대책으로 TAS를 권한다. TAS는 Kueue가 관리하지 않는 파드의 사용량까지 빼서 용량을 계산하므로, TAS 플레이버 안에서는 쿼터상 들어가지만 노드에 자리가 없는 경우를 admission 단계에서 거른다.

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
| **kube-scheduler 변경** | 대체 또는 병행 (별도 구현 스케줄러) | 수정하지 않음 (`kube-scheduler` 그대로) |
| **어떻게 동작** | 자체 스케줄링 로직 전체 구현 | admission 단계에서 "언제 스케줄링 큐에 넣을지" 제어 |
| **추가 바이너리** | volcano-scheduler, volcano-controller, admission webhook | kueue-controller만 |
| **프로필 사용** | 프로필 개념이 없다. ConfigMap의 `actions`·`tiers` 하나와 Queue로 정책을 나눈다 | `kube-scheduler`의 기본 프로필을 그대로 쓴다 |
| **race condition** | 별도 프로세스라 자원 뷰 충돌 가능 | kube-scheduler가 유일한 스케줄러라면 충돌 없음 |

Kueue가 파드를 붙잡아 두는 수단은 워크로드 종류에 따라 다르다.

| 워크로드 | 제어 수단 |
| --- | --- |
| batch/v1 Job 등 suspend를 지원하는 리소스 | webhook으로 `.spec.suspend`를 `true`로 두고, 자원이 확보되면 `false`로 바꾼다 |
| plain 파드 (파드 계열 integration) | [3편에서 다룬 Scheduling Gate]({% post_url 2025-11-05-Kubernetes-Scheduling-03 %}#scheduling-gate)(`kueue.x-k8s.io/admission`)를 주입하고, 자원이 확보되면 제거한다 |

어느 쪽이든 공통점은 **스케줄러 앞단에서 진입 시점만 제어한다**는 것이다. 큐 정책(fair-share, borrowing/lending 등)에 따라 언제 풀어 줄지를 Kueue가 판단하고, 실제 노드 선택은 기본 스케줄러(`kube-scheduler`)가 한다. 스케줄러가 하나뿐이므로 자원 뷰 충돌이 설계 단계에서 발생하지 않는다. 다만 Kueue 뒤에 두 번째 스케줄러를 두면, 충돌 여부는 그 스케줄러 구성에 따라 갈린다.

## Kueue와 Volcano 조합

Kueue와 Volcano를 꼭 같이 써야 하는 것은 아니다.

- Volcano는 Queue CRD와 enqueue action으로 admission 성격의 기능(①)과 그룹 배치(②)를 함께 가지고 있어 단독으로도 쓰인다
- Kueue는 배치를 하지 않으므로 뒤에 붙는 스케줄러가 필요하다
- 둘을 함께 쓰면 큐와 쿼터 관리가 두 곳에서 겹치므로, 조합한다면 어느 쪽이 큐·쿼터를 맡을지 역할을 나눠야 한다

<br>

# 도입 시 고려 사항

## 워크로드 컨트롤러 연동

gang 스케줄러가 동작하려면 그룹 오브젝트(PodGroup, Workload)와 파드 쪽 표시(`schedulerName`, 그룹 라벨, `spec.schedulingGroup`)가 있어야 한다. 사용자가 파드를 직접 만들지 않고 워크로드 컨트롤러(Job, JobSet, KubeRay 등)가 파드를 만드는 경우, 이 둘을 누가 만드는지가 실제 적용의 관건이다.

KubeRay가 대표적인 예다. KubeRay 오퍼레이터는 `batch-scheduler` 설정으로 연동할 스케줄러를 고르면, RayCluster의 파드를 만들 때 해당 스케줄러가 요구하는 그룹 오브젝트와 파드 쪽 표시를 함께 만든다.

| 연동 대상 | 지원 시작 | 방식 |
| --- | --- | --- |
| Volcano | v0.4.0 | Volcano의 PodGroup을 만들고 파드에 `schedulerName: volcano`를 지정 |
| YuniKorn | v1.2.2 | YuniKorn의 애플리케이션·태스크 그룹 표시를 붙임 |
| scheduler-plugins(Coscheduling) | v1.4.0 | RayCluster에 `ray.io/gang-scheduling-enabled: "true"` 라벨이 있으면 Coscheduling PodGroup을 자동 생성. scheduler-plugins를 단일 스케줄러로 쓰는 구성만 지원 |
| KAI Scheduler | v1.5.0 | KAI Scheduler 연동 |
| 네이티브 Workload API | v1.7.0 | `batch-scheduler`가 아니라 KubeRay feature gate `KubernetesWAS`(alpha, 기본 비활성)로 켠다. `scheduling.k8s.io/v1alpha2` Workload·PodGroup을 만들고 파드에 `schedulingGroup`을 지정한다. `batch-scheduler`와 함께 쓸 수 없다 |

학습 잡 오퍼레이터도 같은 방식이다. Training Operator v1은 `--gang-scheduler-name`, MPI Operator는 `--gang-scheduling` 플래그로 volcano 또는 scheduler-plugins를 고르고, Kubeflow Trainer v2는 런타임의 `podGroupPolicy`에 coscheduling 또는 volcano를 적는다. KubeRay는 오토스케일링을 켜면 그룹의 최소 인원과 자원을 `minReplicas` 기준으로 계산하므로, 오토스케일러가 늘린 워커는 gang 조건 밖에서 배치된다.

여기서 두 가지를 알 수 있다.

- **쿠버네티스 버전을 올리는 것만으로는 네이티브 gang scheduling이 동작하지 않는다.** 그룹 오브젝트를 만들고 파드에 `schedulingGroup`을 넣는 쪽(워크로드 컨트롤러)도 같은 API 버전을 지원해야 한다. CRD 안에 파드 템플릿을 담는 워크로드(RayCluster 등)는 템플릿 스키마가 컨트롤러를 빌드할 때의 쿠버네티스 API 버전으로 고정되므로, 템플릿에 새 파드 필드를 적어도 저장 시 잘려 나갈 수 있다. 위 KubeRay v1.7.0의 경우 오퍼레이터가 파드를 만들 때 직접 필드를 넣는 방식이다
- **컨트롤러가 지원하는 API 버전과 클러스터가 서빙하는 버전을 맞춰야 한다.** v1.36은 Workload·PodGroup을 `v1alpha2`로, v1.37은 `v1beta1`과 `v1alpha3`으로 서빙한다. v1.37 소스에는 `v1alpha2`가 없으므로, `v1alpha2` 오브젝트를 만드는 KubeRay v1.7.0의 네이티브 연동은 v1.36 클러스터에서만 쓸 수 있다. v1.37에서 쓰려면 `v1beta1`(또는 `v1alpha3`)을 지원하는 KubeRay 릴리스가 필요하다

<br>

## 스케줄러 구성별 충돌

[1편 - 자원 뷰 충돌]({% post_url 2025-11-05-Kubernetes-Scheduling-01 %}#자원-뷰-충돌)에서 본 것처럼, 서로의 예약(assumed)을 모르는 스케줄러가 같은 노드를 나눠 쓰면 같은 자원을 동시에 골라 충돌할 수 있다. 결론부터 말하면, 충돌 여부를 가르는 것은 "스케줄러가 여러 개 떠 있는가"가 아니라 "서로의 예약을 모르는 스케줄러가 같은 노드 풀을 나눠 쓰는가"다. 프로필이 여러 개인 것은 스케줄러가 여러 개인 것과 다르다.

| 구성 | 충돌 가능성 | 이유 |
| --- | --- | --- |
| Kueue | Kueue 자체는 없음 | 바인딩을 하지 않고, 잡을 대기 상태에서 풀어 줄지만 정한다. 실제 배치는 뒤의 스케줄러가 하므로, 그 스케줄러 구성에 따라 충돌 여부가 갈린다 |
| Coscheduling(커스텀 빌드 kube-scheduler)을 두 번째 스케줄러로 운영 | 있음, 큰 편 | Permit에서 기다리는 동안(타임아웃까지) 잡아 둔 자원을 기본 스케줄러가 알 수 없다. 대기 시간만큼 충돌 가능 구간이 길어진다 |
| Coscheduling(커스텀 빌드 kube-scheduler)을 유일한 스케줄러로 운영(기본 스케줄러 교체) | 없음 | 프로세스가 하나라 캐시를 공유한다. 프로필이 여러 개여도 문제없다 |
| 네이티브 gang scheduling | 없음 | 기본 `kube-scheduler` 안에서 동작해 캐시가 하나다. 단, Volcano 등 다른 스케줄러를 같은 노드에서 함께 쓰면 다시 충돌이 생길 수 있다 |
| Volcano + 기본 스케줄러 | 있음 | 구조는 같다. Volcano는 세션을 열 때 찍은 스냅샷으로 결정하므로, 세션이 도는 동안 기본 스케줄러가 바인딩한 결과를 보지 못한다. Coscheduling의 Permit 대기와 비교한 충돌 구간의 길이는 검증 범위 밖이다 |

조사 결과 검토할 수 있는 대책은 두 가지다(검증 범위 밖).

- **노드 풀 분리**: 그룹 워크로드용 노드를 taint·nodeSelector로 분리해, 그 풀의 일반 워크로드는 gang 스케줄러만 배치하게 한다. 다만 DaemonSet 파드와 모든 taint를 tolerate하는 파드는 기본 스케줄러가 계속 그 풀에 배치하므로, GPU 충돌은 피해도 CPU·메모리 충돌 가능성은 남는다. Omega 분류로는 statically partitioned에 가까워져, 풀 사이에 자원을 나눠 쓰지 못한다
- **스케줄러 하나로 통합**: 한 프로세스 안의 여러 프로필은 캐시를 공유하므로 충돌이 없다. 다만 기본 스케줄러를 교체할 수 있는 환경이어야 하고, QueueSort를 바꾸는 플러그인은 모든 프로필의 큐 정렬을 바꾼다([1편 - 커스텀 빌드 kube-scheduler 배포 방식]({% post_url 2025-11-05-Kubernetes-Scheduling-01 %}#커스텀-빌드-kube-scheduler-배포-방식))

<br>

## bin packing과 affinity의 위치

gang scheduling은 "다 같이 놓을 수 있나"를 풀고, "어디에 놓을까"는 배치 정책(Score)이 따로 푼다. 둘을 함께 쓸 때 위치를 정해야 하는 설정이 있다.

- **bin packing**: `NodeResourcesFit`의 `scoringStrategy`를 MostAllocated나 RequestedToCapacityRatio로 바꾸고 `nvidia.com/gpu`에 가중치를 준다([4편 - 해결: MostAllocated 또는 RequestedToCapacityRatio]({% post_url 2025-11-05-Kubernetes-Scheduling-04 %}#해결-mostallocated-또는-requestedtocapacityratio)). GPU를 일부 노드에 몰아 채워 큰 잡이 통째로 들어갈 빈 노드를 남기므로, gang 대기와 단편화를 줄이는 방향이다
- **pod affinity·토폴로지**: 같은 잡의 워커를 가까운 토폴로지에 두는 방법으로 preferred pod affinity를 생각할 수 있지만, 파드 단위 사이클에서는 먼저 놓인 파드를 뒤 파드가 따라가는 방식이라 그룹 전체의 배치를 보장하지 않는다. 노드를 통째로 쓰는 학습 파드라면 같은 노드 affinity는 의미가 없고, 랙·NVLink 같은 토폴로지 배치가 필요하다. 그룹 단위 토폴로지 배치는 Kueue TAS([3편 - 사례: Kueue TAS의 배치 주입]({% post_url 2025-11-05-Kubernetes-Scheduling-03 %}#사례-kueue-tas의-배치-주입)), Volcano의 HyperNode 기반 배치, 네이티브 KEP-5732가 다룬다(Volcano·KEP-5732는 검증 범위 밖). `requiredDuringScheduling`은 조건을 맞추지 못하면 파드가 계속 Pending이 되고, gang과 함께 쓰면 Permit 대기를 길게 만들 수 있다

kube-scheduler 계열에서 bin packing(`NodeResourcesFit`의 `scoringStrategy`)은 프로필 설정이므로 **그룹 파드가 쓰는 프로필**에 두어야 한다. 그룹 파드는 자기 `schedulerName`의 프로필로 스케줄링되므로(Coscheduling이면 커스텀 빌드 kube-scheduler의 프로필, 네이티브 gang scheduling이면 보통 `default-scheduler`), 다른 프로필에만 bin packing을 넣으면 그룹 파드에는 적용되지 않는다. pod affinity는 프로필이 아니라 파드 스펙 필드이므로, 파드를 만드는 워크로드 컨트롤러의 템플릿에 넣어야 한다. 프로필에서는 `InterPodAffinity` 플러그인이 켜져 있는지(기본 활성)와 가중치만 정한다. 프로필 개념이 없는 Volcano는 `volcano-scheduler` ConfigMap의 `tiers`에 binpack·nodeorder 플러그인을 둔다. 반대로 그룹 워크로드용 프로필에만 bin packing을 적용하면 다른 워크로드에는 영향이 없다. bin packing은 배치 시점의 점수만 바꿀 뿐, 이미 단편화된 상태를 재배치하지는 않는다(재배치는 Descheduler 영역이다).

<br>

## 도구 비교

| 도구 | 레이어 | gang | 잡 단위 큐잉 | 쿼터 | 대여 | gang 인지 선점 |
| --- | --- | --- | --- | --- | --- | --- |
| Coscheduling | ③ | O (Permit 대기) | X | X | X | X |
| 네이티브 gang scheduling | ③(v1.35) → ②(v1.36+) | O | X | X | X | v1.36+ (KEP-5710, 기본 비활성) |
| 배치 보완(bin packing, affinity) | 배치 정책 | X | X | X | X | X |
| Kueue | ① | admission 수준(쿼터 일괄 예약, TAS, waitForPodsReady·blockAdmission) | O | O | O (cohort) | O (워크로드 단위) |
| Volcano | ①·② | O | O | O (capability) | O (reclaim) | △ (v1.15+ `gangPreempt`·`gangReclaim`, alpha. 기존 preempt·reclaim은 태스크 단위) |

용도별로 나누면 다음과 같다. 조사 결과에 따른 정리이고, 실제 도입으로 검증한 범위는 아니다.

- **경합이 낮고 부분 배정만 막으면 되는 경우**: gang scheduling과 배치 보완만 적용한다(Coscheduling 또는 네이티브 gang scheduling). 네이티브는 kube-apiserver·kube-controller-manager·kube-scheduler 설정이 필요해 컨트롤 플레인 설정에 접근할 수 있어야 한다. 관리형 컨트롤 플레인에서는 Coscheduling을 두 번째 스케줄러로 띄우게 되므로 [노드 풀 분리](#스케줄러-구성별-충돌)를 함께 검토한다
- **여러 팀이 GPU를 두고 경합하는 경우**: 위에 admission(Kueue)을 더한다
- **큐, 쿼터, gang을 한 도구로 처리하고 싶은 경우**: Volcano를 단독으로 쓴다. 기본 스케줄러와의 충돌 조건을 함께 고려한다

<br>

# 정리

이 글에서 다룬 핵심 내용을 정리한다.

1. **`kube-scheduler`는 잡이라는 단위를 모른다.** 큐잉, 배치, 선점이 모두 파드 단위라 그룹 워크로드에서 부분 배정이 생기고, 잡 단위 대기·쿼터·선점을 표현할 수 없다.
2. **gang scheduling은 세 레이어에서 풀 수 있다.** admission(①), 그룹 단위 스케줄링 사이클(②), 파드 단위 사이클의 확정 지점 제어(③)이고, 배치 정책은 별도의 문제다. ①은 ②·③을 보완하고, ②와 ③은 같은 문제를 다른 방식으로 푼다.
3. **Coscheduling은 ③이다.** 커스텀 빌드 kube-scheduler에서 Permit으로 바인딩을 미룬다. 스케줄러 안에서 자원을 잡아 두므로 그룹끼리 경쟁하면 잡았다 반납하는 경합이 반복될 수 있고(`minResources`로 완화), 두 번째 스케줄러로 띄우면 기본 스케줄러와의 충돌 구간이 길어진다.
4. **v1.35에서 기본 스케줄러의 네이티브 gang scheduling(alpha)이, v1.36에서 PodGroup 단위 스케줄링 사이클이 도입되었다.** 그룹에 속한 파드는 별도 사이클로 분기하여, `minCount` 이상 배치할 수 있으면 bind하고 아니면 전부 반환하는 atomic 결정을 받는다. v1.36까지는 alpha였고, v1.37에서 `GenericWorkload` beta(기본 비활성)로 합쳐졌다. placement extension point는 KEP-5732로 여전히 alpha다.
5. **Volcano는 별도 구현 스케줄러다.** 주기적 세션 안에서 잡 전체를 가상 배치해 commit 또는 discard하므로 ②를 구조적으로 지원하고, Queue로 ①도 함께 맡는다.
6. **Kueue는 스케줄러가 아니다.** 잡을 들여보낼 시점을 정하는 워크로드 admission 컨트롤러로, 쿼터·대여·워크로드 단위 선점을 맡고 노드 배치는 뒤의 스케줄러에 맡긴다. Kueue는 suspend와 Scheduling Gate로 진입 시점을 제어하므로 그 자체로는 race condition이 없다.
7. **도입할 때는 워크로드 컨트롤러 연동, 스케줄러 구성별 충돌, 배치 설정의 위치를 함께 본다.** 그룹 오브젝트를 만드는 쪽이 같은 API를 지원해야 하고, 서로의 예약을 모르는 스케줄러가 같은 노드 풀을 나눠 쓰면 충돌할 수 있으며, bin packing은 그룹 파드를 처리하는 스케줄러의 설정(kube-scheduler 계열은 그 프로필, Volcano는 `tiers`)에 두어야 한다.

시리즈 전체의 편별 구성은 [0편 - 시리즈 구성]({% post_url 2025-11-05-Kubernetes-Scheduling-00 %}#시리즈-구성)에 있다.

<br>

# 참고 링크

- [KEP-4671: Gang Scheduling](https://github.com/kubernetes/enhancements/tree/master/keps/sig-scheduling/4671-gang-scheduling)
- [KEP-5732: Topology-aware workload scheduling](https://github.com/kubernetes/enhancements/tree/master/keps/sig-scheduling/5732-topology-aware-workload-scheduling)
- [KEP-5710: Workload-aware preemption](https://github.com/kubernetes/enhancements/tree/master/keps/sig-scheduling/5710-workload-aware-preemption)
- [Gang Scheduling - Kubernetes 공식 문서](https://kubernetes.io/docs/concepts/scheduling-eviction/gang-scheduling/)
- [PodGroup Scheduling - Kubernetes 공식 문서](https://kubernetes.io/docs/concepts/scheduling-eviction/podgroup-scheduling/)
- [Kubernetes v1.37: Advancing Workload-Aware Scheduling - Kubernetes Blog](https://kubernetes.io/blog/2026/09/08/kubernetes-v1-37-advancing-workload-aware-scheduling/)
- [kubernetes-sigs/scheduler-plugins - Coscheduling](https://scheduler-plugins.sigs.k8s.io/docs/plugins/coscheduling)
- [scheduler-plugins KEP: Coscheduling based on PodGroup CRD](https://github.com/kubernetes-sigs/scheduler-plugins/blob/master/kep/42-podgroup-coscheduling/README.md)
- [Volcano - High Performance Batch System](https://volcano.sh/)
- [Kueue - Job Queueing](https://kueue.sigs.k8s.io/)
- [Kueue - Run Plain Pods](https://kueue.sigs.k8s.io/docs/tasks/run/plain_pods/)
- [KubeRay - Gang scheduling with scheduler-plugins](https://docs.ray.io/en/latest/cluster/kubernetes/k8s-ecosystem/scheduler-plugins.html)
- [KubeRay - YuniKorn](https://docs.ray.io/en/latest/cluster/kubernetes/k8s-ecosystem/yunikorn.html)

<br>
