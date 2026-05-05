---
title:  "[Kubernetes] 쿠버네티스 스케줄링 - 2. 프로세스와 선점"
excerpt: "Kubernetes 스케줄러의 파드 배치 프로세스와 선점 메커니즘에 대해 알아보자."
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
  - Preemption
  - Filter
  - Score
  - Plugin
---

<br>

# TL;DR

- Scheduling Framework는 **코어(오케스트레이터)를 가볍게 유지**하고, 구체적인 판단 로직은 모두 플러그인에 격리하는 설계다. 플러그인은 Go 패키지로 구현되어 스케줄러 바이너리에 함께 컴파일되며(in-process), 이는 성능과 상태 공유를 위한 의도적 결정이다.
- 쿠버네티스 스케줄링 프레임워크는 **Scheduling Cycle**(PreFilter → Filter → PostFilter → PreScore → Score → NormalizeScore → Reserve → Permit)과 **Binding Cycle**(PreBind → Bind → PostBind)로 구성된다. 각 단계는 **extension point**로, 플러그인을 등록하여 스케줄링 로직을 구성한다.
- **Filter**는 부적합 노드를 탈락시키고(리소스, 배치 규칙, 볼륨 등), **Score**는 통과 노드에 0~100 점수를 가중 합산하여 최적 노드를 선택한다. 필터링에서 적합 노드가 하나뿐이면 Score 단계를 거쳐도 결과는 동일하다(해당 노드가 선택됨).
- 하나의 플러그인이 여러 extension point에 등록될 수 있다. v1.32 기준 `TaintToleration`, `NodeAffinity`, `NodeResourcesFit` 등이 Filter와 Score 양쪽에 등록된다.
- 큐의 재시도 효율화를 위해 **EnqueueExtension**과 **QueueingHint**가 2단계 필터링으로 동작한다. 플러그인이 "의미 있는 이벤트"를 선언하고, 콜백 함수가 구체적 이벤트 인스턴스의 관련성을 판단하여 불필요한 재시도를 최소화한다.
- **선점(Preemption)**: 모든 노드가 부적합할 때, PostFilter 단계에서 낮은 우선순위 파드를 축출하여 공간을 확보한다. 선점이 동작하려면 `PriorityClass`가 정의되어 있어야 한다.
- `nominatedNodeName`은 선점 후 다른 파드가 해당 공간에 끼어드는 것을 방지하는 예약 마커이며, 해당 노드에 반드시 스케줄링된다는 보장은 없다.

<br>

# 들어가며

[이전 글]({% post_url 2025-11-05-Kubernetes-Scheduling-01 %})에서 스케줄링의 기본 개념, 스케줄링 대상, 스케줄러 큐 구조에 대해 알아보았다. 이번 글에서는 다음 네 가지를 다룬다.

1. **스케줄링 프레임워크 아키텍처**: lightweight core 설계 철학, in-process compilation 결정, interface와 extension point의 관계
2. **전체 Extension Point**: Scheduling Cycle과 Binding Cycle의 모든 extension point(PreEnqueue → Sort → PreFilter → Filter → PostFilter → PreScore → Score → NormalizeScore → Reserve → Permit → PreBind → Bind → PostBind)와 각 단계의 역할, 큐 재시도 메커니즘(EnqueueExtension, QueueingHint)
3. **스케줄링 플러그인**: 각 extension point에 등록되는 기본 플러그인(v1.32 기준) 목록과 동작 원리
4. **선점 메커니즘**: PriorityClass 기반의 선점이 동작하는 방식, `nominatedNodeName`의 역할과 한계

스케줄러가 *어떤 단계*를 거쳐 노드를 선택하는지, 모든 노드가 부적합할 때 *어떻게* 선점이 동작하는지를 이해하면, 파드가 Pending 상태에 빠졌을 때 원인을 빠르게 좁혀 나갈 수 있다.



<br>

# 스케줄링 프레임워크

