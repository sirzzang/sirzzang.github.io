---
title:  "[Kubernetes] Kubernetes Deployment 재배포 실패 원인과 해결 - 1. 스케줄링"
excerpt: Kubernetes에서의 파드 스케줄링 전략에 대해 알아 보자
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



~~도대체 거의 1년 가까이 된 내용을 왜 이제서야 작성하게 되었는지 반성하며~~ 회사에서 Deployment를 재배포하다가 쿠버네티스에서의 스케줄링과 Deployment 업데이트 전략에 대해 공부하게 된 내용을 작성한다.



<br>



# 문제

회사에서 객체 인식 모델로 추론한 객체 Bbox를 트래킹하기 위해 Boost 트래커를 사용하고 있다. 해당 컴포넌트는 GPU를 이용하기 때문에 GPU 노드에 배치되어 있고, Deployment로 배포되어 있다. 클러스터 내에 해당 목적으로 사용하기 위한 노드를 정해 두었다(이하 '`트래커노드`'라고 칭한다). 배포와 관련된 상세 사항은 다음과 같다.

- 해당 노드에서만 실행될 수 있도록, `nodeSelector`로 해당 노드명을 사용해서 배치하고 있다.
- 해당 노드에 GPU가 1개이기 때문에, `replicas` 값은 1로 설정되어 있다.



<br>



해당 트래커 서빙 코드를 수정할 일이 있어서, 수정한 뒤 Deployment를 재배포했다. 근데 실패했다.

```bash
$ kubectl get pods -n <namespace> -l app=<namespace>-object-tracker
NAME                                          READY   STATUS        RESTARTS   AGE
<namespace>-object-tracker-7d59fb84b9-rj7mt   1/1     Running       0          17h
<namespace>-object-tracker-7fbf4cd6cf-d4bwb   0/1     Pending       0          5m31s
```



<br>

Pending 상태에 놓여 있는 파드의 이벤트를 확인해 보니, 해당 파드의 스케줄링에 실패했음을 알게 되었다.

```bash
Events:
  Type     Reason            Age                    From               Message
  ----     ------            ----                   ----               -------
  Warning  FailedScheduling  6m                     default-scheduler  0/10 nodes are available: 1 Insufficient nvidia.com/gpu, 9 node(s) didn't match Pod's node affinity/selector. preemption: 0/10 nodes are available: 1 No preemption victims found for incoming pod, 9 Preemption is not helpful for scheduling..
  Warning  FailedScheduling  4m18s (x2 over 4m30s)  default-scheduler  0/10 nodes are available: 1 Insufficient nvidia.com/gpu, 9 node(s) didn't match Pod's node affinity/selector. preemption: 0/10 nodes are available: 1 No preemption victims found for incoming pod, 9 Preemption is not helpful for scheduling..

```

<br>

처음에는 막연히 `nodeSelector`로 해당 노드명을 걸어 놓고, 재배포하려면 GPU가 1개밖에 없으니까 안 되는 게 아닐까 생각했다. 한편으로는 맞는 말이기도 하지만, 더 자세히 고찰해 볼 것이 너무나도 많은 사태였다. 



결과적으로, **문제는 Deployment 배포 시 업데이트 전략을 명확하게 설정하지 않았기 때문**에 발생한 것이었다. 그러나 이 문제의 원인을 더 정확하게 파악하기 위해서는 Deployment 배치 전략과 스케줄링 전략에 대해 자세히 알아야 한다. 

<br>





# 스케줄링



## 개념



Kubernetes 스케줄링이란, **Kubernetes 스케줄러가 파드를 적합한 노드에 배치하는 프로세스**를 의미한다. 조금 더 정확하게는, 생성된 파드를 클러스터 내 어느 노드에서 실행할지 결정하고 할당하는 과정이다. 더 상세한 개념을 말해 보라면,

