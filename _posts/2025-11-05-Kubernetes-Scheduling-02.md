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

- 쿠버네티스 스케줄링 프레임워크는 **Scheduling Cycle**(PreFilter → Filter → PostFilter → PreScore → Score → NormalizeScore → Reserve → Permit)과 **Binding Cycle**(PreBind → Bind → PostBind)로 구성된다. 각 단계는 **extension point**로, 플러그인을 등록하여 스케줄링 로직을 구성한다.
- **Filter**는 부적합 노드를 탈락시키고(리소스, 배치 규칙, 볼륨 등), **Score**는 통과 노드에 0~100 점수를 가중 합산하여 최적 노드를 선택한다. 필터링에서 적합 노드가 하나뿐이면 Score 단계를 거쳐도 결과는 동일하다(해당 노드가 선택됨).
- 하나의 플러그인이 여러 extension point에 등록될 수 있다. v1.32 기준 `TaintToleration`, `NodeAffinity`, `NodeResourcesFit` 등이 Filter와 Score 양쪽에 등록된다.
- **선점(Preemption)**: 모든 노드가 부적합할 때, PostFilter 단계에서 낮은 우선순위 파드를 축출하여 공간을 확보한다. 선점이 동작하려면 `PriorityClass`가 정의되어 있어야 한다.
- `nominatedNodeName`은 선점 후 다른 파드가 해당 공간에 끼어드는 것을 방지하는 예약 마커이며, 해당 노드에 반드시 스케줄링된다는 보장은 없다.

<br>

# 들어가며

[이전 글]({% post_url 2025-11-05-Kubernetes-Scheduling-01 %})에서 스케줄링의 기본 개념, 스케줄링 대상, 스케줄러 큐 구조에 대해 알아보았다. 이번 글에서는 다음 세 가지를 다룬다.

1. **스케줄링 프레임워크**: Scheduling Cycle과 Binding Cycle의 전체 extension point(PreEnqueue → Sort → PreFilter → Filter → PostFilter → PreScore → Score → NormalizeScore → Reserve → Permit → PreBind → Bind → PostBind)와 각 단계의 역할
2. **스케줄링 플러그인**: 각 extension point에 등록되는 기본 플러그인(v1.32 기준) 목록과 동작 원리
3. **선점 메커니즘**: PriorityClass 기반의 선점이 동작하는 방식, `nominatedNodeName`의 역할과 한계

스케줄러가 *어떤 단계*를 거쳐 노드를 선택하는지, 모든 노드가 부적합할 때 *어떻게* 선점이 동작하는지를 이해하면, 파드가 Pending 상태에 빠졌을 때 원인을 빠르게 좁혀 나갈 수 있다.



<br>

# 스케줄링 프레임워크