쿠버네티스 스케줄러는 [Scheduling Framework](https://kubernetes.io/docs/concepts/scheduling-eviction/scheduling-framework/)라는 플러그인 기반 아키텍처로 동작한다. 프레임워크는 여러 **extension point**를 정의하고, 각 extension point에 플러그인을 등록하여 스케줄링 로직을 구성한다. 하나의 플러그인이 여러 extension point에 동시에 등록될 수 있다(예: `TaintToleration`은 Filter, PreScore, Score에 등록).

<br>

## 프레임워크 아키텍처

### Lightweight Core 설계 철학

Scheduling Framework의 핵심 설계 원칙은 **코어를 가볍게 유지**하는 것이다. 여기서 "가벼움"이란 바이너리 크기가 아니라, **코어가 담당하는 책임(로직)이 최소화**되었다는 아키텍처 차원의 의미다.

- **코어(Scheduling Framework)**: 스케줄링 사이클의 순서를 관리하는 오케스트레이터. QueueSort → PreFilter → Filter → … → PostBind까지 어떤 순서로 누구를 호출할지만 알고, 구체적인 판단 로직은 전혀 없다.
- **플러그인**: 실제 판단 로직을 구현한다. `NodeResourcesFit`, `TaintToleration`, `NodeAffinity`, `InterPodAffinity`, `VolumeBinding` 등이 각자의 extension point에서 동작한다.

프레임워크 도입 이전에는 스케줄러 코어 코드 안에 모든 filtering, scoring 로직이 직접 들어가 있었다.

```go
// 프레임워크 이전: 코어 코드에 모든 로직이 직접 구현
if !checkNodeResources(pod, node) { return false }
if !checkTaints(pod, node) { return false }
if !checkAffinity(pod, node) { return false }
// 새 기능 추가? → 코어 코드를 직접 수정해야 함
```

프레임워크 도입 이후, 코어는 등록된 플러그인을 순서대로 호출하는 루프만 돌린다.

```go
// 프레임워크 이후: 코어는 플러그인 호출 루프만 담당
for _, plugin := range profile.FilterPlugins {
    status := plugin.Filter(ctx, state, pod, nodeInfo)
    if !status.IsSuccess() { return }
}
```

기능 하나를 추가하거나 수정할 때 코어 전체를 이해하고 건드릴 필요 없이, 해당 플러그인만 구현하면 된다. 코어 코드 자체는 수백 줄 수준으로 얇아졌다.

<br>

### In-Process Compilation

플러그인들은 Go 패키지로 구현되어 **스케줄러 바이너리에 함께 컴파일**된다. 런타임에 동적으로 로드하는 방식이 아니다. 이것은 의도적인 설계 결정이다.

Kubernetes 초기에는 **Scheduler Extender**라는 웹훅 기반 외부 프로세스 방식이 있었으나, 다음과 같은 문제가 있었다.

| 문제 | 설명 |
| --- | --- |
| HTTP 호출 오버헤드 | 노드 수천 개 × Pod 수천 개 filtering마다 네트워크 왕복. 성능에 치명적 |
| 에러 핸들링 복잡 | 외부 프로세스가 죽으면 스케줄러 전체가 멈춤 |
| 상태 공유 불가 | PreFilter에서 계산한 결과를 Filter에서 재사용할 수 없음 |

이러한 문제를 해결하기 위해, **성능과 안전성을 위해 같은 프로세스에 넣되, 인터페이스로 관심사를 분리하여 코어를 가볍게 유지하는 전략**을 선택했다. 같은 프로세스 안이므로 함수 호출로 플러그인을 실행하고, `CycleState`를 통해 extension point 간 상태를 공유할 수 있다.

<br>

### Interface와 Extension Point

Scheduling Framework가 정의하는 **Go 인터페이스**와, 운영자가 `KubeSchedulerConfiguration`에서 조작할 수 있는 **extension point**는 1:1이 아니다.

```
Interface (Go 인터페이스, 플러그인이 구현할 수 있는 것)
├── Extension Point (Scheduler Configuration에 노출된 것) ← "Extensible API"
│   └─ QueueSort, PreFilter, Filter, PostFilter, PreScore,
│      Score, NormalizeScore, Reserve, Permit, PreBind, Bind, PostBind
│
└── 내부 인터페이스 (설정에 노출 안 된 것) ← "Internal API"
    └─ PreEnqueue, EnqueueExtensions, WaitOnPermit 등
```

- **Extension Point(Extensible API)**: `KubeSchedulerConfiguration`의 `plugins` 섹션에서 enable/disable/weight 조정이 가능하다. 클러스터 운영자와 플러그인 개발자 모두의 관심사다.
- **내부 인터페이스(Internal API)**: 프레임워크가 내부적으로 호출하며, YAML 설정으로 조작할 수 없다. 플러그인 개발자만 관심을 가진다.

위에서 본 `kubernetes-scheduling-framework.png` 그림의 **초록색 실선**(Extensible API)이 설정 가능한 extension point, **주황색 점선**(Internal API)이 설정 불가능한 내부 인터페이스에 해당한다.

실무적으로는 interface ≈ extension point로 이해해도 크게 문제없다. 대부분의 인터페이스가 extension point이고 내부 전용인 것은 소수이기 때문이다. 다만 정확히는, **extension point는 interface의 부분집합(= configurable한 것들)**이다.

<br>

### 참고: Scheduling Policies (레거시)

현재의 Scheduling Framework 이전에는 **Scheduling Policies**라는 방식으로 스케줄러의 filtering과 scoring을 설정했다. Predicates(Filtering 단계의 boolean 평가식)와 Priorities(Scoring 단계의 점수 함수)를 정의하는 구조였다.

- **Predicates**: "이 노드에 이 Pod를 놓을 수 있는가"에 대한 `true/false` 판정. 예: `PodFitsResources`, `MatchNodeSelector`, `NoTaintsTolerated`
- **Priorities**: feasible 노드들에 0~10 점수를 매기고, 가중치를 곱하여 최고 점수 노드를 선택. 예: `LeastRequestedPriority`, `BalancedResourceAllocation`, `ImageLocalityPriority`

이 방식은 v1.23부터 deprecated되었으며, 현재는 **Scheduling Profiles + Scheduling Framework**가 표준이다. 개념적으로 filtering/scoring 2단계는 동일하나, 단순한 predicate/priority 함수 목록이 아니라 plugin point 기반으로 세분화된 것이 핵심 차이다.

<br>

## 전체 구조: Scheduling Cycle과 Binding Cycle

하나의 파드를 스케줄링하는 과정은 **Scheduling Cycle**과 **Binding Cycle**, 두 단계로 나뉜다. 이 둘을 합쳐 하나의 **Scheduling Context**라고 한다.

- **Scheduling Cycle**: 파드에 적합한 노드를 선택하는 단계. **직렬**로 실행된다(한 번에 하나의 파드만 처리).
- **Binding Cycle**: 선택된 노드에 파드를 실제로 바인딩하는 단계. **병렬**로 실행될 수 있다.

![kubernetes-scheduling-framework]({{site.url}}/assets/images/kubernetes-scheduling-framework.png){: .align-center}
<center><sup>Extension Point 종류와 API 분류 (초록 실선: Extensible API, 주황 점선: Internal API). 출처: <a href="https://kubernetes.io/docs/concepts/scheduling-eviction/scheduling-framework/#interfaces">Kubernetes Docs - Scheduling Framework</a></sup></center>

![kubernetes-scheduling]({{site.url}}/assets/images/kubernetes-scheduling.png){: .align-center}
<center><sup>큐에서 꺼낸 파드가 각 extension point를 거쳐 running 상태가 되기까지의 전체 흐름</sup></center>

두 Cycle 모두, 파드가 스케줄링 불가능하다고 판단되거나 내부 오류가 발생하면 중단된다. 중단된 파드는 큐로 돌아가 재시도된다.

<br>

## 모든 Extension Point

전체 extension point를 순서대로 정리하면 다음과 같다.

### PreEnqueue

파드가 내부 Active Queue에 추가되기 **전에** 호출된다. 모든 PreEnqueue 플러그인이 `Success`를 반환해야 파드가 Active Queue에 진입할 수 있다. 하나라도 실패하면 파드는 내부 Unschedulable 리스트에 배치되며, 스케줄링을 시도하지 않는다.

PreEnqueue는 **Pod이 Active Queue에 진입하려 할 때마다** 호출된다. 새 Pod의 최초 진입뿐 아니라, Backoff Queue에서의 복귀, Unschedulable Pool에서의 복귀 시에도 거친다. "애초에 스케줄링 대상이 될 자격이 있는가"를 판단하는 입구 게이트 역할이다.

| 시나리오 | PreEnqueue 거치나? |
| --- | --- |
| 새 Pod 생성 → 최초 진입 | O |
| Backoff Queue → Active Queue 복귀 | O |
| Unschedulable Pool → Active Queue 복귀 | O |

대표 사용 사례는 [Scheduling Gate](https://kubernetes.io/docs/concepts/scheduling-eviction/pod-scheduling-readiness/)다. Pod에 `spec.schedulingGates`가 설정되어 있으면 PreEnqueue 플러그인이 Success를 반환하지 않아 Active Queue에 진입할 수 없다. 외부 컨트롤러가 gate를 제거해야 비로소 스케줄링이 시작된다. Scheduling Gate의 구체적인 사용법은 [3편 - 스케줄링 제어]({% post_url 2025-11-05-Kubernetes-Scheduling-03 %})에서 다룬다.

<br>

### EnqueueExtension과 QueueingHint

PreEnqueue와 마찬가지로 `KubeSchedulerConfiguration`에 노출되지 않는 **내부 인터페이스**다. 큐에서 reject된 파드의 재시도를 효율적으로 관리하기 위한 메커니즘이다.

앞서 본 것처럼 파드는 여러 단계에서 reject될 수 있고, reject된 파드는 Unschedulable Pool에 머문다. 문제는 이 파드를 **언제** 다시 꺼낼지 판단하는 기준이다.

- **문제**: Filter나 Reserve 등의 단계에서 플러그인이 파드를 reject하면, 해당 파드는 Unschedulable Pool로 들어간다. 그런데 이 파드를 언제 다시 꺼내서 스케줄링을 시도해야 할까? 기준이 없다면, 클러스터에서 *아무* 변화(노드 라벨 변경, 새 Pod 삭제 등)가 생길 때마다 모든 unschedulable 파드를 다시 시도해야 한다. 불필요한 재시도 폭증을 초래한다.
- **해결**: `EnqueueExtension` 인터페이스를 구현하면, 플러그인이 "나한테 의미 있는 이벤트가 뭔지"를 선언할 수 있다.

```go
// NodeResourcesFit 플러그인의 EnqueueExtension 구현 (개념적)
func (pl *NodeResourcesFit) EventsToRegister() []ClusterEventWithHint {
    return []ClusterEventWithHint{
        {Event: ClusterEvent{Resource: Pod, ActionType: Delete}},   // Pod 삭제 → 자원 해제
        {Event: ClusterEvent{Resource: Node, ActionType: Add}},     // 노드 추가 → 새 자원
    }
}
```

"내가 reject한 Pod은, **Pod이 삭제되거나 Node가 추가될 때만** 다시 시도해봐"라고 스케줄러에게 알려주는 것이다. 노드 라벨 변경 같은 무관한 이벤트에는 반응하지 않는다.

Pod을 reject할 수 있는 인터페이스(PreEnqueue, PreFilter, Filter, Reserve, Permit)를 구현하는 플러그인은 이 인터페이스도 함께 구현해야 한다. reject할 수 있는 플러그인이기 때문에, "어떤 이벤트에서 재시도하는 게 의미 있는지"를 선언해 줘야 하는 것이다.

`EnqueueExtension`만으로는 이벤트 **타입**까지만 필터링된다. 더 세밀한 판단을 위해 **QueueingHint** 콜백 함수가 존재한다. 둘이 합쳐서 2단계 필터링 메커니즘을 구성한다.

```
1단계: EventsToRegister() → "어떤 종류의 이벤트에 반응할지" (이벤트 타입 필터)
       예: Pod 삭제, Node 추가

2단계: QueueingHintFn() → "이 구체적 이벤트가 이 Pod에 의미 있는가?" (인스턴스 필터)
       예: "삭제된 Pod이 같은 노드에 있었나? 자원이 실제로 해제되나?"
```

```go
func (pl *NodeResourcesFit) EventsToRegister() []ClusterEventWithHint {
    return []ClusterEventWithHint{
        {
            Event: ClusterEvent{Resource: Pod, ActionType: Delete},
            QueueingHintFn: func(pod *Pod, oldObj, newObj interface{}) QueueingHint {
                deletedPod := oldObj.(*Pod)
                if deletedPod.Spec.NodeName == "" {
                    return QueueSkip  // 아직 스케줄링 안 된 Pod → 자원 해제 없음
                }
                return QueueAfterBackoff  // 노드에서 자원 해제됨 → 재시도 가치 있음
            },
        },
    }
}
```

QueueingHint 반환값은 다음과 같다.

| 반환값 | 의미 | Pod 이동 |
| --- | --- | --- |
| `Queue` | 스케줄 가능성 있음 | Active Queue로 |
| `QueueAfterBackoff` | 가능성 있음 (잠깐 대기) | Backoff Queue로 |
| `QueueSkip` | 이 이벤트는 무관함 | 그대로 둠 |

정리하면, [이전 글]({% post_url 2025-11-05-Kubernetes-Scheduling-01 %})에서 "클러스터 이벤트 발생 시 Unschedulable Queue에서 Active Queue로 복귀"라고 설명한 동작의 내부 구현이 바로 이 EnqueueExtension + QueueingHint 메커니즘이다.

<br>

### Sort (QueueSort)

Active Queue 내에서 파드의 정렬 순서를 결정한다. `Less(Pod1, Pod2)` 함수를 제공하여 어떤 파드를 먼저 스케줄링할지 정한다. **한 번에 하나의 QueueSort 플러그인만** 활성화할 수 있다. 기본 플러그인인 `PrioritySort`는 파드 우선순위 기준으로 정렬한다.

### PreFilter

파드 또는 클러스터의 정보를 **사전 처리**하거나, 파드가 만족해야 하는 조건을 확인하는 단계다. PreFilter가 오류를 반환하면 Scheduling Cycle이 즉시 중단된다. v1.26부터는 플러그인이 `Skip` 상태를 반환하여, 해당 플러그인의 Filter 실행을 건너뛸 수 있다(예: 파드에 nodeAffinity가 없으면 NodeAffinity 플러그인의 Filter를 Skip).

### Filter

**부적합한 노드를 탈락시키는 단계**다. 각 노드에 대해 등록된 Filter 플러그인을 순차 실행하며, 하나라도 실패하면 해당 노드는 즉시 탈락한다. 모든 노드가 Filter에서 탈락하면 파드는 Unschedulable로 표시되고 PostFilter가 실행된다.

### PostFilter

정상 흐름(Filter → Score → Bind)에서 벗어나, Filter 단계에서 **적합한 노드가 하나도 없을 때만** 진입하는 실패 경로다. 설정된 순서대로 플러그인이 실행되며, 첫 번째로 성공한 플러그인에서 종료한다. 기본 플러그인인 `DefaultPreemption`이 여기서 선점 로직을 수행하며, 선점의 구체적인 동작 방식(선택 기준, `nominatedNodeName`의 역할 등)은 [아래 선점 섹션](#선점)에서 상세히 다룬다.

### PreScore

Score 플러그인이 사용할 **공유 상태를 생성**하는 사전 처리 단계다. 오류를 반환하면 Scheduling Cycle이 중단된다.

### Score

Filter를 통과한 노드들에 **0~100 범위의 점수를 부여**하는 단계다. 각 Score 플러그인이 모든 적합 노드에 대해 점수를 매긴다.

### NormalizeScore

Score 결과를 **0~100 범위로 정규화**하는 단계다. 같은 플러그인의 Score 결과만 정규화하며, Scheduling Cycle당 플러그인당 한 번 호출된다. 정규화 후, 각 플러그인에 설정된 가중치(weight)를 곱하고 모든 플러그인의 점수를 합산하여 최고 점수 노드를 선택한다.

### Reserve

선택된 노드에 **리소스를 예약**하는 단계다. 실제 바인딩 전에 리소스를 예약하여, 스케줄러가 바인딩 완료를 기다리는 동안 다른 파드가 동일 리소스를 사용하는 것을 방지한다. `Reserve`와 `Unreserve` 두 메서드로 구성되며, Reserve 실패 시 또는 이후 단계 실패 시 **모든** Reserve 플러그인의 `Unreserve`가 역순으로 호출된다.

### Permit

Scheduling Cycle의 **마지막 단계**로, 파드의 바인딩을 승인(approve), 거부(deny), 또는 대기(wait)시킬 수 있다. 기본적으로는 즉시 승인된다.

- **approve**: 모든 Permit 플러그인이 승인하면 Binding Cycle로 진행
- **deny**: 하나라도 거부하면 파드가 큐로 돌아가고, Reserve 플러그인의 Unreserve가 호출됨
- **wait**: 타임아웃 내에 승인되지 않으면 deny로 전환

### PreBind (Binding Cycle)

파드가 바인딩되기 **전에 필요한 작업**을 수행한다. 예를 들어, VolumeBinding 플러그인이 네트워크 볼륨을 프로비저닝하고 마운트하는 작업이 여기서 이루어진다. 하나라도 실패하면 파드는 큐로 돌아간다.

### Bind (Binding Cycle)

파드를 노드에 **실제로 바인딩**하는 단계다. API Server에 PATCH 요청을 보내 `spec.nodeName`을 설정하는 것이 핵심 작업이다. 설정된 순서대로 Bind 플러그인이 호출되며, 하나가 처리하면 나머지는 건너뛴다.

```
PATCH /api/v1/namespaces/default/pods/my-pod
{
  "spec": {
    "nodeName": "worker-node-1"
  }
}
```

`spec.nodeName`이 설정되면 해당 노드의 Kubelet이 파드를 감지하고 실행을 시작한다. `PodScheduled` condition은 API Server가 자동으로 업데이트한다. Bind 실패 시(노드 NotReady, 네트워크 문제 등) 파드는 Backoff Queue로 이동한다.

### PostBind (Binding Cycle)

파드가 성공적으로 바인딩된 **후** 호출되는 정보성 단계다. Binding Cycle의 마지막이며, 관련 리소스 정리 등에 사용된다.

<br>

### Extension Point별 동작 규칙 요약

각 extension point에서 복수 플러그인이 어떻게 동작하고, 실패 시 어떤 일이 발생하는지를 정리한다.

| Extension Point | 복수 플러그인 | 실패 시 동작 |
| --- | --- | --- |
| **QueueSort** | 정확히 1개만 허용 | — |
| **PreFilter** | 순서대로 전부 호출 | 하나라도 실패 → 사이클 중단 |
| **Filter** | 노드별로 순서대로 호출 | 하나라도 실패 → 해당 노드 탈락 |
| **PostFilter** | 순서대로 호출 | 첫 번째 성공 → 나머지 스킵 |
| **Score** | 전부 호출 후 가중합 | 실패 시 사이클 중단 |
| **Reserve** | 순서대로 전부 호출 | 하나라도 실패 → 이전 것들 Unreserve 역순 롤백 |
| **Permit** | 순서대로 전부 호출 | 하나라도 거부 → 사이클 중단 |
| **PreBind** | 순서대로 전부 호출 | 하나라도 실패 → Unreserve 롤백 |
| **Bind** | 순서대로 시도 | 첫 번째 성공한 게 독점 (나머지 스킵) |

대부분의 extension point는 등록된 플러그인을 모두 실행(AND 조건 또는 합산)하지만, QueueSort와 Bind는 "하나만 동작해야 한다"는 공통점이 있다. 다만 그 제약의 메커니즘이 다르다.

- **QueueSort — 등록 자체가 1개로 제한**: `Less(Pod1, Pod2)`로 전체 순서(total ordering)를 결정하는 비교 함수다. 비교 함수가 2개 존재하면 순서가 모순될 수 있으므로, 단일 비교 기준만 허용된다.
- **Bind — 복수 등록 가능, 실행은 1개만 (Chain of Responsibility)**: 여러 Bind 플러그인을 등록할 수 있지만, "Pod을 Node에 묶는 API 호출"은 한 번만 이뤄져야 하므로 첫 번째로 처리하겠다고 한 플러그인이 독점하고 나머지는 스킵된다.

<br>

## 주요 단계 상세

위 extension point 중 핵심이 되는 세 단계(Filter, Score, PostFilter)를 상세히 살펴본다.

<br>

### Filter 단계

**부적합한 노드를 탈락시키는 단계**다. 각 노드에 대해 등록된 Filter 플러그인을 순차 실행하며, 하나라도 실패하면 해당 노드는 즉시 탈락한다.

주요 특성은 아래와 같다.

- **노드 간 병렬 처리**: 여러 노드에 대한 필터링을 동시에 수행한다.
- **대규모 클러스터 최적화**: 클러스터 노드가 많을 경우, 모든 노드를 평가하지 않는다. 스케줄러는 `percentageOfNodesToScore` 파라미터(기본값: 클러스터 규모에 따라 자동 조정, 최소 100개 또는 전체의 약 50%)에 따라 **충분한 수의 적합 노드를 찾으면 나머지 노드 평가를 중단**한다. 예를 들어 5,000노드 클러스터에서 모든 노드를 평가하면 스케줄링 지연이 커지므로, 적합 노드를 일정 수 확보하면 바로 Score 단계로 넘어간다. 이것은 스케줄링 품질과 성능 사이의 트레이드오프이다.
- **PreFilter Skip 최적화 (v1.26+)**: PreFilter 플러그인이 `Skip` 상태를 반환하면, 해당 플러그인의 Filter 실행을 건너뛸 수 있다. 예를 들어 파드에 nodeAffinity가 정의되어 있지 않으면 NodeAffinity 플러그인이 PreFilter에서 Skip을 반환하여, Filter 단계에서 불필요한 평가를 줄인다.

#### 적합 노드가 하나뿐인 경우

Filter 단계에서 **하나의 노드만 적합한 것으로 확인**된 경우, Score 단계는 여전히 실행된다. 다만 경쟁할 노드가 없으므로 어떤 점수를 받든 그 노드가 선택된다. 실질적으로 Score의 결과가 달라지지 않는 것이다. `percentageOfNodesToScore` 최적화와 별개로, Filter를 통과한 노드 목록이 Score에 그대로 전달되기 때문에 노드가 하나면 곧바로 그 노드로 진행한다.

대표적인 Filter 플러그인은 다음과 같다(v1.32 기준).

| 분류 | 플러그인 | 체크 항목 |
| --- | --- | --- |
| 이름 매칭 | NodeName | 파드 spec에 `nodeName`이 지정된 경우 해당 노드와 일치하는지 |
| 노드 상태 | NodeUnschedulable | 노드가 `Unschedulable`로 마킹되어 있는지 (`kubectl cordon` 적용 여부) |
| 리소스 | NodeResourcesFit | CPU, Memory 등 리소스 충분 여부. **`requests` 기준**으로 판단하며, `limits`는 스케줄링 시 고려하지 않는다. GPU 등 extended resource는 `limits`만 설정하면 `requests`도 동일하게 자동 설정되므로 결과적으로는 같지만, 원리적으로는 항상 `requests` 기준 |
| 배치 규칙 | NodeAffinity | `nodeSelector` 라벨 일치 및 `requiredDuringSchedulingIgnoredDuringExecution` 조건 만족 여부 |
| 배치 규칙 | TaintToleration | 노드의 taint를 파드가 tolerate하는지 |
| 배치 규칙 | PodTopologySpread | 토폴로지 분산 규칙의 `maxSkew` 위반 여부 |
| 배치 규칙 | InterPodAffinity | 파드 간 anti-affinity의 `requiredDuringScheduling` 조건 충족 여부 |
| 볼륨 | VolumeBinding | 요청한 PVC/PV가 해당 노드에서 마운트 가능한지 |
| 볼륨 | VolumeRestrictions | 볼륨 제공자의 제한 사항 충족 여부 |
| 볼륨 | VolumeZone | 볼륨의 zone 요구 사항 충족 여부 |
| 볼륨 | NodeVolumeLimits | CSI 볼륨 수 제한 초과 여부 |
| 포트 | NodePorts | 요청한 `hostPort`가 해당 노드에서 이미 사용 중인지 |

> **참고**: NodeAffinity와 InterPodAffinity의 `preferredDuringScheduling` 조건은 Filter가 아닌 Score 단계에서 처리된다. Filter에서는 `required` 조건만 체크한다.

<br>

### Score 단계

Filter를 통과한 노드들 중 **최적의 노드를 선택하는 단계**다. 각 노드에 점수를 부여하고, 최종적으로 가장 높은 점수를 받은 노드에 파드를 배치한다.

스코어링 과정은 다음과 같다.

1. **Score**: 각 Score 플러그인이 노드에 0~100 범위의 점수를 부여한다.
2. **NormalizeScore**: 플러그인별로 점수를 0~100 범위로 정규화한다.
3. **가중치 적용**: 각 플러그인에 설정된 가중치(weight)를 곱한다. 가중치는 `KubeSchedulerConfiguration`에서 플러그인별로 설정할 수 있으며, 기본값은 1이다.
4. **합산 및 선택**: 모든 플러그인의 가중 점수를 합산하여 최고 점수 노드를 선택한다. 동점인 경우 라운드 로빈으로 선택한다.

대표적인 Score 플러그인은 다음과 같다(v1.32 기준, 기본 가중치 포함).

| 플러그인 | 기본 가중치 | 스코어링 기준 |
| --- | --- | --- |
| TaintToleration | 3 | toleration이 필요 없는(taint가 적은) 노드 선호 |
| NodeAffinity | 2 | `preferredDuringScheduling` 조건에 부합하는 노드에 높은 점수 |
| PodTopologySpread | 2 | 토폴로지 분산이 균일한 배치에 높은 점수 |
| InterPodAffinity | 2 | 파드 간 `preferredDuringScheduling` 친화성 조건 반영 |
| NodeResourcesFit | 1 | 리소스 분산 전략에 따른 점수 (`LeastAllocated` / `MostAllocated` / `RequestedToCapacityRatio`) |
| VolumeBinding | 1 | 요청 볼륨 크기에 적합한 PV가 있는 노드 선호 |
| NodeResourcesBalancedAllocation | 1 | CPU와 Memory의 사용 비율이 균형 잡힌 노드 선호 |
| ImageLocality | 1 | 파드에 필요한 컨테이너 이미지가 이미 존재하는 노드 선호 |

> **가중치 변경 이력**: v1beta2(v1.23) 이전에는 모든 Score 플러그인의 가중치가 1이었다. v1beta2부터 `TaintToleration`이 3, `NodeAffinity`/`PodTopologySpread`/`InterPodAffinity`가 2로 상향되었다. 이는 배치 규칙(taint, affinity, topology)이 리소스 분산보다 스케줄링 결정에 더 중요한 요소라는 판단을 반영한 것이다.

> **참고**: `NodeResourcesFit`은 Filter와 Score 양쪽에 등록되는 대표적인 플러그인이다. Filter에서는 "리소스가 충분한가"를 판단하고, Score에서는 "충분한 노드들 중 어디가 더 적합한가"를 평가한다. Score에서의 기본 전략은 `LeastAllocated`(리소스를 고르게 분산)이며, `MostAllocated`(노드를 채우는 방향)로 변경할 수 있다.

<br>

### 기본 플러그인과 Extension Point 매핑

![kubernetes-scheduling-default-plugins]({{site.url}}/assets/images/kubernetes-scheduling-default-plugins.png){: .align-center}
> 이미지 출처: [YouTube - Kubernetes Scheduler Deep Dive](https://youtu.be/BMMeLgvpkWA?si=AAYj6a4DQV-yA__H&t=166)

v1.32 기준 기본 활성화된 플러그인이 어떤 extension point에 등록되어 있는지 전체 매핑이다. 하나의 플러그인이 여러 extension point에 걸쳐 동작하는 것을 확인할 수 있다.

| 플러그인 | Extension Points | 설명 |
| --- | --- | --- |
| PrioritySort | queueSort | 파드 우선순위 기반 큐 정렬 |
| NodeName | filter | `spec.nodeName` 지정 시 해당 노드 매칭 |
| NodeUnschedulable | filter | cordon 상태 노드 제외 |
| NodePorts | preFilter, filter | hostPort 충돌 확인 |
| NodeResourcesFit | preFilter, filter, score | 리소스 충분 여부 및 분산 전략 |
| NodeAffinity | filter, score | nodeSelector 및 nodeAffinity 평가 |
| TaintToleration | filter, preScore, score | taint/toleration 평가 |
| PodTopologySpread | preFilter, filter, preScore, score | 토폴로지 분산 제약 |
| InterPodAffinity | preFilter, filter, preScore, score | 파드 간 affinity/anti-affinity |
| VolumeBinding | preFilter, filter, reserve, preBind, score | PVC/PV 바인딩 및 프로비저닝 |
| VolumeRestrictions | filter | 볼륨 제공자별 제한 확인 |
| VolumeZone | filter | 볼륨 zone 요구 사항 확인 |
| NodeVolumeLimits | filter | CSI 볼륨 수 제한 확인 |
| EBSLimits | filter | AWS EBS 볼륨 수 제한 확인 |
| GCEPDLimits | filter | GCP PD 볼륨 수 제한 확인 |
| AzureDiskLimits | filter | Azure Disk 볼륨 수 제한 확인 |
| NodeResourcesBalancedAllocation | score | CPU/Memory 균형 배치 |
| ImageLocality | score | 이미지 캐시 존재 여부 |
| DefaultPreemption | postFilter | 기본 선점 로직 |
| DefaultBinder | bind | 기본 바인딩 (API Server에 nodeName 설정) |

Filter와 Score **양쪽에** 등록되는 플러그인에 주목할 필요가 있다. 예를 들어:

- **NodeResourcesFit**: Filter에서는 "리소스가 충분한가"를 확인하고, Score에서는 "충분한 노드들 중 어디가 더 적합한가"를 평가
- **TaintToleration**: Filter에서는 "taint를 tolerate할 수 있는가"를 확인하고, Score에서는 "taint가 적은 노드"에 높은 점수
- **NodeAffinity**: Filter에서는 `required` 조건만 확인하고, Score에서는 `preferred` 조건을 점수에 반영
- **InterPodAffinity**: Filter에서는 `required` anti-affinity를 확인하고, Score에서는 `preferred` affinity를 점수에 반영

<br>

### 큐 복귀

[이전 글에서 스케줄러가 큐 관리 역할을 담당한다]({% post_url 2025-11-05-Kubernetes-Scheduling-01 %}#스케줄러-큐)고 했는데, **스케줄링 프로세스의 결과에 따른 큐 간 파드 이동**도 모두 스케줄러가 담당한다.

1. **스케줄링 실패 시 큐 이동**: 실패 유형에 따라 다른 큐로 이동시킨다
   - Score 단계 이후, 노드가 선택된 상태에서 바인딩까지 일시적 문제로 실패한 경우 → Backoff Queue
   - 애초에 배치 가능한 노드를 찾지 못해 노드 선택 자체가 실패한 경우 → Unschedulable Queue

2. **Active Queue로의 복귀**: 조건이 충족되면 다시 Active Queue로 이동시킨다
   - Backoff Queue: 타이머 만료 시(스케줄러가 주기적으로 확인)
   - Unschedulable Queue: 클러스터 이벤트 발생 시
   - 선점 성공: PostFilter 단계에서 선점에 성공하여 `nominatedNodeName`이 설정된 경우 즉시 Active Queue로 이동

> *실전 사례*: GPU 1개뿐인 노드에 `nodeSelector`로 고정 배치한 Deployment를 업데이트할 때, 기본값(`maxSurge: 1`, `maxUnavailable: 0`)이 적용되면 새 파드를 먼저 생성하려 하지만, GPU가 이미 점유 중이라 Filter에서 탈락하고, 같은 우선순위라 선점도 불가하여 Unschedulable Queue에 갇히는 교착 상태가 발생한다. 기존 파드가 종료되어 GPU 리소스가 해제되는 클러스터 이벤트가 발생해야 복귀할 수 있다. 자세한 분석은 [Deployment 재배포 실패 시리즈]({% post_url 2025-11-05-Dev-Kubernetes-Deployment-Failure-2 %})를 참고한다.

<br>

## PostFilter 단계

필터링 단계에서 **모든** 노드에 대한 필터링이 실패했을 경우, PostFilter 단계를 진행한다. 아래 그림에서, 이전 그림에 비해 더 자세히 나타난 `3` 이후의 부분이다.

![kubernetes-scheduling-2]({{site.url}}/assets/images/kubernetes-scheduling-2.png){: .align-center}
<center><sup>Filter 실패 후 PostFilter(선점) 흐름 상세. 큐 복귀 경로와 각 플러그인의 분기를 함께 나타냈다.</sup></center>

Filter 단계가 실패하면 실행되는 확장점(extension point)이다. 공식 문서에 의하면, 다음과 같다.

> PostFilter is called by the scheduling framework when the scheduling cycle failed at Prefilter or Filter

다양한 플러그인으로 구성되어, 각각의 플러그인이 실행되는 형태이다. DefaultPreemption(선점)이라는 기본 플러그인이 제공되며, 그 외에 다른 플러그인도 등록할 수 있다. 커스텀 플러그인을 만들어 등록하는 것 또한 가능하다.

플러그인은 설정된 순서대로 실행되며(순차 실행), 첫 번째로 성공한 플러그인에서 종료된다(Early Exit). 성공한 플러그인이 `nominatedNodeName`을 설정하며, 파드당 하나의 후보 노드만 설정 가능하다.

플러그인별 동작 방식은 아래와 같다.

| 플러그인 | 동작 |
| --- | --- |
| **DefaultPreemption** | 모든 노드를 평가하여 선점 가능 여부를 확인하고, 최적의 단일 노드를 선택하여 victim을 축출한다. 선택 기준은 PDB 위반 최소 → 최고 victim 우선순위 최소 → victim 개수 최소 순이다. |
| **CrossNodePreemption** | 여러 노드 조합을 평가하며, cross-node 제약(PodTopologySpread, AntiAffinity)을 고려하여 여러 노드에 걸쳐 victim을 축출할 수 있다. |
| **PreemptionToleration** | victim 측면의 선점 정책을 커스터마이징한다. |

`nominatedNodeName`이 설정된 파드는 다시 스케줄링 큐로 돌아가며, 추후 다시 스케줄링 프로세스를 거친다.

<br>

## 프로세스 결과와 큐 이동 요약

위 프로세스를 종합하면, PostFilter에서 선점에 성공하여 `nominatedNodeName`이 설정된 파드는 큐로 돌아가 재스케줄링을 시도하고, PostFilter에서도 후보 노드를 찾지 못하면 Unschedulable Queue로 이동한다. 이 모든 과정에서 파드는 Pending 상태를 유지하며, 스케줄링에 성공해 바인딩되고 컨테이너가 시작되어야 비로소 Running 상태가 된다. 큐 구조와 큐 간 이동 조건에 대한 자세한 내용은 [이전 글의 스케줄러 큐 섹션]({% post_url 2025-11-05-Kubernetes-Scheduling-01 %}#스케줄러-큐)을 참고한다.

| 프로세스 결과 | 이동 대상 큐 |
| --- | --- |
| Filter 통과 → Score → Bind 성공 | 스케줄링 완료 (큐에서 제거) |
| Filter 통과 → Bind 실패 (일시적 문제) | Backoff Queue |
| Filter 전체 실패 → PostFilter 선점 성공 | Active Queue (재스케줄링) |
| Filter 전체 실패 → PostFilter 실패 | Unschedulable Queue |


<br>

# 선점

[공식 문서](https://kubernetes.io/docs/concepts/scheduling-eviction/pod-priority-preemption/)에서는 이렇게 설명한다.

> Pods can have priority. Priority indicates the importance of a Pod relative to other Pods. If a Pod cannot be scheduled, the scheduler tries to preempt (evict) lower priority Pods to make scheduling of the pending Pod possible.

즉, 우선순위가 더 높은 파드를 위해 더 낮은 우선순위 파드를 종료하는 것이다. "선점"이라는 표현이 해당 파드가 직접 리소스를 빼앗는 것처럼 들리지만, 실제 동작은 **낮은 우선순위 파드를 종료시켜 공간을 확보한 후, 높은 우선순위 파드가 그 공간에 스케줄링되는 방식**이다. 선점한 파드에는 `nominatedNodeName`이 설정된다.

<br>

우선순위에 따라 결정한다는 것이 중요하다. 즉, 선점이 이루어지기 위해서는 우선순위가 있어야 한다.

- priorityClass 리소스를 정의해야 함

  ```yaml
  ---
  apiVersion: scheduling.k8s.io/v1
  kind: PriorityClass
  metadata:
    name: high-priority
  value: 1000000
  globalDefault: false  # true로 설정하면 priorityClassName 미지정 파드의 기본값으로 사용됨 (클러스터당 1개만 가능)
  preemptionPolicy: PreemptLowerPriority  # PreemptLowerPriority: 낮은 우선순위 파드 선점 가능 / Never: 선점하지 않음
  description: "High priority pods"
  ---
  apiVersion: scheduling.k8s.io/v1
  kind: PriorityClass
  metadata:
    name: low-priority
  value: 1000
  globalDefault: false
  description: "Low priority pods"
  ```

- 기존 파드와 우선순위 대상 파드에 해당 priorityClass가 적용되어 있어야 함

  ```yaml
  apiVersion: v1
  kind: Pod
  metadata:
    name: nginx
    labels:
      env: test
  spec:
    containers:
    - name: nginx
      image: nginx
      imagePullPolicy: IfNotPresent 
    priorityClassName: high-priority
  ```



<br>

대부분 파드를 그 자체로 띄우지 않으므로, Deployment와 같은 리소스 컨트롤러에 우선순위를 적용한다. 같은 리소스 컨트롤러에서 생성된 파드는 같은 우선순위를 갖는다. 실제 프로덕션 환경에서는 서로 다른 워크로드 간 우선순위 차이를 적용해 선점을 활용한다.

| 높은 우선순위 | 낮은 우선순위 | 비고 |
| --- | --- | --- |
| 프로덕션 환경 파드 | 개발/테스트 환경 파드 | |
| 핵심 서비스 | 배치 작업 | |
| 상시 서비스 | ML 학습 작업 | `preemptionPolicy: Never` 활용 |
| 시스템 컴포넌트 | 사용자 워크로드 | `system-cluster-critical` |

<br>

리소스가 제한적인 클러스터에서는 이러한 우선순위 설정이 서비스 안정성 확보를 위해 필수적이다. 예를 들어, ML 서비스에서 긴급한 추론 요청이 들어왔을 때 학습 워크로드보다 높은 우선순위를 부여하거나, 권한이 다른 사용자 간 학습 작업의 우선순위를 차등 적용하는 등의 방식으로 활용할 수 있다.

<br>

## nominatedNodeName이 하는 일

PostFilter 단계 이후, `nominatedNodeName`이 설정된 파드는 스케줄링 큐로 돌아가 다시 필터링, 스코어링 등 원래 스케줄링 프로세스를 거친다. 그렇다면 `nominatedNodeName`의 역할은 무엇인가?

nominatedNodeName은 선점 후 victim 파드가 종료되는 동안:

- 다른 낮은 우선순위 파드가 끼어들어 그 공간을 차지하는 것을 방지하고,
- 리소스 예약을 표시하는 역할을 하여,
- 스케줄러가 다른 파드를 평가할 때, nominated 파드도 실행 중인 것처럼 계산한다.

예컨대, 아래와 같은 문제 상황을 방지하는 것이다.

- 높은 우선순위 파드 P가 선점 성공
- victim 파드 축출 시작
- 파드 P는 큐로 돌아가 대기
- 그 사이 다른 파드가 끼어 들어서 victim이 비운 공간을 차지
- 파드 P는 영원히 기다림

`nominatedNodeName`이 설정되면, 스케줄러가 해당 파드도 실행 중인 것처럼 계산하므로, 다른 파드를 평가할 때 이미 예약된 리소스로 간주하여 끼어들기를 방지한다.

다만, nominatedNodeName이 설정된 파드더라도, nominated node에 항상 스케줄링된다는 보장은 없다. 높은 우선순위 파드가 나타나게 되면, 변경될 수 있다. 공식 문서의 표현에 따르면, 아래와 같다. 보장되지는 않는다는 것이다.

> Please note that Pod P is **not necessarily scheduled** to the 'nominated Node'.

<br>

# 정리

이 글에서 다룬 핵심 내용을 정리한다.

1. **Scheduling Framework는 코어를 가볍게 유지하는 설계다.** 코어는 extension point 호출 순서만 관리하는 오케스트레이터이고, 구체적 판단 로직은 모두 플러그인에 격리된다. 플러그인은 in-process로 컴파일되며, 이는 Scheduler Extender의 HTTP 오버헤드·상태 공유 불가 문제를 해결하기 위한 의도적 결정이다.
2. **스케줄링 프레임워크는 Scheduling Cycle과 Binding Cycle로 구성된다.** Scheduling Cycle(PreFilter → Filter → PostFilter → PreScore → Score → NormalizeScore → Reserve → Permit)에서 최적 노드를 선택하고, Binding Cycle(PreBind → Bind → PostBind)에서 실제 바인딩을 수행한다.
3. **Filter는 부적합 노드를 탈락시키고, Score는 최적 노드를 선택한다.** Filter에서는 `requests` 기준으로 리소스를 판단하며, `required` 조건만 체크한다. Score에서는 `preferred` 조건과 리소스 분산 전략 등을 반영하여 0~100 점수를 가중 합산한다. 적합 노드가 하나뿐이면 Score를 거쳐도 해당 노드가 선택된다.
4. **하나의 플러그인이 여러 extension point에 등록될 수 있다.** `TaintToleration`, `NodeAffinity`, `NodeResourcesFit`, `InterPodAffinity` 등이 Filter와 Score 양쪽에서 동작한다. v1.32 기준 Score 가중치는 `TaintToleration`(3), `NodeAffinity`/`PodTopologySpread`/`InterPodAffinity`(2), 나머지(1)이다.
5. **큐 재시도는 EnqueueExtension + QueueingHint로 효율화된다.** 플러그인이 "의미 있는 이벤트 타입"을 선언하고(1단계), 콜백이 "이 구체적 이벤트가 이 Pod에 관련 있는가"를 판단한다(2단계). 이를 통해 불필요한 재시도를 최소화한다.
6. **선점은 PriorityClass 기반으로 동작한다.** 우선순위가 정의되지 않으면 선점은 발생하지 않는다. 선점의 핵심 선택 기준은 PDB 위반 최소 → 최고 victim 우선순위 최소 → victim 개수 최소 순이다.
7. **`nominatedNodeName`은 예약 마커일 뿐, 보장이 아니다.** 선점 후 다른 파드의 끼어들기를 방지하는 역할을 하지만, 해당 노드에 반드시 스케줄링된다는 보장은 없다.

[이전 글]({% post_url 2025-11-05-Kubernetes-Scheduling-01 %})의 큐 구조와 함께 이해하면, 파드가 왜 Pending 상태에 빠지는지, 어떤 조건에서 빠져나올 수 있는지를 체계적으로 파악할 수 있다. [다음 글]({% post_url 2025-11-05-Kubernetes-Scheduling-03 %})에서는 스케줄링 제어 설정(Scheduling Gate, nodeSelector, Node Affinity, Taints/Tolerations 등)을 다룬다. 

<br>