- `kube-scheduler`가 스케줄링이 필요한 파드를 감지하여,
- (후술할) 필터링과 스코어링(과 필요하다면 선점)을 통해 최적의 노드를 선택하고,
- 해당 노드에 파드를 바인딩하는 일련의 프로세스

라고 할 수 있지 않을까 싶다.

<br>



[공식 문서](https://kubernetes.io/docs/concepts/scheduling-eviction/kube-scheduler/)는 아래와 같이 정의한다.

> In Kubernetes, scheduling refers to making sure that Pods are matched to nodes so that Kubelet can run them.

Kubelet이 실행할 수 있도록, 파드가 노드에 매치되게 하는 작업이라고 한다. 정의에서도 확인할 수 있지만, 스케줄링은 순전히 **배치** 작업일 뿐이다. 아래와 같은 작업은, 스케줄링이 아니다.

- 파드 생성 그 자체: 리소스 컨트롤러가 API server에 요청하면, API server가 etcd에 저장
  - Deployment의 경우: Deployment Controller → ReplicaSet Controller → API Server
- 파드 실행: Kubelet 담당. Kubelet이 Container Runtime을 통해 실행. Scheduler는 어디서 실행할지만 결정
- 리소스 할당: Linux cgroups/namespaces가 담당

그리고 이와 같은 스케줄링에 포함될 수 있는 작업의 범위는 다음과 같다:

- 노드 선택: Filter + Score를 통한 최적 노드 결정
- 파드와 노드 연결(바인딩): `spec.nodeName` 설정
- (필요 시) 선점: 낮은 우선순위 파드(victim) 선택 및 종료 요청

또한, 당연히 스케줄링은 **파드**에 적용되는 개념이다. Deployment, Statefulset 등과 같은 리소스 컨트롤러에 적용되는 개념이 아니라는 의미다.

<br>


## 대상

스케줄러는 정확히 어떤 파드를 스케줄링 대상으로 인식하는가?

스케줄러는 **`spec.nodeName`이 비어 있는 파드**를 대상으로 스케줄링을 시도한다. `status.phase: Pending`은 파드의 광범위한 상태를 나타내는 것이고, 스케줄러의 실제 판단 기준은 `spec.nodeName`이다.

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: my-pod
spec:
  nodeName: "" # 비어 있음 
status:
  phase: Pending # 파드 상태 Pending
  conditions: # 파드 Condition
  - type: PodScheduled 
    status: "False"  
    reason: Unschedulable
    message: "0/10 nodes available: 1 Insufficient gpu"
```

### PodScheduled 조건의 역할

`status.conditions`에는 `PodScheduled`라는 타입이 있다. 이것은 스케줄링 결과를 기록하기 위한 것으로, **해당 파드가 스케줄링되었는지 아닌지**를 나타낸다.

중요한 점은, 스케줄러가 이 조건을 판단 기준으로 사용하지 **않는다**는 것이다. `spec.nodeName`이 수동으로 지정된 경우, Pending 상태이더라도 스케줄러가 개입하지 않는다.

1. 파드 생성(nodeName 비어 있음) → PodScheduled: False
2. 스케줄러가 nodeName이 비어 있는 파드 감지 후 스케줄링 시도
3. 성공 시 nodeName 설정 → PodScheduled: True로 자동 업데이트
4. 실패 시 nodeName 여전히 비어 있음 → PodScheduled: False 유지

### Pending 상태 파드 처리 예시

- 정상 케이스: 스케줄링 대상이 됨
  ```yaml
  # 정상 케이스: 스케줄링 대상
  spec:
    nodeName: ""  # 비어 있음 → 스케줄링 대상
  status:
    phase: Pending
    conditions:
    - type: PodScheduled
      status: "False"
    - type: PodScheduled
      status: "False"  # 아직 업데이트 안됨
  ```
- 수동 스케줄링 케이스
  ```yaml
  spec:
    nodeName: "worker-1"  # 수동 지정됨 → 스케줄러 개입하지 않음
  status:
    phase: Pending  # 아직 Pending이지만 스케줄러가 처리하지 않음
    conditions:
    - type: PodScheduled
      status: "False"  # 아직 업데이트 안됨
  ```
- 예외 케이스
  ```yaml
  # 예외 케이스: nodeName 비어 있는데 PodScheduled가 True
  spec:
    nodeName: ""
  status:
    phase: Pending
    conditions:
    - type: PodScheduled
      status: "True"  # 비정상 상태
  ```

<br>

결과적으로, Kubernetes에서 파드가 Pending 상태(Phase)가 될 수 있는 경우는 다양하다.

- 새로 생성되어 스케줄링 대기 중일 때
- 스케줄링된 후 컨테이너 시작 대기 중일 때
- 스케줄링 실패 후 재시도 중일 때
- 노드에 장애가 났을 때
- ...

더 자세히 보자면 파드 상태에 대한 고찰이 필요하겠으나, 일단 지금은 스케줄링 관점에서만 집중하기 위해, **Pending 상태인 파드 중 스케줄링이 되지 않은 파드**가 스케줄링 프로세스의 대상이 된다고 알아 두자.

<br>

## 메커니즘

스케줄러는 스케줄링 대상인 파드를 감지하기 위해, 타이머와 이벤트를 이용한다. 특정 시간 간격으로 스케줄링을 시도하고(~~스케줄러의 스케줄링?~~), 또 클러스터 내 특정 이벤트가 발생하면 바로 스케줄링을 시도하는 것이다. 어쨌든 클러스터 내에서는 이렇게 스케줄러가 스케줄링을 시도하고, 실패한 파드들에 대해 특정 시간 간격을 두고 재시도하는 루프가 무한 반복된다.

<br>

### 스케줄러 큐
쿠버네티스 스케줄러는 아래와 같이 3개의 큐를 관리한다.
```
Active Queue  ──────► 스케줄러가 꺼내서 스케줄링 시도
Backoff Queue ──────► 타이머 만료 시 → Active Queue로 이동
Unschedulable Queue ► 클러스터 이벤트 발생 시 → Active Queue로 이동
```

<br>
Active Queue에 있는 파드만 스케줄링 대상이 되며, BackOff Queue와 Unschedulable Queue에 있는 파드들은 조건 충족 후 Active Queue로 이동한 뒤에야 스케줄링 대상이 된다.

- Active Queue: 활성 큐. 즉시 스케줄링 시도할 파드들. **스케줄링 대상** 파드
  - 새로 생성된 파드
  - Backoff Queue에서 타이머 만료된 파드
  - Unschedulable Queue에서 조건 충족된 파드
- Backoff Queue: 백오프 큐. 일시적으로 스케줄링에 실패한 파드들
  - 지수 백오프(exponential backoff) 타이머 대기 중
  - **일시적 실패**: 스케줄링 시도는 가능했으나 실패한 경우
    - 리소스가 약간 부족 (CPU 90% 사용 중)
    - 노드가 일시적으로 NotReady 상태
    - 다른 파드가 먼저 리소스를 선점함
  - 초기 1초부터 시작하여 점진적으로 증가 (2초, 4초, 8초... 최대 약 10초)
  - **지수 백오프를 사용하는 이유**:
    - 스케줄러 부하 감소: 즉시 재시도하면 CPU 낭비
    - 클러스터 상태 변경 대기: 리소스 확보 등을 위한 시간 확보
    - 시스템 안정성: 초기에는 빠르게 재시도하되, 계속 실패하면 간격을 늘림
- Unschedulable Queue: 스케줄 불가 큐. 현재 클러스터 구조상 스케줄링이 불가능한 파드들
  - **구조적 실패**: 클러스터 상태 변경이 필요한 경우
    - 배치 가능한 노드가 없음
      - 모든 노드가 `nodeSelector` 불일치
      - taint/toleration 불일치로 배치 가능한 노드가 없음
    - 요청한 PV가 아예 존재하지 않음
    - 요청한 GPU 타입이 클러스터에 없음
  - **빠져나오는 조건**: 클러스터 이벤트 발생 시 Active Queue로 이동
    - 노드 추가/변경 (라벨, taint 등)
    - PV/PVC 생성
    - 다른 파드 삭제 (affinity 조건 변경)
    - 리소스 증가 이벤트

<br>

결국, 백오프 타이머에 의해 정기적으로 아래와 같은 스케줄링 루프가 동작하게 된다.

```
Active Queue에서 파드 꺼냄
    ↓
스케줄링 시도
    ↓
실패 → BackOff Queue 또는 Unschedulable Queue로 이동
    ↓
조건 충족(타이머 만료 / 클러스터 이벤트 발생) 시 Active Queue로 이동
    ↓
(무한 반복)
```

<br>

그리고, 무한 반복 루프 외에 스케줄링을 트리거하는 아래와 같은 이벤트가 발생하면, 즉시 재시도가 트리거링된다:

- 노드 추가, 변경: 새 노드 추가, 노드 리소스 증가, 노드 레이블 변경
- 파드 종료: 기존 파드 삭제, 기존 파드 종료, 리소스 확보
- PV, PVC 변경: 새 볼륨 생성, 볼륨 바인딩 완료
- Service/Configmap 변경: 관련 리소스 업데이트



<br>

## 프로세스

쿠버네티스 스케줄러가 파드를 노드에 배치하는 프로세스에 대해 알아 보자. 조금 복잡하니, 두 단계로 나눠서 알아 보자.

<br>

### 메인 스케줄링 프로세스

![kubernetes-scheduling]({{site.url}}/assets/images/kubernetes-scheduling.png){: width="600"}{: .align-center}
> 그림에서는 단일 큐로 표현했지만, 실제로는 Active Queue, Backoff Queue, Unschedulable Queue 3개로 구성된다.

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
  8. Permit: 스케줄링 승인 대기
  9. PreBind: 바인딩 전 작업 (예: 볼륨 프로비저닝)
  10. Bind: 실제 노드에 파드 바인딩
    ```bash
    PATCH /api/v1/namespaces/default/pods/my-pod
    {
      "spec": {
        "nodeName": "worker-node-1"  # 바인딩
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

> 참고: 스코어링 단계에서 동점인 노드가 여러 개 있는 경우
>
> 스코어링 단계에서 당연히 동점 노드가 발생할 수 있는데, 이 경우 랜덤 선택, 라운드 로빈, 노드 이름 순서 등의 방법을 통해 선택한다고 한다. 동점이 발생하는 게 좋은지 나쁜지는, 생각을 해 봐야겠지만. 만약 노드들이 대부분 비슷한 조건을 가졌다면, 해당 클러스터에서는 동점이 많이 나오는 게 당연할 수 있고, 오히려 그 경우 스케줄러에게 적절히 맡기는 게 나을 것이라는 생각이 든다. 그런데 만약 그렇지 않은 클러스터에서 동점이 많이 나온다면, 그건 문제가 있지 않을까.
>
> 물론, 동점이 나온 걸 어떻게 파악하는가에 대해서는 조금 더 공부해 봐야 한다. 일단 지금은 여기까지만!

<br>



### PostFilter 단계

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

### Pending 상태와 스케줄링 재시도

PostFilter 단계마저 실패하면 파드는 Pending 상태가 된다. 애초에 파드는 생성된 직후에 Pending 상태가 된다고 했기 때문에, 스케줄링에 실패하면 그렇게 Pending 상태가 되는 것이다. 반대로, 생성된 후, 스케줄링에 성공해 바인딩되어 컨테이너가 시작한 파드는, Running 상태가 된다.

이렇게 Pending 상태로 남아 있는 파드들은, 다음과 같은 클러스터 이벤트 발생 시 자동으로 재스케줄링이 시도된다.

* 새로운 노드가 클러스터에 추가됨
* 기존 파드가 종료되어 리소스가 확보됨
* 노드의 taint가 제거되거나 상태가 변경됨
* 리소스 쿼터가 조정됨

<br>

### 선점

[공식 문서](https://kubernetes.io/docs/concepts/scheduling-eviction/pod-priority-preemption/)에서는 이렇게 설명한다.

> Pods can have priority. Priority indicates the importance of a Pod relative to other Pods. If a Pod cannot be scheduled, the scheduler tries to preempt (evict) lower priority Pods to make scheduling of the pending Pod possible.

다시 말해, 우선 순위가 더 높은 파드를 위해 더 낮은 우선 순위 파드를 종료하는 것이다. 선점이라고 하니 뭔가 해당 파드가 직접 뺏어 가는 것처럼 들린다. 그러나 공식 문서 맥락을 보면, 더 낮은 우선 순위의 파드를 종료하는 것 뿐이다. 그렇게 되면, 우선순위가 더 높은 파드가 스케줄링될 수 있을 테니.

 **낮은 우선 순위 파드를 종료시켜 공간을 확보한 후, 높은 우선순위 파드가 그 공간에 스케줄링되는 방식**이다. 선점한 파드에는 nominatedName이 설정된다.

<br>

우선 순위에 따라 결정한다는 것이 중요하다. 즉, 선점이 이루어지기 위해서는 우선 순위가 있어야 한다.

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

- 기존 파드와 우선 순위 대상 파드에 해당 priorityClass가 적용되어 있어야 함

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

 대부분, 파드를 그 자체로 띄우진 않으니, Deployment와 같은 리소스 컨트롤러에 우선 순위를 적용한다. 중요한 것은, 같은 리소스 컨트롤러에서 생성된 파드는 같은 우선 순위를 갖는다는 것이다. 다만, 실제 프로덕션 환경에서는 서로 다른 워크로드 간 우선순위 차이를 적용해, 아래와 같은 경우에 우선순위 차이를 이용한 선점을 활발히 사용한다고 한다:

- 프로덕션(high) vs 개발/테스트(low) 환경 파드
- 핵심 서비스(high) vs 배치 작업(low)
- 상시 서비스(high) vs ML 학습 작업(preemptionPolicy: Never)
- 시스템 컴포넌트(system-cluster-critical) vs 사용자 워크로드 

<br>

리소스가 제한적인 클러스터에서는 이러한 우선순위 설정이 서비스 안정성 확보를 위해 필수적이다. 안타깝게도, 나는 아직까지 실무에서 써본 적이 없다. 다만, 만약 MLOps 서비스에서 권한이 다른 사용자 간 학습 우선 순위를 조정해야 할 일이 생긴다거나, 혹은 긴급한 추론이 필요할 때 학습 워크로드보다 우선 순위를 높게 주는 등의 방식으로 사용해 볼 수 있을 것 같다. 써볼 일이 생긴다면 좋겠다. ~~혹은 써볼 일을 만들어도 좋겠다!~~

<br>

### nominatedNodeName이 하는 일

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

다만, nominatedNodeName이 설정된 파드더라도, nominated node에 항상 스케줄링된다는 보장은 없다. 높은 우선순위 파드가 나타나게 되면, 변경될  수 있다. 공식 문서의 표현에 따르면, 아래와 같다. 보장되지는 않는다는 것이다.

> Please note that Pod P is **not necessarily scheduled** to the 'nominated Node'.

<br>

---

다음 글에서는 이 스케줄링 개념을 바탕으로, **Deployment 업데이트 전략(RollingUpdate의 maxSurge, maxUnavailable)**이 어떻게 이 문제와 연결되는지, 그리고 실제 해결 방법에 대해 다룬다. 

