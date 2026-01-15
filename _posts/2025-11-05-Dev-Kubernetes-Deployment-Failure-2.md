---
title:  "[Kubernetes] Kubernetes Deployment 재배포 실패 원인과 해결 - 2. 스케줄링 프로세스"
excerpt: Kubernetes 스케줄러의 파드 배치 프로세스와 선점 메커니즘에 대해 알아보자
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - k8s
  - k3s
  - kubernetes
  - deployment
  - scheduler
---

~~도대체 거의 1년 가까이 된 내용을 왜 이제서야 작성하게 되었는지 반성하며~~ Deployment를 재배포하다가 쿠버네티스의 스케줄링과 Deployment 업데이트 전략에 대해 공부하게 된 내용을 작성한다. [스케줄링 기본 개념에 이어서](https://sirzzang.github.io/dev/Dev-Kubernetes-Deployment-Failure-1/)



<br>

# 프로세스

쿠버네티스 스케줄러가 파드를 노드에 배치하는 프로세스에 대해 알아 보자. 조금 복잡하니, 두 단계로 나눠서 알아 보자.

<br>

## 메인 스케줄링 프로세스

![kubernetes-scheduling]({{site.url}}/assets/images/kubernetes-scheduling.png){: width="600"}{: .align-center}
- 스케줄링 대상 파드: Active Queue에 있는 파드
- 전체 단계
  1. PreFilter: 스케줄링 전 사전 처리 
  2. Filter: 모든 노드 동시 체크 (병렬)
     - 성공 시, PreScore 단계로 감
     - 실패 시, PostFilter 단계로 감
  3. PostFilter: 필터링 실패 시 실행 (여기서 선점 로직 동작)
  4. PreScore: 스코어링 전 사전 처리
  5. Score: 필터링 통과한 노드에 대해 점수 부여 (병렬)
  6. NormalizeScore: 점수 정규화
  7. Reserve: 선택된 노드에 리소스 예약
    - 실제 바인딩 전에 리소스를 예약하여 다른 스케줄러 인스턴스와의 경쟁 방지
    - Reserve 실패 시 다른 노드로 재시도, Reserve 성공 후 Bind 실패 시 예약 해제(Unreserve)
  8. Permit: 스케줄링 승인 대기
    - 웹훅 등 외부 승인을 기다리는 단계 (기본적으로는 즉시 승인)
    - 승인 대기 중에는 다른 파드가 해당 노드의 리소스를 사용할 수 있음
  9. PreBind: 바인딩 전 작업 (예: 볼륨 프로비저닝)
  10. Bind: 실제 노드에 파드 바인딩
    - API Server에 PATCH 요청을 보내 `spec.nodeName`을 설정하는 것이 핵심 작업
    - `spec.nodeName`이 설정되면 해당 노드의 Kubelet이 파드를 감지하고 실행을 시작
    - PodScheduled condition은 API Server가 자동으로 업데이트
    - Bind 실패 가능성: 노드가 갑자기 NotReady 상태가 되거나, 노드의 리소스가 부족해지거나, 네트워크 문제로 API Server와 통신 실패
    - 실패 시 파드가 Backoff Queue로 이동
    ```
    PATCH /api/v1/namespaces/default/pods/my-pod
    {
      "spec": {
        "nodeName": "worker-node-1"  # 바인딩: nodeName 설정
      }
    }
    ```
  11. PostBind: 바인딩 후 작업

- 주요 단계
  - Filter 단계(필터링): 각 노드 별로 다음 조건을 만족하는지 확인. 하나라도 실패 시 탈락
    - 리소스 체크
      - NodeResourcesFit: CPU, Memory 등 리소스 충분한가
      - NodeResourcesBalancedAllocation: 리소스가 밸런스 있게 사용되나
    - 배치 규칙 체크
      - NodeSelector: `nodeSelector` 일치 여부
      - NodeAffinity: node affinity 조건 만족 여부
      - PodTopologySpread: 파드 토폴로지 분산 규칙 만족 여부
      - TaintToleration: taint/toleration 적합한가
    - 실용성 체크
      - VolumeBinding: 볼륨 마운트 가능 여부
      - NodePorts: 포트 충돌 유무
  - PostFilter 단계: 모든 노드가 Filter 실패 시에만 실행되는 조건부 extension point. 개별 플러그인으로 구성됨
    - 선점(Preemption): 낮은 우선순위 파드를 축출하여 노드 확보
  - Score 단계(스코어링): 필터링 통과 노드에 점수 부여 후 최고 점수 노드 선택
    - ImageLocality: 이미지가 이미 있는 노드 선호
    - NodeResourcesBalancedAllocation: 리소스 밸런스
    - InterPodAffinity: 파드 간 친화성
    - ...

<br>

### 스케줄링 프로세스 주요 단계에 따른 큐 복귀

[이전 글에서 스케줄러가 큐 관리 역할을 담당한다](https://sirzzang.github.io/dev/Dev-Kubernetes-Deployment-Failure-1/#스케줄러-큐)고 했는데, **스케줄링 프로세스의 결과에 따른 큐 간 파드 이동**도 모두 스케줄러가 담당한다.

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

## Pending 상태와 스케줄링 재시도

Filter 단계에서 모든 노드가 실패하면 PostFilter가 실행된다. PostFilter(선점 등의 플러그인)에서 적합한 후보 노드를 찾으면 `nominatedNodeName`이 설정되고, 파드는 큐로 돌아가서 재스케줄링을 시도한다. 반면, PostFilter에서도 후보 노드를 찾지 못하면 파드는 UnschedulableQueue로 이동한다.

이 모든 과정에서 파드는 Pending 상태를 유지한다. 파드는 **생성된 직후부터 Pending 상태**이며, 스케줄링에 성공해 바인딩되고 컨테이너가 시작되어야 비로소 Running 상태가 된다.

UnschedulableQueue에 있는 Pending 파드들은 다음과 같은 클러스터 이벤트 발생 시 자동으로 재스케줄링이 시도된다:
* 새로운 노드가 클러스터에 추가됨
* 기존 파드가 종료되어 리소스가 확보됨
* 노드의 taint가 제거되거나 상태가 변경됨
* 리소스 쿼터가 조정됨

<br>




<br>

# 선점

[공식 문서](https://kubernetes.io/docs/concepts/scheduling-eviction/pod-priority-preemption/)에서는 이렇게 설명한다.

> Pods can have priority. Priority indicates the importance of a Pod relative to other Pods. If a Pod cannot be scheduled, the scheduler tries to preempt (evict) lower priority Pods to make scheduling of the pending Pod possible.

다시 말해, 우선순위가 더 높은 파드를 위해 더 낮은 우선순위 파드를 종료하는 것이다. 선점이라고 하니 뭔가 해당 파드가 직접 뺏어가는 것처럼 들린다. 그러나 공식 문서 맥락을 보면, 더 낮은 우선순위의 파드를 종료하는 것 뿐이다. 그렇게 되면, 우선순위가 더 높은 파드가 스케줄링될 수 있을 테니.

**낮은 우선순위 파드를 종료시켜 공간을 확보한 후, 높은 우선순위 파드가 그 공간에 스케줄링되는 방식**이다. 선점한 파드에는 nominatedName이 설정된다.

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

대부분, 파드를 그 자체로 띄우진 않으니, Deployment와 같은 리소스 컨트롤러에 우선순위를 적용한다. 중요한 것은, 같은 리소스 컨트롤러에서 생성된 파드는 같은 우선순위를 갖는다는 것이다. 다만, 실제 프로덕션 환경에서는 서로 다른 워크로드 간 우선순위 차이를 적용해, 아래와 같은 경우에 우선순위 차이를 이용한 선점을 활발히 사용한다고 한다:

- 프로덕션(high) vs 개발/테스트(low) 환경 파드
- 핵심 서비스(high) vs 배치 작업(low)
- 상시 서비스(high) vs ML 학습 작업(preemptionPolicy: Never)
- 시스템 컴포넌트(system-cluster-critical) vs 사용자 워크로드 

<br>

리소스가 제한적인 클러스터에서는 이러한 우선순위 설정이 서비스 안정성 확보를 위해 필수적이다. 안타깝게도, 나는 아직까지 실무에서 써본 적이 없다. 다만, 만약 ML 서비스에서 권한이 다른 사용자 간 학습 우선순위를 조정해야 할 일이 생긴다거나, 혹은 긴급한 추론이 필요할 때 학습 워크로드보다 우선순위를 높게 주는 등의 방식으로 사용해 볼 수 있을 것 같다. 써볼 일이 생긴다면 좋겠다. ~~혹은 써볼 일을 만들어도 좋겠다!~~

<br>

## nominatedNodeName이 하는 일

PostFilter 단계 이후, nominatedNodeName이 설정된 파드는 스케줄링 큐로 돌아가 이후 다시 필터링, 스코어링 등 원래 스케줄링 프로세스를 거친다고 했다. 그러면 그건 뭐하러 설정하나 싶을 수도 있다.

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

nominatedNodeName이 설정되면, 스케줄러가 nominated 파드도 실행 중인 것처럼 계산하기 때문에, `아, 이 노드는 이미 예약된 공간이 있네`라고 생각한다는 것이다.

다만, nominatedNodeName이 설정된 파드더라도, nominated node에 항상 스케줄링된다는 보장은 없다. 높은 우선순위 파드가 나타나게 되면, 변경될 수 있다. 공식 문서의 표현에 따르면, 아래와 같다. 보장되지는 않는다는 것이다.

> Please note that Pod P is **not necessarily scheduled** to the 'nominated Node'.

<br>

---

다음 글에서는 이 스케줄링 개념을 바탕으로, **Deployment 업데이트 전략(RollingUpdate의 maxSurge, maxUnavailable)**이 어떻게 이 문제와 연결되는지 알아본다. [다음 글 보기](https://sirzzang.github.io/dev/Dev-Kubernetes-Deployment-Failure-3/)
