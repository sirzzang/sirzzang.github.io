---
title:  "[Kubernetes] Kubernetes Deployment 재배포 실패 원인과 해결 - 1. 스케줄링"
excerpt: Kubernetes에서의 파드 스케줄링 전략에 대해 알아보자.
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



해당 트래커 서빙 코드를 수정할 일이 있어서, 수정한 뒤 Deployment를 업데이트했다. 근데 실패했다.

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

Kubelet이 실행할 수 있도록, 파드가 노드에 매치되게 하는 작업이라고 한다. 정의에서도 확인할 수 있지만, 스케줄링은 **배치** 작업일 뿐이다. 아래와 같은 작업은, 스케줄링이 아니다.

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

### 스케줄러의 판단 기준: spec.nodeName

스케줄러는 **spec.nodeName이 비어 있는 파드**를 대상으로 스케줄링을 시도한다. 이것이 스케줄러가 파드를 선택하는 유일한 기준이다.

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: my-pod
spec:
  nodeName: "" # 비어 있음 → 스케줄링 대상
status:
  phase: Pending
  conditions:
  - type: PodScheduled 
    status: "False"  
    reason: Unschedulable
    message: "0/10 nodes available: 1 Insufficient gpu"
```

`spec.nodeName`이 비어 있으면 스케줄러가 해당 파드를 감지하고 스케줄링을 시도하며, 값이 이미 지정되어 있으면 스케줄러는 해당 파드를 무시한다.

<br>

### Pending 상태의 개념과 범위

`status.phase: Pending`은 파드의 광범위한 상태를 나타낸다. Kubernetes에서 파드가 Pending 상태가 될 수 있는 경우는 다양하다:

- 새로 생성되어 스케줄링 대기 중일 때
- 스케줄링된 후 컨테이너 시작 대기 중일 때
- 스케줄링 실패 후 재시도 중일 때
- 이미지 pull 중일 때
- init container 실행 중일 때
- 노드에 장애가 났을 때
- ...

<br>

**중요한 점**은, Pending 상태는 스케줄러의 판단 기준이 **아니라는 것**이다. 스케줄러의 실제 판단 기준은 `spec.nodeName`이다.

<br>

### 스케줄러 관점에서 Pending 파드 분류

넓은 범위에서 Pending 상태에 있는 파드들은 스케줄링 큐 관점에서 아래와 같이 분류해 볼 수 있다:
- (후술할) 스케줄링 큐에 있는 파드들: `spec.nodeName`이 비어 있음
  - Active Queue
  - Backoff Queue
  - Unschedulable Queue
- 스케줄링 큐에 없는 파드들
  - 수동으로 `spec.nodeName`이 지정됨: 스케줄러가 관여하지 않음
  - 스케줄링 완료, 컨테이너 시작 전
  - 이미지 pull 중
  - init container 실행 중


<br>

스케줄링 필요 여부를 아래와 같은 예시로 나눠서 살펴볼 수 있다.

<br>
**1. 스케줄링 대상 (spec.nodeName이 비어 있음)**
```yaml
spec:
  nodeName: ""  # 비어 있음 → 스케줄링 대상
status:
  phase: Pending
  conditions:
  - type: PodScheduled
    status: "False"
```

- 스케줄러가 감지하고 스케줄링을 시도하는 파드
- 스케줄링 큐(Active Queue, Backoff Queue, Unschedulable Queue)에 포함됨

<br>
**2. 스케줄링 비대상 (spec.nodeName이 지정됨)**

```yaml
spec:
  nodeName: "worker-1"  # 수동 지정됨 → 스케줄러 개입하지 않음
status:
  phase: Pending  # 아직 Pending이지만 스케줄러가 처리하지 않음
  conditions:
  - type: PodScheduled
    status: "False"  # 아직 업데이트 안됨
```

- 수동으로 노드가 지정된 파드
- 스케줄러가 관여하지 않음
- Pending 상태일 수 있지만(예: 이미지 pull 중, 컨테이너 시작 대기 중), 스케줄링과는 무관

<br>

**3. 스케줄링 완료 (spec.nodeName이 설정됨)**

```yaml
spec:
  nodeName: "worker-1"  # 스케줄러가 설정함
status:
  phase: Pending  # 컨테이너 시작 전까지는 여전히 Pending
  conditions:
  - type: PodScheduled
    status: "True"  # 스케줄링 완료