쿠버네티스 스케줄러는 [Scheduling Framework](https://kubernetes.io/docs/concepts/scheduling-eviction/scheduling-framework/)라는 플러그인 기반 아키텍처로 동작한다. 프레임워크는 여러 **extension point**를 정의하고, 각 extension point에 플러그인을 등록하여 스케줄링 로직을 구성한다. 하나의 플러그인이 여러 extension point에 동시에 등록될 수 있다(예: `TaintToleration`은 Filter, PreScore, Score에 등록).

## 전체 구조: Scheduling Cycle과 Binding Cycle

하나의 파드를 스케줄링하는 과정은 **Scheduling Cycle**과 **Binding Cycle**, 두 단계로 나뉜다. 이 둘을 합쳐 하나의 **Scheduling Context**라고 한다.

![kubernetes-scheduling-framework]({{site.url}}/assets/images/kubernetes-scheduling-framework.png){: .align-center}

- **Scheduling Cycle**: 파드에 적합한 노드를 선택하는 단계. **직렬**로 실행된다(한 번에 하나의 파드만 처리).
- **Binding Cycle**: 선택된 노드에 파드를 실제로 바인딩하는 단계. **병렬**로 실행될 수 있다.

두 Cycle 모두, 파드가 스케줄링 불가능하다고 판단되거나 내부 오류가 발생하면 중단된다. 중단된 파드는 큐로 돌아가 재시도된다.

<br>

## 모든 Extension Point

전체 extension point를 순서대로 정리하면 다음과 같다.

### PreEnqueue

파드가 내부 Active Queue에 추가되기 **전에** 호출된다. 모든 PreEnqueue 플러그인이 `Success`를 반환해야 파드가 Active Queue에 진입할 수 있다. 하나라도 실패하면 파드는 내부 Unschedulable 리스트에 배치되며, 스케줄링을 시도하지 않는다. [Scheduling Gate](https://kubernetes.io/docs/concepts/scheduling-eviction/pod-scheduling-readiness/)가 이 단계에서 동작한다.

### Sort (QueueSort)

Active Queue 내에서 파드의 정렬 순서를 결정한다. `Less(Pod1, Pod2)` 함수를 제공하여 어떤 파드를 먼저 스케줄링할지 정한다. **한 번에 하나의 QueueSort 플러그인만** 활성화할 수 있다. 기본 플러그인인 `PrioritySort`는 파드 우선순위 기준으로 정렬한다.

### PreFilter

파드 또는 클러스터의 정보를 **사전 처리**하거나, 파드가 만족해야 하는 조건을 확인하는 단계다. PreFilter가 오류를 반환하면 Scheduling Cycle이 즉시 중단된다. v1.26부터는 플러그인이 `Skip` 상태를 반환하여, 해당 플러그인의 Filter 실행을 건너뛸 수 있다(예: 파드에 nodeAffinity가 없으면 NodeAffinity 플러그인의 Filter를 Skip).

### Filter

**부적합한 노드를 탈락시키는 단계**다. 각 노드에 대해 등록된 Filter 플러그인을 순차 실행하며, 하나라도 실패하면 해당 노드는 즉시 탈락한다. 모든 노드가 Filter에서 탈락하면 파드는 Unschedulable로 표시되고 PostFilter가 실행된다.

### PostFilter

Filter 단계에서 **적합한 노드가 하나도 없을 때만** 호출된다. 설정된 순서대로 플러그인이 실행되며, 첫 번째로 성공한 플러그인에서 종료한다. 기본 플러그인인 `DefaultPreemption`이 여기서 선점 로직을 수행한다.

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

<br>

## PostFilter 단계

필터링 단계에서 **모든** 노드에 대한 필터링이 실패했을 경우, PostFilter 단계를 진행한다. 아래 그림에서, 이전 그림에 비해 더 자세히 나타난 `3` 이후의 부분이다.

![kubernetes-scheduling-2]({{site.url}}/assets/images/kubernetes-scheduling-2.png){: .align-center}
> 그림에서는 단일 큐로 표현했지만, 실제로는 Active Queue, Backoff Queue, Unschedulable Queue 3개로 구성된다.

Filter 단계가 실패하면 실행되는 확장점(extension point)이다. 공식 문서에 의하면, 다음과 같다.

> PostFilter is called by the scheduling framework when the scheduling cycle failed at Prefilter or Filter

다양한 플러그인으로 구성되어, 각각의 플러그인이 실행되는 형태이다. DefaultPreemption(선점)이라는 기본 플러그인이 제공되며, 그 외에 다른 플러그인도 등록할 수 있다. 커스텀 플러그인을 만들어 등록하는 것 또한 가능하다.

설정된 순서대로 실행되며, 첫 번째로 성공한 플러그인에서 nominatedNodeName, 즉, 파드를 실행할 수 있는 노드명이 설정된다.

- PostFilter 플러그인 실행 규칙
  - **순차 실행**: 설정된 순서대로 하나씩 실행
  - **Early Exit**: 첫 번째 성공한 플러그인에서 종료, 나머지는 실행 안 함
  - **단일 nominatedNodeName**: 파드당 하나의 후보 노드만 설정 가능
- 플러그인별 동작 방식
  - **DefaultPreemption**:
    * 모든 노드를 평가하여 각 노드에서 선점 가능 여부 확인
    * 선점 알고리즘으로 최적의 단일 노드 선택
    * 선택 기준: PDB 위반 최소 → 최고 victim 우선순위 최소 → victim 개수 최소
    * 선택된 하나의 노드에서만 victim 축출
  - **CrossNodePreemption**:
    * 여러 노드 조합을 평가
    * cross-node 제약(PodTopologySpread, AntiAffinity) 고려
    * 여러 노드에 걸쳐 victim 축출 가능
  - **PreemptionToleration**: victim 측면의 선점 정책 커스터마이징

nominatedNodeName이 설정된 파드는 다시 스케줄링 큐로 돌아가며, 추후 다시 스케줄링 프로세스를 거친다.

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

1. **스케줄링 프레임워크는 Scheduling Cycle과 Binding Cycle로 구성된다.** Scheduling Cycle(PreFilter → Filter → PostFilter → PreScore → Score → NormalizeScore → Reserve → Permit)에서 최적 노드를 선택하고, Binding Cycle(PreBind → Bind → PostBind)에서 실제 바인딩을 수행한다.
2. **Filter는 부적합 노드를 탈락시키고, Score는 최적 노드를 선택한다.** Filter에서는 `requests` 기준으로 리소스를 판단하며, `required` 조건만 체크한다. Score에서는 `preferred` 조건과 리소스 분산 전략 등을 반영하여 0~100 점수를 가중 합산한다. 적합 노드가 하나뿐이면 Score를 거쳐도 해당 노드가 선택된다.
3. **하나의 플러그인이 여러 extension point에 등록될 수 있다.** `TaintToleration`, `NodeAffinity`, `NodeResourcesFit`, `InterPodAffinity` 등이 Filter와 Score 양쪽에서 동작한다. v1.32 기준 Score 가중치는 `TaintToleration`(3), `NodeAffinity`/`PodTopologySpread`/`InterPodAffinity`(2), 나머지(1)이다.
4. **선점은 PriorityClass 기반으로 동작한다.** 우선순위가 정의되지 않으면 선점은 발생하지 않는다. 선점의 핵심 선택 기준은 PDB 위반 최소 → 최고 victim 우선순위 최소 → victim 개수 최소 순이다.
5. **`nominatedNodeName`은 예약 마커일 뿐, 보장이 아니다.** 선점 후 다른 파드의 끼어들기를 방지하는 역할을 하지만, 해당 노드에 반드시 스케줄링된다는 보장은 없다.

[이전 글]({% post_url 2025-11-05-Kubernetes-Scheduling-01 %})의 큐 구조와 함께 이해하면, 파드가 왜 Pending 상태에 빠지는지, 어떤 조건에서 빠져나올 수 있는지를 체계적으로 파악할 수 있다. [다음 글]({% post_url 2025-11-05-Kubernetes-Scheduling-03 %})에서는 스케줄링 제어 설정(Scheduling Gate, nodeSelector, Node Affinity, Taints/Tolerations 등)을 다룬다. 

<br>