```

- 스케줄러가 이미 노드를 할당한 파드
- 컨테이너가 시작되기 전까지는 Pending 상태를 유지할 수 있음

<br>

더 자세히 보자면 파드 상태에 대한 고찰이 필요하겠으나, 일단 지금은 스케줄링 관점에서만 집중하기 위해, **`spec.nodeName`이 비어 있는 Pending 상태의 파드**가 스케줄링 프로세스의 대상이 된다고 알아 두자.

<br>

### PodScheduled 조건의 역할

`status.conditions`에는 `PodScheduled`라는 타입이 있다. 이것은 **스케줄링 결과를 기록하기 위한 지표**로, 해당 파드가 스케줄링되었는지 아닌지를 나타낸다.

**중요한 점**: 스케줄러가 이 조건을 판단 기준으로 사용하지 **않는다**. 스케줄러는 `spec.nodeName`만을 기준으로 파드를 선택한다. `PodScheduled` 조건은 스케줄링이 완료된 후 그 결과를 반영하는 지표일 뿐이다.

<br>

**PodScheduled 조건의 동작 흐름**

1. 파드 생성(`nodeName` 비어 있음) → `PodScheduled: False`
2. 스케줄러가 `nodeName`이 비어 있는 파드 감지 후 스케줄링 시도
3. 성공 시 `nodeName` 설정 → `PodScheduled: True`로 자동 업데이트
4. 실패 시 `nodeName` 여전히 비어 있음 → `PodScheduled: False` 유지

<br>
**예외 케이스**

```yaml
# 예외 케이스: nodeName 비어 있는데 PodScheduled가 True
spec:
  nodeName: ""
status:
  phase: Pending
  conditions:
  - type: PodScheduled
    status: "True"  # 비정상 상태 (일시적일 수 있음)
```

이런 경우는 일반적으로 발생하지 않지만, 시스템의 일시적인 불일치 상태일 수 있다.

<br>

## 메커니즘

앞서 Pending 상태의 파드를 스케줄링 큐 관점에서 분류해 보았다. 스케줄러는 그 중 **Active Queue에 있는 파드만 꺼내서 스케줄링을 시도**한다. Active Queue에 파드가 들어오는 경로는 다음과 같다:

- 새로 생성된 파드: API 서버에 대한 Watch를 통해 `spec.nodeName`이 비어 있는 파드를 감지
- Backoff Queue에서 이동: 백오프 타이머가 만료된 파드
- Unschedulable Queue에서 이동: 클러스터 이벤트(노드 추가, 리소스 해제 등) 발생으로 조건이 충족된 파드

스케줄링에 실패한 파드들은 실패 원인에 따라 Backoff Queue 또는 Unschedulable Queue로 이동하고, 조건이 충족되면 다시 Active Queue로 돌아온다. 이렇게 클러스터 내에서는 스케줄러가 Active Queue에서 파드를 꺼내 스케줄링을 시도하고, 실패 시 다른 큐로 이동시킨 뒤 조건 충족 시 다시 Active Queue로 복귀시키는 루프가 무한 반복된다.

<br>

### 스케줄러 큐
쿠버네티스 스케줄러는 아래와 같이 3개의 큐를 관리한다. 여기서 중요한 점은, **큐 관리 자체도 스케줄러가 담당**한다는 것이다. 스케줄러 내부의 Scheduling Queue 컴포넌트가 Watch를 통한 새 파드 감지, 타이머 기반의 Backoff Queue 확인(1초 주기), 클러스터 이벤트에 따른 Unschedulable Queue 처리, 스케줄링 실패 시 적절한 큐로의 이동 등을 모두 수행한다.
```
Active Queue  ───────► 스케줄러가 꺼내서 스케줄링 시도
Backoff Queue ───────► 타이머 만료 시 ────────► Active Queue로 이동
Unschedulable Queue ─► 클러스터 이벤트 발생 시 ─► Active Queue로 이동
```

<br>
Active Queue에 있는 파드만 스케줄링 대상이 되며, BackOff Queue와 Unschedulable Queue에 있는 파드들은 조건 충족 후 Active Queue로 이동한 뒤에야 스케줄링 대상이 된다.

- Active Queue: 활성 큐. 즉시 스케줄링 시도할 파드들. **스케줄링 대상** 파드
  - 새로 생성된 파드
  - Backoff Queue에서 타이머 만료된 파드
  - Unschedulable Queue에서 조건 충족된 파드
  - **스케줄러의 동시성과 순서**: 스케줄러는 여러 파드를 동시에 처리할 수 있다. Active Queue에서 파드를 꺼내는 순서는 우선순위 기반이며, 동일한 우선순위의 경우 큐에 들어온 순서(FIFO)를 따른다.
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

---

다음 글에서는 스케줄러가 파드를 노드에 배치하는 **프로세스(Filter, Score, PostFilter)**와 **선점(Preemption)** 메커니즘에 대해 자세히 알아본다. [다음 글 보기](https://sirzzang.github.io/dev/Dev-Kubernetes-Deployment-Failure-2/) 

